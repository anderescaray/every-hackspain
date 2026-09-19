"""The frontend adapter must only expose precomputed advisor facts."""

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from xray.product.actionability import from_sensitivity
from xray.product.frontend_export import _advisor_sensitivities, company_detail, run
from xray.group_advisor.sensitivity import score_with_baseline_momentum


@pytest.fixture
def sensitivity():
    path = Path(__file__).parent / "fixtures" / "advisor_sensitivity_example.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_business_fallback_and_exact_grid_provenance(sensitivity):
    sensitivity["structural_note"] = None
    result = from_sensitivity(sensitivity)
    assert result["status"] == "actionable_treasury"
    primary = result["primary"]
    assert primary["lever"] == "debt_service_cut"  # advisor by_cash first, not largest Health delta
    source = next(lever for lever in sensitivity["levers"] if lever["lever"] == primary["lever"])
    row = source["grid"][-1]
    assert primary["health_after"] == row["score_after_k6"]
    assert primary["level_after"] == row["level_after_k6"]
    assert primary["quantity"]["after"] == row["quantity_after"]
    assert primary["delta_points"] == pytest.approx(row["score_after_k6"] - sensitivity["baseline"]["score"])
    assert primary["efficiency"]["value"] == source["slope_now"]["level_per_10k"]
    assert primary["efficiency"]["unit"] == "level_points_per_10k"
    assert primary["horizon"]["k1_level_delta"] == pytest.approx(row["level_after_k1"] - sensitivity["baseline"]["level"])
    assert primary["scenario_id"] is None  # advisor != existing What-if scenario model
    assert primary["change_description"] == "Reducir servicio de deuda un 25 %"
    assert primary["required_change"]["relative_pct"] == 25
    assert primary["required_change"]["absolute"] == pytest.approx(abs(source["current"] - row["quantity_after"]))
    assert result["next_band"]["target_level"] == sensitivity["next_tramo_target"]
    assert result["next_band"]["current_health"] == sensitivity["baseline"]["score"]
    assert result["next_band"]["projected_health"] == primary["health_after"]
    assert result["next_band"]["target_health"] == score_with_baseline_momentum(
        sensitivity["next_tramo_target"], sensitivity["baseline"]["momentum_adjustment"])
    assert result["next_band"]["reachable_with_primary"] is False
    assert {a["lever"] for a in result["alternatives"]} == {"cut_outflow", "raise_inflow"}
    assert next(a for a in result["alternatives"] if a["lever"] == "raise_inflow")["efficiency"] is None
    assert all(a["type"] == "business" for a in result["alternatives"])
    assert len(result["treasury_actions"]) == 1 and len(result["business_sensitivities"]) == 2
    assert all(a["efficiency"] is None for a in result["business_sensitivities"])


def test_treasury_without_cash_efficiency_uses_modeled_impact(sensitivity):
    doc = copy.deepcopy(sensitivity)
    doc["structural_note"] = None
    debt = next(l for l in doc["levers"] if l["lever"] == "debt_service_cut")
    debt["slope_now"]["level_per_10k"] = None
    doc["ranking"]["by_cash"] = ["cut_outflow"]
    assert from_sensitivity(doc)["primary"]["lever"] == "debt_service_cut"


def test_business_sensitivity_not_recommendation(sensitivity):
    doc = copy.deepcopy(sensitivity)
    doc["structural_note"] = None
    for lever in doc["levers"]:
        if lever["type"] == "treasury":
            lever["available"] = False
    result = from_sensitivity(doc)
    assert result["status"] == "business_sensitivity_only"
    assert result["primary"]["type"] == "business"
    assert result["primary"]["lever"] == "cut_outflow"


def test_no_positive_impact_and_missing_baseline(sensitivity):
    doc = copy.deepcopy(sensitivity)
    for lever in doc["levers"]:
        for row in lever.get("grid", []):
            row["score_after_k6"] = doc["baseline"]["score"]
    result = from_sensitivity(doc)
    assert result["status"] == "no_actionable_lever" and result["primary"] is None
    doc["baseline"]["score"] = None
    assert from_sensitivity(doc)["status"] == "insufficient_data"


def test_ap_liquidity_uses_selected_grid_not_full_settlement(sensitivity):
    doc = copy.deepcopy(sensitivity)
    doc["structural_note"] = None
    for lever in doc["levers"]:
        if lever["lever"] == "ap_on_time":
            lever.update(available=True, reason=None, current=27, unit="days", direction="decrease",
                         slope_now={"level_per_10k": 1.35, "valid_until": 15},
                         grid=[{"rel_change": .25, "quantity_after": 20.25, "level_after_k1": 54,
                                "level_after_k6": 60, "score_after_k6": 55.2, "cash_equivalent": 52000}],
                         feasibility={"cash_needed": 208000, "own_excess_cash": 31000, "feasible_alone": False})
        elif lever["type"] == "treasury":
            lever["available"] = False
    doc["ranking"]["by_cash"] = ["ap_on_time"]
    result = from_sensitivity(doc)
    assert result["primary"]["lever"] == "ap_on_time"
    assert result["primary"]["resources"] == {
        "kind": "liquidity", "required": 52000, "own_available": 31000, "gap": 21000,
        "currency": "EUR", "feasibility": "requires_financing", "scope": "selected_grid_scenario"}
    assert result["primary"]["efficiency"]["label"] == "Eficiencia de liquidez"
    doc["levers"][3]["feasibility"]["own_excess_cash"] = None
    assert from_sensitivity(doc)["primary"]["resources"]["feasibility"] == "unknown"


