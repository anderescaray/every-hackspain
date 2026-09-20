"""Scenario-local FX translation sensitivity through the existing transaction builder.

This is a retrospective constant-multiplier counterfactual on observed source
currency flows, NOT a historical exchange-rate series or a forecast. It never
changes the global fixed-FX policy or the frozen V2 reference.
"""

from __future__ import annotations

import math

import pandas as pd

from xray.features.config import FeatureConfig
from xray.features.transactions import prepare_transactions, transaction_features
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.signals import month_quality

V2_TRANSACTION_FIELDS = (
    "tx_inflow", "tx_outflow", "debt_principal_paid", "debt_interest_paid",
    "tx_lfl_inflow_growth", "tx_operating_amount_share",
)
RECONCILIATION_TOLERANCE = 1e-6


class FXStressUnavailable(ValueError):
    """Evidence is insufficient to rerun the FX counterfactual faithfully."""


def _same(a, b, tolerance=RECONCILIATION_TOLERANCE):
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=tolerance)


def _transaction_panel(raw, companies, banking_products, debt_products,
                       config, company_id, months):
    tables = {"transactions": raw, "companies": companies,
              "banking_products": banking_products, "debt_products": debt_products}
    prepared = prepare_transactions(tables, config)
    skeleton = pd.DataFrame({"company_id": [company_id] * len(months),
                             "currency": ["EUR"] * len(months), "month": months})
    return transaction_features(prepared, skeleton, "company_id").set_index("month")


def apply_source_currency_shock(frame: pd.DataFrame, raw_transactions: pd.DataFrame,
                                companies: pd.DataFrame, banking_products: pd.DataFrame,
                                debt_products: pd.DataFrame, config: FeatureConfig,
                                *, source_currency: str, relative_pct: float,
                                window_months: pd.DatetimeIndex,
                                score_config: ScoreV2Config | None = None) -> tuple[pd.DataFrame, dict]:
    """Rerun transaction features for one currency and project V2-consumed fields.

    `raw_transactions` must include the month immediately preceding the shocked
    window. The caller passes one company and a contiguous window ending at the
    scored month. Baseline amounts, LFL growth, and quality input are reconciled
    against the published feature panel before any scenario is returned.
    """
    if not isinstance(config, FeatureConfig):
        raise TypeError("FX stress requires the published FeatureConfig")
    if not isinstance(source_currency, str) or len(source_currency) != 3 or source_currency == "EUR":
        raise ValueError("FX stress requires one non-EUR source currency")
    if not math.isfinite(relative_pct) or not -100 < relative_pct <= 100 or relative_pct == 0:
        raise ValueError("FX stress multiplier must be nonzero and keep positive currency value")
    months = pd.DatetimeIndex(pd.to_datetime(window_months)).sort_values().unique()
    if len(months) not in (1, 3, 6) or not months.equals(pd.date_range(months[0], periods=len(months), freq="MS")):
        raise ValueError("FX stress window must be contiguous 1/3/6 complete observed months")
    f = frame.copy()
    if f.empty or f.company_id.nunique() != 1:
        raise ValueError("FX stress frame must contain exactly one company")
    company_id = str(f.company_id.iloc[0])
    f["month"] = pd.to_datetime(f.month)
    cutoff = f.month.max()
    if months[-1] != cutoff:
        raise ValueError("FX stress window must end at the scored month")
    previous = months[0] - pd.offsets.MonthBegin(1)
    all_months = pd.date_range(previous, cutoff, freq="MS")
    raw = raw_transactions.loc[raw_transactions.company_id.eq(company_id)].copy()
    raw["date"] = pd.to_datetime(raw.date)
    raw = raw.loc[raw.date.ge(previous) & raw.date.lt(cutoff + pd.offsets.MonthBegin(1))]
    if raw.empty or not raw.date.dt.to_period("M").eq(previous.to_period("M")).any():
        raise FXStressUnavailable("missing_predecessor_month_transactions")
    if "product_currency" not in raw:
        raise FXStressUnavailable("missing_source_currency")
    affected = raw.product_currency.eq(source_currency) & raw.date.dt.to_period("M").dt.to_timestamp().isin(months)
    if not affected.any():
        raise FXStressUnavailable("no_source_currency_movements_in_window")
    baseline = _transaction_panel(raw, companies, banking_products, debt_products,
                                  config, company_id, all_months)
    panel = f.set_index("month")
    for month in months:
        if month not in panel.index or month not in baseline.index:
            raise FXStressUnavailable("missing_feature_month")
        for field in V2_TRANSACTION_FIELDS:
            published, rebuilt = panel.at[month, field], baseline.at[month, field]
            # D33/onboarding may deliberately mask a rebuilt numeric field.
            if pd.notna(published) and not _same(published, rebuilt):
                raise FXStressUnavailable(f"baseline_{field}_does_not_reconcile:{month:%Y-%m}")
        if pd.notna(panel.at[month, "tx_operating_margin"]):
            inflow, outflow = baseline.at[month, "tx_inflow"], baseline.at[month, "tx_outflow"]
            denominator = inflow + outflow
            rebuilt_margin = (inflow - outflow) / denominator if denominator > 0 else float("nan")
            if not _same(panel.at[month, "tx_operating_margin"], rebuilt_margin):
                raise FXStressUnavailable(f"baseline_tx_operating_margin_does_not_reconcile:{month:%Y-%m}")
    changed = raw.copy()
    changed["amount"] = pd.to_numeric(changed.amount, errors="raise").astype(float)
    changed.loc[affected, "amount"] = changed.loc[affected, "amount"] * (1 + relative_pct / 100)
    rerun = _transaction_panel(changed, companies, banking_products, debt_products,
                               config, company_id, all_months)
    replaced = []
    for month in months:
        if month not in f.month.values:
            raise FXStressUnavailable("missing_feature_month")
        index = f.index[f.month.eq(month)][0]
        for field in V2_TRANSACTION_FIELDS:
            if pd.notna(f.at[index, field]):
                f.at[index, field] = rerun.at[month, field]
        if pd.notna(f.at[index, "tx_operating_margin"]):
            inflow, outflow = f.at[index, "tx_inflow"], f.at[index, "tx_outflow"]
            denominator = inflow + outflow
            f.at[index, "tx_operating_margin"] = (inflow - outflow) / denominator if denominator > 0 else float("nan")
        replaced.append(month.strftime("%Y-%m"))
    quality_config = score_config or ScoreV2Config()
    before_quality = month_quality(frame.loc[frame.month.isin(months)], quality_config).tolist()
    after_quality = month_quality(f.loc[f.month.isin(months)], quality_config).tolist()
    if before_quality != after_quality:
        raise FXStressUnavailable("quality_gate_changed_by_fx_translation")
    return f, {"source_currency": source_currency, "relative_pct": relative_pct,
               "affected_months": replaced, "source_transaction_count": int(affected.sum()),
               "method": "same_transaction_feature_builder_frozen_v2_reference",
               "interpretation": "retrospective_constant_fx_translation_sensitivity_not_forecast"}
