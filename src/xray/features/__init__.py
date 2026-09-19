import json
import platform
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow

from xray.artifacts import cash_classification_manifest, check_output_path, code_manifest, publish_bundle, sha256
from xray.features.config import FeatureConfig
from xray.features.context import debt_snapshot, liquidity_snapshot, liquidity_summary, reconstruct_liquidity
from xray.features.coverage import STATES, add_coverage_state
from xray.features.invoices import invoice_features, prepare_invoices
from xray.features.temporal import add_ratios, add_temporal, model_columns
from xray.features.transactions import (PARTIAL_MONTH_COLUMNS, coverage_by_company, prepare_transactions,
                                       stress_events, transaction_features)
from xray.fx import REPORTING_CURRENCY
from xray.io import read_cleaned
from xray.paths import CLEANED_DIR, DATA_START, PROCESSED_DIR


INPUTS = ("companies", "groups", "transactions", "invoices", "banking_products", "debt_products", "balances")


def build_features(tables: dict[str, pd.DataFrame], config: FeatureConfig | None = None) -> dict[str, pd.DataFrame]:
    config = config or FeatureConfig()
    declared = tables["companies"]
    # D32: todos los paneles van en EUR; la moneda declarada se conserva como contexto.
    companies = declared.assign(currency=REPORTING_CURRENCY)
    t = prepare_transactions(tables, config)
    f = prepare_invoices(tables, config)
    pairs = pd.concat([companies[["company_id", "currency"]], t[["company_id", "currency"]],
                       f[["company_id", "currency"]]], ignore_index=True).dropna().drop_duplicates()
    result = {}
    for unit, filename in (("company_id", "company_currency_monthly_features"),
                           ("group_id", "group_currency_monthly_features")):
        units = pairs.copy()
        if unit == "group_id":
            units[unit] = units.company_id.map(companies.set_index("company_id").group_id)
        units = units[[unit, "currency"]].drop_duplicates()
        skeleton = units.merge(pd.DataFrame({"month": config.months}), how="cross")
        p = transaction_features(t, skeleton, unit)
        invoice_panel = invoice_features(f, skeleton, unit)
        p = p.merge(invoice_panel, on=[unit, "currency", "month"], how="left", validate="one_to_one")
        p = mask_partial_first_month(add_coverage_state(p, t, unit, config))
        p = add_temporal(add_ratios(p), unit, config)
        if unit == "company_id":
            p["group_id"] = p.company_id.map(companies.set_index("company_id").group_id)
        result[filename] = p
    currency = result["company_currency_monthly_features"]
    primary = currency.merge(companies[["company_id", "currency"]], on=["company_id", "currency"], validate="many_to_one")
    coverage = coverage_by_company(t, declared, config.months)
    primary = primary.merge(coverage, on=["company_id", "currency", "month"], validate="one_to_one")
    primary["declared_currency"] = primary.company_id.map(declared.set_index("company_id").currency)
    primary["has_partial_currency_coverage"] = primary.tx_unknown_currency_count.gt(0)
    result["company_monthly_features"] = primary.sort_values(["company_id", "month"]).reset_index(drop=True)
    result["stress_events_reserved"] = stress_events(t, companies, config.months)
    result["reconstructed_liquidity_context"] = reconstruct_liquidity(tables, config)
    result["company_currency_liquidity_context"] = liquidity_summary(result["reconstructed_liquidity_context"], currency)
    result["debt_snapshot_context"] = debt_snapshot(tables, config)
    result["liquidity_snapshot_context"] = liquidity_snapshot(tables, config)
    validate_features(result, companies, config)
    return result


def mask_partial_first_month(panel):
    """D33: el mes `onboarding` (primer mes con actividad real) es parcial; sus importes bancarios no cuentan.

    Se conservan los conteos (el mes existe y se ve en la cobertura), pero los importes quedan NaN, así las
    ventanas, ratios y el score empiezan en el primer mes completo en lugar de ver un crecimiento falso.
    Si ese mes es el primero de la extracción (`DATA_START`), está completo: la entidad ya existía y no se anula.
    """
    p = panel.copy()
    onboarding = p.coverage_state.eq("onboarding").fillna(False).astype(bool)
    p["is_partial_first_month"] = onboarding & p.month.gt(DATA_START)
    p.loc[p.is_partial_first_month, PARTIAL_MONTH_COLUMNS] = np.nan
    return p


