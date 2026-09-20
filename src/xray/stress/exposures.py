"""Cutoff-safe evidence for V2 stress scenarios; no scenario or score arithmetic.

Amounts in the canonical ledger are already EUR. Invoice source amounts are
converted with the same fixed FX table as ``xray.features.invoices``. The
returned gates deliberately distinguish observed zero from missing evidence.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from xray.features.invoices import FILLER_EXACT_SHARE, FILLER_MIN_PAID
from xray.fx import to_eur
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.signals import month_quality

FIXED_SUBCLASSES = frozenset({"salary", "social_security", "tax", "utility"})
DEBT_SUBCLASSES = frozenset({"debt_principal", "debt_interest", "financial_fee"})
OPERATING_PAYMENT_SUBCLASSES = frozenset({"salary", "social_security", "tax", "utility",
                                          "payment_processing_fee", "operating_payment", "operating_refund_paid"})
STRESS_COST_CATEGORIES = frozenset({"payroll", "utilities", "payment_processing", "other_operating_payment"})
CATEGORY_SUBCLASSES = {
    "payroll": frozenset({"salary", "social_security"}), "utilities": frozenset({"utility"}),
    "payment_processing": frozenset({"payment_processing_fee"}),
    "other_operating_payment": frozenset({"operating_payment"}),
}
# Scenario pruning only, not V2 score methodology. Both gates must hold.
MIN_COST_STRESS_EUR = 100.0
MIN_COST_STRESS_SHARE = 0.01
RECONCILIATION_TOLERANCE_EUR = 0.01


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) and abs(result) != float("inf") else None


def _sum_or_none(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce")
    return float(numeric.sum()) if numeric.notna().any() else None


def _paid_amount(values: pd.Series) -> float:
    """Turn negative booked payments into positive magnitudes without signed zero."""
    return float((-values).clip(lower=0).sum())


def _company(frame: pd.DataFrame | None, company_id: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    if "company_id" not in frame:
        raise ValueError("Exposure source lacks company_id")
    return frame.loc[frame.company_id.eq(company_id)].copy()


def _window(as_of: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    end = pd.Timestamp(as_of).normalize()
    if end != end + pd.offsets.MonthEnd(0):
        raise ValueError("Stress exposures require a complete calendar month as_of")
    first = end.to_period("M").to_timestamp() - pd.DateOffset(months=5)
    next_month = end + pd.Timedelta(days=1)
    return first, end, next_month


def _operating(features: pd.DataFrame, first: pd.Timestamp, next_month: pd.Timestamp,
               config: ScoreV2Config) -> dict[str, Any]:
    if features.empty or "month" not in features:
        return {"status": "unavailable", "reason": "missing_feature_panel", "inflows_6m": None,
                "outflows_6m": None, "net_6m": None, "months_observed": [], "quality_months": []}
    f = features.copy()
    f["month"] = pd.to_datetime(f.month)
    f = f.loc[f.month.ge(first) & f.month.lt(next_month)].sort_values("month")
    if f.month.duplicated().any():
        raise ValueError("Duplicate company-month in feature panel")
    observed = f.loc[f.tx_count.fillna(0).gt(0), "month"].dt.strftime("%Y-%m").tolist()
    quality = month_quality(f, config) if not f.empty else pd.Series(dtype=bool)
    usable = f.loc[quality & f.tx_inflow.notna() & f.tx_outflow.notna()]
    quality_months = usable.month.dt.strftime("%Y-%m").tolist()
    inflows, outflows = _sum_or_none(usable.tx_inflow), _sum_or_none(usable.tx_outflow)
    status = "available" if len(quality_months) >= config.level_min_months else "unavailable"
    reason = None if status == "available" else "insufficient_quality_months"
    return {"status": status, "reason": reason, "inflows_6m": inflows,
            "outflows_6m": outflows, "net_6m": None if inflows is None or outflows is None else inflows - outflows,
            "months_observed": observed, "quality_months": quality_months,
            "required_quality_months": config.level_min_months}


def _monthly_operating(ledger: pd.DataFrame, features: pd.DataFrame,
                       first: pd.Timestamp, end: pd.Timestamp,
                       quality_months: list[str]) -> dict[str, Any]:
    """Reconcile exact monthly canonical flows to the V2 feature panel."""
    quality = set(quality_months)
    months = pd.date_range(first, end.to_period("M").to_timestamp(), freq="MS").strftime("%Y-%m")
    op = ledger.loc[ledger.included_in_operating_inflows.fillna(False) |
                    ledger.included_in_operating_outflows.fillna(False)].copy()
    op["month_key"] = op.date.dt.strftime("%Y-%m")
    panel = features.copy()
    if not panel.empty:
        panel["month_key"] = pd.to_datetime(panel.month).dt.strftime("%Y-%m")
        panel = panel.set_index("month_key")
    by_subclass, by_category, by_currency, diffs = {}, {}, {}, {}
    for month in months:
        rows = op.loc[op.month_key.eq(month)]
        if rows.empty:
            by_subclass[month], by_category[month], by_currency[month] = None, None, None
        else:
            outgoing = rows.loc[rows.included_in_operating_outflows.fillna(False)]
            sub = {name: _paid_amount(outgoing.loc[outgoing.economic_subclass.eq(name), "amount"])
                   for name in sorted(OPERATING_PAYMENT_SUBCLASSES)}
            by_subclass[month] = sub
            by_category[month] = {
                "payroll": sub["salary"] + sub["social_security"], "utilities": sub["utility"],
                "payment_processing": sub["payment_processing_fee"],
                "other_operating_payment": sub["operating_payment"], "taxes": sub["tax"],
                "operating_refunds": sub["operating_refund_paid"],
            }
            currency = {}
            for source, group in rows.groupby(rows.source_currency.fillna("UNKNOWN"), dropna=False):
                currency[str(source)] = {
                    "inflows": float(group.loc[group.included_in_operating_inflows.fillna(False), "amount"].clip(lower=0).sum()),
                    "outflows": _paid_amount(group.loc[group.included_in_operating_outflows.fillna(False), "amount"]),
                }
            by_currency[month] = currency
        if month not in quality:
            continue
        if rows.empty or panel.empty or month not in panel.index:
            diffs[month] = {"status": "missing", "inflow_delta": None, "outflow_delta": None}
            continue
        expected = panel.loc[month]
        actual_in = float(rows.loc[rows.included_in_operating_inflows.fillna(False), "amount"].clip(lower=0).sum())
        actual_out = _paid_amount(rows.loc[rows.included_in_operating_outflows.fillna(False), "amount"])
        expected_in, expected_out = _number(expected.tx_inflow), _number(expected.tx_outflow)
        if expected_in is None or expected_out is None:
            diffs[month] = {"status": "missing", "inflow_delta": None, "outflow_delta": None}
            continue
        inflow_delta, outflow_delta = actual_in - expected_in, actual_out - expected_out
        mapped = set(rows.loc[rows.included_in_operating_outflows.fillna(False), "economic_subclass"].dropna())
        unmapped = sorted(mapped - OPERATING_PAYMENT_SUBCLASSES)
        matched = (abs(inflow_delta) <= RECONCILIATION_TOLERANCE_EUR and
                   abs(outflow_delta) <= RECONCILIATION_TOLERANCE_EUR and not unmapped)
        diffs[month] = {"status": "matched" if matched else "mismatch",
                        "inflow_delta": inflow_delta, "outflow_delta": outflow_delta,
                        "unmapped_outflow_subclasses": unmapped}
    reconciled = bool(quality) and all(diffs.get(month, {}).get("status") == "matched" for month in quality)
    return {"monthly_by_subclass": by_subclass, "monthly_by_category": by_category,
            "monthly_by_currency": by_currency,
            "reconciliation": {"status": "matched" if reconciled else "unavailable",
                               "reason": None if reconciled else "ledger_v2_monthly_mismatch_or_missing",
                               "quality_months": sorted(quality), "monthly": diffs,
                               "tolerance_eur": RECONCILIATION_TOLERANCE_EUR}}


def _ledger_components(ledger: pd.DataFrame, features: pd.DataFrame,
                       first: pd.Timestamp, end: pd.Timestamp,
                       quality_months: list[str]) -> tuple[dict, dict, dict, dict]:
    unavailable_costs = {"status": "unavailable", "reason": "missing_canonical_ledger", "by_subclass": {},
                         "monthly_by_subclass": {}, "monthly_by_category": {}, "category_gates": {},
                         "reconciliation": {"status": "unavailable", "reason": "missing_canonical_ledger"},
                         "score_runnable": False}
    unavailable_debt = {"status": "unavailable", "reason": "missing_canonical_ledger", "principal_6m": None,
                        "interest_6m": None, "verified_financing_fees_6m": None, "total_6m": None,
                        "v2_service_6m": None}
    unavailable_fx = {"status": "unavailable", "reason": "missing_canonical_ledger", "non_eur_share": None,
                      "source_currency_amounts": {}, "monthly_by_currency": {}, "score_runnable": False}
    unavailable_group = {"status": "unavailable", "reason": "missing_canonical_ledger",
                         "candidate_in_6m": None, "candidate_out_6m": None, "score_runnable": False}
    if ledger.empty:
        return unavailable_costs, unavailable_debt, unavailable_fx, unavailable_group
    required = {"date", "amount", "economic_class", "economic_subclass", "eligible",
                "included_in_operating_inflows", "included_in_operating_outflows",
                "included_in_debt_service", "source_currency"}
    if missing := required - set(ledger):
        raise ValueError(f"Canonical ledger lacks columns: {sorted(missing)}")
    x = ledger.copy()
    x["date"] = pd.to_datetime(x.date)
    x = x.loc[x.date.ge(first) & x.date.le(end) & x.eligible.fillna(False)]
    x["amount"] = pd.to_numeric(x.amount, errors="coerce")
    x = x.loc[x.amount.notna()]
    if x.empty:
        for component in (unavailable_costs, unavailable_debt, unavailable_fx, unavailable_group):
            component["reason"] = "no_eligible_ledger_rows_in_window"
        unavailable_costs["reconciliation"]["reason"] = "no_eligible_ledger_rows_in_window"
        return unavailable_costs, unavailable_debt, unavailable_fx, unavailable_group
    costs = x.loc[x.included_in_operating_outflows.fillna(False) & x.economic_subclass.isin(FIXED_SUBCLASSES)]
    by_subclass = {subclass: _paid_amount(costs.loc[costs.economic_subclass.eq(subclass), "amount"])
                   for subclass in sorted(FIXED_SUBCLASSES)}
    # A generic operating_payment is not an identified discretionary category.
    monthly = _monthly_operating(x, features, first, end, quality_months)
    reconciled = monthly["reconciliation"]["status"] == "matched"
    quality_outflow = _sum_or_none(features.loc[pd.to_datetime(features.month).dt.strftime("%Y-%m")
                                                 .isin(quality_months), "tx_outflow"]) if not features.empty else None
    category_gates = {}
    for category in sorted(STRESS_COST_CATEGORIES):
        amount = sum((parts or {}).get(category, 0.0) for month, parts in monthly["monthly_by_category"].items()
                     if month in quality_months)
        share = amount / quality_outflow if quality_outflow is not None and quality_outflow > 0 else None
        material = amount >= MIN_COST_STRESS_EUR and share is not None and share >= MIN_COST_STRESS_SHARE
        evidence_rows = x.loc[x.date.dt.strftime("%Y-%m").isin(quality_months) &
                              x.included_in_operating_outflows.fillna(False) &
                              x.economic_subclass.isin(CATEGORY_SUBCLASSES[category]) & x.amount.lt(0)]
        high_confidence = ("classification_confidence" in evidence_rows and not evidence_rows.empty and
                           evidence_rows.classification_confidence.eq("high").all())
        # Classified operating_payment is a broad sensitivity, never a promised saving.
        if not reconciled:
            reason = "ledger_v2_monthly_mismatch_or_missing"
        elif not high_confidence:
            reason = "classification_confidence_unavailable_or_low"
        elif not material:
            reason = "category_not_material"
        else:
            reason = None
        category_gates[category] = {"status": "available" if reason is None else "unavailable",
                                    "reason": reason, "amount_6m": amount if reconciled else None,
                                    "share_of_outflow": share if reconciled else None,
                                    "score_runnable": reason is None}
    cost_result = {"status": "available" if costs.shape[0] else "unavailable",
                   "reason": None if costs.shape[0] else "no_identified_fixed_costs",
                   "by_subclass": by_subclass if costs.shape[0] else {},
                   "monthly_by_subclass": monthly["monthly_by_subclass"],
                   "monthly_by_category": monthly["monthly_by_category"],
                   "category_gates": category_gates,
                   "reconciliation": monthly["reconciliation"],
                   "score_runnable": any(gate["score_runnable"] for gate in category_gates.values()),
                   "materiality_gate": {"min_amount_eur": MIN_COST_STRESS_EUR,
                                        "min_share_of_quality_outflow": MIN_COST_STRESS_SHARE},
                   "unclassified_discretionary_cost": None}
    service_rows = x.loc[x.included_in_debt_service.fillna(False)]
    principal = _paid_amount(service_rows.loc[service_rows.economic_subclass.eq("debt_principal"), "amount"])
    interest = _paid_amount(service_rows.loc[service_rows.economic_subclass.eq("debt_interest"), "amount"])
    fees = _paid_amount(service_rows.loc[service_rows.economic_subclass.eq("financial_fee"), "amount"])
    service = principal + interest
    v2_rows = service_rows.loc[service_rows.date.dt.strftime("%Y-%m").isin(quality_months)]
    v2_service = (_paid_amount(v2_rows.loc[v2_rows.economic_subclass.eq("debt_principal"), "amount"])
                  + _paid_amount(v2_rows.loc[v2_rows.economic_subclass.eq("debt_interest"), "amount"]))
    debt = {"status": "available" if v2_service > 0 else "unavailable",
            "reason": None if v2_service > 0 else "no_identified_v2_service_in_quality_months",
            "principal_6m": principal, "interest_6m": interest,
            "verified_financing_fees_6m": fees, "total_6m": service + fees,
            "v2_service_6m": v2_service,
            "method_note": "V2 score uses principal + interest from quality months only; fees are context."}
    operating = x.loc[x.included_in_operating_inflows.fillna(False) |
                      x.included_in_operating_outflows.fillna(False)]
    source = operating.source_currency.fillna("UNKNOWN")
    amounts = defaultdict(float)
    for currency, amount in zip(source, operating.amount.abs()):
        amounts[str(currency)] += float(amount)
    denominator = sum(amounts.values())
    non_eur = sum(value for currency, value in amounts.items() if currency != "EUR")
    fx = {"status": "context_only" if denominator > 0 else "unavailable",
          "reason": "fixed_fx_rates_no_historical_path" if denominator > 0 else "no_operating_fx_evidence",
          "non_eur_share": non_eur / denominator if denominator > 0 else None,
          "source_currency_amounts": dict(sorted(amounts.items())), "score_runnable": False,
          "monthly_by_currency": monthly["monthly_by_currency"],
          "reconciliation_status": monthly["reconciliation"]["status"],
          "basis": "absolute_canonical_operating_amount_eur"}
    group = x.loc[x.economic_class.eq("group_or_internal")]
    group_result = {"status": "context_only" if not group.empty else "unavailable",
                    "reason": "group_candidate_not_verified_fungible" if not group.empty else "no_group_transfer_candidate",
                    "candidate_in_6m": float(group.loc[group.amount.gt(0), "amount"].sum()),
                    "candidate_out_6m": _paid_amount(group.loc[group.amount.lt(0), "amount"]),
                    "score_runnable": False}
    return cost_result, debt, fx, group_result


def _collections(invoices: pd.DataFrame, current: pd.Series | None,
                 first: pd.Timestamp, end: pd.Timestamp) -> dict[str, Any]:
    base = {"status": "unavailable", "reason": "missing_invoice_evidence", "score_runnable": False,
            "largest_customer_id": None, "largest_customer_share": None,
            "eligible_paid_count": None, "delay_median_days": None}
    if invoices.empty or current is None:
        return base
    required = {"issuance_date", "payment_date", "due_date", "direction", "document_type",
                "is_possible_duplicate", "counterparty_id", "amount", "currency"}
    if missing := required - set(invoices):
        raise ValueError(f"Invoice source lacks columns: {sorted(missing)}")
    i = invoices.copy()
    for column in ("issuance_date", "payment_date", "due_date"):
        i[column] = pd.to_datetime(i[column])
    i = i.loc[i.direction.eq("AR") & i.document_type.eq("invoice") &
              ~i.is_possible_duplicate.fillna(True) & i.issuance_date.le(end) &
              i.counterparty_id.notna()].copy()
    if i.empty:
        base["reason"] = "no_valid_ar_invoices"
        return base
    i["absolute_eur"] = to_eur(pd.to_numeric(i.amount, errors="coerce").abs(), i.currency)
    issued = i.loc[i.issuance_date.ge(first) & i.absolute_eur.notna()]
    totals = issued.groupby("counterparty_id").absolute_eur.sum()
    if totals.empty or totals.sum() <= 0:
        base["reason"] = "no_ar_issuance_in_window"
        return base
    top = min(totals.items(), key=lambda item: (-item[1], str(item[0])))
    base["largest_customer_id"] = str(top[0])
    base["largest_customer_share"] = float(top[1] / totals.sum())
    if bool(current.get("inv_ar_payment_date_filler", False)):
        base["reason"] = "payment_date_filler_d39"
        return base
    if _number(current.get("inv_ar_delay_median")) is None:
        base["reason"] = "missing_valid_ar_delay"
        return base
    valid = i.loc[i.counterparty_id.eq(top[0]) & i.payment_date.notna() &
                  i.payment_date.le(end) & i.due_date.notna() &
                  i.payment_date.ge(i.issuance_date)].copy()
    for flag in ("has_anomalous_term", "is_future_payment", "is_payment_before_issuance"):
        if flag in valid:
            valid = valid.loc[~valid[flag].fillna(True)]
    base["eligible_paid_count"] = len(valid)
    if len(valid) < 5:
        base["reason"] = "top_customer_paid_history_lt_5"
        return base
    # Double-check D39 on the exact observed invoice history, never future payments.
    all_valid = i.loc[i.payment_date.notna() & i.payment_date.le(end) & i.due_date.notna()]
    exact_share = all_valid.payment_date.dt.normalize().eq(all_valid.due_date.dt.normalize()).mean()
    if len(all_valid) >= FILLER_MIN_PAID and exact_share >= FILLER_EXACT_SHARE:
        base["reason"] = "payment_date_filler_d39"
        return base
    delay = (valid.payment_date - valid.due_date).dt.days.clip(-60, 365)
    base.update(status="available", reason=None, score_runnable=True,
                delay_median_days=float(delay.median()))
    return base


def _variable_rate(schedule: pd.DataFrame | None, end: pd.Timestamp,
                   snapshot_as_of: pd.Timestamp | None) -> dict[str, Any]:
    base = {"status": "unavailable", "reason": "missing_debt_schedule",
            "score_runnable": False, "fresh_variable_products": 0, "outstanding_eur": None}
    if schedule is None or schedule.empty:
        return base
    # Extraction vintage may land a few days after month-end; reject stale photos.
    snapshot = None if snapshot_as_of is None else pd.Timestamp(snapshot_as_of).normalize()
    if snapshot is None or snapshot > end + pd.Timedelta(days=7):
        base["reason"] = "schedule_snapshot_after_as_of"
        return base
    required = {"interest_type", "next_payment_date", "outstanding_balance", "annual_interest_rate_or_spread"}
    if missing := required - set(schedule):
        raise ValueError(f"Debt schedule lacks columns: {sorted(missing)}")
    x = schedule.copy()
    x["next_payment_date"] = pd.to_datetime(x.next_payment_date)
    x["outstanding_balance"] = pd.to_numeric(x.outstanding_balance, errors="coerce")
    x["annual_interest_rate_or_spread"] = pd.to_numeric(x.annual_interest_rate_or_spread, errors="coerce")
    # next_payment_date must still be in the future relative to as_of; do not revive lapsed products.
    valid = x.interest_type.astype(str).str.lower().eq("variable") & x.next_payment_date.gt(end) & \
        x.outstanding_balance.gt(0) & x.annual_interest_rate_or_spread.notna()
    if "currency" in x:
        valid &= x.currency.eq("EUR")
    outstanding = float(x.loc[valid, "outstanding_balance"].sum()) if valid.any() else 0.0
    base["fresh_variable_products"] = int(valid.sum())
    base["outstanding_eur"] = outstanding if outstanding > 0 else None
    if outstanding > 0:
        base.update(status="available", reason=None, score_runnable=True)
    else:
        base["reason"] = "no_fresh_variable_schedule"
    return base


def build_company_exposures(company_id: str, as_of: pd.Timestamp, features: pd.DataFrame,
                            ledger: pd.DataFrame, invoices: pd.DataFrame,
                            debt_schedule: pd.DataFrame | None = None,
                            *, config: ScoreV2Config | None = None,
                            schedule_snapshot_as_of: pd.Timestamp | None = None) -> dict[str, Any]:
    """Return observed evidence/gates for one company at a completed-month cutoff.

    Sources may be pre-grouped by company by the caller; this function filters again
    for safety. `schedule_snapshot_as_of` is mandatory before rate context is usable.
    """
    first, end, next_month = _window(pd.Timestamp(as_of))
    cfg = config or ScoreV2Config()
    f = _company(features, company_id)
    ledger_company = _company(ledger, company_id)
    invoice_company = _company(invoices, company_id)
    schedule_company = _company(debt_schedule, company_id)
    operating = _operating(f, first, next_month, cfg)
    costs, debt, fx, group = _ledger_components(ledger_company, f, first, end, operating["quality_months"])
    current = None
    if not f.empty and "month" in f:
        latest = f.loc[pd.to_datetime(f.month).eq(end.to_period("M").to_timestamp())]
        if len(latest) > 1:
            raise ValueError("Duplicate company-month in feature panel")
        if not latest.empty:
            current = latest.iloc[0]
    collections = _collections(invoice_company, current, first, end)
    rate = _variable_rate(schedule_company, end, schedule_snapshot_as_of)
    classification_versions = (ledger_company.classification_version.dropna().unique().tolist()
                               if "classification_version" in ledger_company else [])
    if len(classification_versions) > 1:
        raise ValueError("Mixed classification versions in stress ledger")
    return {"company_id": company_id, "as_of": end.strftime("%Y-%m-%d"),
            "window_start": first.strftime("%Y-%m-%d"), "window_end": end.strftime("%Y-%m-%d"),
            "operating": operating, "costs": costs, "debt_service": debt,
            "collections": collections, "fx": fx, "variable_rate": rate,
            "group_support": group,
            "source_versions": {"score_method": "financial_smoothed_v2",
                                "classification_method": classification_versions[0] if classification_versions else None}}
