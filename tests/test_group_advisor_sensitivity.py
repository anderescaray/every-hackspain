import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from advisor_fixtures import anchor_reference_state, make_group_state
from xray.group_advisor.config import SENSITIVITY_LEVERS, AdvisorConfig
from xray.group_advisor.counterfactual import derive
from xray.group_advisor.grounding import validate_grounding
from xray.group_advisor.narrative import render_sensitivity, tramo_change_phrase
from xray.group_advisor.sensitivity import (
    LEVER_SPECS, apply_lever, cash_equivalent, company_sensitivity, feasibility, iter_company_sensitivities, knot_quantities,
    level_at, lever_available, next_knot, quantity_now, sensitivity_to_json, slope_now, to_next_tramo)
from xray.group_advisor.state import build_group_state, load_inputs
from xray.paths import PROCESSED_DIR

H = 6
CONFIG = AdvisorConfig()
REF = anchor_reference_state()
REAL_DATA = (PROCESSED_DIR / "scores_v2").exists()
WIP_DIR = PROCESSED_DIR / "advisor_wip"

# Nivel ≈ 53,3 (ámbar), sin ERP: como el fixture de WP4 (I = 540.000, O = 730.600, S = 32.400).
AMBER = {"company_id": "AMBER", "level_inflow_sum": 540000., "window_outflow_sum": 730600., "window_debt_service_sum": 32400.,
         "reconstructed_cash": 25000., "tx_outflow_ma3": 121766.7, "momentum_adjustment": -4.8}
# Cuatro componentes: m = 0,0909, d = 0,2, AP 20 días, AR 40 días; caja 90.000, colchón 200.000.
FULL = {"company_id": "FULL", "level_inflow_sum": 600000., "window_outflow_sum": 500000., "window_debt_service_sum": 120000.,
        "ap_delay_w": 20., "ap_delay_count_w": 12., "ar_delay_w": 40., "ar_delay_count_w": 8., "reconstructed_cash": 90000.,
        "tx_outflow_ma3": 80000., "inv_ap_overdue_amount": 8000., "inv_ap_due_30_amount": 5000., "inv_ap_due_60_amount": 2000.}
# Solo operaciones, m = −0,5 → nivel 13,3; con r_max = 0,5 el margen llega a −0,2 (nota 27) y no alcanza 40.
RED = {"company_id": "RED", "level_inflow_sum": 100000., "window_outflow_sum": 300000.}
GREEN = {"company_id": "GREEN", "level_inflow_sum": 1000000., "window_outflow_sum": 500000., "window_debt_service_sum": 10000.}
NOFLOW = {"company_id": "NOFLOW", "level_inflow_sum": 0., "window_outflow_sum": 100000., "window_debt_service_sum": 5000.}
NOTSCORED = {"company_id": "NOTSCORED"}


@pytest.fixture(scope="module")
def state():
    return make_group_state([AMBER, FULL, RED, GREEN, NOFLOW, NOTSCORED], reference_state=REF, config=CONFIG)


@pytest.fixture(scope="module")
def docs(state):
    return {cid: company_sensitivity(state, cid, CONFIG) for cid in state.subsidiaries.index}


def parts(state, cid):
    return state.subsidiaries.loc[cid], state.signal_row(cid)


def level_after(row, lever, r, k=H):
    return level_at(apply_lever(row, lever, r, k, H), REF)


def lever_of(doc, lever):
    return next(lv for lv in doc["levers"] if lv["lever"] == lever)


# ---------------------------------------------------------------- especificación y disponibilidad


def test_lever_specs_match_config_and_spec_table():
    assert tuple(LEVER_SPECS) == SENSITIVITY_LEVERS
    assert {s.type for s in LEVER_SPECS.values()} == {"business", "treasury"}
    assert LEVER_SPECS["cut_outflow"].direction == "decrease" and LEVER_SPECS["raise_inflow"].direction == "increase"
    assert LEVER_SPECS["ap_on_time"].unit_kind == "days" and LEVER_SPECS["debt_service_cut"].unit_kind == "money"
    assert [s.component for s in LEVER_SPECS.values()] == ["operations", "operations", "debt", "payments", "collections"]


