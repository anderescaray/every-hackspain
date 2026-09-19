"""Small deterministic assumption checks; ranges are not confidence intervals."""
from typing import Any

import pandas as pd

from xray.pulse.config import PulseConfig
from xray.pulse.contracts import PulseScoreResult
from xray.pulse.critical import recalculate, window_ledger, without_transaction
from xray.pulse.features import FeatureWindow


def evaluate_robustness(ledger: pd.DataFrame | None, window: FeatureWindow, baseline: PulseScoreResult,
                        config: PulseConfig) -> dict[str, Any]:
    policy = config.to_dict()["robustness"]
    checks = []
    sensitive = []

    def add(name, scenario, assumptions):
        result = recalculate(scenario, baseline, config)
        evaluable = result.health is not None and baseline.health is not None
        stable = (result.direction == baseline.direction and result.missing_components == baseline.missing_components
                  and evaluable and abs(result.health - baseline.health) <= policy["max_stable_health_range"])
        checks.append({"name": name, "version": policy["version"], "health": result.health,
                       "evaluable": evaluable, "direction": result.direction, "diagnosis_stable": stable,
                       "missing_components": result.missing_components, "assumptions": assumptions,
                       "pillar_scores": {k: v["score"] for k, v in result.pillars.items()}})
        if not evaluable or not stable or (result.health is not None and baseline.health is not None and
                                           abs(result.health - baseline.health) > policy["max_stable_health_range"]):
            sensitive.append(name)

    uncertain_share = window.confidence.get("uncertain_amount_share")
    if uncertain_share is not None and uncertain_share >= policy["material_uncertain_share"]:
        for side in ("inflows", "outflows"):
            field = "uncertain_" + side
            if field in window.frame and window.frame[field].fillna(0).sum() > 0:
                frame = window.frame.copy(deep=True)
                frame["operating_" + side] += frame[field]
                frame["operating_net_cash"] = frame.operating_inflows - frame.operating_outflows
                # Leave uncertainty/evidence intact: an assumed economic class cannot certify observed debt.
                add("uncertain_as_operating_" + side, frame,
                    {"hypothesis": "all_material_uncertain_side_is_operating", "evidence_unchanged": True,
                     "ledger_unchanged": True})
    t = window_ledger(ledger, baseline, window)
    if baseline.critical_movements and not t.empty:
        txid = baseline.critical_movements[0]["transaction_id"]
        rows = t.loc[t.transaction_id.astype(str).eq(txid)]
        if not rows.empty:
            add("exclude_most_influential", without_transaction(window.frame, rows.iloc[0].to_dict()),
                {"transaction_id": txid, "ledger_unchanged": True, "observed_month_metadata_preserved": True})
    sets = [set(v) for v in window.evidence.get("monthly_product_ids", []) if v]
    comparable = set.intersection(*sets) if len(sets) == 6 else set()
    all_products = set.union(*sets) if sets else set()
    if comparable and comparable != all_products and not t.empty:
        from xray.ledger import build_monthly_facts
        restricted = t.loc[t.product_id.isin(comparable)].copy()
        if not restricted.empty:
            frame = build_monthly_facts(restricted, as_of=baseline.as_of,
                                        company_currencies=pd.DataFrame({"company_id": [baseline.company_id], "currency": [baseline.currency]}),
                                        start_month=window.window["start"])
            # Restriction is a sensitivity assumption, not stronger knowledge about the remaining debt service.
            original = window.frame.set_index("month")
            for col in ("uncertain_outflows", "excluded_outflows", "unknown_currency_count", "ambiguous_currency_count", "excluded_row_count",
                        "debt_possible_uncertain_outflows", "debt_impossible_uncertain_outflows",
                        "debt_unresolved_uncertain_outflows", "potentially_financial_uncertain_outflows"):
                if col in original:
                    frame[col] = frame.month.map(original[col])
            add("observed_common_account_perimeter", frame,
                {"product_ids": sorted(comparable), "method": "active_in_each_observed_month_proxy",
                 "complete_coverage_verified": False})
    elif len(sets) < 6 or not comparable:
        checks.append({"name": "observed_common_account_perimeter", "version": policy["version"],
                       "evaluable": False, "health": None,
                       "reason": "six_month_account_evidence_unavailable" if len(sets) < 6 else "no_common_account_perimeter",
                       "assumptions": {"complete_coverage_verified": False}})
        sensitive.append("observed_common_account_perimeter")
    values = [baseline.health] if baseline.health is not None else []
    values += [c["health"] for c in checks if c.get("evaluable") and c.get("health") is not None]
    unavailable = baseline.health is None or any(not c.get("evaluable", False) for c in checks)
    stable = None if unavailable else all(c.get("diagnosis_stable", False) for c in checks)
    if stable and values and max(values) - min(values) > policy["max_stable_health_range"]:
        stable = False
    if not checks:
        level = "not_evaluated"
        stable = None
    elif unavailable:
        level = "indeterminate"
    else:
        level = "sensitive" if sensitive or max(values) - min(values) > policy["max_stable_health_range"] else "stable_under_tested_assumptions"
    return {"level": level, "baseline_health": baseline.health,
            "tested_range": {"min": min(values) if values else None, "max": max(values) if values else None},
            "diagnosis_stable": stable, "tested_assumptions": checks, "sensitive_to": sorted(set(sensitive)),
            "version": policy["version"], "range_kind": "deterministic_sensitivity_not_confidence_interval",
            "includes_baseline": baseline.health is not None}
