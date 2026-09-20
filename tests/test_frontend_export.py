"""Exportación al contrato del frontend: traducción sin recálculo, neutros documentados y ausencias explícitas."""
import json
from pathlib import Path

import pandas as pd
import pytest

from xray.product.frontend_export import WEIGHTS, _advisor_recommendations, company_detail, group_detail


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


def test_only_production_safe_advisor_plans_become_group_recommendations():
    plan = json.loads((Path(__file__).parent / "fixtures" / "advisor_plan_example.json").read_text(encoding="utf-8"))
    assert _advisor_recommendations(plan) == []
    plan["config"].update({"production_safe": True, "min_recipient_inflow_6m": 10_000.,
                           "min_recipient_inflow_outflow_ratio": .01})
    recommendations = _advisor_recommendations(plan)
    assert len(recommendations) == len(plan["plan"]["steps"])
    first = recommendations[0]
    assert first["id"].startswith("advisor-") and first["confidence"] is None
    assert first["company_refs"] == [plan["plan"]["steps"][0]["recipient"], plan["plan"]["steps"][0]["donor"]]
    assert "Escenario mecánico" in first["constraints"][0] and "no mueve fondos" in first["review_steps"][-1]
    assert "ΔG" in first["explanation"] and first["evidence_refs"] == []
    json.dumps(recommendations, allow_nan=False)
    incomplete = json.loads(json.dumps(plan))
    incomplete["plan"]["steps"][0]["effects"]["k6"]["recipient"]["level_after"] = None
    assert len(_advisor_recommendations(incomplete)) == len(plan["plan"]["steps"]) - 1


def test_portfolio_items_map_status_trajectory_and_attention():
    from xray.product.frontend_export import portfolio_export
    rows = [
        {"company_id": "COMP_0001", "group_id": "GROUP_0001", "score": 61.4, "delta_vs_prev": -3.26, "trajectory": "deteriorating",
         "score_status": "scored", "score_reason": "ok", "confidence": 88.2, "main_signal": "Margen", "main_signal_delta": -4.26},
        {"company_id": "COMP_0002", "group_id": None, "score": 70.0, "delta_vs_prev": 1.0, "trajectory": "emerging_improvement",
         "score_status": "provisional", "score_reason": "coverage_account_change", "confidence": 60.0, "main_signal": None, "main_signal_delta": None},
        {"company_id": "COMP_0003", "group_id": "GROUP_0001", "score": None, "delta_vs_prev": None, "trajectory": "insufficient_history",
         "score_status": "not_scored", "score_reason": "no_usable_transactions", "confidence": 0.0, "main_signal": None, "main_signal_delta": None},
    ]
    out = portfolio_export({"latest_month": "2026-08-01T00:00:00", "companies": rows}, {"COMP_0001": {}},
                           {"COMP_0002": {"support_dependency_ratio": 0.55}})
    items = {i["company_id"]: i for i in out["items"]}
    assert out["as_of"] == "2026-08-31" and len(out["items"]) == 3
    assert items["COMP_0001"]["health_score"] == 61 and items["COMP_0001"]["attention"] == "high" and items["COMP_0001"]["trajectory_stage"] == "confirmed"
    assert items["COMP_0002"]["trajectory"] == "improving" and items["COMP_0002"]["trajectory_stage"] == "emerging"
    assert items["COMP_0002"]["attention"] == "high" and items["COMP_0002"]["status_reason"] == "Cambio de cuentas activas"
    assert items["COMP_0003"]["health_score"] is None and items["COMP_0003"]["trajectory"] is None and items["COMP_0003"]["has_detail"] is False
    json.dumps(out, allow_nan=False)


def test_select_whatif_publishes_everything_when_no_filter_is_given():
    from xray.product.frontend_export import select_whatif

    groups = {"COMP_0001": "a", "COMP_0764": "b"}
    assert select_whatif(groups, None) == (groups, [])


def test_select_whatif_limits_the_cards_that_carry_the_simulator():
    """La demo publica escenarios de unas pocas empresas; el resto queda sin sección."""
    from xray.product.frontend_export import select_whatif

    groups = {"COMP_0001": "a", "COMP_0764": "b", "COMP_0045": "c"}
    selected, missing = select_whatif(groups, ["COMP_0764", "COMP_0045"])
    assert set(selected) == {"COMP_0764", "COMP_0045"} and missing == []
    # Pedir una empresa sin escenarios no es un error silencioso: se devuelve para avisar.
    selected, missing = select_whatif(groups, ["COMP_0764", "COMP_9999"])
    assert set(selected) == {"COMP_0764"} and missing == ["COMP_9999"]
    # Una lista vacía deja el despliegue sin simulador en ninguna ficha.
    assert select_whatif(groups, []) == ({}, [])