def test_lever_availability_reasons(state):
    sub, row = parts(state, "AMBER")
    assert lever_available(sub, row, "cut_outflow") == (True, None)
    assert lever_available(sub, row, "ap_on_time", REF) == (False, "ap_component_unavailable")
    assert lever_available(sub, row, "ar_faster", REF) == (False, "ar_component_unavailable")
    sub, row = parts(state, "RED")
    assert lever_available(sub, row, "debt_service_cut") == (False, "no_debt_service_observed")
    sub, row = parts(state, "NOFLOW")
    assert lever_available(sub, row, "raise_inflow") == (False, "no_operating_inflow")
    assert lever_available(sub, row, "debt_service_cut") == (False, "debt_without_inflow_indicator")
    zero = make_group_state([{**FULL, "ap_delay_w": 0., "ar_delay_w": -3.}], reference_state=REF)
    sub, row = parts(zero, "FULL")
    assert lever_available(sub, row, "ap_on_time", REF) == (False, "ap_delay_already_zero")
    assert lever_available(sub, row, "ar_faster", REF) == (False, "ar_delay_already_zero")
    thin = make_group_state([{**FULL, "ap_delay_count_w": 3.}], reference_state=REF)
    assert lever_available(*parts(thin, "FULL"), "ap_on_time", REF) == (False, "ap_component_unavailable")
    nothing = make_group_state([{"company_id": "X", "level_inflow_sum": 10., "window_outflow_sum": 0.}], reference_state=REF)
    assert lever_available(*parts(nothing, "X"), "cut_outflow") == (False, "no_operating_outflow")


def test_apply_lever_uses_primitive_with_sign_and_raise_inflow_lowers_debt_service(state):
    row = state.signal_row("FULL")
    after = apply_lever(row, "raise_inflow", 0.1, H, H)
    assert after["level_inflow_sum"] == pytest.approx(row["level_inflow_sum"] * 1.1)
    assert after["debt_service_w"] < row["debt_service_w"] and after["op_margin_w"] > row["op_margin_w"]
    assert apply_lever(row, "cut_outflow", 0.1, H, H)["window_outflow_sum"] == pytest.approx(row["window_outflow_sum"] * 0.9)
    assert apply_lever(row, "debt_service_cut", 0.1, H, H)["window_debt_service_sum"] == pytest.approx(row["window_debt_service_sum"] * 0.9)
    assert apply_lever(row, "ap_on_time", 0.1, H, H)["ap_delay_w"] == pytest.approx(18.)
    assert apply_lever(row, "ar_faster", 0.5, 3, H)["ar_delay_w"] == pytest.approx(30.)
    assert row == state.signal_row("FULL")  # sin mutación


def test_cash_equivalent_per_lever(state):
    sub, _ = parts(state, "FULL")
    assert cash_equivalent(sub, "cut_outflow", 0.1) == pytest.approx(50000.)
    assert cash_equivalent(sub, "debt_service_cut", 0.25) == pytest.approx(30000.)
    assert cash_equivalent(sub, "ap_on_time", 1.0) == pytest.approx(13000.)
    assert cash_equivalent(sub, "raise_inflow", 0.1) is None and cash_equivalent(sub, "ar_faster", 0.1) is None
    assert cash_equivalent(state.subsidiaries.loc["AMBER"], "ap_on_time", 1.0) is None
    partial = make_group_state([{**FULL, "inv_ap_due_30_amount": np.nan}], reference_state=REF).subsidiaries.loc["FULL"]
    assert cash_equivalent(partial, "ap_on_time", 0.5) == pytest.approx(4000.)


# ---------------------------------------------------------------- pendiente y nudos


