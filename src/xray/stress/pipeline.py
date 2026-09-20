"""Immutable, cutoff-checked Stress Test artifacts for the canonical V2 product."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd

from xray.artifacts import (
    cash_classification_manifest,
    publish_immutable_run,
    recursive_hashes,
    sha256,
)
from xray.features.config import FeatureConfig
from xray.ledger.classify import classify_transactions
from xray.paths import CLEANED_DIR, PROCESSED_DIR, ROOT
from xray.score.pipeline import read_panel
from xray.score_v2.config import ScoreV2Config
from xray.stress.engine import build_batch_stress
from xray.stress.exposures import build_company_exposures
from xray.stress.scenarios import ENGINE_VERSION, METHOD, SCHEMA_VERSION


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def _source_hashes(features_dir, scores_dir, cleaned_dir):
    sources = {
        "features": features_dir / "company_monthly_features.parquet",
        "feature_manifest": features_dir / "_feature_manifest.json",
        "scores": scores_dir / "company_monthly_scores.parquet",
        "score_manifest": scores_dir / "_company_score_manifest.json",
        "reference": scores_dir / "_company_score_reference.json",
        "cleaned_manifest": cleaned_dir / "_manifest.json",
        "transactions": cleaned_dir / "transactions.parquet",
        "invoices": cleaned_dir / "invoices.parquet",
        "debt_schedule_config": cleaned_dir / "debt_schedule_config.parquet",
        "companies": cleaned_dir / "companies.parquet",
        "banking_products": cleaned_dir / "banking_products.parquet",
        "debt_products": cleaned_dir / "debt_products.parquet",
    }
    return {name: sha256(path) for name, path in sources.items()}


def _code_hashes():
    paths = sorted((ROOT / "src" / "xray" / "stress").glob("*.py"))
    paths += [ROOT / "src" / "xray" / "product" / "whatif.py"]
    paths += sorted((ROOT / "src" / "xray" / "score_v2").glob("*.py"))
    paths += sorted((ROOT / "src" / "xray" / "ledger").glob("*.py"))
    paths += sorted((ROOT / "src" / "xray" / "features").glob("*.py"))
    paths += [ROOT / "src" / "xray" / name for name in
              ("fx.py", "artifacts.py", "paths.py", "score/pipeline.py", "score/core.py")]
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in paths}


def run(features_dir=PROCESSED_DIR, scores_dir=None, cleaned_dir=CLEANED_DIR, out_dir=None,
        month=None, company_ids=None, verbose=True):
    features_dir, cleaned_dir = Path(features_dir), Path(cleaned_dir)
    scores_dir = Path(scores_dir or features_dir / "scores_v2")
    out_dir = Path(out_dir or features_dir / "stress")
    if out_dir.resolve() in (features_dir.resolve(), cleaned_dir.resolve(), scores_dir.resolve()):
        raise ValueError("Stress output must not overwrite source directories")
    inputs = _source_hashes(features_dir, scores_dir, cleaned_dir)
    score_manifest = json.loads((scores_dir / "_company_score_manifest.json").read_text(encoding="utf-8"))
    outputs = score_manifest.get("outputs_sha256") or {}
    if (score_manifest.get("method") != "financial_smoothed_v2"
            or outputs.get("company_monthly_scores.parquet") != inputs["scores"]
            or outputs.get("_company_score_reference.json") != inputs["reference"]):
        raise ValueError("Published V2 scores/reference do not match score manifest")
    feature_manifest = json.loads((features_dir / "_feature_manifest.json").read_text(encoding="utf-8"))
    # Reuse of V2/feature code is safe only when it is the exact code that
    # produced the frozen source artifacts, not merely a compatible API.
    for directory, manifest in ((ROOT / "src" / "xray" / "score_v2", score_manifest),
                                (ROOT / "src" / "xray" / "features", feature_manifest)):
        published_code = manifest.get("code", {}).get("source_sha256") or {}
        for path in sorted(directory.glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if published_code.get(relative) != sha256(path):
                raise ValueError(f"Current code differs from published V2/features methodology: {relative}")
    for path, manifest in ((ROOT / "src" / "xray" / "score" / "core.py", score_manifest),
                           (ROOT / "src" / "xray" / "fx.py", feature_manifest)):
        relative = path.relative_to(ROOT).as_posix()
        if manifest.get("code", {}).get("source_sha256", {}).get(relative) != sha256(path):
            raise ValueError(f"Current code differs from published V2/features methodology: {relative}")
    if feature_manifest.get("outputs_sha256", {}).get("company_monthly_features.parquet") != inputs["features"]:
        raise ValueError("Published V2 features do not match feature manifest")
    if score_manifest.get("input", {}).get("feature_sha256") != inputs["features"] or score_manifest.get("input", {}).get("feature_manifest_sha256") != inputs["feature_manifest"]:
        raise ValueError("V2 score snapshot was fitted on different features")
    cleaned_manifest = json.loads((cleaned_dir / "_manifest.json").read_text(encoding="utf-8"))
    for name in ("transactions", "invoices", "debt_schedule_config", "companies", "banking_products", "debt_products"):
        if cleaned_manifest.get("outputs_sha256", {}).get(f"{name}.parquet") != inputs[name]:
            raise ValueError(f"Cleaned source does not match manifest: {name}")
    for name in ("transactions", "invoices", "companies", "banking_products", "debt_products"):
        if feature_manifest.get("inputs_sha256", {}).get(f"{name}.parquet") != inputs[name]:
            raise ValueError(f"Cleaned source differs from V2 feature input: {name}")
    code = _code_hashes()
    reference = json.loads((scores_dir / "_company_score_reference.json").read_text(encoding="utf-8"))
    config = ScoreV2Config(**reference["config"])
    if config.unit != "company_id" or reference.get("method") != "financial_smoothed_v2":
        raise ValueError("Stress requires frozen V2 company reference")
    panel, feature_source = read_panel(features_dir, config)
    if feature_source["feature_sha256"] != inputs["features"] or feature_source["feature_manifest_sha256"] != inputs["feature_manifest"]:
        raise ValueError("Feature source changed during stress input read")
    panel["month"] = pd.to_datetime(panel.month)
    scores = pd.read_parquet(scores_dir / "company_monthly_scores.parquet")
    month = pd.Timestamp(month) if month else pd.Timestamp(scores.month.max())
    month = month.to_period("M").to_timestamp()
    current = scores.loc[scores.month.eq(month) & scores.score.notna() & scores.currency.eq("EUR")]
    if company_ids is not None:
        current = current.loc[current.company_id.isin(company_ids)]
    if current.company_id.duplicated().any():
        raise ValueError("Duplicate company score at stress cutoff")
    first = month - pd.DateOffset(months=5)
    end = month + pd.offsets.MonthEnd(0)
    feature_config = feature_manifest["config"]
    ai_path = feature_config.get("ai_categories_path")
    ai_confidence = feature_config.get("ai_min_confidence", 0.7)
    if cash_classification_manifest(ai_path, ai_confidence) != feature_manifest.get("classification"):
        raise ValueError("Current D31/classification evidence differs from feature snapshot")
    fx_feature_config = FeatureConfig(**feature_config)
    raw = pd.read_parquet(cleaned_dir / "transactions.parquet")
    raw["date"] = pd.to_datetime(raw.date)
    raw = raw.loc[raw.date.ge(first - pd.offsets.MonthBegin(1)) & raw.date.le(end) &
                  raw.company_id.isin(current.company_id)]
    raw_by_company = dict(tuple(raw.groupby("company_id", sort=False)))
    empty_raw = raw.iloc[:0]
    ledger = classify_transactions(raw.loc[raw.date.ge(first)], as_of=end,
                                   ai_categories_path=ai_path, ai_min_confidence=ai_confidence)
    del raw
    invoices = pd.read_parquet(cleaned_dir / "invoices.parquet")
    invoices = invoices.loc[invoices.company_id.isin(current.company_id)]
    companies = pd.read_parquet(cleaned_dir / "companies.parquet")
    banking = pd.read_parquet(cleaned_dir / "banking_products.parquet")
    debt_products = pd.read_parquet(cleaned_dir / "debt_products.parquet")
    schedule = pd.read_parquet(cleaned_dir / "debt_schedule_config.parquet")
    schedule = schedule.loc[schedule.company_id.isin(current.company_id)]
    panels = dict(tuple(panel.loc[panel.month.le(month)].groupby("company_id", sort=False)))
    ledgers = dict(tuple(ledger.groupby("company_id", sort=False)))
    invoices_by = dict(tuple(invoices.groupby("company_id", sort=False)))
    schedule_by = dict(tuple(schedule.groupby("company_id", sort=False)))
    empty_ledger, empty_invoices, empty_schedule = ledger.iloc[:0], invoices.iloc[:0], schedule.iloc[:0]
    as_of = end.strftime("%Y-%m-%d")
    basis = {"method": METHOD, "engine_version": ENGINE_VERSION, "schema_version": SCHEMA_VERSION,
             "month": month.strftime("%Y-%m-%d"), "inputs_sha256": inputs, "source_sha256": code,
             "company_ids": sorted(current.company_id.tolist())}
    run_id = hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()[:24]
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stress-stage-", dir=out_dir) as directory:
        staged = Path(directory)
        count = 0
        ordered = list(current.sort_values("company_id").itertuples(index=False))
        for offset in range(0, len(ordered), 12):
            chunk = ordered[offset:offset + 12]
            rows = []
            for row in chunk:
                cid = row.company_id
                company_panel = panels.get(cid)
                if company_panel is None:
                    raise ValueError(f"V2 scored company has no features: {cid}")
                exposure = build_company_exposures(
                    cid, end, company_panel, ledgers.get(cid, empty_ledger),
                    invoices_by.get(cid, empty_invoices), schedule_by.get(cid, empty_schedule),
                    config=config, schedule_snapshot_as_of=pd.Timestamp(feature_config["extraction_date"]))
                rows.append((cid, row.score, exposure))
            chunk_panel = pd.concat([panels[cid] for cid, _, _ in rows], ignore_index=True)
            fx_contexts = {cid: {"raw_transactions": raw_by_company.get(cid, empty_raw),
                                 "companies": companies, "banking_products": banking,
                                 "debt_products": debt_products, "config": fx_feature_config}
                           for cid, _, _ in rows}
            results = build_batch_stress(chunk_panel, reference, rows, month=month,
                                         fx_context_by_company=fx_contexts)
            for cid, _, _ in rows:
                result = results[cid]
                result["lineage"] = {"run_id": run_id, "reference_sha256": inputs["reference"],
                                     "features_sha256": inputs["features"], "scores_sha256": inputs["scores"],
                                     "engine_version": ENGINE_VERSION}
                _json(staged / "companies" / f"{cid}.json", result)
                count += 1
            if verbose:
                print(f"  stress {count}/{len(current)} empresas", flush=True)
        outputs = recursive_hashes(staged)
        manifest = {**basis, "run_id": run_id, "as_of": as_of, "company_count": count,
                    "outputs_sha256": outputs}
        _json(staged / "manifest.json", manifest)
        if _source_hashes(features_dir, scores_dir, cleaned_dir) != inputs or _code_hashes() != code:
            raise RuntimeError("Stress sources changed during computation; nothing published")
        published = publish_immutable_run(staged, out_dir, run_id)
    if verbose:
        print(f"  stress {count} empresas · {as_of} -> {published}")
    return published, manifest
