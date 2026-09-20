"""Focused cutoff and evidence-gate tests for stress exposure extraction."""

import pandas as pd
import pytest

from xray.stress.exposures import build_company_exposures

AS_OF = pd.Timestamp("2026-08-31")


def _features(*, filler=False, delay=4.0):
    months = pd.date_range("2026-03-01", periods=6, freq="MS")
    return pd.DataFrame({
        "company_id": ["C"] * 6, "month": months, "tx_count": [20] * 6,
        "tx_usable_count": [20] * 6, "tx_usable_row_share": [1.0] * 6,
        "tx_operating_amount_share": [0.8] * 6, "tx_company_coverage": [1.0] * 6,
        "tx_inflow": [100.0] * 6, "tx_outflow": [80.0] * 6,
        "inv_ar_payment_date_filler": [False] * 5 + [filler],
        "inv_ar_delay_median": [delay] * 6,
    })


def _ledger():
    rows = [
        ("2026-04-10", -20.0, "operating", "salary", False, True, "EUR"),
        ("2026-04-11", -12.0, "debt_service", "debt_principal", False, False, "EUR"),
        ("2026-04-12", -3.0, "debt_service", "debt_interest", False, False, "EUR"),
        ("2026-04-13", -2.0, "debt_service", "financial_fee", False, False, "EUR"),
        ("2026-04-14", 40.0, "operating", "operating_collection", True, False, "USD"),
        ("2026-04-15", 9.0, "group_or_internal", "group_transfer_candidate", False, False, "EUR"),
        # Future entries must not leak into as_of exposures.
        ("2026-09-01", -1000.0, "debt_service", "debt_principal", False, False, "EUR"),
    ]
    return pd.DataFrame(rows, columns=["date", "amount", "economic_class", "economic_subclass",
                                       "included_in_operating_inflows", "included_in_operating_outflows",
                                       "source_currency"]).assign(
        company_id="C", eligible=True, classification_confidence="high",
        included_in_debt_service=lambda frame: frame.economic_class.eq("debt_service"))


def _invoices():
    rows = []
    for day in range(1, 7):
        rows.append((f"2026-05-{day:02d}", f"2026-05-{day+10:02d}", f"2026-05-{day+12:02d}",
                     "CUSTOMER_A", 100.0))
    rows.append(("2026-06-01", "2026-06-11", "2026-06-13", "CUSTOMER_B", 10.0))
    rows.append(("2026-08-01", "2026-09-01", "2026-09-02", "CUSTOMER_A", 1000.0))
    return pd.DataFrame(rows, columns=["issuance_date", "due_date", "payment_date", "counterparty_id", "amount"]).assign(
        company_id="C", direction="AR", document_type="invoice", is_possible_duplicate=False, currency="EUR")


def _extract(**kwargs):
    return build_company_exposures("C", AS_OF, kwargs.pop("features", _features()),
                                   kwargs.pop("ledger", _ledger()), kwargs.pop("invoices", _invoices()),
                                   **kwargs)


def test_observed_exposures_use_only_completed_months_and_v2_service():
    x = _extract()
    assert x["operating"]["inflows_6m"] == 600
    assert x["operating"]["outflows_6m"] == 480
    assert x["operating"]["quality_months"] == ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
    assert x["costs"]["by_subclass"]["salary"] == 20
    assert x["costs"]["unclassified_discretionary_cost"] is None
    assert x["debt_service"]["v2_service_6m"] == 15
    assert x["debt_service"]["total_6m"] == 17  # fees stay context, not V2 score input
    assert x["group_support"]["status"] == "context_only"
    assert x["group_support"]["score_runnable"] is False
    assert x["fx"]["non_eur_share"] == pytest.approx(40 / 60)
    assert x["fx"]["score_runnable"] is False


def test_collections_require_reliable_paid_top_customer_history():
    x = _extract()
    assert x["collections"]["largest_customer_id"] == "CUSTOMER_A"
    assert x["collections"]["eligible_paid_count"] == 6
    assert x["collections"]["status"] == "available"
    assert x["collections"]["score_runnable"] is True
    assert x["collections"]["delay_median_days"] == 2
    filler = _extract(features=_features(filler=True))
    assert filler["collections"]["status"] == "unavailable"
    assert filler["collections"]["reason"] == "payment_date_filler_d39"