@pytest.mark.parametrize("cid", ["AMBER", "FULL"])
def test_slope_now_is_the_finite_difference(state, cid):
    sub, row = parts(state, cid)
    eps = CONFIG.finite_difference_eps
    for lever in SENSITIVITY_LEVERS:
        if not lever_available(sub, row, lever, REF)[0]:
            continue
        slope = slope_now(sub, row, lever, REF, CONFIG)
        expected = level_after(row, lever, eps) - level_after(row, lever, 0.0)
        assert slope["level_per_pct"] * 100 * eps == pytest.approx(expected, abs=1e-9)
        assert slope["level_per_unit"] * quantity_now(row, lever, H) == pytest.approx(slope["level_per_pct"] * 100)
        cash = cash_equivalent(sub, lever, 1.0)
        if cash is None:
            assert slope["level_per_10k"] is None
        else:
            assert slope["level_per_10k"] == pytest.approx(slope["level_per_pct"] * 100 * 10000 / cash)
        assert slope["level_per_pct"] >= 0


def test_valid_until_is_the_next_anchor_for_ap_delay(state):
    sub, row = parts(state, "FULL")  # ap_delay_w = 20; anclas 0, 7, 15, 30, 60, 90 → siguiente nudo bajando: 15
    valid_until, slope_after = next_knot(sub, row, "ap_on_time", REF, CONFIG)
    assert valid_until == pytest.approx(15.0, abs=1e-6)
    slope = slope_now(sub, row, "ap_on_time", REF, CONFIG)
    weight = 0.15  # cuatro componentes disponibles → peso efectivo de pagos
    assert slope["level_per_unit"] == pytest.approx(25 / 15 * weight, rel=1e-6)   # tramo 15–30: 1,667 puntos/día
    assert slope_after * 100 / 20 == pytest.approx(20 / 8 * weight, rel=1e-6)     # tramo 7–15: 2,5 puntos/día
    assert slope_after > slope["level_per_pct"]
    eps, r_knot = CONFIG.finite_difference_eps, 0.25
    before = (level_after(row, "ap_on_time", r_knot) - level_after(row, "ap_on_time", r_knot - eps)) / eps / 100
    after = (level_after(row, "ap_on_time", r_knot + eps) - level_after(row, "ap_on_time", r_knot)) / eps / 100
    assert before == pytest.approx(slope["level_per_pct"], rel=1e-6)   # la pendiente no cambia antes del nudo
    assert after == pytest.approx(slope_after, rel=1e-6) and after != pytest.approx(before, rel=1e-3)


def test_valid_until_for_debt_service_cut_is_anchor_times_inflow(state):
    sub, row = parts(state, "FULL")  # d = 0,2 → siguiente ancla bajando 0,15 → S* = 0,15·I, mensual /H
    valid_until, slope_after = next_knot(sub, row, "debt_service_cut", REF, CONFIG)
    assert valid_until == pytest.approx(0.15 * 600000. / H, abs=1e-6)
    assert slope_after is not None and slope_after >= 0
    knots = knot_quantities(row, "debt_service_cut", REF, H)
    assert knots == pytest.approx([d * 600000. / H for d in (0.0, 0.05, 0.15, 0.3, 0.5, 1.0)])


def test_knots_for_margin_levers_convert_signal_to_quantity(state):
    sub, row = parts(state, "AMBER")
    inflow, outflow, service = 540000., 730600., 32400.
    cut = knot_quantities(row, "cut_outflow", REF, H)
    assert pytest.approx(inflow * (1 - 0.0) / (1 + 0.0) / H) in cut and pytest.approx(0.0) in cut       # m* = 0 → O* = I; m* = 1 → 0
    assert next_knot(sub, row, "cut_outflow", REF, CONFIG)[0] == pytest.approx(inflow / H)             # 90.000 < 121.767
    raise_ = knot_quantities(row, "raise_inflow", REF, H)
    assert pytest.approx(outflow / H) in raise_ and pytest.approx(service / 0.05 / H) in raise_       # margen y deuda
    assert next_knot(sub, row, "raise_inflow", REF, CONFIG)[0] == pytest.approx(service / 0.05 / H)   # 108.000 antes que 121.767


