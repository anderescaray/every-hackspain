"""Exportación al contrato del frontend: traducción sin recálculo, neutros documentados y ausencias explícitas."""
import json

import pandas as pd
import pytest

from xray.product.frontend_export import WEIGHTS, company_detail, group_detail
from xray.product.cash_truth import classify, monthly_buckets


def timeline(scores, **last):
    rows = []
    for i, s in enumerate(scores):
        rows.append({"month": f"2026-0{i + 1}-01T00:00:00", "score": s, "level": s, "momentum": 55.0 if s else None,
                     "trajectory": "stable", "score_status": "scored", "score_reason": "ok",
                     "level_operations": 60.0, "level_debt": 80.0, "level_collections": 70.0, "level_payments": 50.0})
    rows[-1].update(last)
    return rows


def company(scores, cash=None, **last):
    return {"company_id": "COMP_0001", "group_id": "GROUP_0001", "currencies": {"EUR": {
        "timeline": timeline(scores, **last),
        "why_changed": {"terms": [{"rank": 1, "layer": "level", "feature": "op_margin_w", "component": "operations",
                                   "label": "Margen operativo (6m)", "delta_contribution": -4.26, "sentence": "Margen: 0,20 → 0,05 · -4,3 pts"}]},
        "confidence": {"confidence": 81.4},
        "cash_truth": cash or {"window_months": ["2026-03-01T00:00:00", "2026-08-01T00:00:00"], "buckets": [
            {"bucket": "operations", "amount_in": 1000.0, "amount_out": 400.0, "amount_abs": 1400.0, "n_tx": 10},
            {"bucket": "own_circulation", "amount_in": 500.0, "amount_out": 500.0, "amount_abs": 1000.0, "n_tx": 4},
            {"bucket": "group_support", "amount_in": 300.0, "amount_out": 0.0, "amount_abs": 300.0, "n_tx": 2},
            {"bucket": "unpaired_transfer", "amount_in": 0.0, "amount_out": 50.0, "amount_abs": 50.0, "n_tx": 1},
        ]}}}}


EVIDENCE = pd.DataFrame({"company_id": ["COMP_0001"] * 2, "transaction_id": ["t1", "t2"], "date": ["2026-04-03", "2026-05-09"],
                         "amount": [1000.0, -400.0], "bucket": ["operations", "operations"], "description": ["COBRO", None]})


def test_scores_are_rounded_not_recomputed_and_history_ends_at_current():
    d = company_detail(company([None, 61.4, 63.6]), {"support_dependency_ratio": 0.1}, EVIDENCE)
    assert d["health_score"] == 64 and [h["health_score"] for h in d["history"]] == [61, 64]
    assert d["as_of"] == "2026-03-31" and d["history"][-1]["month"] == "2026-03-01"
    assert d["dimensions"] == {"momentum": 55, "cash_generation": 60, "resilience": 60, "debt": 80}
    assert d["health_score_model"]["provisional"] is False and sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_missing_dimension_uses_health_score_and_marks_provisional():
    d = company_detail(company([50.0], momentum=None, level_collections=None, level_payments=None), None, EVIDENCE)
    assert d["dimensions"]["momentum"] == 50 and d["dimensions"]["resilience"] == 50
    assert d["health_score_model"]["provisional"] is True


def test_trajectory_is_collapsed_to_three_values():
    for v2, expected in (("emerging_deterioration", "deteriorating"), ("improving", "improving"), ("mixed_signals", "stable"),
                         ("insufficient_history", "stable")):
        assert company_detail(company([50.0], trajectory=v2), None, EVIDENCE)["trajectory"] == expected


def test_cash_truth_has_exactly_four_categories_with_unpaired_as_uncertain():
    d = company_detail(company([50.0]), {"support_dependency_ratio": 0.35}, EVIDENCE)
    c = {x["category"]: x for x in d["cash_truth"]["components"]}
    assert list(c) == ["operating", "circulation", "support", "uncertain"]
    assert c["operating"]["net_amount"] == 600.0 and c["circulation"]["net_amount"] == 0 and c["support"]["net_amount"] == 300.0
    assert c["uncertain"]["net_amount"] is None and c["uncertain"]["gross_movement"] == 50.0
    own = d["cash_truth"]["own_account_circulation"]
    assert (own["transferred_amount"], own["transfer_count"]) == (500.0, 2)   # una vez por traslado, no el bruto
    assert d["cash_truth"]["total_gross_movement"] == 2750.0 and d["cash_truth"]["apparent_net"] == pytest.approx(850.0)
    assert "dependencia de apoyo" in d["assessment"]