def test_missing_evidence_does_not_become_zero_or_rate_shock():
    x = _extract(ledger=pd.DataFrame(), invoices=pd.DataFrame())
    assert x["debt_service"]["v2_service_6m"] is None
    assert x["fx"]["non_eur_share"] is None
    assert x["collections"]["largest_customer_id"] is None
    schedule = pd.DataFrame({"company_id": ["C"], "interest_type": ["variable"],
                             "next_payment_date": ["2026-09-30"], "outstanding_balance": [100],
                             "annual_interest_rate_or_spread": [0.04], "currency": ["EUR"]})
    x = _extract(debt_schedule=schedule, schedule_snapshot_as_of=pd.Timestamp("2026-09-01"))
    assert x["variable_rate"]["status"] == "available"
    assert x["variable_rate"]["score_runnable"] is True
    assert x["variable_rate"]["outstanding_eur"] == 100
    stale = _extract(debt_schedule=schedule, schedule_snapshot_as_of=pd.Timestamp("2026-10-15"))
    assert stale["variable_rate"]["status"] == "unavailable"
    assert stale["variable_rate"]["reason"] == "schedule_snapshot_after_as_of"
    old_ledger = _ledger()
    old_ledger["date"] = "2026-02-01"
    x = _extract(ledger=old_ledger)
    assert x["debt_service"]["v2_service_6m"] is None
    assert x["debt_service"]["reason"] == "no_eligible_ledger_rows_in_window"


def test_debt_in_thin_month_is_observed_but_not_v2_service():
    f = _features()
    f.loc[f.month.eq(pd.Timestamp("2026-04-01")), "tx_usable_row_share"] = 0.2
    x = _extract(features=f)
    assert x["debt_service"]["total_6m"] == 17
    assert x["debt_service"]["v2_service_6m"] == 0
    assert x["debt_service"]["status"] == "unavailable"
    assert "2026-04" not in x["operating"]["quality_months"]


def test_midmonth_cutoff_rejected():
    with pytest.raises(ValueError, match="complete calendar month"):
        build_company_exposures("C", pd.Timestamp("2026-08-15"), _features(), _ledger(), _invoices())


def test_category_monthly_amounts_gate_on_exact_v2_reconciliation_and_materiality():
    rows = []
    for month in pd.date_range("2026-03-01", periods=6, freq="MS"):
        rows.extend([
            {"date": month, "amount": 100.0, "economic_class": "operating",
             "economic_subclass": "operating_collection", "included_in_operating_inflows": True,
             "included_in_operating_outflows": False, "source_currency": "EUR"},
            {"date": month, "amount": -50.0, "economic_class": "operating", "economic_subclass": "salary",
             "included_in_operating_inflows": False, "included_in_operating_outflows": True,
             "source_currency": "EUR"},
            {"date": month, "amount": -30.0, "economic_class": "operating",
             "economic_subclass": "operating_payment", "included_in_operating_inflows": False,
             "included_in_operating_outflows": True, "source_currency": "EUR"},
        ])
    ledger = pd.DataFrame(rows).assign(company_id="C", eligible=True,
                                       included_in_debt_service=False, classification_confidence="high")
    x = _extract(ledger=ledger)
    assert x["costs"]["reconciliation"]["status"] == "matched"
    assert x["costs"]["monthly_by_category"]["2026-03"]["payroll"] == 50
    assert x["costs"]["monthly_by_category"]["2026-03"]["other_operating_payment"] == 30
    assert x["costs"]["monthly_by_subclass"]["2026-03"]["salary"] == 50
    assert x["fx"]["monthly_by_currency"]["2026-03"]["EUR"] == {"inflows": 100, "outflows": 80}
    assert x["costs"]["category_gates"]["payroll"]["score_runnable"] is True
    assert x["costs"]["category_gates"]["other_operating_payment"]["score_runnable"] is True
    assert x["costs"]["category_gates"]["utilities"]["score_runnable"] is False
    ledger.loc[ledger.date.eq(pd.Timestamp("2026-04-01")) & ledger.amount.eq(-50), "amount"] = -60
    mismatch = _extract(ledger=ledger)
    assert mismatch["costs"]["reconciliation"]["monthly"]["2026-04"]["status"] == "mismatch"
    assert mismatch["costs"]["category_gates"]["payroll"]["score_runnable"] is False
    assert mismatch["costs"]["category_gates"]["payroll"]["amount_6m"] is None