def test_knot_beyond_r_max_or_at_cap(state):
    high = make_group_state([{"company_id": "X", "level_inflow_sum": 1000000., "window_outflow_sum": 400000.}], reference_state=REF)
    sub, row = parts(high, "X")  # m = 0,43; siguiente nudo bajando O: m* = 0,5 → O* = 333.333 (r = 0,17); luego m* = 1 → 0 (r = 1 > 0,5)
    assert next_knot(sub, row, "cut_outflow", REF, CONFIG)[0] == pytest.approx(1000000. / 3 / H)
    tight = AdvisorConfig(sensitivity_r_max={**CONFIG.sensitivity_r_max, "cut_outflow": 0.1})
    assert next_knot(sub, row, "cut_outflow", REF, tight) == (None, None)
    low = make_group_state([{**FULL, "ap_delay_w": 5.}], reference_state=REF)
    sub, row = parts(low, "FULL")  # siguiente nudo 0 se alcanza justo en r = 1 = r_max: sin dominio detrás
    assert next_knot(sub, row, "ap_on_time", REF, CONFIG) == (0.0, None)


# ---------------------------------------------------------------- siguiente tramo


def test_bisection_returns_minimal_r_reaching_target(state):
    sub, row = parts(state, "AMBER")
    result = to_next_tramo(sub, row, "cut_outflow", REF, CONFIG)
    assert result["target"] == 70.0 and result["reachable"] is True
    r_star, tol = result["rel_change_needed"], CONFIG.bisection_tol
    assert 0 < r_star <= CONFIG.sensitivity_r_max["cut_outflow"]
    assert level_after(row, "cut_outflow", r_star) >= 70.0
    assert level_after(row, "cut_outflow", r_star - tol) < 70.0
    assert result["quantity_needed"] == pytest.approx(730600. / H * (1 - r_star))
    assert result["cash_equivalent"] == pytest.approx(r_star * 730600.)
    assert r_star == pytest.approx(0.2969, abs=2e-4)  # coherente con el fixture de WP4


def test_bisection_for_increase_and_days_levers(state):
    sub, row = parts(state, "FULL")
    for lever in ("raise_inflow", "ar_faster"):
        result = to_next_tramo(sub, row, lever, REF, CONFIG)
        assert result["reachable"] and result["cash_equivalent"] is None
        r_star = result["rel_change_needed"]
        assert level_after(row, lever, r_star) >= 70.0 > level_after(row, lever, r_star - CONFIG.bisection_tol)
    assert to_next_tramo(sub, row, "raise_inflow", REF, CONFIG)["quantity_needed"] > 100000.
    assert to_next_tramo(sub, row, "ar_faster", REF, CONFIG)["quantity_needed"] < 40.


def test_unreachable_when_level_at_r_max_is_below_target(state):
    sub, row = parts(state, "RED")
    assert state.subsidiaries.loc["RED", "level"] == pytest.approx(13.3333, abs=1e-3)
    result = to_next_tramo(sub, row, "cut_outflow", REF, CONFIG)
    assert level_after(row, "cut_outflow", CONFIG.sensitivity_r_max["cut_outflow"]) < 40.0
    assert result == {"target": 40.0, "rel_change_needed": None, "quantity_needed": None, "reachable": False, "cash_equivalent": None}


def test_green_company_has_no_target(docs):
    doc = docs["GREEN"]
    assert doc["baseline"]["level"] >= 70 and doc["baseline"]["tramo"] == "green" and doc["next_tramo_target"] is None
    for lever in doc["levers"]:
        if lever["available"]:
            assert lever["to_next_tramo"] == {"target": None, "rel_change_needed": None, "quantity_needed": None,
                                              "reachable": False, "cash_equivalent": None}


# ---------------------------------------------------------------- documento


