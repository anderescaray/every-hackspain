"""Conservative identification bounds for observed service, never debt absence."""
import math
from typing import Any

import numpy as np
import pandas as pd

UNCERTAINTY_COLUMNS = (
    "debt_possible_uncertain_outflows", "debt_impossible_uncertain_outflows",
    "debt_unresolved_uncertain_outflows", "potentially_financial_uncertain_outflows",
)
SERVICE_COLUMNS = ("debt_principal_paid", "debt_interest_paid", "verified_financing_fees", "debt_service_paid")


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _total(frame: pd.DataFrame, column: str, *, available: bool = False) -> float | None:
    values = list(frame[column]) if column in frame else []
    finite = [float(v) for v in values if _finite(v)]
    if not finite or (not available and len(finite) != len(values)):
        return None
    return math.fsum(finite)


def assess_debt(frame: pd.DataFrame, sums: dict, *, base_reason: str | None,
                debt_finite: bool, currency_issue: bool, policy: dict) -> dict[str, Any]:
    """Keep available evidence distinct from a complete six-month financial ratio."""
    required = {*UNCERTAINTY_COLUMNS, "debt_uncertainty_version", "uncertain_outflows", "excluded_outflows"}
    if missing := required.difference(frame.columns):
        raise ValueError(f"Debt assessment facts missing; regenerate canonical facts: {sorted(missing)}")
    versions = set(frame.debt_uncertainty_version.dropna())
    if (versions or frame.history_observed.eq(True).any()) and versions != {policy["debt_uncertainty_version"]}:
        raise ValueError("Debt uncertainty assessment version differs from score configuration")
    for row in frame.itertuples():
        values = [getattr(row, col) for col in UNCERTAINTY_COLUMNS]
        if any(_finite(v) and v < 0 for v in values):
            raise ValueError("Debt uncertainty magnitudes must be nonnegative")
        if all(_finite(v) for v in values) and _finite(row.uncertain_outflows):
            possible, impossible, unresolved, potential = map(float, values)
            for actual, expected in ((potential, math.fsum((possible, unresolved))),
                                     (float(row.uncertain_outflows), math.fsum((possible, impossible, unresolved)))):
                tolerance = math.fsum(math.ulp(float(v)) for v in values + [row.uncertain_outflows])
                if abs(actual - expected) > tolerance:
                    raise ValueError("Debt uncertainty partition does not reconcile")
    observed = int(frame.history_observed.eq(True).sum())
    identified: dict[str, Any] = {col: _total(frame, col, available=True) for col in SERVICE_COLUMNS}
    identified.update(observed_months=observed, required_months=len(frame), history_complete=observed == len(frame))
    service_available = identified["debt_service_paid"]
    status = "partial" if service_available is not None and service_available > 0 else "unknown"
    uncertainty: dict[str, Any] = {col: _total(frame, col, available=True) for col in UNCERTAINTY_COLUMNS}
    uncertainty["version"] = policy["debt_uncertainty_version"]
    result: dict[str, Any] = {"evidence_status": status, "reason": None, "identified_service": identified,
              "service_absence_verified": False, "uncertainty": uncertainty,
              "service_bounds": {"min": service_available, "max": None},
              "identified_score": None, "score_range": {"min": None, "max": None},
              "score_range_width": None, "score_estimation": None, "point_score": None, "raw": None}
    service, inflows = sums["debt_service_paid"], sums["operating_inflows"]
    def transform(value: float) -> float:
        anchors = policy["anchors"]["debt_obligations"]
        return float(np.interp(value, [a[0] for a in anchors], [a[1] for a in anchors]))
    if not base_reason and debt_finite and service is not None and service > 0 and inflows is not None and inflows > 0:
        result["raw"] = service / inflows
        result["identified_score"] = transform(result["raw"])
    excluded = _total(frame, "excluded_outflows")
    totals = {col: _total(frame, col) for col in UNCERTAINTY_COLUMNS}
    if base_reason or not debt_finite:
        reason = base_reason or "invalid_debt_facts"
    elif service == 0:
        status, reason = "unknown", "no_identified_service_is_not_verified_absence"
    elif excluded is None:
        reason = "outflow_evidence_unavailable"
    elif excluded > 0:
        reason = "excluded_outflows_unbounded"
    elif currency_issue:
        reason = "currency_evidence_unbounded"
    elif any(value is None for value in totals.values()) or _total(frame, "uncertain_outflows") is None:
        reason = "invalid_debt_uncertainty_facts"
    elif inflows == 0:
        reason = "zero_operating_inflows"
    else:
        assert service is not None and inflows is not None and inflows > 0
        potential_total = totals["potentially_financial_uncertain_outflows"]
        assert potential_total is not None
        maximum_service = math.fsum((service, potential_total))
        low, high = transform(maximum_service / inflows), transform(service / inflows)
        width = high - low
        result.update(service_bounds={"min": service, "max": maximum_service},
                      score_range={"min": low, "max": high}, score_range_width=width)
        if potential_total == 0:
            status, reason = "verified", "six_month_identified_observed_service"
            result.update(point_score=high, score_estimation="identified")
        elif width <= policy["debt_bounds"]["max_score_width"]:
            status, reason = "bounded", "potential_financial_uncertainty_within_score_tolerance"
            result.update(point_score=(low + high) / 2, score_estimation="bounded_midpoint")
        else:
            status, reason = "partial", "potential_financial_uncertainty_exceeds_score_tolerance"
    result.update(evidence_status=status, reason=reason)
    return result
