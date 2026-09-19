"""Cash Truth's economic contracts, not statistical target tests."""
import json
from dataclasses import fields

import pandas as pd
import pytest

from xray.fx import FX_TO_EUR

from xray.ledger import (
    CashTruthResult,
    LedgerTransaction,
    MonthlyFacts,
    build_cash_truth_result,
    build_monthly_facts,
    classification_metadata,
    classify_transactions,
)
from xray.product.cash_truth import classify as classify_product


def tx(i, amount, category="collection", **kwargs):
    row = {"transaction_id": f"TX{i}", "company_id": "COMP_1084", "product_id": "P1", "currency": "EUR",
               "date": pd.Timestamp("2026-01-10"), "amount": float(amount), "category": category,
               "status": "booked", "exchange_rate": 1., "description": "", "is_internal_transfer": False,
               "is_intragroup": False, "_source_row_number": i}
    row.update(kwargs)
    return row


def facts(rows, **kwargs):
    ledger = classify_transactions(pd.DataFrame(rows))
    monthly = build_monthly_facts(ledger, as_of="2026-06-30", start_month="2026-01-01", **kwargs)
    return ledger, monthly


def test_financing_and_own_transfer_never_create_operating_generation():
    rows = [tx(1, 100), tx(2, -80, "payment"), tx(3, 50000, "loan_drawdown"),
            tx(4, 2000, is_internal_transfer=True), tx(5, -2000, "transfer", is_internal_transfer=True),
            tx(6, 600, "collection", description="ABONO PRÉSTAMO")]
    ledger, monthly = facts(rows)
    jan = monthly.iloc[0]
    assert (jan.operating_inflows, jan.operating_outflows, jan.operating_net_cash) == (100, 80, 20)
    assert jan.external_financing_inflows == 50600
    assert jan.internal_or_group_flows == 0
    assert jan.internal_or_group_inflows == 2000
    assert ledger.loc[ledger.economic_class.eq("external_financing"), "included_in_operating_inflows"].eq(False).all()


def test_debt_once_even_own_settlement_and_only_verified_financing_fees():
    ledger, monthly = facts([tx(1, 1000), tx(2, -100, "debt_repayment", is_internal_transfer=True),
                            tx(3, 100, "uncategorized", is_internal_transfer=True),
                            tx(4, -10, "interest_charge"), tx(5, -5, "fee", is_verified_financing_fee=True),
                            tx(6, -3, "fee"), tx(7, -2, "interest_charge", description="[2024-12-01] stripe_fee")])
    jan = monthly.iloc[0]
    assert jan.debt_service_paid == jan.debt_principal_paid + jan.debt_interest_paid + jan.verified_financing_fees == 115
    assert jan.operating_outflows == 2
    assert jan.uncertain_outflows == 3
    assert jan.debt_evidence_status == "partial"
    roles = ledger[["included_in_operating_inflows", "included_in_operating_outflows", "included_in_debt_service"]]
    assert roles.sum(axis=1).le(1).all()
    assert ledger.set_index("transaction_id").loc["TX6", "economic_class"] == "uncertain"


def test_uncertain_stays_explicit_and_coverage_reconciles_eligible_ledger():
    ledger, monthly = facts([tx(1, 100), tx(2, -30, "uncategorized"), tx(3, 50, "transfer"),
                            tx(4, 99999, status="pending"), tx(5, -1000, "payment", is_sync_duplicate=True)])  # D32: fuera por calidad, no por tamaño
    jan = monthly.iloc[0]
    assert jan.uncertain_amount == 80
    assert jan.classified_amount == 100
    assert jan.classification_coverage == pytest.approx(100 / 180)
    assert jan.classified_amount + jan.uncertain_amount == ledger.loc[ledger.eligible, "amount"].abs().sum()
    assert jan.excluded_outflows == 1000
    assert jan.excluded_inflows == 0  # Pending is not booked cash.
    assert len(ledger) == 5
    assert ledger.loc[~ledger.eligible, "economic_class"].eq("uncertain").all()


