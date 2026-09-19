"""Compone los artefactos que sirve el backend, sin cómputo en caliente.

Salida en `data/processed/product/`:
    score_changes.parquet      un término por entidad-moneda-mes (change_narrative)
    confidence.parquet         confidence por entidad-moneda-mes
    cash_truth_monthly.parquet / cash_truth_summary.parquet   buckets y dependencia de apoyo (cash_truth)
    evidence/cash_truth_tx.parquet   movimiento -> bucket, para el drill-down
    portfolio.json             una fila por empresa (moneda principal, último mes)
    companies/{company_id}.json   timeline 24m + cambios del último mes + confidence + cash_truth, por moneda
    groups/{group_id}.json     filiales con su última fila del portfolio
    _product_manifest.json     hashes de entradas y salidas, código y versiones

Todo se lee de `scores_v2/` y de `*_monthly_features.parquet`; no se recalcula ningún score.
"""
import json
import os
import platform
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from xray.artifacts import check_output_path, code_manifest, sha256
from xray.paths import CLEANED_DIR, PROCESSED_DIR
from xray.product.cash_truth import BUCKET_LABELS, compute_cash_truth, evidence
from xray.product.change_narrative import compute_changes, top_changes
from xray.product.confidence import compute_confidence
from xray.score.report import json_safe

TIMELINE_COLUMNS = ["month", "score", "level", "momentum", "stability", "trajectory", "episode", "score_status",
                    "score_reason", "delta_vs_prev", "level_operations", "level_debt", "level_collections", "level_payments"]
CASH_SUMMARY_COLUMNS = ["support_dependency_ratio", "support_dependency_trend", "support_role", "support_net_6m",
                        "uncertain_share_6m", "own_circulation_share_6m", "months_active_6m"]
PORTFOLIO_COLUMNS = ["company_id", "group_id", "currency", "currencies", "month", "score", "level", "momentum", "stability",
                     "trajectory", "episode", "score_status", "score_reason", "delta_vs_prev", "confidence",
                     "confidence_band", "main_signal", "main_signal_delta",
                     "support_dependency_ratio", "support_dependency_trend", "support_role", "uncertain_share_6m"]
CHANGES_TOP_K = 3
CASH_MONTHS = 6


def _records(frame):
    return json_safe(frame.replace({np.nan: None}).to_dict(orient="records"))


def primary_currency(scores):
    """Moneda con más movimientos en toda la historia por empresa."""
    counts = scores.groupby(["company_id", "currency"]).tx_count.sum().reset_index()
    counts = counts.sort_values(["company_id", "tx_count", "currency"], ascending=[True, False, True])
    return counts.drop_duplicates("company_id").set_index("company_id").currency


def build_portfolio(scores, confidence, changes, latest_month, cash_summary=None):
    primary = primary_currency(scores)
    currencies = scores.groupby("company_id").currency.unique().map(sorted).rename("currencies")
    latest = scores[scores.month.eq(latest_month)].merge(primary.rename("primary").reset_index(), on="company_id")
    latest = latest[latest.currency.eq(latest.primary)].drop(columns="primary")
    latest = latest.merge(confidence[["company_id", "currency", "month", "confidence", "confidence_band"]],
                          on=["company_id", "currency", "month"], how="left", validate="one_to_one")
    main = changes[changes["rank"].eq(1)][["company_id", "currency", "month", "label", "delta_contribution"]]
    main = main.rename(columns={"label": "main_signal", "delta_contribution": "main_signal_delta"})
    latest = latest.merge(main, on=["company_id", "currency", "month"], how="left", validate="one_to_one")
    latest = latest.merge(currencies.reset_index(), on="company_id", how="left")
    cash_cols = ["support_dependency_ratio", "support_dependency_trend", "support_role", "uncertain_share_6m"]
    if cash_summary is not None:
        latest = latest.merge(cash_summary[["company_id", "currency", "month"] + cash_cols],
                              on=["company_id", "currency", "month"], how="left", validate="one_to_one")
    else:
        for col in cash_cols:
            latest[col] = np.nan
    return latest[PORTFOLIO_COLUMNS].sort_values("company_id").reset_index(drop=True)


