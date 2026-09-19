"""Deterministic raw-to-Pulse batch; no legacy score or frontend dependency.

The economic cutoff is applied BEFORE cleaning (notably pending/booked matching).
Catalogs are a named source vintage: their ``created_at`` is a connection date,
not an account opening date. This is a retrospective restatement, not a claim
that the source snapshot was available at the historical economic cutoff.
"""
from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from xray.artifacts import (
    check_output_path,
    publish_immutable_run,
    recursive_hashes,
    sha256,
    verify_run,
)
from xray.clean import clean_all
from xray.io import TABLES, read_raw
from xray.ledger.classify import classification_metadata, classify_transactions
from xray.ledger.contracts import CLEANING_VERSION
from xray.ledger.monthly import build_monthly_facts
from xray.pulse.config import PulseConfig, load_config
from xray.pulse.scorer import score_company

PIPELINE_VERSION = "pulse-batch-v1.0"


def _json(value: Any) -> str:
    """Canonical serialization for identity and files (nonfinite is forbidden)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(value) + "\n", encoding="utf-8")


def _date(value: str | pd.Timestamp, name: str) -> pd.Timestamp:
    date = pd.Timestamp(value)
    if pd.isna(date) or date.tzinfo is not None or date != date.normalize():
        raise ValueError(f"{name} must be a valid timezone-naive calendar date")
    return date


def _complete_cutoff(as_of: pd.Timestamp) -> pd.Timestamp:
    period = as_of.to_period("M")
    end = period.to_timestamp("M")
    return end if as_of >= end else (period - 1).to_timestamp("M")


def _segment(value: Any) -> str:
    text = str(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", text) or text in {".", ".."}:
        raise ValueError(f"Unsafe company/currency path segment: {text!r}")
    return text


def _source_code() -> dict[str, Any]:
    """Hash runtime Python only, excluding git metadata, docs and research files.

    This works from an installed wheel too; no repository root is required.
    Every file used by cleaning, canonical facts or Pulse is included.
    """
    package = Path(__file__).resolve().parents[1]
    paths = [package / name for name in ("__init__.py", "io.py", "paths.py", "artifacts.py")]
    for folder in ("clean", "ledger", "pulse"):
        paths.extend((package / folder).rglob("*.py"))
    hashes = {path.relative_to(package).as_posix(): sha256(path) for path in sorted(paths)}
    return {"code_sha256": _digest(hashes), "source_sha256": hashes}


def _runtime() -> dict[str, str]:
    return {"python": platform.python_version(), **{name: version(name) for name in ("numpy", "pandas", "pyarrow")}}


def _load_raw(raw_dir: Path, company_ids: list[str] | None) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """A company selection retains group peers for canonical mirror matching."""
    companies = read_raw("companies", raw_dir)
    if companies.company_id.isna().any() or companies.company_id.duplicated().any():
        raise ValueError("companies.company_id must be nonnull and unique")
    requested = sorted(set(company_ids)) if company_ids else sorted(companies.company_id.astype(str))
    unknown = set(requested) - set(companies.company_id)
    if unknown:
        raise ValueError(f"Unknown companies: {sorted(unknown)}")
    selected_groups = companies.loc[companies.company_id.isin(requested), "group_id"]
    peers = set(companies.loc[companies.group_id.isin(selected_groups), "company_id"])
    raw = {}
    for name in TABLES:
        frame = companies.copy() if name == "companies" else read_raw(name, raw_dir)
        if name == "transactions":
            # CSV fields can contain newlines: this is a logical record ordinal,
            # excluding the header, NOT a physical line number.
            frame["_source_row_number"] = np.arange(1, len(frame) + 1, dtype=np.int64)
        if "company_id" in frame:
            frame = frame.loc[frame.company_id.isin(peers)].copy()
        elif name == "groups":
            frame = frame.loc[frame.group_id.isin(selected_groups)].copy()
        raw[name] = frame.reset_index(drop=True)
    return raw, requested


def _cut_raw(raw: dict[str, pd.DataFrame], cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """Remove future economic events before any matching or annotation."""
    cutoff_exclusive = cutoff + pd.Timedelta(days=1)
    result = {}
    for name, source in raw.items():
        frame = source.copy()
        column = {"transactions": "date", "balances": "date", "invoices": "issuance_date"}.get(name)
        if column:
            if frame[column].isna().any():
                raise ValueError(f"{name}.{column} contains invalid required dates")
            frame = frame.loc[frame[column] < cutoff_exclusive].copy()
        result[name] = frame.reset_index(drop=True)
    return result


def _company_currencies(raw: dict[str, pd.DataFrame], requested: list[str]) -> pd.DataFrame:
    frames = [raw[name][["company_id", "currency"]] for name in ("companies", "banking_products", "debt_products")]
    result = pd.concat(frames, ignore_index=True).dropna().drop_duplicates()
    return result.loc[result.company_id.isin(requested)].sort_values(["company_id", "currency"]).reset_index(drop=True)


def _frame_hash(frame: pd.DataFrame) -> str:
    # Used for the consumed input snapshot: row order is meaningful for cleaning
    # duplicate tie breaks and source ordinals, and is therefore not discarded.
    payload = frame.to_json(orient="split", date_format="iso", date_unit="ns", double_precision=15, index=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _prepare(raw: dict[str, pd.DataFrame], cutoff: pd.Timestamp, company_currencies: pd.DataFrame,
             classification_config: dict | None = None):
    cut = _cut_raw(raw, cutoff)
    cleaned, log = clean_all(cut)
    ledger = classify_transactions(cleaned["transactions"], as_of=cutoff, **(classification_config or {}))
    start = (cutoff.to_period("M") - 6).to_timestamp()  # includes the previous score's sixth month
    if not ledger.empty:
        start = min(start, pd.to_datetime(ledger.date).min().to_period("M").to_timestamp())
    facts = build_monthly_facts(ledger, as_of=cutoff, company_currencies=company_currencies, start_month=start)
    return cut, cleaned, log.to_frame(), ledger, facts


def _previous_scores(previous_run: Path | None, requested_as_of: pd.Timestamp) -> tuple[dict[tuple[str, str], dict], str | None]:
    if previous_run is None:
        return {}, None
    previous_run = Path(previous_run)
    manifest = verify_run(previous_run)
    if pd.Timestamp(manifest["as_of"]) > requested_as_of:
        raise ValueError("Previous run cannot be from a future as_of")
    result = {}
    for path in sorted((previous_run / "companies").glob("*/*/score.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        result[(payload["company_id"], payload["currency"])] = payload
    return result, sha256(previous_run / "manifest.json")


def _score_flat(payload: dict) -> dict:
    result = {"company_id": payload["company_id"], "currency": payload["currency"], "as_of": payload["as_of"],
            "score_version": payload["score_version"], "status": payload["status"], "health": payload["health"],
            "known_weight": payload["known_weight"], "health_min": payload["health_min"], "health_max": payload["health_max"],
            **{key: pillar["score"] for key, pillar in payload["pillars"].items()},
            "result_json": _json(payload)}
    if "composition_version" in payload:
        result.update({key: payload.get(key) for key in ("composition_version", "operating_health",
                                                       "extended_health", "health_level")})
    return result


def _features_flat(payload: dict) -> list[dict]:
    records = []
    for pillar, value in payload["pillars"].items():
        for name, feature in value["features"].items():
            records.append({"company_id": payload["company_id"], "currency": payload["currency"], "as_of": payload["as_of"],
                            "pillar": pillar, "feature": name,
                            **{key: feature.get(key) for key in ("raw", "score", "numerator", "denominator", "formula_id", "window")},
                            "window": "6m", "window_json": _json(feature["window6m"]),
                            "feature_json": _json(feature)})
    return records


def _portfolio_row(payload: dict) -> dict:
    flags = payload.get("flags", [])
    movements = payload.get("critical_movements", [])
    row = {"company_id": payload["company_id"], "currency": payload["currency"], "as_of": payload["as_of"],
            "score_version": payload["score_version"], "health": payload["health"], "status": payload["status"],
            **{key: value["score"] for key, value in payload["pillars"].items()},
            "direction": payload.get("direction", "unknown"),
            "robustness": payload.get("robustness", {}).get("level", "unknown"),
            "confidence": payload.get("confidence", {}).get("level", "unknown"),
            "main_signal": movements[0]["reason"] if movements else (flags[0] if flags else "no_material_signal"),
            "alert_count": 0}
    if "health_evidence" in payload:
        row.update(health_evidence=payload["health_evidence"], identified_range=payload["identified_range"])
    if "composition_version" in payload:
        row.update({key: payload.get(key) for key in ("composition_version", "operating_health",
                                                     "extended_health", "health_level", "insights_available",
                                                     "missing_modules")})
    return row


def run(raw_dir: Path, out_dir: Path, *, as_of: str | pd.Timestamp, data_vintage: str | pd.Timestamp,
        config: PulseConfig | None = None, config_path: Path | None = None,
        previous_run: Path | None = None, company_ids: list[str] | None = None,
        ai_categories_path: Path | None = None, ai_min_confidence: float = 0.7,
        verbose: bool = True) -> dict:
    """Produce a complete immutable run and publish its pointer.

    ``data_vintage`` is required: a retrospective as_of cannot masquerade as
    original historical knowledge. ``previous_run`` compares stored results
    (including same-as_of restatements); otherwise prior month is rebuilt from
    the SAME raw vintage with its own pre-clean cutoff.
    """
    from xray.ledger import build_cash_truth_result

    raw_dir, out_dir = Path(raw_dir).resolve(), Path(out_dir).resolve()
    if out_dir == raw_dir or out_dir in raw_dir.parents:
        raise ValueError("Output must not replace the raw input directory")
    # This checkout keeps CSVs directly in data/. A dedicated data/processed
    # child is safe: protect each CSV, not every unrelated descendant of data/.
    for name in TABLES:
        check_output_path(out_dir, raw_dir / f"{name}.csv")
    if config is not None and config_path is not None:
        raise ValueError("Use either config or config_path, not both")
    configuration = config or load_config(config_path)
    if not 0 <= ai_min_confidence <= 1:
        raise ValueError("ai_min_confidence must be in [0, 1]")
    cache_path = Path(ai_categories_path).resolve() if ai_categories_path else None
    if cache_path:
        check_output_path(out_dir, cache_path)
    cache_hash = sha256(cache_path) if cache_path else None
    classification = classification_metadata(cache_path, ai_min_confidence)
    classification_policy = classification["config"]
    classification_config = {"ai_categories_path": cache_path, "ai_min_confidence": ai_min_confidence}
    cutoff_date, vintage = _date(as_of, "as_of"), _date(data_vintage, "data_vintage")
    if vintage < cutoff_date:
        raise ValueError("data_vintage cannot predate as_of")
    economic_cutoff = _complete_cutoff(cutoff_date)
    inputs = {f"{name}.csv": sha256(raw_dir / f"{name}.csv") for name in TABLES}
    code, runtime = _source_code(), _runtime()
    raw, requested = _load_raw(raw_dir, company_ids)
    company_currencies = _company_currencies(raw, requested)
    if company_currencies.empty:
        raise ValueError("No verified company/currency perimeter")
    cut, cleaned, cleaning_log, ledger, facts = _prepare(raw, economic_cutoff, company_currencies, classification_config)
    consumed = {name: _frame_hash(frame) for name, frame in cut.items()}
    input_hash = _digest(consumed)
    stored_previous, previous_manifest_hash = _previous_scores(previous_run, cutoff_date)
    identity = {"pipeline_version": PIPELINE_VERSION, "as_of": cutoff_date.date().isoformat(),
                "economic_cutoff": economic_cutoff.date().isoformat(), "data_vintage": vintage.date().isoformat(),
                "input_hash": input_hash, "raw_sha256": inputs, "config_hash": configuration.config_hash,
                "code_version": code["code_sha256"], "runtime": runtime, "companies": requested,
                "classification_version": classification["classification_version"],
                "classification_config_hash": classification["config_hash"], "classification_evidence_hash": cache_hash,
                "previous_manifest_hash": previous_manifest_hash}
    run_id = "pulse-" + _digest(identity)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pulse-stage-", dir=out_dir) as temp:
        staged = Path(temp) / "run"
        staged.mkdir()
        # Keep consumed sources and cleaning decisions for audit/replay. The
        # original raw byte hashes identify the external immutable source files.
        for folder, tables in (("source_snapshot", cut), ("cleaned", cleaned)):
            (staged / folder).mkdir()
            for name, frame in sorted(tables.items()):
                frame.to_parquet(staged / folder / f"{name}.parquet", index=False)
        # Source frames are already serialized and their digests captured. Do
        # not retain duplicate full raw/cleaned tables throughout portfolio scoring.
        del cut, cleaned, tables, frame
        cleaning_log.to_csv(staged / "cleaning_log.csv", index=False)
        ledger.to_parquet(staged / "ledger.parquet", index=False)
        facts.to_parquet(staged / "monthly_facts.parquet", index=False)
        _write_json(staged / "classification_config.json", classification_policy)
        if cache_path:
            (staged / "classification_evidence").mkdir()
            shutil.copyfile(cache_path, staged / "classification_evidence" / "template_categories.parquet")
        ledger_hash, facts_hash = sha256(staged / "ledger.parquet"), sha256(staged / "monthly_facts.parquet")
        lineage = {"input_hash": input_hash, "ledger_hash": ledger_hash, "facts_hash": facts_hash,
                   "config_hash": configuration.config_hash, "code_version": code["code_sha256"],
                   "classification_config_hash": identity["classification_config_hash"],
                   "classification_evidence_hash": cache_hash,
                   "classification_version": classification["classification_version"],
                   "data_vintage": vintage.date().isoformat(), "knowledge_cutoff": vintage.date().isoformat(),
                   "economic_cutoff": economic_cutoff.date().isoformat(),
                   "history_mode": "retrospective_restatement", "cleaning_version": CLEANING_VERSION,
                   "temporal_limitations": ["source_snapshot_has_no_row_known_at_history",
                                            "catalog_created_at_is_connection_not_account_opening",
                                            "invoices_and_debt_snapshots_are_not_scoring_inputs"],
                   "ledger_ref": "ledger.parquet", "facts_ref": "monthly_facts.parquet"}
        prior_facts = prior_ledger = None
        prior_lineage = None
        prior_cutoff = (economic_cutoff.to_period("M") - 1).to_timestamp("M")
        if previous_run is None:
            prior_cut, _, _, prior_ledger, prior_facts = _prepare(raw, prior_cutoff, company_currencies, classification_config)
            previous_dir = staged / "comparisons" / "previous_month"
            previous_dir.mkdir(parents=True)
            prior_ledger.to_parquet(previous_dir / "ledger.parquet", index=False)
            prior_facts.to_parquet(previous_dir / "monthly_facts.parquet", index=False)
            prior_lineage = {**lineage, "comparison_basis": "same_vintage_previous_month",
                             "input_hash": _digest({name: _frame_hash(frame) for name, frame in prior_cut.items()}),
                             "economic_cutoff": prior_cutoff.date().isoformat(),
                             "ledger_hash": sha256(previous_dir / "ledger.parquet"),
                             "facts_hash": sha256(previous_dir / "monthly_facts.parquet"),
                             "ledger_ref": "comparisons/previous_month/ledger.parquet",
                             "facts_ref": "comparisons/previous_month/monthly_facts.parquet"}
            del prior_cut
        del raw
        # Index once: do not scan millions of transactions again for every
        # company and each leave-one-out/sensitivity scenario.
        ledger_groups = ledger.groupby(["company_id", "currency"]).groups
        prior_groups = prior_ledger.groupby(["company_id", "currency"]).groups if prior_ledger is not None else {}
        scores, feature_rows, portfolio = [], [], []
        for pair in company_currencies.itertuples(index=False):
            company_id, currency = str(pair.company_id), str(pair.currency)
            unit_ledger = ledger.loc[ledger_groups.get((company_id, currency), [])]
            company_path = staged / "companies" / _segment(company_id) / _segment(currency)
            previous = stored_previous.get((company_id, currency))
            if previous_run is None:
                assert prior_ledger is not None
                previous = score_company(prior_facts, company_id=company_id, currency=currency,
                                         as_of=prior_cutoff, config=configuration, run_id=run_id,
                                         lineage=prior_lineage,
                                         ledger=prior_ledger.loc[prior_groups.get((company_id, currency), [])]).to_dict()
                previous_ref = f"comparisons/previous_month/{_segment(company_id)}/{_segment(currency)}/score.json"
                _write_json(staged / previous_ref, previous)
            else:
                previous_ref = f"companies/{_segment(company_id)}/{_segment(currency)}/score.json"
            score = score_company(facts, company_id=company_id, currency=currency, as_of=cutoff_date,
                                  config=configuration, run_id=run_id, lineage=lineage, ledger=unit_ledger,
                                  previous=previous)
            payload = score.to_dict()
            payload["change"]["previous_result_ref"] = (
                {"run_id": previous["run_id"], "path": previous_ref} if previous else None)
            cash = build_cash_truth_result(unit_ledger, facts, company_id=company_id, currency=currency,
                                          as_of=cutoff_date, critical_movements=payload["critical_movements"],
                                          detail_ref="ledger.parquet")
            _write_json(company_path / "score.json", payload)
            _write_json(company_path / "cash_truth.json", cash.to_dict())
            scores.append(_score_flat(payload))
            feature_rows.extend(_features_flat(payload))
            portfolio.append(_portfolio_row(payload))
            if verbose:
                print(f"  {company_id} {currency}: {payload['status']} health={payload['health']}")
        pd.DataFrame(scores).to_parquet(staged / "pulse_scores.parquet", index=False)
        pd.DataFrame(feature_rows).to_parquet(staged / "pulse_features.parquet", index=False)
        _write_json(staged / "portfolio.json", {"schema_version": "1.0", "run_id": run_id,
                                               "as_of": cutoff_date.date().isoformat(), "companies": portfolio})
        _write_json(staged / "config.json", configuration.to_dict())
        sample = scores[0]
        score_payload = json.loads(sample["result_json"])
        versions = {key: score_payload.get(key) for key in ("schema_version", "classification_version", "facts_version", "score_version", "config_version")}
        versions["cleaning_version"] = CLEANING_VERSION
        manifest = {"run_id": run_id, **identity, "versions": versions, "code": code,
                    "consumed_input_sha256": consumed, "lineage": lineage,
                    "rows": {"ledger": len(ledger), "monthly_facts": len(facts), "scores": len(scores)},
                    "outputs_sha256": recursive_hashes(staged)}
        _write_json(staged / "manifest.json", manifest)
        if any(sha256(raw_dir / name) != digest for name, digest in inputs.items()):
            raise RuntimeError("Raw inputs changed during calculation; run not published")
        if cache_path and sha256(cache_path) != cache_hash:
            raise RuntimeError("Classification evidence changed during calculation; run not published")
        if _source_code() != code:
            raise RuntimeError("Runtime source changed during calculation; run not published")
        publish_immutable_run(staged, out_dir, run_id)
    return manifest