def test_ap_zero_stock_proxy_does_not_claim_free_feasibility(sensitivity):
    doc = copy.deepcopy(sensitivity)
    doc["structural_note"] = None
    for lever in doc["levers"]:
        if lever["lever"] == "ap_on_time":
            lever.update(available=True, reason=None, current=21.8, unit="days", direction="decrease",
                         slope_now={"level_per_10k": None, "valid_until": None},
                         grid=[{"rel_change": .25, "quantity_after": 16.35, "level_after_k1": 54,
                                "level_after_k6": 56, "score_after_k6": 51.2, "cash_equivalent": 0}],
                         feasibility={"cash_needed": 0, "own_excess_cash": 0, "feasible_alone": True})
        elif lever["type"] == "treasury":
            lever["available"] = False
    action = from_sensitivity(doc)["primary"]
    assert action["lever"] == "ap_on_time"
    assert action["cash_equivalent"] == 0  # retain exact source for audit
    assert action["resources"]["required"] is None
    assert action["resources"]["gap"] is None
    assert action["resources"]["feasibility"] == "unknown"
    assert action["efficiency"] is None


def test_company_detail_preserves_unavailable_when_score_is_stale(sensitivity):
    sensitivity = copy.deepcopy(sensitivity)
    sensitivity["company_id"] = "COMP_0001"
    company = {"company_id": "COMP_0001", "group_id": "GROUP_0001", "currencies": {"EUR": {
        "timeline": [{"month": "2026-07-01", "score": 48.5, "score_status": "scored"}],
        "cash_truth": {"window_months": [], "buckets": []}, "confidence": {"confidence": 80},
    }}}
    evidence = pd.DataFrame(columns=["company_id", "month", "bucket", "transaction_id", "date", "amount", "description"])
    detail = company_detail(company, None, evidence, sensitivity=sensitivity)
    assert detail["actionability"]["status"] == "insufficient_data"
    assert detail["actionability"]["reason"] == "score_month_not_current"


def test_export_requires_advisor_artifact(tmp_path):
    product = tmp_path / "product"
    product.mkdir()
    (product / "portfolio.json").write_text(json.dumps({"latest_month": "2026-08-01", "companies": []}))
    with pytest.raises(FileNotFoundError, match="08_treasury_advisor.py"):
        run(product, tmp_path / "out", tmp_path / "advisor", verbose=False)


def test_advisor_hash_preflight_rejects_mixed_run(tmp_path, sensitivity):
    advisor = tmp_path / "advisor"
    folder = advisor / "company_sensitivity"
    folder.mkdir(parents=True)
    path = folder / "COMP_0007.json"
    path.write_text(json.dumps(sensitivity))
    manifest = {"outputs_sha256": {"company_sensitivity/COMP_0007.json": "0" * 64}}
    with pytest.raises(ValueError, match="Hash de sensibilidad"):
        _advisor_sensitivities(advisor, manifest, [tmp_path / "COMP_0007.json"])


def test_top_band_has_no_promoted_hero(sensitivity):
    doc = copy.deepcopy(sensitivity)
    doc["baseline"]["level"] = 98
    doc["baseline"]["score"] = 98
    doc["baseline"]["tramo"] = "green"
    doc["next_tramo_target"] = None
    result = from_sensitivity(doc)
    assert result["status"] == "top_band_no_action"
    assert result["band_basis"] == "level_v2"
    assert result["primary"] is None and result["next_band"] is None


def test_top_level_band_can_have_health_below_70(sensitivity):
    doc = copy.deepcopy(sensitivity)
    doc["baseline"].update(level=71, score=62, momentum_adjustment=-9, tramo="green")
    doc["next_tramo_target"] = None
    result = from_sensitivity(doc)
    assert result["status"] == "top_band_no_action"
    assert result["band_basis"] == "level_v2" and result["primary"] is None


def test_health_target_clips_like_advisor_grid_and_suppresses_false_path(sensitivity):
    assert score_with_baseline_momentum(70, 40) == 100
    assert score_with_baseline_momentum(40, -50) == 0
    doc = copy.deepcopy(sensitivity)
    doc["structural_note"] = None
    doc["baseline"].update(level=53, score=100, momentum_adjustment=50)
    result = from_sensitivity(doc)
    assert result["next_band"] is None  # target Level 70 maps to same clipped Health 100


def test_business_sensitivities_ranked_by_precomputed_health_impact(sensitivity):
    doc = copy.deepcopy(sensitivity)
    doc["structural_note"] = None
    more = next(lever for lever in doc["levers"] if lever["lever"] == "raise_inflow")
    more["grid"][-1]["score_after_k6"] = 65
    result = from_sensitivity(doc)
    assert [lever["lever"] for lever in result["business_sensitivities"]] == ["raise_inflow", "cut_outflow"]


def test_structural_issue_is_not_pretended_treasury_solution(sensitivity):
    result = from_sensitivity(sensitivity)
    assert result["status"] == "structural_issue"
    assert result["primary"]["type"] == "business"
    assert result["business_sensitivities"][0]["type"] == "business"
    assert result["treasury_actions"][0]["lever"] == "debt_service_cut"