def validate_features(artifacts, companies, config):
    company = artifacts["company_monthly_features"]
    if len(company) != len(companies) * len(config.months):
        raise ValueError("Panel incompleto: falta alguna empresa o mes; revisar moneda maestra")
    for name, frame in artifacts.items():
        numeric = frame.select_dtypes(include="number")
        if np.isinf(numeric.to_numpy(dtype=float)).any():
            raise ValueError(f"{name}: valores infinitos")
        if name.endswith("monthly_features"):
            unit = "company_id" if name.startswith("company") else "group_id"
            if frame.duplicated([unit, "currency", "month"]).any():
                raise ValueError(f"{name}: claves duplicadas")
            if not frame.month.isin(config.months).all():
                raise ValueError(f"{name}: mes fuera del calendario")
            if not frame.groupby([unit, "currency"]).size().eq(len(config.months)).all():
                raise ValueError(f"{name}: calendario discontinuo")
            if frame.tx_usable_count.gt(frame.tx_count).any():
                raise ValueError(f"{name}: conteos inconsistentes")
            for col in ("tx_inflow", "tx_outflow", "inv_issued_amount", "inv_received_amount"):
                if frame[col].lt(0).any():
                    raise ValueError(f"{name}.{col}: magnitud negativa")
            for col in ("tx_company_coverage", "inv_ar_overdue_ratio", "inv_ap_overdue_ratio"):
                if not frame[col].dropna().between(0, 1).all():
                    raise ValueError(f"{name}.{col}: cobertura o proporción fuera de [0, 1]")
            for side in ("ar", "ap"):
                if frame[f"inv_{side}_overdue_amount"].gt(frame[f"inv_{side}_open_amount"] + 1e-6).any():
                    raise ValueError(f"{name}: vencido mayor que abierto")
            absent = frame.tx_usable_count.eq(0)
            if frame.loc[absent, "tx_inflow"].notna().any():
                raise ValueError(f"{name}: se ha convertido falta de datos a cero")
            if not frame.coverage_state.isin(STATES).all():
                raise ValueError(f"{name}: coverage_state fuera del contrato")
            if (frame.coverage_state.eq("no_data") != frame.tx_count.eq(0)).any():
                raise ValueError(f"{name}: no_data no coincide con tx_count == 0")
            if frame.loc[frame.coverage_state.eq("ok"), "tx_active_accounts_real"].eq(0).any():
                raise ValueError(f"{name}: mes comparable sin cuentas activas reales")
            forbidden = {"cash_balance", "outstanding", "pending_amount", "status", "is_stale_pending"}
            if forbidden.intersection(frame.columns):
                raise ValueError(f"{name}: snapshot en panel histórico")


def feature_catalog(artifacts):
    panel = artifacts["company_monthly_features"]
    allowed = model_columns(panel.columns)
    return {
        "schema_version": 1,
        "decisions": "docs/decisiones.md",
        "model_features": allowed,
        "training_filter": "is_training_eligible; evaluar aparte la cobertura de moneda y cuentas",
        "group_split_key": "group_id",
        "excluded_artifacts": ["stress_events_reserved", "reconstructed_liquidity_context",
                               "company_currency_liquidity_context", "debt_snapshot_context",
                               "liquidity_snapshot_context"],
        "columns": {name: {"dtype": str(panel[name].dtype), "model_candidate": name in allowed,
                           "role": "feature" if name in allowed else "context_or_quality"} for name in panel},
    }


def quality_report(artifacts):
    report = {}
    for name, frame in artifacts.items():
        section = {"rows": len(frame), "columns": len(frame.columns),
                   "null_fraction": frame.isna().mean().to_dict() if len(frame) else dict.fromkeys(frame.columns)}
        if name.endswith("monthly_features"):
            section.update({"observed_months": int(frame.tx_count.gt(0).sum()),
                            "usable_months": int(frame.tx_usable_count.gt(0).sum()),
                            "eligible_rows": int(frame.is_training_eligible.sum()),
                            "missing_after_onboarding": int(frame.is_missing_after_onboarding.sum()),
                            "thin_months": int(frame.is_thin_month.sum()),
                            "invoice_source_rows": int(frame.inv_source_seen.sum()),
                            "coverage_state": frame.coverage_state.value_counts().astype(int).to_dict()})
        report[name] = section
    return report


def run(cleaned_dir: Path = CLEANED_DIR, out_dir: Path = PROCESSED_DIR,
        config: FeatureConfig | None = None, verbose: bool = True):
    config = config or FeatureConfig()
    cleaned_dir, out_dir = Path(cleaned_dir), Path(out_dir)
    check_output_path(out_dir, cleaned_dir)
    if (cleaned_dir / ".pipeline.lock").exists():
        raise RuntimeError("La capa cleaned se está publicando; reintentar cuando termine")
    source_manifest = json.loads((cleaned_dir / "_manifest.json").read_text(encoding="utf-8"))
    hashes = {f"{name}.parquet": sha256(cleaned_dir / f"{name}.parquet") for name in INPUTS}
    for name, digest in hashes.items():
        if source_manifest.get("outputs_sha256", {}).get(name) != digest:
            raise ValueError(f"{name}: hash ausente o distinto del manifiesto; ejecutar 00_clean_data.py")
    tables = {name: read_cleaned(name, cleaned_dir) for name in INPUTS}
    classification = cash_classification_manifest(config.ai_categories_path, config.ai_min_confidence)
    artifacts = build_features(tables, config)
    report = quality_report(artifacts)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="features-", dir=out_dir.parent) as directory:
        staged = Path(directory)
        for name, frame in artifacts.items():
            frame.to_parquet(staged / f"{name}.parquet", index=False)
            if verbose:
                print(f"  {name}: {len(frame):,} filas, {len(frame.columns)} columnas")
        for name, content in (("_feature_catalog.json", feature_catalog(artifacts)), ("_feature_quality.json", report)):
            (staged / name).write_text(json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "config": asdict(config), "code": code_manifest(), "inputs_sha256": hashes,
                    "classification": classification,
                    "cleaning_manifest_sha256": sha256(cleaned_dir / "_manifest.json"),
                    "ai_categories_sha256": classification["evidence_hash"],
                    "versions": {"python": platform.python_version(), "pandas": pd.__version__,
                                 "numpy": np.__version__, "pyarrow": pyarrow.__version__},
                    "outputs_sha256": {path.name: sha256(path) for path in sorted(staged.iterdir())}}
        (staged / "_feature_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        if (cleaned_dir / ".pipeline.lock").exists() or any(sha256(cleaned_dir / name) != digest for name, digest in hashes.items()):
            raise RuntimeError("La capa cleaned cambió durante el build; no se publica")
        if classification != cash_classification_manifest(config.ai_categories_path, config.ai_min_confidence):
            raise RuntimeError("Classification method/evidence changed during features; not published")
        publish_bundle(staged, out_dir, "_feature_manifest.json")
    return report