def test_unavailable_lever_has_only_reason_keys_and_is_out_of_rankings(docs):
    doc = docs["AMBER"]
    ap = lever_of(doc, "ap_on_time")
    assert ap == {"lever": "ap_on_time", "type": "treasury", "component": "payments", "available": False, "reason": "ap_component_unavailable"}
    assert lever_of(doc, "ar_faster")["reason"] == "ar_component_unavailable"
    assert [lv["lever"] for lv in doc["levers"]] == list(SENSITIVITY_LEVERS)
    assert set(doc["ranking"]["by_pct"]) == {"cut_outflow", "raise_inflow", "debt_service_cut"}
    assert "ap_on_time" not in doc["ranking"]["by_cash"] and "ar_faster" not in doc["ranking"]["by_pct"]
    noflow = docs["NOFLOW"]
    assert lever_of(noflow, "debt_service_cut")["reason"] == "debt_without_inflow_indicator"
    assert lever_of(noflow, "cut_outflow")["available"] and lever_of(noflow, "cut_outflow")["slope_now"]["level_per_pct"] == 0.0


def test_rankings_sorted_and_by_cash_excludes_levers_without_equivalent(docs):
    doc = docs["FULL"]
    levers = {lv["lever"]: lv for lv in doc["levers"] if lv["available"]}
    assert len(levers) == 5
    pct = [levers[l]["slope_now"]["level_per_pct"] for l in doc["ranking"]["by_pct"]]
    assert pct == sorted(pct, reverse=True) and len(doc["ranking"]["by_pct"]) == 5
    assert set(doc["ranking"]["by_cash"]) == {"cut_outflow", "debt_service_cut", "ap_on_time"}
    cash = [levers[l]["slope_now"]["level_per_10k"] for l in doc["ranking"]["by_cash"]]
    assert cash == sorted(cash, reverse=True)
    assert levers["raise_inflow"]["slope_now"]["level_per_10k"] is None and levers["ar_faster"]["slope_now"]["level_per_10k"] is None
    assert doc["ranking"]["by_pct"][0] == "raise_inflow"  # empate 0,05 entre ap_on_time y ar_faster: orden alfabético
    assert doc["ranking"]["by_pct"][-2:] == ["ap_on_time", "ar_faster"]


def test_feasibility_ap_on_time_depends_on_own_excess_cash():
    def feas(**overrides):
        st = make_group_state([{**FULL, **overrides}], reference_state=REF)
        return feasibility(st.subsidiaries.loc["FULL"], "ap_on_time", CONFIG)
    buffer = max(2.0 * (80000. + 120000. / H), 5000. + 2000.)  # 200.000
    poor = feas(reconstructed_cash=90000.)
    assert poor == {"feasible_alone": False, "cash_needed": 13000., "own_excess_cash": 0., "note": "requiere financiacion"}
    rich = feas(reconstructed_cash=buffer + 13000.)
    assert rich["feasible_alone"] is True and rich["own_excess_cash"] == pytest.approx(13000.) and rich["note"] == "alcanzable con caja propia"
    almost = feas(reconstructed_cash=buffer + 12999.)
    assert almost["feasible_alone"] is False
    unknown = feas(reconstructed_cash=np.nan)
    assert unknown["feasible_alone"] is None and unknown["own_excess_cash"] is None and unknown["note"] == "caja no fiable"
    assert unknown["cash_needed"] == 13000.
    unreliable = make_group_state([{**FULL, "cash_reliable": False}], reference_state=REF)
    assert feasibility(unreliable.subsidiaries.loc["FULL"], "ap_on_time", CONFIG)["feasible_alone"] is None
    other = feasibility(make_group_state([FULL], reference_state=REF).subsidiaries.loc["FULL"], "debt_service_cut", CONFIG)
    assert other == {"feasible_alone": None, "cash_needed": None, "own_excess_cash": 0., "note": "renegociacion con el acreedor"}


