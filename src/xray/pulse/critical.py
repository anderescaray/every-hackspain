"""Bounded leave-one-out evidence, selected by impact rather than transaction size."""
from typing import Any

import numpy as np
import pandas as pd

from xray.pulse.config import PulseConfig
from xray.pulse.contracts import PulseScoreResult
from xray.pulse.features import FeatureWindow, extract_features
from xray.pulse.scorer import score_core


def window_ledger(ledger: pd.DataFrame | None, baseline: PulseScoreResult, window: FeatureWindow) -> pd.DataFrame:
    if ledger is None or ledger.empty:
        return pd.DataFrame()
    t = ledger.loc[ledger.company_id.eq(baseline.company_id) & ledger.currency.eq(baseline.currency)].copy()
    t["date"] = pd.to_datetime(t.date)
    t["month"] = t.date.dt.to_period("M").dt.to_timestamp()
    return t.loc[t.month.isin(window.frame.month)].sort_values(["date", "transaction_id"]).reset_index(drop=True)


def included(t: pd.DataFrame, name: str) -> pd.Series:
    return t[name].fillna(False).astype(bool) if name in t else pd.Series(False, index=t.index)


def recalculate(frame: pd.DataFrame, baseline: PulseScoreResult, config: PulseConfig) -> PulseScoreResult:
    fresh = extract_features(frame, company_id=baseline.company_id, currency=baseline.currency,
                             as_of=baseline.as_of, config=config)
    return score_core(fresh, company_id=baseline.company_id, currency=baseline.currency, as_of=baseline.as_of,
                      config=config, run_id=baseline.run_id, lineage=baseline.lineage)


def without_transaction(frame: pd.DataFrame, row: dict[str, Any]) -> pd.DataFrame:
    """One monthly cell changes; observed-month metadata stays observed in the scenario."""
    out = frame.copy(deep=True)
    month = pd.Timestamp(row["date"]).to_period("M").start_time
    match = out.month.eq(month)
    amount = float(row["amount"])
    if row.get("included_in_operating_inflows", False):
        out.loc[match, "operating_inflows"] -= amount
    if row.get("included_in_operating_outflows", False):
        out.loc[match, "operating_outflows"] -= -amount
    if row.get("included_in_debt_service", False):
        subclass = str(row.get("economic_subclass"))
        debt_column = {"debt_principal": "debt_principal_paid", "debt_interest": "debt_interest_paid",
                       "financial_fee": "verified_financing_fees"}.get(subclass)
        if debt_column is None:
            raise ValueError(f"Unknown debt-service subclass for leave-one-out: {subclass}")
        out.loc[match, debt_column] -= -amount
    out["operating_net_cash"] = out.operating_inflows - out.operating_outflows
    out["debt_service_paid"] = out.debt_principal_paid + out.debt_interest_paid + out.verified_financing_fees
    return out


