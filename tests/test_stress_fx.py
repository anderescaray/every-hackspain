"""Scenario-local FX reaggregation must use the existing transaction feature builder."""

import pandas as pd
import pytest

from xray.features.config import FeatureConfig
from xray.features.transactions import prepare_transactions, transaction_features
from xray.stress.fx import FXStressUnavailable, apply_source_currency_shock


def _sources():
    records = []
    for month in ("2026-07", "2026-08"):
        for index, (product, amount, category, currency) in enumerate([
            ("USD_ACCOUNT", 100, "collection", "USD"),
            ("EUR_ACCOUNT", 100, "collection", "EUR"),
            ("EUR_ACCOUNT", -50, "payment", "EUR"),
            ("EUR_ACCOUNT", -20, "salary", "EUR"),
            ("EUR_ACCOUNT", -10, "utility", "EUR"),
            ("EUR_ACCOUNT", -5, "tax", "EUR"),
        ]):
            records.append({"transaction_id": f"{month}-{index}", "company_id": "C", "product_id": product,
                            "date": f"{month}-15", "amount": amount, "category": category,
                            "product_currency": currency, "status": "booked", "exchange_rate": 1.0,
                            "description": category, "counterparty_id": None})
    raw = pd.DataFrame(records)
    companies = pd.DataFrame({"company_id": ["C"], "group_id": ["G"]})
    banking = pd.DataFrame({"product_id": ["USD_ACCOUNT", "EUR_ACCOUNT"], "company_id": ["C", "C"],
                            "created_at": ["2025-01-01", "2025-01-01"]})
    debt = pd.DataFrame(columns=["product_id", "company_id", "created_at"])
    config = FeatureConfig(start_month="2026-07-01", end_month="2026-08-01", extraction_date="2026-09-01")
    prepared = prepare_transactions({"transactions": raw, "companies": companies,
                                     "banking_products": banking, "debt_products": debt}, config)
    months = pd.date_range("2026-07-01", periods=2, freq="MS")
    skeleton = pd.DataFrame({"company_id": ["C"] * 2, "currency": ["EUR"] * 2, "month": months})
    panel = transaction_features(prepared, skeleton, "company_id")
    panel["tx_operating_margin"] = ((panel.tx_inflow - panel.tx_outflow) /
                                     (panel.tx_inflow + panel.tx_outflow))
    raw["date"] = pd.to_datetime(raw.date)
    return panel, raw, companies, banking, debt, config


def _run(panel, raw, companies, banking, debt, config):
    return apply_source_currency_shock(panel, raw, companies, banking, debt, config,
                                       source_currency="USD", relative_pct=10,
                                       window_months=pd.DatetimeIndex([pd.Timestamp("2026-08-01")]))


def test_fx_reaggregates_through_same_builder_and_preserves_other_months():
    panel, raw, companies, banking, debt, config = _sources()
    changed, evidence = _run(panel, raw, companies, banking, debt, config)
    july = panel.loc[panel.month.eq("2026-07-01")].iloc[0]
    aug = panel.loc[panel.month.eq("2026-08-01")].iloc[0]
    stressed_aug = changed.loc[changed.month.eq("2026-08-01")].iloc[0]
    assert changed.loc[changed.month.eq("2026-07-01"), "tx_inflow"].iloc[0] == july.tx_inflow
    assert stressed_aug.tx_inflow > aug.tx_inflow
    assert stressed_aug.tx_outflow == aug.tx_outflow
    assert stressed_aug.tx_lfl_inflow_growth > aug.tx_lfl_inflow_growth
    assert stressed_aug.tx_operating_margin > aug.tx_operating_margin
    assert evidence["source_transaction_count"] == 1
    assert evidence["affected_months"] == ["2026-08"]


def test_fx_refuses_missing_predecessor_or_baseline_mismatch():
    panel, raw, companies, banking, debt, config = _sources()
    with pytest.raises(FXStressUnavailable, match="missing_predecessor"):
        _run(panel, raw.loc[raw.date.dt.month.eq(8)], companies, banking, debt, config)
    bad = panel.copy()
    bad.loc[bad.month.eq("2026-08-01"), "tx_inflow"] += 1
    with pytest.raises(FXStressUnavailable, match="baseline_tx_inflow"):
        _run(bad, raw, companies, banking, debt, config)