def test_baseline_liquidity_and_structural_note(docs):
    amber, full = docs["AMBER"], docs["FULL"]
    assert amber["baseline"]["liquidity"] == {"reconstructed_cash": 25000., "reliable": True,
                                              "buffer": pytest.approx(2 * (121766.7 + 5400.), abs=1e-3), "excess_cash": 0.}
    assert amber["baseline"]["tramo"] == "amber" and amber["baseline"]["score"] == pytest.approx(amber["baseline"]["level"] - 4.8)
    assert amber["structural_note"].startswith("El margen 6m (-0,15) es el componente que arrastra el nivel")
    assert full["structural_note"] is None and full["baseline"]["ap"] == {"overdue_amount": 8000., "due_30": 5000., "due_60": 2000.}
    assert docs["RED"]["structural_note"].startswith("El margen 6m (-0,50)")
    assert full["baseline"]["signals"]["monthly_debt_service"] == 20000. and full["baseline"]["signals"]["ap_delay_w"] == 20.


def test_grid_is_monotone_in_r_and_in_k(docs):
    for doc in docs.values():
        for lever in doc["levers"]:
            if not lever["available"]:
                continue
            rows = lever["grid"]
            assert [g["rel_change"] for g in rows] == list(CONFIG.sensitivity_grid)
            k6 = [g["level_after_k6"] for g in rows]
            assert k6 == sorted(k6) and all(g["level_after_k1"] <= g["level_after_k6"] + 1e-9 for g in rows)
            assert all(doc["baseline"]["level"] <= g["level_after_k1"] + 1e-9 for g in rows)
            for g in rows:
                assert g["score_after_k6"] == pytest.approx(min(100., max(0., g["level_after_k6"] + doc["baseline"]["momentum_adjustment"])), abs=1e-6)
                expected_q = lever["current"] * (1 + g["rel_change"] if lever["direction"] == "increase" else 1 - g["rel_change"])
                assert g["quantity_after"] == pytest.approx(expected_q, rel=1e-6)
                assert set(g) == {"rel_change", "quantity_after", "level_after_k1", "level_after_k6", "score_after_k6", "cash_equivalent"}


def test_not_scored_document(docs):
    doc = docs["NOTSCORED"]
    assert doc["status"] == "not_scored" and doc["score_reason"] == "insufficient_components"
    assert doc["levers"] == [] and doc["ranking"] == {"by_pct": [], "by_cash": []}
    assert doc["baseline"]["level"] is None and doc["baseline"]["tramo"] == "none" and doc["next_tramo_target"] is None
    assert doc["structural_note"] is None and doc["evidence"] == {}
    assert doc["group_context"] == {"has_group_plan": None, "role": None, "steps": []}


def test_document_is_deterministic_and_json_native(state):
    first, second = company_sensitivity(state, "FULL", CONFIG), company_sensitivity(state, "FULL", CONFIG)
    assert pd.Timestamp(first.pop("generated_at")).tzinfo is not None and isinstance(second.pop("generated_at"), str)
    assert first == second
    text = sensitivity_to_json(company_sensitivity(state, "FULL", CONFIG))
    assert json.loads(text)["company_id"] == "FULL"

    def walk(node):
        assert type(node) in (dict, list, str, int, float, bool, type(None)), type(node)
        if isinstance(node, dict):
            for key, value in node.items():
                assert isinstance(key, str)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, float):
            assert math.isfinite(node) and round(node, 6) == node or abs(node) < 1e-3

    walk(first)
    assert first["month"] == "2026-08-01" and first["method"] == "company_sensitivity_v1" and first["schema_version"] == 1
    with pytest.raises(KeyError):
        company_sensitivity(state, "MISSING", CONFIG)


def test_evidence_is_restricted_to_the_company(state, docs):
    doc = docs["FULL"]
    assert doc["evidence"] and all(item["company_id"] == "FULL" for item in doc["evidence"].values())
    assert set(doc["evidence"]) == {eid for eid, item in state.evidence.items() if item["company_id"] == "FULL"}
    fields = {eid: item["field"] for eid, item in doc["evidence"].items()}
    assert {fields[e] for e in lever_of(doc, "cut_outflow")["evidence"]} == {"window_outflow_sum", "level_inflow_sum"}
    assert {fields[e] for e in lever_of(doc, "ap_on_time")["evidence"]} == {"inv_ap_overdue_amount", "inv_ap_due_30_amount",
                                                                             "inv_ap_due_60_amount", "reconstructed_cash"}


