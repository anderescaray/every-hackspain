"""Independent adversarial review cases for the approved V1 contract."""
import numpy as np
import pandas as pd
import pytest

from xray.ledger import build_monthly_facts, classify_transactions
from xray.pulse import score_company


def sample(*, rotating_accounts=False):
    rows = []
    for index, month in enumerate(pd.date_range("2026-01-01", periods=6, freq="MS")):
        for label, amount, category in (("in", 110., "collection"), ("out", -100., "payment"),
                                        ("debt", -1., "debt_repayment")):
            rows.append({"transaction_id": f"{index}-{label}", "company_id": "C", "currency": "EUR",
                         "product_id": f"P{index}" if rotating_accounts else "P", "date": month,
                         "amount": amount, "category": category, "status": "booked", "exchange_rate": 1.,
                         "description": ""})
    ledger = classify_transactions(pd.DataFrame(rows))
    facts = build_monthly_facts(ledger, as_of="2026-06-30")
    return ledger, facts


def score(ledger, facts):
    return score_company(facts, company_id="C", currency="EUR", as_of="2026-06-30", ledger=ledger)


def test_large_health_sensitivity_cannot_claim_diagnosis_stable():
    ledger, facts = sample()
    result = score(ledger, facts)
    bounds = result.robustness["tested_range"]
    assert bounds["max"] - bounds["min"] > 5
    assert result.robustness["level"] == "sensitive"
    assert result.robustness["diagnosis_stable"] is False


def test_disjoint_six_month_perimeter_is_explicitly_unevaluable():
    ledger, facts = sample(rotating_accounts=True)
    result = score(ledger, facts)
    checks = result.robustness["tested_assumptions"]
    perimeter = [item for item in checks if item["name"] == "observed_common_account_perimeter"]
    assert len(perimeter) == 1
    assert perimeter[0]["evaluable"] is False
    assert result.robustness["level"] == "indeterminate"
    assert result.robustness["diagnosis_stable"] is None


def test_operating_reconciliation_is_validated_even_without_debt_facts():
    ledger, facts = sample()
    facts.loc[0, "debt_service_paid"] = np.nan
    facts.loc[0, "operating_net_cash"] = 9999.
    with pytest.raises(ValueError, match="operating_net"):
        score(ledger, facts)


def test_perimeter_hypothesis_cannot_remove_unknown_currency_evidence():
    ledger, _ = sample()
    extra = pd.DataFrame([
        {"transaction_id": "new-account", "company_id": "C", "currency": "EUR", "product_id": "NEW",
         "date": pd.Timestamp("2026-06-10"), "amount": 50., "category": "collection", "status": "booked", "exchange_rate": 1., "description": ""},
        {"transaction_id": "unknown-currency", "company_id": "C", "currency": None, "product_id": "UNKNOWN",
         "date": pd.Timestamp("2026-06-11"), "amount": -5., "category": "uncategorized", "status": "booked", "exchange_rate": 1., "description": ""},
    ])
    combined = pd.concat([ledger, classify_transactions(extra)], ignore_index=True)
    facts = build_monthly_facts(combined, as_of="2026-06-30")
    result = score(combined, facts)
    assert result.pillars["debt_obligations"]["score"] is None
    scenario = next(c for c in result.robustness["tested_assumptions"]
                    if c["name"] == "observed_common_account_perimeter")
    assert scenario["pillar_scores"]["debt_obligations"] is None
