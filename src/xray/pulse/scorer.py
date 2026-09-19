"""Pure independent four-pillar scorer; confidence never scales financial health."""
import math
from typing import Any

import numpy as np
import pandas as pd

from xray.pulse.config import PulseConfig, load_config
from xray.pulse.contracts import PILLARS, PulseScoreResult
from xray.pulse.features import FeatureWindow, extract_features

FEATURE_NAMES = dict(zip(PILLARS, ("generation_ratio", "operating_net_trend", "operating_downside_ratio",
                                 "observed_debt_service_burden")))


def score_core(window: FeatureWindow, *, company_id: str, currency: str, as_of,
               config: PulseConfig, run_id: str = "", lineage: dict[str, Any] | None = None) -> PulseScoreResult:
    pillars: dict[str, dict[str, Any]] = {}
    for name in PILLARS:
        feature = dict(window.features[FEATURE_NAMES[name]])
        raw = feature["raw"]
        if feature["missing_reason"] or raw is None:
            score = None
        else:
            anchors = feature["anchors"]
            score = float(np.interp(raw, [a[0] for a in anchors], [a[1] for a in anchors]))
        feature["score"] = score
        weight = config.weights[name]
        pillars[name] = {"score": score, "weight": weight,
                         "health_contribution": weight * score if score is not None else None,
                         "features": {FEATURE_NAMES[name]: feature}}
        if name == "resilience":
            pillars[name]["diagnostics"] = window.diagnostics
        if name == "debt_obligations":
            pillars[name].update(evidence_status=window.debt_status, evidence_reason=window.debt_reason,
                                 semantics="observed_debt_service_pressure")
    missing = [name for name in PILLARS if pillars[name]["score"] is None]
    contributions: dict[str, float | None] = {name: pillars[name]["health_contribution"] for name in PILLARS}
    known_weight = sum(config.weights[name] for name in PILLARS if name not in missing)
    lower = sum(v for v in contributions.values() if v is not None)
    upper = min(100., lower + 100 * sum(config.weights[name] for name in missing))
    health = lower if not missing else None
    if health is not None and not math.isfinite(health):
        raise ValueError("Health must be finite")
    momentum = pillars["momentum"]["score"]
    direction = "unknown" if momentum is None else "improving" if momentum > 50 else "deteriorating" if momentum < 50 else "stable"
    versions = window.frame.get("classification_version", pd.Series(dtype=str)).dropna().unique()
    if len(versions) > 1:
        raise ValueError("Monthly facts mix classification versions")
    classification_version = str(versions[0]) if len(versions) else (lineage or {}).get("classification_version", config.classification_version)
    window.evidence["source_refs"] = {"ledger": (lineage or {}).get("ledger_ref", "ledger.parquet"),
                                      "facts": (lineage or {}).get("facts_ref", "monthly_facts.parquet")}
    window.evidence["feature_lineage"] = {
        FEATURE_NAMES[name]: {"company_id": company_id, "currency": currency, "months": window.window["months"],
                              "ledger_inclusion_fields": (["included_in_debt_service"] if name == "debt_obligations" else
                                                          ["included_in_operating_inflows", "included_in_operating_outflows"])}
        for name in PILLARS}
    return PulseScoreResult(company_id=str(company_id), currency=currency, as_of=str(pd.Timestamp(as_of).date()),
                            score_version=config.score_version, classification_version=classification_version,
                            run_id=run_id, status="complete" if not missing else "partial", health=health,
                            pillars=pillars, known_weight=known_weight, health_min=lower, health_max=upper,
                            missing_components=missing, confidence=window.confidence,
                            lineage={**(lineage or {}), "config_hash": config.config_hash},
                            direction=direction, raw_features={k: v["raw"] for k, v in window.features.items()},
                            normalized_features={FEATURE_NAMES[k]: v["score"] for k, v in pillars.items()},
                            contributions=contributions, economic_facts=window.sums, evidence=window.evidence,
                            flags=window.flags)


def score_company(facts: pd.DataFrame, *, company_id: str, currency: str, as_of,
                  config: PulseConfig | None = None, lineage: dict[str, Any] | None = None,
                  run_id: str = "", ledger: pd.DataFrame | None = None,
                  previous: PulseScoreResult | dict | None = None) -> PulseScoreResult:
    config = config or load_config()
    window = extract_features(facts, company_id=company_id, currency=currency, as_of=as_of, config=config)
    result = score_core(window, company_id=company_id, currency=currency, as_of=as_of,
                        config=config, run_id=run_id, lineage=lineage)
    from xray.pulse.change import attribute_change
    from xray.pulse.critical import critical_movements
    from xray.pulse.robustness import evaluate_robustness
    result.critical_movements = critical_movements(ledger, window, result, config)
    result.change = attribute_change(result, previous)
    result.robustness = evaluate_robustness(ledger, window, result, config)
    return result


def feature_records(result: PulseScoreResult | dict) -> list[dict[str, Any]]:
    payload = result.to_dict() if isinstance(result, PulseScoreResult) else result
    rows = []
    for pillar, block in payload["pillars"].items():
        for name, feature in block["features"].items():
            rows.append({"company_id": payload["company_id"], "currency": payload["currency"], "as_of": payload["as_of"],
                         "score_version": payload["score_version"], "pillar": pillar, "feature": name, **feature})
    return rows