def test_render_and_grounding_on_synthetic_documents(docs):
    for cid, doc in docs.items():
        for fmt in ("markdown", "text"):
            text = render_sensitivity(doc, fmt)
            result = validate_grounding(text, doc)
            assert result.ok, (cid, fmt, result)


# ---------------------------------------------------------------- datos reales


@pytest.fixture(scope="module")
def real_inputs():
    if not REAL_DATA:
        pytest.skip("Sin data/processed/scores_v2")
    return load_inputs()


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_group_0064_sensitivities(real_inputs):
    state = build_group_state(real_inputs, "GROUP_0064", "2026-08-01")
    docs = {cid: company_sensitivity(state, cid) for cid in ("COMP_0007", "COMP_0222", "COMP_0738")}
    assert docs["COMP_0222"]["next_tramo_target"] is None and docs["COMP_0222"]["baseline"]["tramo"] == "green"
    assert docs["COMP_0007"]["baseline"]["tramo"] == "amber" and docs["COMP_0007"]["next_tramo_target"] == 70.0
    assert docs["COMP_0738"]["baseline"]["tramo"] == "red" and docs["COMP_0738"]["structural_note"]
    assert docs["COMP_0738"]["baseline"]["signals"]["op_margin_w"] == pytest.approx(-0.80, abs=0.01)
    for cid, doc in docs.items():
        assert doc["status"] == "sensitivity" and doc["inputs_sha256"] == real_inputs.inputs_sha256
        text = render_sensitivity(doc)
        assert validate_grounding(text, doc).ok, cid
    WIP_DIR.mkdir(parents=True, exist_ok=True)
    for cid in ("COMP_0007", "COMP_0738"):
        (WIP_DIR / f"{cid}.json").write_text(sensitivity_to_json(docs[cid]), encoding="utf-8")
        (WIP_DIR / f"{cid}.md").write_text(render_sensitivity(docs[cid]), encoding="utf-8")


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_first_ten_optimizable_companies_august_2026(real_inputs):
    month = pd.Timestamp("2026-08-01")
    rows = real_inputs.rows.loc[real_inputs.rows.month.eq(month) & real_inputs.rows.level.notna()].sort_values("company_id").head(10)
    states = {gid: build_group_state(real_inputs, gid, month) for gid in sorted(rows.group_id.unique())}
    for company_id, group_id in zip(rows.company_id, rows.group_id):
        doc = company_sensitivity(states[group_id], company_id)
        json.dumps(doc, allow_nan=False)
        assert doc["status"] == "sensitivity" and doc["baseline"]["level"] is not None
        reachable = None
        for lever in doc["levers"]:
            if not lever["available"]:
                continue
            k6 = [g["level_after_k6"] for g in lever["grid"]]
            assert k6 == sorted(k6) and all(g["level_after_k1"] <= g["level_after_k6"] + 1e-9 for g in lever["grid"])
            if reachable is None and lever["to_next_tramo"]["reachable"]:
                reachable = lever
        phrase = tramo_change_phrase(reachable, doc["currency"]) if reachable else "ninguna palanca alcanza el siguiente tramo"
        slopes = {lv["lever"]: lv["slope_now"]["level_per_pct"] for lv in doc["levers"] if lv["available"]}
        line = (f"{company_id} nivel {doc['baseline']['level']:.1f} ({doc['baseline']['tramo']}) by_pct="
                f"{[(l, round(slopes[l], 3)) for l in doc['ranking']['by_pct']]} -> {phrase}")
        print(line.encode("ascii", "replace").decode("ascii"))  # consola Windows sin -X utf8
        assert validate_grounding(render_sensitivity(doc), doc).ok, company_id


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_iter_company_sensitivities_is_sorted(real_inputs):
    iterator = iter_company_sensitivities(real_inputs, "2026-08-01")
    seen = [next(iterator)[0] for _ in range(3)]
    assert seen == sorted(seen) and len(set(seen)) == 3