def test_missing_month_is_not_zero_and_explicit_observed_zero_has_unknown_debt():
    observed = pd.DataFrame([{"company_id": "COMP_1084", "currency": "EUR", "month": "2026-03-01", "history_observed": True}])
    _, monthly = facts([tx(1, 100)], observed_months=observed)
    f = monthly.set_index("month")
    assert not f.loc["2026-02-01", "history_observed"]
    assert pd.isna(f.loc["2026-02-01", "operating_inflows"])
    assert f.loc["2026-03-01", "history_observed"]
    assert f.loc["2026-03-01", "operating_inflows"] == 0
    assert f.loc["2026-03-01", "debt_evidence_status"] == "unknown"
    assert pd.isna(f.loc["2026-03-01", "classification_coverage"])


def test_debt_verified_is_observed_service_not_absence_or_contractual_debt():
    _, monthly = facts([tx(1, 100), tx(2, -10, "debt_repayment"),
                        tx(3, 100, date=pd.Timestamp("2026-02-10"))])
    assert monthly.iloc[0].debt_evidence_status == "verified"
    assert monthly.iloc[1].debt_evidence_status == "unknown"
    assert "no_debt" in monthly.iloc[1].debt_evidence_reason


def test_legacy_product_and_ledger_share_exact_economics_and_source_lineage():
    frame = pd.DataFrame([tx(1, 1000, "loan_drawdown"), tx(2, -10, "interest_charge"),
                          tx(3, -2, "fee"), tx(4, 10), tx(5, 99, status="pending")])
    ledger = classify_transactions(frame)
    product = classify_product(frame).set_index("transaction_id")
    eligible = ledger.loc[ledger.eligible].set_index("transaction_id")
    pd.testing.assert_frame_equal(product[eligible.columns], eligible)
    assert eligible.loc["TX1", "source_lineage"]["source_row_number"] == 1
    record = eligible.loc["TX1"].to_dict() | {"transaction_id": "TX1"}
    contract = LedgerTransaction(**{f.name: record[f.name] for f in fields(LedgerTransaction)})
    json.dumps(contract.to_dict(), allow_nan=False)


def test_refund_sign_gateway_and_structural_nonoperating_overrides():
    ledger, monthly = facts([tx(1, 20, "collection_refund"), tx(2, -5, "payment_refund"),
                            tx(3, 1000, description="SCF-AJUS.SALDO C."),
                            tx(4, 5000, description="VT.A [NUM]"),
                            tx(5, -2, "interest_charge", description="[2024-12-01] network_cost")])
    assert monthly.iloc[0].operating_inflows == 20
    assert monthly.iloc[0].operating_outflows == 7
    assert monthly.iloc[0].external_financing_inflows == 1000
    assert monthly.iloc[0].investment_flows == 5000
    assert ledger.loc[ledger.transaction_id.eq("TX5"), "economic_class"].item() == "operating"


def test_cash_truth_json_reconciles_and_is_typed_with_null_missing():
    ledger, monthly = facts([tx(1, 100), tx(2, -80, "payment"), tx(3, -4, "debt_repayment")])
    result = build_cash_truth_result(ledger, monthly, company_id="COMP_1084", currency="EUR", as_of="2026-06-30")
    assert isinstance(result, CashTruthResult)
    payload = result.to_dict()
    assert payload["summary"]["net_operating_cash"] == 20
    assert sum(c["amount_abs"] for c in payload["classes"]) == 184
    assert payload["coverage"]["observed_months"] == 1
    assert payload["flags"] == ["missing_months"]
    json.dumps(payload, allow_nan=False)
    record = monthly.iloc[1].to_dict()
    record["month"] = record["month"].date().isoformat()
    contract = MonthlyFacts(**{f.name: record[f.name] for f in fields(MonthlyFacts)})
    assert contract.to_dict()["operating_inflows"] is None


