"""Reconciled monthly cash facts and a score-free Cash Truth projection."""
import math
from typing import Any

import numpy as np
import pandas as pd

from xray.ledger.contracts import CLASSIFICATION_VERSION, FACTS_VERSION, CashTruthResult
from xray.ledger.debt_uncertainty import (
    DEBT_UNCERTAINTY_COLUMNS,
    DEBT_UNCERTAINTY_VERSION,
    assess_debt_uncertainty,
)

KEYS = ["company_id", "currency", "month"]
FLOW_COLUMNS = (
    "operating_inflows", "operating_outflows", "operating_net_cash",
    "debt_principal_paid", "debt_interest_paid", "verified_financing_fees", "debt_service_paid",
    "external_financing_inflows", "external_financing_outflows", "eligible_net_cash",
    "internal_or_group_flows", "investment_flows",
    "uncertain_inflows", "uncertain_outflows", "classified_amount", "uncertain_amount",
    "internal_or_group_inflows", "internal_or_group_outflows",
) + DEBT_UNCERTAINTY_COLUMNS


def _last_month(as_of: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(as_of).normalize()
    if stamp != stamp + pd.offsets.MonthEnd(0):
        stamp = stamp - pd.offsets.MonthEnd(1)
    return stamp.to_period("M").to_timestamp()


def build_monthly_facts(ledger: pd.DataFrame, *, as_of: Any,
                        company_currencies: pd.DataFrame | None = None,
                        start_month: Any = None,
                        observed_months: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return independent facts, never manufacturing activity from a calendar gap.

    ``observed_months`` optionally certifies ingestion observation: unique company,
    currency, month, history_observed rows. It cannot certify the absence of debt.
    Known negative debt service is enough to evidence an observed payment, not a
    complete contractual inventory. Debt adequacy over six months is the scorer's
    responsibility; this module publishes the evidence, not a score.
    """
    last = _last_month(as_of)
    t = ledger.loc[ledger.date.lt(last + pd.offsets.MonthBegin(1))].copy()
    assess_debt_uncertainty(t, copy=False)
    units = t.loc[t.currency.notna(), ["company_id", "currency"]].drop_duplicates()
    if company_currencies is not None:
        units = pd.concat([units, company_currencies[["company_id", "currency"]]], ignore_index=True).drop_duplicates()
    coverage = None
    if observed_months is not None:
        coverage = observed_months[KEYS + ["history_observed"]].copy()
        coverage["month"] = pd.to_datetime(coverage.month).dt.to_period("M").dt.to_timestamp()
        if coverage.duplicated(KEYS).any():
            raise ValueError("observed_months contains duplicate company/currency/month")
        units = pd.concat([units, coverage[["company_id", "currency"]]], ignore_index=True).drop_duplicates()
    units = units.dropna().sort_values(["company_id", "currency"])
    first = pd.Timestamp(start_month).to_period("M").to_timestamp() if start_month is not None else min(
        last - pd.DateOffset(months=5), t.month.min() if len(t) else last)
    if first > last:
        raise ValueError("start_month must not follow as_of")
    grid = units.merge(pd.DataFrame({"month": pd.date_range(first, last, freq="MS")}), how="cross")
    eligible = t.eligible
    pos, neg = t.amount.clip(lower=0), (-t.amount).clip(lower=0)
    cls, sub = t.economic_class, t.economic_subclass
    eligible_abs = t.amount.abs().where(eligible, 0.)
    t["operating_inflows"] = pos.where(t.included_in_operating_inflows, 0.)
    t["operating_outflows"] = neg.where(t.included_in_operating_outflows, 0.)
    t["operating_net_cash"] = t.operating_inflows - t.operating_outflows
    for name, subclass in (("debt_principal_paid", "debt_principal"), ("debt_interest_paid", "debt_interest"),
                           ("verified_financing_fees", "financial_fee")):
        t[name] = neg.where(t.included_in_debt_service & sub.eq(subclass), 0.)
    t["debt_service_paid"] = t.debt_principal_paid + t.debt_interest_paid + t.verified_financing_fees
    t["external_financing_inflows"] = pos.where(eligible & cls.eq("external_financing"), 0.)
    t["external_financing_outflows"] = neg.where(eligible & cls.eq("external_financing"), 0.)
    t["eligible_net_cash"] = t.amount.where(eligible, 0.)
    internal = eligible & cls.isin(["own_account_circulation", "group_or_internal"])
    t["internal_or_group_flows"] = t.amount.where(internal, 0.)
    t["internal_or_group_inflows"] = pos.where(internal, 0.)
    t["internal_or_group_outflows"] = neg.where(internal, 0.)
    t["investment_flows"] = t.amount.where(eligible & cls.eq("investment"), 0.)
    t["uncertain_inflows"] = pos.where(eligible & t.is_uncertain, 0.)
    t["uncertain_outflows"] = neg.where(eligible & t.is_uncertain, 0.)
    for state in ("possible", "impossible", "unresolved"):
        t[f"debt_{state}_uncertain_outflows"] = neg.where(
            t.debt_uncertainty_status.eq(f"debt_{state}"), 0.)
    t["potentially_financial_uncertain_outflows"] = neg.where(
        t.debt_uncertainty_status.isin(("debt_possible", "debt_unresolved")), 0.)
    t["uncertain_amount"] = eligible_abs.where(t.is_uncertain, 0.)
    t["classified_amount"] = eligible_abs.where(~t.is_uncertain, 0.)
    # Pending rows are not cash. Booked quality exclusions remain diagnostics.
    # D32: every known currency is converted to EUR in the ledger, so there is no
    # FX ambiguity left; only rows with unknown currency have no valid amount.
    valid_currency = t.currency.notna()
    excluded = t.status.eq("booked") & ~eligible
    t["excluded_inflows"] = pos.where(excluded & valid_currency, 0.)
    t["excluded_outflows"] = neg.where(excluded & valid_currency, 0.)
    t["excluded_row_count"] = excluded.astype(int)
    t["ambiguous_currency_count"] = 0   # D32; unknown currency is added below as unknown_currency_count
    grouped = t.groupby(KEYS, observed=True)
    amounts = grouped[list(FLOW_COLUMNS) + ["excluded_inflows", "excluded_outflows"]].agg(math.fsum)
    # Financial identities use aggregated components, not a second summation path.
    amounts["operating_net_cash"] = amounts.operating_inflows - amounts.operating_outflows
    amounts["debt_service_paid"] = [math.fsum(values) for values in zip(
        amounts.debt_principal_paid, amounts.debt_interest_paid, amounts.verified_financing_fees)]
    counts = grouped.agg(transaction_count=("amount", "size"), eligible_transaction_count=("eligible", "sum"),
                         excluded_row_count=("excluded_row_count", "sum"),
                         ambiguous_currency_count=("ambiguous_currency_count", "sum"))
    merged = amounts.join(counts).reset_index()
    out = grid.merge(merged, on=KEYS, how="left", validate="one_to_one")
    # Unresolved-currency rows cannot be summed into any monetary unit, but
    # their existence must remain visible on every company/currency view.
    unknown_currency = t.loc[t.currency.isna() & t.status.eq("booked")].groupby(
        ["company_id", "month"], observed=True).size().rename("unknown_currency_count")
    out = out.merge(unknown_currency.reset_index(), on=["company_id", "month"], how="left")
    out["unknown_currency_count"] = out.unknown_currency_count.fillna(0).astype(int)
    for col in counts.columns:
        out[col] = out[col].fillna(0).astype(int)
    for col in ("excluded_inflows", "excluded_outflows"):
        out[col] = out[col].fillna(0.)
    out["history_observed"] = out.eligible_transaction_count.gt(0)
    if coverage is not None:
        out = out.merge(coverage.rename(columns={"history_observed": "explicitly_observed"}), on=KEYS, how="left")
        out["history_observed"] |= out.explicitly_observed.eq(True)
        out = out.drop(columns="explicitly_observed")
    for col in FLOW_COLUMNS:
        out[col] = out[col].fillna(0.).where(out.history_observed)
    total = out.classified_amount + out.uncertain_amount
    out["classification_coverage"] = out.classified_amount / total.where(total.gt(0))
    out["uncertain_amount_share"] = out.uncertain_amount / total.where(total.gt(0))
    active = t.loc[eligible].groupby(KEYS, observed=True).product_id.agg(lambda values: sorted({str(v) for v in values})).rename("active_product_ids")
    out = out.merge(active.reset_index(), on=KEYS, how="left")
    out["active_product_ids"] = [v if isinstance(v, list) else [] for v in out.active_product_ids]
    out["ambiguous_currency_count"] += out.unknown_currency_count
    payment = out.debt_service_paid.gt(0)
    incomplete = out.uncertain_outflows.gt(0) | out.excluded_outflows.gt(0) | out.ambiguous_currency_count.gt(0)
    out["debt_evidence_status"] = np.select([payment & ~incomplete, payment], ["verified", "partial"], default="unknown")
    out["debt_evidence_reason"] = np.select([payment & ~incomplete, payment],
        ["observed_service_identified_no_ambiguous_outflows", "observed_service_with_ambiguous_or_excluded_outflows"],
        default="no_identified_service_not_evidence_of_no_debt")
    out["facts_version"] = FACTS_VERSION
    out["debt_uncertainty_version"] = DEBT_UNCERTAINTY_VERSION
    versions = sorted(set(t.classification_version.dropna()))
    if len(versions) > 1:
        raise ValueError("Ledger must use one classification methodology per run")
    out["classification_version"] = versions[0] if versions else ledger.attrs.get(
        "classification_metadata", {}).get("classification_version", CLASSIFICATION_VERSION)
    validate_monthly_reconciliation(out)
    return out.sort_values(KEYS).reset_index(drop=True)


def validate_monthly_reconciliation(facts: pd.DataFrame) -> None:
    """Reconcile every class, allowing only float representation error.

    Near-zero net flows can be cancellation of tens of millions. An arbitrary
    fixed absolute tolerance or relative tolerance on net cash is unsuitable.
    Each aggregate is correctly rounded via fsum; the check allows one ULP per
    represented operand plus the I−O intermediate subtraction. This is a bound
    on arithmetic representation, NOT an epsilon denominator or materiality rule.
    """
    signed = [("operating_net_cash", 1), ("external_financing_inflows", 1),
              ("external_financing_outflows", -1), ("debt_service_paid", -1),
              ("internal_or_group_flows", 1), ("investment_flows", 1),
              ("uncertain_inflows", 1), ("uncertain_outflows", -1)]
    residuals, bounds = [], []
    for row in facts.itertuples():
        values = [sign * float(getattr(row, name)) for name, sign in signed]
        reference = float(row.eligible_net_cash)
        if not all(math.isfinite(v) for v in values + [reference]):
            residuals.append(float("nan"))
            bounds.append(float("nan"))
            continue
        reconstructed = math.fsum(values)
        residual = reconstructed - reference
        operands = values + [reference, reconstructed, float(row.operating_inflows), float(row.operating_outflows),
                             float(row.debt_principal_paid), float(row.debt_interest_paid), float(row.verified_financing_fees)]
        bound = math.fsum(math.ulp(value) for value in operands)
        if abs(residual) > bound:
            raise ValueError(f"Monthly facts do not reconcile to canonical eligible cash: "
                             f"{row.company_id}/{row.currency}/{row.month}, residual={residual}, roundoff_bound={bound}")
        residuals.append(residual)
        bounds.append(bound)
    facts["cash_reconciliation_residual"] = residuals
    facts["cash_reconciliation_roundoff_bound"] = bounds


def build_cash_truth_result(ledger: pd.DataFrame, facts: pd.DataFrame, *, company_id: str,
                           currency: str, as_of: Any, critical_movements: list[dict] | None = None,
                           detail_ref: str = "ledger.parquet") -> CashTruthResult:
    """Six calendar months of observed facts; no score logic lives in this view."""
    last = _last_month(as_of)
    first = last - pd.DateOffset(months=5)
    tx = ledger.loc[ledger.company_id.eq(company_id) & ledger.currency.eq(currency)
                    & ledger.month.between(first, last)].copy()
    f = facts.loc[facts.company_id.eq(company_id) & facts.currency.eq(currency)
                  & facts.month.between(first, last)]
    c = tx.loc[tx.eligible]
    total = float(c.amount.abs().sum())
    uncertain = float(c.loc[c.is_uncertain, "amount"].abs().sum())
    mappings = {"operating_inflows": "operating_inflows", "operating_outflows": "operating_outflows",
                "net_operating_cash": "operating_net_cash", "external_financing": "external_financing_inflows",
                "external_financing_outflows": "external_financing_outflows",
                "eligible_net_cash": "eligible_net_cash", "debt_service": "debt_service_paid", "investment": "investment_flows",
                "internal_or_group": "internal_or_group_flows", "uncertain": "uncertain_amount"}
    summary = {name: f[col].sum(min_count=1) for name, col in mappings.items()}
    classes = []
    for cls, rows in c.groupby("economic_class", sort=True):
        classes.append({"economic_class": cls, "inflows": float(rows.amount.clip(lower=0).sum()),
                        "outflows": float((-rows.amount).clip(lower=0).sum()),
                        "amount_abs": float(rows.amount.abs().sum()), "transaction_count": len(rows),
                        "detail_ref": detail_ref, "filter": {"economic_class": cls}})
    missing = sorted(set(pd.date_range(first, last, freq="MS")) - set(f.loc[f.history_observed, "month"]))
    flags = ["missing_months"] if missing else []
    if uncertain:
        flags.append("uncertain_classification")
    if (~tx.eligible).any():
        flags.append("excluded_transactions")
    if f.ambiguous_currency_count.gt(0).any():
        flags.append("ambiguous_currency_or_fx")
    return CashTruthResult(
        company_id=company_id, currency=currency, as_of=pd.Timestamp(as_of).date().isoformat(),
        summary=summary, coverage={"classified_amount_share": (total - uncertain) / total if total > 0 else None,
            "uncertain_amount_share": uncertain / total if total > 0 else None, "transaction_count": len(tx),
            "eligible_transaction_count": len(c), "observed_months": int(f.history_observed.sum()),
            "expected_months": 6, "ambiguous_currency_count": int(f.ambiguous_currency_count.sum()),
            "missing_months": [m.date().isoformat() for m in missing]},
        classes=classes, critical_movements=critical_movements or [], flags=flags,
        classification_version=str(f.classification_version.iloc[0]) if len(f) else CLASSIFICATION_VERSION,
        evidence={"detail_ref": detail_ref, "filter": {"company_id": company_id, "currency": currency},
            "window_start": first.date().isoformat(), "window_end": (last + pd.offsets.MonthEnd(0)).date().isoformat(),
            "lineage_key": "transaction_id", "scope": "observed_cash_not_certified_total_bank_universe",
            "debt_semantics": "observed_service_not_contractual_inventory"})