def critical_movements(ledger: pd.DataFrame | None, window: FeatureWindow, baseline: PulseScoreResult,
                       config: PulseConfig) -> list[dict[str, Any]]:
    t = window_ledger(ledger, baseline, window)
    policy = config.to_dict()["critical"]
    audit = {"method_version": policy["version"], "ledger_rows_in_window": len(t), "candidate_count": 0,
             "evaluated_count": 0, "candidate_limit": policy["max_candidates"], "result_limit": policy["max_results"],
             "candidate_search_truncated": False,
             "preselection": "identified_operating_or_service_then_identification_signflip_and_normalized_impact"}
    baseline.evidence["critical_analysis"] = audit
    if t.empty or window.confidence["history_coverage"] < 1:
        return []
    op_in, op_out, debt = (included(t, name) for name in
                           ("included_in_operating_inflows", "included_in_operating_outflows", "included_in_debt_service"))
    t = t.loc[op_in | op_out | debt].copy()
    audit["candidate_count"] = len(t)
    if t.empty:
        return []
    net_by_month = window.frame.set_index("month").operating_net_cash
    t["_before"] = t.month.map(net_by_month)
    operating = included(t, "included_in_operating_inflows") | included(t, "included_in_operating_outflows")
    t["_net_effect"] = t.amount.where(operating, 0.)
    t["_without"] = t._before - t._net_effect
    t["_sign_flip"] = ((t._before >= 0) & (t._without < 0)) | ((t._before < 0) & (t._without >= 0))
    t["_identification_change"] = included(t, "included_in_debt_service") & t.amount.abs().eq(window.sums["debt_service_paid"])
    # Cheap exact G/R screen over all candidates; at most max_candidates get 15-slope Momentum LOO.
    n, o = window.sums["operating_net_cash"], window.sums["operating_outflows"]
    if n is None or o is None or o <= 0:
        return []
    without_o = o + t.amount.where(included(t, "included_in_operating_outflows"), 0.)
    without_n = n - t._net_effect
    g = (50 + 200 * without_n / without_o.where(without_o > 0)).clip(0, 100)
    downside = float(window.features["operating_downside_ratio"]["numerator"])
    without_down = downside - (-t._before).clip(lower=0) + (-t._without).clip(lower=0)
    r = (100 - 400 * without_down / without_o.where(without_o > 0)).clip(0, 100)
    current_g, current_r = baseline.pillars["generation"]["score"], baseline.pillars["resilience"]["score"]
    score_screen = np.maximum((g - current_g).abs(), (r - current_r).abs())
    # Momentum candidates cannot be screened solely by saturated G/R. Normalized N perturbation is an upper-bound proxy.
    trend_screen = 200 * 3 * t._net_effect.abs() / (o / 6)
    t["_screen"] = np.maximum(score_screen.fillna(100), trend_screen)
    t.loc[included(t, "included_in_debt_service"), "_screen"] = 100.
    t = t.sort_values(["_identification_change", "_sign_flip", "_screen", "transaction_id"], ascending=[False, False, False, True])
    audit["evaluated_count"] = min(len(t), policy["max_candidates"])
    audit["candidate_search_truncated"] = len(t) > policy["max_candidates"]
    if audit["candidate_search_truncated"]:
        baseline.flags = sorted(set(baseline.flags + ["critical_search_bounded_not_exhaustive"]))
    results = []
    for row in t.head(policy["max_candidates"]).to_dict("records"):
        changed = recalculate(without_transaction(window.frame, row), baseline, config)
        impact = {}
        for name in ("generation", "resilience", "momentum"):
            before, after = baseline.pillars[name]["score"], changed.pillars[name]["score"]
            impact[f"{name}_delta"] = after - before if before is not None and after is not None else None
        impact["health_delta"] = changed.health - baseline.health if changed.health is not None and baseline.health is not None else None
        impact["monthly_net_before"], impact["monthly_net_without"] = float(row["_before"]), float(row["_without"])
        magnitude = max((abs(v) for key, v in impact.items() if key.endswith("_delta") and v is not None), default=0.)
        lost_evidence = changed.missing_components != baseline.missing_components
        direction_change = baseline.direction != changed.direction
        if not (row["_sign_flip"] or magnitude >= policy["minimum_score_impact"] or lost_evidence or direction_change):
            continue
        reason = ("changes_month_from_positive_to_deficit" if row["_before"] >= 0 and row["_without"] < 0 else
                  "changes_month_from_deficit_to_nonnegative" if row["_before"] < 0 and row["_without"] >= 0 else
                  "removal_changes_identified_components" if lost_evidence else
                  "changes_operating_direction" if direction_change else "material_pillar_change")
        results.append({"transaction_id": str(row["transaction_id"]), "amount": float(row["amount"]),
                        "date": str(pd.Timestamp(row["date"]).date()), "impact": impact,
                        "criticality": "high" if row["_sign_flip"] or lost_evidence else "material",
                        "reason": reason, "diagnosis_without": changed.direction,
                        "missing_components_without": changed.missing_components,
                        "method_version": policy["version"], "delta_definition": "without_minus_baseline",
                        "interpretation": "leave_one_out_sensitivity_not_causal_effect", "_rank": magnitude,
                        "identification_changed": lost_evidence})
    results.sort(key=lambda item: (not item["identification_changed"], item["criticality"] != "high", -item["_rank"], item["transaction_id"]))
    for item in results:
        item.pop("_rank")
    return results[:policy["max_results"]]