def cash_truth_block(company_id, currency, cash_monthly, cash_summary, latest_month):
    """Últimos meses por bucket, resumen del último mes y serie del ratio de dependencia."""
    if cash_monthly is None:
        return None
    m = cash_monthly[cash_monthly.company_id.eq(company_id) & cash_monthly.currency.eq(currency)]
    s = cash_summary[cash_summary.company_id.eq(company_id) & cash_summary.currency.eq(currency)].sort_values("month")
    if m.empty:
        return None
    recent_months = sorted(m.month.unique())[-CASH_MONTHS:]
    recent = m[m.month.isin(recent_months)]
    by_bucket = recent.groupby("bucket").agg(amount_in=("amount_in", "sum"), amount_out=("amount_out", "sum"),
                                            amount_abs=("amount_abs", "sum"), n_tx=("n_tx", "sum")).reset_index()
    by_bucket["share_abs"] = by_bucket.amount_abs / by_bucket.amount_abs.sum()
    by_bucket["label"] = by_bucket.bucket.map(BUCKET_LABELS)
    latest = s[s.month.eq(latest_month)]
    return {"window_months": [json_safe(x) for x in recent_months],
            "buckets": _records(by_bucket),
            "monthly": _records(m[m.month.isin(recent_months)].drop(columns=["company_id", "currency"])),
            "summary": _records(latest[["month"] + CASH_SUMMARY_COLUMNS])[0] if len(latest) else None,
            "series": _records(s[["month", "support_dependency_ratio", "support_dependency_trend", "uncertain_share_6m"]])}


def build_company(company_id, scores, confidence, changes, latest_month, cash_monthly=None, cash_summary=None):
    s = scores[scores.company_id.eq(company_id)]
    conf = confidence[confidence.company_id.eq(company_id)]
    payload = {"company_id": company_id, "group_id": s.group_id.iloc[0], "latest_month": latest_month, "currencies": {}}
    for currency, rows in s.groupby("currency"):
        timeline = rows[TIMELINE_COLUMNS].merge(conf.loc[conf.currency.eq(currency), ["month", "confidence", "confidence_band"]],
                                                on="month", how="left").sort_values("month")
        recent = changes[changes.company_id.eq(company_id) & changes.currency.eq(currency)]
        last_change_month = recent.month.max() if not recent.empty else None
        top = top_changes(recent[recent.month.eq(last_change_month)], CHANGES_TOP_K) if last_change_month is not None else recent
        latest_conf = conf[conf.currency.eq(currency) & conf.month.eq(latest_month)]
        payload["currencies"][currency] = {
            "timeline": _records(timeline),
            "why_changed": {"month": last_change_month, "terms": _records(top.drop(columns=["company_id", "currency"]))},
            "confidence": _records(latest_conf.drop(columns=["company_id", "currency"]))[0] if len(latest_conf) else None,
            "cash_truth": cash_truth_block(company_id, currency, cash_monthly, cash_summary, latest_month),
        }
    return payload


def build_groups(portfolio, scores):
    members = scores[["company_id", "group_id"]].drop_duplicates()
    groups = {}
    for group_id, rows in members.groupby("group_id"):
        companies = portfolio[portfolio.company_id.isin(rows.company_id)]
        groups[group_id] = {"group_id": group_id, "n_companies": int(len(rows)),
                            "companies": _records(companies), "n_scored": int(companies.score.notna().sum())}
    return groups


def _replace_dir(staged: Path, target: Path):
    if target.exists():
        backup = target.parent / ".history" / uuid4().hex
        backup.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(backup / target.name))
    shutil.move(str(staged), str(target))


