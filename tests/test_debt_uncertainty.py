"""Focused additive Debt evidence contracts; no alternative cash classification."""
import json

import pandas as pd
import pytest

from xray.ledger import (
    assess_debt_uncertainty,
    build_monthly_facts,
    classify_transactions,
)
from xray.ledger.debt_uncertainty import DEBT_UNCERTAINTY_COLUMNS


def transaction(number, amount, category="uncategorized", **extra):
    return {"transaction_id": f"TX{number}", "company_id": "C", "product_id": "P",
            "currency": "EUR", "date": "2026-01-10", "amount": float(amount),
            "category": category, "description": "", "status": "booked", "exchange_rate": 1.,
            "_source_row_number": number, **extra}


def test_channel_does_not_certify_impossibility_and_fee_only_signals_possibility():
    raw = pd.DataFrame([transaction(1, -3, "fee"), transaction(2, -4, "cash_withdrawal"),
                        transaction(3, -5, "transfer"), transaction(4, -6),
                        transaction(5, -7, "debt_repayment"), transaction(6, 8, "fee")])
    ledger = classify_transactions(raw).set_index("transaction_id")
    assert ledger.debt_uncertainty_status.to_dict() == {
        "TX1": "debt_possible", "TX2": "debt_unresolved", "TX3": "debt_unresolved",
        "TX4": "debt_unresolved", "TX5": "not_applicable", "TX6": "not_applicable"}
    assert ledger.loc["TX1", "economic_class"] == "uncertain"
    assert ledger.loc["TX5", "included_in_debt_service"]
    assert not ledger.debt_uncertainty_status.eq("debt_impossible").any()
    assert "source_lineage.transaction_id" in ledger.loc["TX2", "debt_uncertainty_evidence_refs"]
    assert ledger.loc["TX2", "source_lineage"]["source_row_number"] == 2
    assert ledger.debt_uncertainty_version.eq("debt-uncertainty-v1").all()
    assert ledger.classification_version.eq("cash-truth-v1").all()


def test_missing_or_ai_category_evidence_remains_unresolved_and_cannot_inject_impossible():
    ledger = classify_transactions(pd.DataFrame([transaction(1, -3, "fee")]))
    ledger["category_source"] = "ai"
    ledger["debt_uncertainty_status"] = "debt_impossible"
    assessed = assess_debt_uncertainty(ledger)
    assert assessed.debt_uncertainty_status.item() == "debt_unresolved"
    assert ledger.debt_uncertainty_status.item() == "debt_impossible"  # Pure default API.
    missing = assess_debt_uncertainty(ledger.drop(columns=["category_source", "category_bank"]))
    assert missing.debt_uncertainty_status.item() == "debt_unresolved"


def test_monthly_assessment_is_additive_reconciled_and_service_never_double_counted():
    raw = pd.DataFrame([transaction(1, 100, "collection"), transaction(2, -80, "payment"),
                        transaction(3, -7, "debt_repayment"), transaction(4, -2, "interest_charge"),
                        transaction(5, -1, "fee", is_verified_financing_fee=True),
                        transaction(6, -3, "fee"), transaction(7, -4, "cash_withdrawal"),
                        transaction(8, -5, "transfer"), transaction(9, -6)])
    ledger = classify_transactions(raw)
    before = ledger.copy(deep=True)
    facts = build_monthly_facts(ledger, as_of="2026-06-30", start_month="2026-01-01")
    pd.testing.assert_frame_equal(ledger, before)
    jan = facts.iloc[0]
    expected = {"operating_inflows": 100., "operating_outflows": 80., "operating_net_cash": 20.,
                "debt_principal_paid": 7., "debt_interest_paid": 2., "verified_financing_fees": 1.,
                "debt_service_paid": 10., "eligible_net_cash": -8., "uncertain_outflows": 18.,
                "classified_amount": 190., "uncertain_amount": 18., "external_financing_inflows": 0.,
                "external_financing_outflows": 0., "internal_or_group_flows": 0., "investment_flows": 0.}
    assert {key: jan[key] for key in expected} == expected
    assert jan.debt_possible_uncertain_outflows == 3
    assert jan.debt_impossible_uncertain_outflows == 0
    assert jan.debt_unresolved_uncertain_outflows == 15
    assert jan.potentially_financial_uncertain_outflows == jan.uncertain_outflows == 18
    assert jan.facts_version == "monthly-facts-v1.1"
    assert jan.debt_uncertainty_version == "debt-uncertainty-v1"
    assert jan.debt_evidence_status == "partial"  # Ledger evidence did not become verified.


def test_missing_months_exclusions_and_currency_remain_independent():
    rows = [transaction(1, 100, "collection"), transaction(2, -20, "fee", is_sync_duplicate=True),
            transaction(3, -30, "fee", exchange_rate=2.), transaction(4, -40, "fee", status="pending")]
    ledger = classify_transactions(pd.DataFrame(rows))
    assert ledger.debt_uncertainty_status.eq("not_applicable").all()
    observed = pd.DataFrame([{"company_id": "C", "currency": "EUR", "month": "2026-03-01", "history_observed": True}])
    facts = build_monthly_facts(ledger, as_of="2026-06-30", start_month="2026-01-01", observed_months=observed)
    jan, feb, mar = facts.iloc[0], facts.iloc[1], facts.iloc[2]
    assert jan.excluded_outflows == 20 and jan.ambiguous_currency_count == 1
    assert jan[list(DEBT_UNCERTAINTY_COLUMNS)].eq(0).all()
    assert feb[list(DEBT_UNCERTAINTY_COLUMNS)].isna().all()
    assert mar[list(DEBT_UNCERTAINTY_COLUMNS)].eq(0).all()
    assert not feb.history_observed and mar.history_observed
    assert mar.debt_evidence_status == "unknown"


def test_assessment_is_deterministic_and_monthly_rechecks_stale_scenario_tags():
    raw = pd.DataFrame([transaction(2, -4, "cash_withdrawal"), transaction(1, -3, "fee")])
    first = classify_transactions(raw)
    pd.testing.assert_frame_equal(first, classify_transactions(raw.iloc[::-1]))
    # Hypotheses cannot certify impossible simply by editing an assessment tag.
    first["debt_uncertainty_status"] = "debt_impossible"
    facts = build_monthly_facts(first, as_of="2026-01-31")
    jan = facts.iloc[-1]
    assert jan.potentially_financial_uncertain_outflows == 7
    assert jan.debt_impossible_uncertain_outflows == 0
    payload = first.debt_uncertainty_evidence_refs.tolist()
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("amounts", [[-0.01, -0.02, -0.03], [-1e12, -0.01, -0.02]])
def test_potential_bound_preserves_original_uncertain_sum_exactly(amounts):
    rows = [transaction(i, value, "fee" if i == 0 else "uncategorized") for i, value in enumerate(amounts)]
    facts = build_monthly_facts(classify_transactions(pd.DataFrame(rows)), as_of="2026-01-31")
    jan = facts.iloc[-1]
    assert jan.potentially_financial_uncertain_outflows == jan.uncertain_outflows