def test_evidence_refs_resolve_and_absent_blocks_are_explicit():
    d = company_detail(company([50.0]), None, EVIDENCE)
    ids = {e["id"] for e in d["evidence"]}
    assert all(ref in ids for comp in d["cash_truth"]["components"] for ref in comp["evidence_refs"])
    assert d["evidence"][0]["rows"][1]["description"] == "Sin concepto"
    assert d["time_borrowed"] == {"ar": None, "ap": None} and d["alerts"] == [] and d["simulation"]["scenarios"] == []
    assert d["drivers"][0]["impact"] == -4.3 and d["drivers"][0]["direction"] == "negative"
    json.dumps(d, allow_nan=False)


def test_company_without_any_score_is_not_exported():
    assert company_detail(company([None, None]), None, EVIDENCE) is None


def test_group_members_keep_nulls_and_roles_from_cash_truth():
    detail = company_detail(company([70.0]), {"support_dependency_ratio": 0.6}, EVIDENCE)
    g = group_detail({"group_id": "GROUP_0001", "latest_month": "2026-01-01T00:00:00",
                      "companies": [{"company_id": "COMP_0001"}, {"company_id": "COMP_0002"}]},
                     {"COMP_0001": detail},
                     {"COMP_0001": {"support_role": "net_receiver", "support_dependency_ratio": 0.6, "support_in_6m": 300.0,
                                    "support_out_6m": 0.0, "operations_in_6m": 1000.0}})
    m = {x["company_id"]: x for x in g["members"]}
    assert m["COMP_0001"]["role"] == "receiver" and m["COMP_0001"]["attention"] == "high"
    assert m["COMP_0002"]["health_score"] is None and m["COMP_0002"]["role"] == "unknown"
    assert g["available_liquidity"]["value"] is None and g["relations"] == [] and len(g["limitations"]) >= 1
    json.dumps(g, allow_nan=False)


@pytest.mark.parametrize("category, expected_own", [("transfer", 100.0), ("debt_repayment", None)])
def test_canonical_own_pair_or_debt_settlement_keeps_evidence(category, expected_own):
    transactions = pd.DataFrame([
        {"transaction_id": "debit", "company_id": "COMP_0001", "product_id": "P1",
         "date": pd.Timestamp("2026-01-05"), "amount": -100.0, "category": category},
        {"transaction_id": "credit", "company_id": "COMP_0001", "product_id": "P2",
         "date": pd.Timestamp("2026-01-05"), "amount": 100.0, "category": "transfer"},
    ]).assign(product_currency="EUR", exchange_rate=1.0, status="booked",
              description="", is_internal_transfer=True)
    classified = classify(transactions, stop=pd.Timestamp("2026-02-01"))
    cash = {"window_months": ["2026-01-01"], "buckets": monthly_buckets(classified).to_dict("records")}
    detail = company_detail(company([50.0], cash=cash), None, classified)
    out = detail["cash_truth"]
    circulation = next(c for c in out["components"] if c["category"] == "circulation")
    assert out["total_gross_movement"] == 200.0 and out["apparent_net"] == 0.0
    assert circulation["evidence_refs"] == ["cash-movements"]
    if expected_own is None:
        assert out["own_account_circulation"] is None
        assert circulation["net_amount"] is None and circulation["gross_movement"] == 100.0
        assert circulation["confidence"] is None
        assert "neto no evaluable" in out["explanation"]
        debt = classified[classified.economic_class.eq("debt_service")]
        assert len(debt) == 1 and debt.amount.sum() == -100.0
        assert sum(c["gross_movement"] for c in out["components"]) == 200.0
    else:
        assert out["own_account_circulation"]["transferred_amount"] == expected_own
        assert out["own_account_circulation"]["transfer_count"] == 1
        assert circulation["net_amount"] == 0.0
    json.dumps(detail, allow_nan=False)


@pytest.mark.parametrize("missing", [None, float("nan"), pd.NA])
def test_missing_evidence_description_is_not_stringified(missing):
    rows = EVIDENCE.copy()
    rows["description"] = pd.Series([missing, missing], dtype="object")
    detail = company_detail(company([50.0]), None, rows)
    assert all(row["description"] == "Sin concepto" for row in detail["evidence"][0]["rows"])
