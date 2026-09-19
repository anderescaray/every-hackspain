"""Presentation-only adapter for ``company_sensitivity_v1``.

The advisor owns every counterfactual. This module chooses an existing grid row,
labels it, and preserves the distinction between V2 level and Health Score.
"""

from __future__ import annotations

import math

METHOD = "company_sensitivity_v1"
LABELS = {
    "ap_on_time": ("Pagar antes a proveedores", "Retraso a proveedores"),
    "ar_faster": ("Cobrar antes", "Retraso de cobro"),
    "debt_service_cut": ("Reducir servicio de deuda", "Servicio mensual de deuda"),
    "cut_outflow": ("Reducir salidas", "Salidas operativas mensuales"),
    "raise_inflow": ("Aumentar entradas", "Entradas operativas mensuales"),
}
TREASURY = frozenset(("ap_on_time", "ar_faster", "debt_service_cut"))
BUSINESS = frozenset(("cut_outflow", "raise_inflow"))
LIQUIDITY = "ap_on_time"
CASH_RELIEF = frozenset(("debt_service_cut", "cut_outflow"))


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def unavailable(doc, status, reason):
    return {
        "status": status,
        "reason": reason,
        "method": METHOD,
        "month": doc.get("month"),
        "primary": None,
        "alternatives": [],
        "next_band": None,
        "structural_issue": bool(doc.get("structural_note")),
        "assumptions": list(doc.get("assumptions") or []),
        "source": {"method": METHOD, "inputs_sha256": doc.get("inputs_sha256") or {}},
    }


def _best_row(lever, baseline_score):
    """Pick the highest positive *precomputed Health* impact; ties use smaller r."""
    rows = lever.get("grid") or []
    candidates = [row for row in rows if _number(row.get("score_after_k6")) is not None]
    candidates = [row for row in candidates if row["score_after_k6"] > baseline_score]
    return max(candidates, key=lambda row: (row["score_after_k6"], -row["rel_change"])) if candidates else None


def _resources(lever, row, currency):
    if lever["lever"] != LIQUIDITY:
        return None
    required = _number(row.get("cash_equivalent"))
    own = _number((lever.get("feasibility") or {}).get("own_excess_cash"))
    if required is None or own is None:
        feasibility, gap = "unknown", None
    else:
        gap = max(0.0, required - own)
        feasibility = "own_liquidity_sufficient" if gap == 0 else "requires_financing"
    return {"kind": "liquidity", "required": required, "own_available": own, "gap": gap,
            "currency": currency, "feasibility": feasibility, "scope": "selected_grid_scenario"}


def _efficiency(lever):
    value = _number((lever.get("slope_now") or {}).get("level_per_10k"))
    if value is None or value <= 0 or lever["lever"] not in CASH_RELIEF | {LIQUIDITY}:
        return None
    return {"value": value, "unit": "level_points_per_10k",
            "label": "Eficiencia de liquidez" if lever["lever"] == LIQUIDITY else "Eficiencia de caja"}


def _lever(doc, lever, row):
    key = lever["lever"]
    baseline = doc["baseline"]
    level_before, score_before = _number(baseline.get("level")), _number(baseline.get("score"))
    level_after, score_after = _number(row.get("level_after_k6")), _number(row.get("score_after_k6"))
    unit = "days" if lever["unit"] == "days" else doc["currency"]
    breakpoint = _number((lever.get("slope_now") or {}).get("valid_until"))
    return {
        "lever": key, "type": "treasury" if key in TREASURY else "business", "label": LABELS[key][0],
        "level_before": level_before, "level_after": level_after,
        "health_before": score_before, "health_after": score_after,
        "delta_points": None if score_before is None or score_after is None else score_after - score_before,
        "quantity": {"label": LABELS[key][1], "before": _number(lever.get("current")),
                     "after": _number(row.get("quantity_after")), "unit": unit,
                     "direction": lever.get("direction")},
        "resources": _resources(lever, row, doc["currency"]),
        "cash_equivalent": _number(row.get("cash_equivalent")),
        "efficiency": _efficiency(lever),
        "horizon": {
            "k1_level_delta": None if level_before is None or _number(row.get("level_after_k1")) is None else row["level_after_k1"] - level_before,
            "k6_level_delta": None if level_before is None or level_after is None else level_after - level_before,
            "full_effect_months": 6,
        },
        "next_breakpoint": {"available": breakpoint is not None, "quantity": breakpoint, "unit": unit},
        "source_grid_rel_change": _number(row.get("rel_change")),
        # What-if uses different primitives: no safe exact scenario mapping.
        "scenario_id": None,
    }


def from_sensitivity(doc):
    """Translate one advisor document without rescoring or interpolating.

    Prefer treasury by advisor cash-efficiency ranking, then treasury modeled
    Health impact. If no treasury lever improves Health, surface the strongest
    business sensitivity as such. Only precomputed, positive grid outcomes count.
    """
    if doc.get("method") != METHOD:
        raise ValueError(f"Expected {METHOD}, got {doc.get('method')!r}")
    if doc.get("status") != "sensitivity":
        return unavailable(doc, "unavailable", "advisor_not_scored")
    score = _number((doc.get("baseline") or {}).get("score"))
    if score is None:
        return unavailable(doc, "unavailable", "missing_baseline_score")
    candidates = {}
    for lever in doc.get("levers") or []:
        key = lever.get("lever")
        if key not in LABELS or not lever.get("available"):
            continue
        row = _best_row(lever, score)
        if row is not None:
            candidates[key] = (lever, row)
    if not candidates:
        return unavailable(doc, "no_actionable_lever", "no_positive_precomputed_impact")
    by_cash = (doc.get("ranking") or {}).get("by_cash") or []
    cash_rank = {key: rank for rank, key in enumerate(by_cash)}
    treasury_cash = [key for key in candidates if key in TREASURY and key in cash_rank
                     and _efficiency(candidates[key][0]) is not None]
    if treasury_cash:
        primary_key = min(treasury_cash, key=lambda key: (cash_rank[key], key))
    else:
        treasury = [key for key in candidates if key in TREASURY]
        pool = treasury or list(candidates)
        primary_key = min(pool, key=lambda key: (-(candidates[key][1]["score_after_k6"] - score), key))
    ordered = [primary_key] + sorted((key for key in candidates if key != primary_key),
                                     key=lambda key: (key not in TREASURY, -(candidates[key][1]["score_after_k6"] - score), key))
    actions = [_lever(doc, *candidates[key]) for key in ordered]
    target = _number(doc.get("next_tramo_target"))
    current_level = _number((doc.get("baseline") or {}).get("level"))
    primary_level = actions[0]["level_after"]
    result = unavailable(doc, "available" if primary_key in TREASURY else "business_sensitivity", None)
    result.update(primary=actions[0], alternatives=actions[1:], next_band={
        "current_level": current_level, "target_level": target, "projected_level": primary_level,
        "reachable_with_primary": None if target is None or primary_level is None else primary_level >= target,
    })
    return result