def test_calendar_cutoff_no_future_and_deterministic_input_order():
    frame = pd.DataFrame([tx(1, 100), tx(2, 200, date=pd.Timestamp("2026-07-01"))])
    a = classify_transactions(frame, as_of="2026-06-30")
    b = classify_transactions(frame.iloc[::-1], as_of="2026-06-30")
    pd.testing.assert_frame_equal(a, b)
    f = build_monthly_facts(classify_transactions(frame), as_of="2026-07-15")
    assert f.month.max() == pd.Timestamp("2026-06-01")
    assert f.operating_inflows.sum() == 100
    result = build_cash_truth_result(a, f, company_id="COMP_1084", currency="EUR", as_of="2026-07-15")
    assert result.as_of == "2026-07-15"
    assert result.evidence["window_end"] == "2026-06-30"


def test_empty_company_and_multicurrency_do_not_invent_facts():
    ledger = classify_transactions(pd.DataFrame([tx(1, 100), tx(2, 200, currency="USD")]))
    units = pd.DataFrame({"company_id": ["EMPTY"], "currency": ["EUR"]})
    monthly = build_monthly_facts(ledger, as_of="2026-06-30", company_currencies=units)
    jan = monthly.loc[monthly.month.eq("2026-01-01")].set_index(["company_id", "currency"])
    # D32: la cuenta en USD se convierte a EUR con tipo fijo y se consolida, no forma otra unidad.
    assert jan.loc[("COMP_1084", "EUR"), "operating_inflows"] == pytest.approx(100 + 200 / FX_TO_EUR["USD"])
    assert ("COMP_1084", "USD") not in jan.index
    assert pd.isna(jan.loc[("EMPTY", "EUR"), "operating_inflows"])
    empty = ledger.iloc[:0]
    out = build_monthly_facts(empty, as_of="2026-06-30", company_currencies=units)
    assert len(out) == 6 and not out.history_observed.any()


def test_fx_policy_is_versioned_in_cash_truth_metadata():
    meta = classification_metadata()
    policy = meta["config"]
    assert policy["reporting_currency"] == "EUR"
    assert policy["fx_as_of"] == "2026-09-18"
    assert policy["fx_knowledge_date"] == "2026-09-19"
    assert len(policy["fx_rates_sha256"]) == 64
    ledger = classify_transactions(pd.DataFrame([tx(1, 100, currency="USD")]))
    row = ledger.iloc[0]
    assert row.source_currency == "USD"
    assert row.currency == "EUR"
    assert row.amount_source == 100
    assert row.amount == pytest.approx(100 / FX_TO_EUR["USD"])
    assert ledger.attrs["classification_metadata"]["config"] == policy


def test_invalid_ids_or_amounts_fail_loudly():
    with pytest.raises(ValueError, match="unique"):
        classify_transactions(pd.DataFrame([tx(1, 1), tx(1, 2)]))
    with pytest.raises(ValueError, match="finite"):
        classify_transactions(pd.DataFrame([tx(1, float("inf"))]))


def test_static_enrichment_is_shared_versioned_and_cannot_override_financing(tmp_path):
    from xray.ledger.enrichment import template

    frame = pd.DataFrame([tx(1, 100, "uncategorized", description="PAYOUT STRIPE 1"),
                          tx(2, 10000, "uncategorized", description="SCF-AJUS.SALDO C., DC: 1")])
    cache = pd.DataFrame({"tpl": template(frame.description), "sign": [1, 1],
                          "jev_block": ["operating_inflow", "operating_inflow"],
                          "jev_confidence": [.9, .95], "sign_conflict": [False, False]})
    path = tmp_path / "cache.parquet"
    cache.to_parquet(path, index=False)
    a = classify_transactions(frame, ai_categories_path=path)
    legacy = classify_product(frame, ai_categories_path=path)
    assert a.economic_class.tolist() == ["operating", "external_financing"]
    pd.testing.assert_frame_equal(a, legacy.drop(columns="bucket"))
    assert a.category_source.eq("ai").all()
    assert a.classification_evidence_hash.str.len().eq(64).all()
    assert a.classification_version.str.startswith("cash-truth-v2+jev-").all()
    b = classify_transactions(frame, ai_categories_path=path, ai_min_confidence=.99)
    assert a.classification_config_hash.iloc[0] != b.classification_config_hash.iloc[0]
    assert a.classification_evidence_hash.iloc[0] == b.classification_evidence_hash.iloc[0]
    assert b.economic_class.tolist() == ["uncertain", "external_financing"]