def run(scores_dir=None, features_dir=PROCESSED_DIR, out_dir=None, verbose=True):
    features_dir = Path(features_dir)
    scores_dir = Path(scores_dir) if scores_dir is not None else features_dir / "scores_v2"
    out_dir = Path(out_dir) if out_dir is not None else features_dir / "product"
    for protected in (scores_dir, CLEANED_DIR, features_dir / "company_monthly_features.parquet"):
        check_output_path(out_dir, protected)
    inputs = {"scores": scores_dir / "company_monthly_scores.parquet",
              "explanations": scores_dir / "company_score_explanations.parquet",
              "features": features_dir / "company_currency_monthly_features.parquet",
              "transactions": CLEANED_DIR / "transactions.parquet"}
    scores = pd.read_parquet(inputs["scores"])
    explanations = pd.read_parquet(inputs["explanations"])
    features = pd.read_parquet(inputs["features"])
    scores["month"] = pd.to_datetime(scores.month)
    latest_month = scores.loc[scores.score.notna(), "month"].max()

    changes = compute_changes(scores, explanations)
    confidence = compute_confidence(scores, features)
    classified, cash_monthly, cash_summary = compute_cash_truth(pd.read_parquet(inputs["transactions"]))
    cash_evidence = evidence(classified)
    del classified
    portfolio = build_portfolio(scores, confidence, changes, latest_month, cash_summary)
    groups = build_groups(portfolio, scores)
    if verbose:
        print(f"  cambios     {len(changes):>9,} términos · confidence {len(confidence):,} filas · cash truth {len(cash_monthly):,} filas"
              f" · portfolio {len(portfolio):,} empresas · {len(groups):,} grupos")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="product-", dir=out_dir.parent) as directory:
        staged = Path(directory)
        changes.to_parquet(staged / "score_changes.parquet", index=False)
        confidence.to_parquet(staged / "confidence.parquet", index=False)
        cash_monthly.to_parquet(staged / "cash_truth_monthly.parquet", index=False)
        cash_summary.to_parquet(staged / "cash_truth_summary.parquet", index=False)
        (staged / "evidence").mkdir()
        cash_evidence.to_parquet(staged / "evidence" / "cash_truth_tx.parquet", index=False)
        (staged / "portfolio.json").write_text(json.dumps({"latest_month": json_safe(latest_month), "companies": _records(portfolio)},
                                                          ensure_ascii=False, allow_nan=False), encoding="utf-8")
        (staged / "companies").mkdir()
        for company_id in scores.company_id.unique():
            payload = build_company(company_id, scores, confidence, changes, latest_month, cash_monthly, cash_summary)
            (staged / "companies" / f"{company_id}.json").write_text(json.dumps(json_safe(payload), ensure_ascii=False, allow_nan=False), encoding="utf-8")
        (staged / "groups").mkdir()
        for group_id, payload in groups.items():
            (staged / "groups" / f"{group_id}.json").write_text(json.dumps(json_safe(payload), ensure_ascii=False, allow_nan=False), encoding="utf-8")
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "latest_month": json_safe(latest_month),
                    "inputs_sha256": {k: sha256(p) for k, p in inputs.items()},
                    "code": code_manifest(),
                    "versions": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
                    "outputs_sha256": {p.name: sha256(p) for p in sorted(staged.iterdir()) if p.is_file()},
                    "companies_files": len(list((staged / "companies").iterdir())),
                    "groups_files": len(list((staged / "groups").iterdir()))}
        (staged / "_product_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        if any(sha256(p) != manifest["inputs_sha256"][k] for k, p in inputs.items()):
            raise RuntimeError("Las entradas cambiaron durante el cálculo; no se publica")
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in ("companies", "groups", "evidence"):
            _replace_dir(staged / name, out_dir / name)
        for path in sorted(staged.iterdir()):
            os.replace(path, out_dir / path.name)
    if verbose:
        print(f"  OK -> {out_dir}")
    return manifest