def test_unknown_currency_never_summed_but_blocks_verified_debt():
    ledger, monthly = facts([tx(1, 100), tx(2, -10, "debt_repayment"), tx(3, -999, currency=None)])
    jan = monthly.iloc[0]
    assert len(monthly) == 6
    assert jan.operating_inflows == 100 and jan.debt_service_paid == 10
    assert jan.ambiguous_currency_count == jan.unknown_currency_count == 1
    assert jan.debt_evidence_status == "partial"
    assert pd.isna(ledger.loc[ledger.transaction_id.eq("TX3"), "currency"].item())


def test_all_economic_classes_reconcile_signed_cash_including_scf_outflows():
    ledger, monthly = facts([tx(1, 100), tx(2, -80, "payment"), tx(3, 1000, "loan_drawdown"),
                            tx(4, -500, "uncategorized", description="SCF-AJUS.SALDO"),
                            tx(5, -30, "investment_deployment"), tx(6, -7, "debt_repayment"),
                            tx(7, -2, "interest_charge"), tx(8, -11, "uncategorized")])
    f = monthly.iloc[0]
    net = (f.operating_net_cash + f.external_financing_inflows - f.external_financing_outflows
           + f.internal_or_group_flows + f.investment_flows + f.uncertain_inflows
           - f.uncertain_outflows - f.debt_service_paid)
    assert net == f.eligible_net_cash == ledger.loc[ledger.eligible, "amount"].sum()
    assert f.external_financing_outflows == 500


def test_empty_ledger_preserves_explicit_enrichment_methodology(tmp_path):
    from xray.ledger import classification_metadata

    cache = pd.DataFrame(columns=["tpl", "sign", "jev_block", "jev_confidence", "sign_conflict"])
    path = tmp_path / "empty_cache.parquet"
    cache.to_parquet(path)
    empty = classify_transactions(pd.DataFrame([tx(1, 100)]).iloc[:0], ai_categories_path=path)
    units = pd.DataFrame({"company_id": ["COMP_1084"], "currency": ["EUR"]})
    monthly = build_monthly_facts(empty, as_of="2026-06-30", company_currencies=units)
    assert monthly.classification_version.eq(classification_metadata(path)["classification_version"]).all()


def test_static_cache_conflicting_templates_rejected(tmp_path):
    from xray.ledger.enrichment import load_template_categories

    path = tmp_path / "conflicting.parquet"
    pd.DataFrame({"tpl": ["X", "X"], "sign": [1, 1], "jev_block": ["operating_inflow", "bank_adjustment"],
                  "jev_confidence": [.9, .9], "sign_conflict": [False, False]}).to_parquet(path)
    with pytest.raises(ValueError, match="conflicting"):
        load_template_categories(path)


def test_real_comp0356_peer_large_offsetting_flows_use_roundoff_not_money_tolerance():
    from xray.ledger.monthly import validate_monthly_reconciliation

    # COMP_0356 is a COMP_1084 group peer; these are January 2026 class totals.
    ledger, monthly = facts([
        tx(1, 51291.53), tx(2, -79264581.82, "payment"), tx(3, -15418.38, "debt_repayment"),
        tx(4, 1900., is_intragroup=True), tx(5, -81.62, "investment_deployment"),
        tx(6, 79226898.13, "uncategorized"), tx(7, -7.84, "uncategorized"),
    ])
    january = monthly.iloc[0]
    assert abs(january.cash_reconciliation_residual) <= january.cash_reconciliation_roundoff_bound
    assert january.cash_reconciliation_roundoff_bound < 0.01
    assert january.eligible_net_cash == pytest.approx(0, abs=1e-7)
    altered = monthly.copy()
    altered.loc[0, "investment_flows"] += .01
    with pytest.raises(ValueError, match="do not reconcile"):
        validate_monthly_reconciliation(altered)
    assert ledger.amount.abs().sum() > 1e8
