import math

import pandas as pd
import pytest

from advisor_fixtures import make_group_state
from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.objective import group_utility, levels_by_tramo, subsidiary_weights, tramo, utility, utility_max
from xray.group_advisor.optimizer import (BINDING_BUFFER, BINDING_COVERED, REASON_DONOR_BUFFER, REASON_DONOR_CASH, REASON_FX,
                                          REASON_RECIPIENT_ACTIVITY, REASON_RECIPIENT_NOT_CONSTRAINED, STOP_NO_CANDIDATES,
                                          WorkingState, authoritative_effects, certificate, donor_buffer, generate_candidates,
                                          is_liquidity_constrained, optimize_group, recipient_need)
from xray.group_advisor.plan import STATUS_NO_LEVERS, STATUS_PLAN, STATUS_SINGLE, build_plan, plan_to_json
from xray.group_advisor.state import build_group_state, load_inputs
from xray.paths import PROCESSED_DIR

REAL_DATA = (PROCESSED_DIR / "scores_v2").exists()
CONFIG = AdvisorConfig()
H = CONFIG.horizon_months
GENERATED_AT = "2026-09-19T18:00:00+00:00"


# ---------------------------------------------------------------- constructores de filiales sintéticas


def outflow_for(inflow, margin):
    """`O` tal que `(I−O)/(I+O) = margin`."""
    return inflow * (1 - margin) / (1 + margin)


def donor(cid, cash, inflow=6e6, outflow=4e6, service=0., currency="EUR", **extra):
    """Donante con caja fiable, `O3 = O/H` y sin deuda: margen 0,2 → nivel ≈ 90,4 (verde)."""
    row = {"company_id": cid, "currency": currency, "level_inflow_sum": inflow, "window_outflow_sum": outflow,
           "window_debt_service_sum": service, "tx_outflow_ma3": outflow / H, "reconstructed_cash": cash, "runway_months": 3.0}
    row.update(extra)
    return row


def debtor(cid, inflow, margin, service, **extra):
    """Receptora con deuda y sin caja fiable; `margin −0,25` + `d = 0,3` → nivel ≈ 27 (rojo); `margin 0,5` → ≈ 78,6 (verde)."""
    row = {"company_id": cid, "level_inflow_sum": inflow, "window_outflow_sum": outflow_for(inflow, margin), "window_debt_service_sum": service}
    row.update(extra)
    return row


def ap_recipient(cid, cash, runway, delay=30.):
    """Receptora sin deuda que paga tarde (AP vencido 60k + 30 días 30k) con caja fiable dada."""
    return debtor(cid, 1e5, -0.25, 0., ap_delay_w=delay, ap_delay_count_w=8, inv_ap_overdue_amount=6e4, inv_ap_due_30_amount=3e4,
                  inv_ap_due_60_amount=1.5e4, reconstructed_cash=cash, runway_months=runway, tx_outflow_ma3=outflow_for(1e5, -0.25) / H)


BUFFER_A = 2 * (4e6 / H)          # colchón del donante estándar: κ·O3, sin deuda ni AP
NEED_B = 3e4                      # necesidad D1 de la receptora estándar (S = 30.000; s = 5.000/mes)
FULL_D1_CASH = NEED_B + 2 * NEED_B / H   # caja sobre el colchón para cubrir D1 entera: x + κ·s_b


def steps_of(result):
    return [(s.candidate.action.lever, s.candidate.action.donor, s.candidate.action.recipient, s.candidate.action.fraction) for s in result.steps]


def strip_generated(plan):
    return {key: value for key, value in plan.items() if key != "generated_at"}


# ---------------------------------------------------------------- objetivo


def test_utility_is_concave_with_spec_anchor_values():
    assert utility(100, CONFIG) == 210 and utility_max(CONFIG) == 210
    assert utility(40, CONFIG) == 120 and utility(70, CONFIG) == 180 and utility(0, CONFIG) == 0
    assert utility(31, CONFIG) - utility(30, CONFIG) > utility(51, CONFIG) - utility(50, CONFIG) > utility(81, CONFIG) - utility(80, CONFIG)
    assert utility(31, CONFIG) - utility(30, CONFIG) == pytest.approx(3.0)
    assert math.isnan(utility(float("nan"), CONFIG)) and math.isnan(utility(None, CONFIG))
    assert utility(120, CONFIG) == 210 and utility(-5, CONFIG) == 0


def test_group_utility_is_normalised_and_ignores_nan():
    assert group_utility([100, 100, 100], [1, 1, 1], CONFIG) == pytest.approx(100.0)
    assert group_utility([0, 0], None, CONFIG) == 0.0
    assert 0 <= group_utility([12.5, 47.0, 88.0], [1, 1, 1], CONFIG) <= 100
    assert group_utility([40, float("nan"), 70], [1, 1, 1], CONFIG) == pytest.approx((120 + 180) / (2 * 210) * 100)
    assert math.isnan(group_utility([], [], CONFIG)) and math.isnan(group_utility([float("nan")], [1], CONFIG))
    assert group_utility([40, 70], [3, 1], CONFIG) == pytest.approx((3 * 120 + 180) / (4 * 210) * 100)
    with pytest.raises(ValueError):
        group_utility([1, 2], [1], CONFIG)


def test_weights_tramo_and_counts():
    state = make_group_state([donor("A", 1e6), debtor("B", 1e5, -0.25, NEED_B), {"company_id": "C"}])
    assert subsidiary_weights(state, CONFIG) == {"A": 1.0, "B": 1.0, "C": 1.0}
    size = subsidiary_weights(state, AdvisorConfig(subsidiary_weighting="size"))
    assert size["A"] == pytest.approx(1e7) and size["B"] == pytest.approx(1e5 + outflow_for(1e5, -0.25)) and size["C"] == 0.0
    assert [tramo(v, CONFIG) for v in (0, 39.99, 40, 69.99, 70, 100, float("nan"))] == ["red", "red", "amber", "amber", "green", "green", "none"]
    assert levels_by_tramo([10, 40, 70, float("nan"), 99], CONFIG) == {"red": 1, "amber": 1, "green": 2}


# ---------------------------------------------------------------- reglas del optimizador


def test_donor_buffer_liquidity_and_need_helpers():
    row = {"tx_outflow_ma3": 1e5, "monthly_debt_service": 1e4, "inv_ap_due_30_amount": 3e5, "inv_ap_due_60_amount": float("nan")}
    assert donor_buffer(row, 0.0, CONFIG) == pytest.approx(3e5)
    assert donor_buffer(row, 5e4, CONFIG) == pytest.approx(2 * 1.6e5)
    assert math.isnan(donor_buffer({"tx_outflow_ma3": float("nan")}, 0.0, CONFIG))
    constrained = {"reconstructed_cash": 1e4, "cash_reliable": True, "inv_ap_overdue_amount": 2e4, "inv_ap_due_30_amount": 0., "runway_months": 4.}
    assert is_liquidity_constrained(constrained, CONFIG) is True
    assert is_liquidity_constrained({**constrained, "reconstructed_cash": 5e4}, CONFIG) is False
    assert is_liquidity_constrained({**constrained, "reconstructed_cash": 5e4, "runway_months": 0.5}, CONFIG) is True
    assert is_liquidity_constrained({"reconstructed_cash": 5e4, "cash_reliable": False, "runway_months": float("nan")}, CONFIG) is None
    assert recipient_need({"monthly_debt_service": 5e3}, "D1", CONFIG) == pytest.approx(3e4)
    assert recipient_need(constrained, "P", CONFIG) == pytest.approx(1e4)
    assert math.isnan(recipient_need({**constrained, "cash_reliable": False}, "P", CONFIG))


def test_improvement_goes_to_red_subsidiary_before_green():
    state = make_group_state([donor("A", BUFFER_A + FULL_D1_CASH), debtor("B", 1e5, -0.25, NEED_B), debtor("C", 1e5, 0.5, NEED_B)])
    levels = state.subsidiaries.level
    assert levels["B"] < 40 < 70 < levels["C"]
    result = optimize_group(state, CONFIG)
    assert result.steps and all(step[2] == "B" for step in steps_of(result))
    assert result.working_final.fraction_used[("D1", "B")] == pytest.approx(1.0)
    assert result.stopped_because == STOP_NO_CANDIDATES


def test_donor_buffer_blocks_and_is_reported():
    exact = make_group_state([donor("A", BUFFER_A), debtor("B", 1e5, -0.25, NEED_B)])
    result = optimize_group(exact, CONFIG)
    assert not result.steps and result.stopped_because == STOP_NO_CANDIDATES
    pair = next(p for p in result.pairs if (p.lever, p.donor, p.recipient) == ("D1", "A", "B"))
    assert pair.feasible is False and pair.reason == REASON_DONOR_BUFFER and pair.donor_capacity == 0.0
    extra = 2e4
    partial = make_group_state([donor("A", BUFFER_A + extra), debtor("B", 1e5, -0.25, NEED_B)])
    result = optimize_group(partial, CONFIG)
    assert result.steps
    committed = sum(s.candidate.action.amount_donor_ccy for s in result.steps)
    assert committed <= extra + 1e-6 and committed < NEED_B
    assert any(BINDING_BUFFER in s.candidate.binding for s in result.steps)
    plan = build_plan(partial, CONFIG, GENERATED_AT)
    assert any("donor_buffer" in s["binding_constraints"] for s in plan["plan"]["steps"])
    assert plan["plan"]["cash_committed_by_donor"]["A"]["donor_ccy"] == pytest.approx(committed)


def test_two_donors_share_one_need_without_overfunding():
    state = make_group_state([donor("A1", BUFFER_A + 2e4), donor("A2", BUFFER_A + 2e4), debtor("B", 1e5, -0.25, NEED_B)])
    result = optimize_group(state, CONFIG)
    fractions = [s.candidate.action.fraction for s in result.steps if s.candidate.action.recipient == "B"]
    assert sum(fractions) <= 1.0 + 1e-9 and sum(fractions) == pytest.approx(1.0)
    assert {s.candidate.action.donor for s in result.steps} == {"A1", "A2"}
    assert BINDING_COVERED in result.steps[-1].candidate.binding
    assert result.working_final.fraction_used[("D1", "B")] == pytest.approx(1.0)


def test_same_currency_preferred_on_exact_efficiency_tie():
    config = AdvisorConfig(fx_rates_to_eur={"EUR": 1.0, "USD": 1.0})
    state = make_group_state([donor("A0_USD", BUFFER_A + 8e4, currency="USD"), donor("A1_EUR", BUFFER_A + 8e4),
                              debtor("B", 1e5, -0.25, NEED_B)], config=config)
    working = WorkingState.from_state(state, config)
    candidates = generate_candidates(state, working, config).candidates
    best, cross = candidates[0], next(c for c in candidates if c.action.donor == "A0_USD")
    assert best.action.donor == "A1_EUR" and best.action.fx_applied is None
    assert best.efficiency == pytest.approx(cross.efficiency) and best.x_report == pytest.approx(cross.x_report)
    result = optimize_group(state, config)
    assert all(s.candidate.action.donor == "A1_EUR" for s in result.steps)


def test_cross_currency_action_converts_amounts_and_declares_fx_assumption():
    config = AdvisorConfig(fx_rates_to_eur={"EUR": 1.0, "USD": 1.1}, fx_source="test", fx_asof="2026-01-01")
    state = make_group_state([donor("A_USD", BUFFER_A + 8e4, currency="USD"), debtor("B", 1e5, -0.25, NEED_B)], config=config)
    plan = build_plan(state, config, GENERATED_AT)
    assert plan["status"] == STATUS_PLAN
    for step in plan["plan"]["steps"]:
        amount = step["amount"]
        assert amount["fx_applied"] == pytest.approx(1.1)
        assert amount["donor_ccy"] == pytest.approx(amount["recipient_ccy"] * 1.1)
        assert amount["reporting_ccy"] == pytest.approx(amount["recipient_ccy"])
    total_recipient = sum(s["amount"]["recipient_ccy"] for s in plan["plan"]["steps"])
    assert plan["plan"]["cash_committed_by_donor"]["A_USD"]["donor_ccy"] == pytest.approx(total_recipient * 1.1)
    assert plan["plan"]["cash_committed_by_donor"]["A_USD"]["reporting_ccy"] == pytest.approx(total_recipient)
    assert "fx_fixed_rate: tabla test a 2026-01-01" in plan["assumptions"]
    lever = next(l for l in plan["levers_evaluated"] if (l["lever"], l["donor"], l["recipient"]) == ("D1", "A_USD", "B"))
    assert lever["feasible"] is True and lever["fx_applied"] == pytest.approx(1.1)


def test_cross_currency_without_table_is_infeasible():
    state = make_group_state([donor("A_USD", BUFFER_A + 8e4, currency="USD"), debtor("B", 1e5, -0.25, NEED_B)])
    plan = build_plan(state, CONFIG, GENERATED_AT)
    assert plan["status"] == STATUS_NO_LEVERS and not plan["plan"]["steps"]
    lever = next(l for l in plan["levers_evaluated"] if (l["lever"], l["donor"], l["recipient"]) == ("D1", "A_USD", "B"))
    assert lever["feasible"] is False and lever["reason"] == REASON_FX and lever["fx_applied"] is None
    assert not any(a.startswith("fx_fixed_rate") for a in plan["assumptions"])


def test_p_lever_only_when_recipient_is_liquidity_constrained():
    constrained = make_group_state([donor("A", BUFFER_A + 2e5), ap_recipient("B", cash=1.2e4, runway=0.1)])
    result = optimize_group(constrained, CONFIG)
    assert result.steps and all(s.candidate.action.lever == "P" for s in result.steps)
    first = result.steps[0].candidate.action
    assert first.psi == pytest.approx(first.amount_recipient_ccy / 9e4)
    assert sum(s.candidate.action.amount_recipient_ccy for s in result.steps) <= 7.8e4 + 1e-6
    plan = build_plan(constrained, CONFIG, GENERATED_AT)
    assert plan["diagnosis"]["unexplained_ap_delays"] == []
    assert plan["plan"]["steps"][0]["effects"][f"k{H}"]["recipient"]["component"] == "payments"
    assert plan["plan"]["steps"][0]["effects"][f"k{H}"]["recipient"]["signal_after"] < 30.0
    assert plan["plan"]["steps"][0]["effects"]["k1"]["donor"]["signal_before"] is None

    cash_rich = make_group_state([donor("A", BUFFER_A + 2e5), ap_recipient("B", cash=2e5, runway=5.0)])
    plan = build_plan(cash_rich, CONFIG, GENERATED_AT)
    assert plan["status"] == STATUS_NO_LEVERS and not plan["plan"]["steps"]
    [unexplained] = plan["diagnosis"]["unexplained_ap_delays"]
    assert unexplained["company_id"] == "B" and unexplained["ap_need"] == pytest.approx(9e4) and unexplained["ap_delay_w"] == 30.0
    lever = next(l for l in plan["levers_evaluated"] if (l["lever"], l["donor"], l["recipient"]) == ("P", "A", "B"))
    assert lever["reason"] == REASON_RECIPIENT_NOT_CONSTRAINED and lever["need_recipient_ccy"] == 0.0
    assert "B" in plan["diagnosis"]["recipient_candidates"]


def rich_rows():
    return [donor("A", BUFFER_A + 2e5),
            debtor("B", 1e5, -0.25, NEED_B, ap_delay_w=30., ap_delay_count_w=8, inv_ap_overdue_amount=6e4, inv_ap_due_30_amount=3e4,
                   inv_ap_due_60_amount=1.5e4, reconstructed_cash=1.2e4, runway_months=0.1, tx_outflow_ma3=outflow_for(1e5, -0.25) / H),
            debtor("C", 1e5, 0.5, NEED_B),
            {"company_id": "D"}]


def test_plan_is_deterministic_and_invariant_to_row_order():
    rows = rich_rows()
    first = build_plan(make_group_state(rows, consolidated_scores={"EUR": 51.2}), CONFIG, GENERATED_AT)
    second = build_plan(make_group_state(rows, consolidated_scores={"EUR": 51.2}), CONFIG, GENERATED_AT)
    permuted = build_plan(make_group_state(rows[::-1], consolidated_scores={"EUR": 51.2}), CONFIG, GENERATED_AT)
    assert first == second and strip_generated(first) == strip_generated(permuted)
    assert plan_to_json(first) == plan_to_json(second)
    assert first["status"] == STATUS_PLAN and len(first["plan"]["steps"]) >= 2
    assert {s["lever"] for s in first["plan"]["steps"]} == {"D1", "P"}
    assert first["coverage"] == {"subsidiaries": 4, "optimizable": 3, "not_scored": 1, "with_reliable_cash": 2,
                                 "with_debt_component": 3, "with_ap_component": 1, "currencies": ["EUR"]}
    assert first["baseline"]["consolidated_group_currency_score"] == {"EUR": 51.2}
    not_scored = next(s for s in first["baseline"]["subsidiaries"] if s["company_id"] == "D")
    assert not_scored["level"] is None and not_scored["tramo"] == "none" and not_scored["score_reason"] == "insufficient_components"


def test_each_step_gains_at_least_min_gain_and_utility_is_monotone():
    state = make_group_state(rich_rows())
    result = optimize_group(state, CONFIG)
    plan = build_plan(state, CONFIG, GENERATED_AT)
    previous = plan["baseline"]["group_utility_0_100"]
    for greedy_step, step in zip(result.steps, plan["plan"]["steps"]):
        assert greedy_step.candidate.delta_utility >= CONFIG.min_gain_utility
        effect = step["effects"][f"k{H}"]
        assert effect["group_utility_after"] - effect["group_utility_before"] >= CONFIG.min_gain_utility - 1e-6
        assert effect["group_utility_before"] == pytest.approx(previous, abs=1e-6)
        assert effect["group_utility_after"] >= previous
        previous = effect["group_utility_after"]
    assert plan["plan"]["totals"][f"k{H}"]["group_utility_after"] == pytest.approx(previous, abs=1e-6)
    assert plan["plan"]["totals"]["k1"]["group_utility_after"] >= plan["baseline"]["group_utility_0_100"]


def test_totals_are_recomputable_from_final_working_levels():
    state = make_group_state(rich_rows())
    result = optimize_group(state, CONFIG)
    plan = build_plan(state, CONFIG, GENERATED_AT)
    final = result.working_final
    for k in CONFIG.report_k:
        levels = [final.levels_by_k[k][cid] for cid in final.ids]
        expected = group_utility(levels, [final.weights[cid] for cid in final.ids], CONFIG)
        assert plan["plan"]["totals"][f"k{k}"]["group_utility_after"] == pytest.approx(expected, abs=1e-6)
        assert plan["plan"]["totals"][f"k{k}"]["min_level_after"] == pytest.approx(min(levels), abs=1e-6)
    assert plan["plan"]["totals"][f"k{H}"]["group_utility_after"] == pytest.approx(result.utility_after_by_k[H], abs=1e-6)
    assert plan["baseline"]["group_utility_0_100"] == pytest.approx(result.utility_before, abs=1e-6)


def test_batch_evaluation_matches_evaluate_action():
    state = make_group_state(rich_rows())
    working = WorkingState.from_state(state, CONFIG)
    candidates = generate_candidates(state, working, CONFIG).candidates
    assert candidates
    for candidate in candidates:
        reference = authoritative_effects(state, working, candidate)
        for k, effect in candidate.effects.items():
            expected = reference[k]
            for name in ("donor_level_before", "donor_level_after", "recipient_level_before", "recipient_level_after",
                         "donor_signal_before", "donor_signal_after", "recipient_signal_before", "recipient_signal_after"):
                a, b = getattr(effect, name), getattr(expected, name)
                assert (math.isnan(a) and math.isnan(b)) or a == pytest.approx(b, abs=1e-9), (name, candidate.action)
            assert effect.recipient_component_dropped == expected.recipient_component_dropped
            assert effect.donor_hits_zero_inflow_indicator == expected.donor_hits_zero_inflow_indicator
            assert effect.recipient_components_after == expected.recipient_components_after


def test_certificate_detects_greedy_gap_and_zero_gap():
    buffer = 2 * (10e6 / H)
    big_donor = donor("A", buffer + 8e4, inflow=20e6, outflow=10e6)
    cheap = debtor("B", 114e3, -0.1, 16e3)        # muy eficiente por unidad de caja
    large = debtor("C", 200e3, -0.1, 60e3)        # más ΔG total, menos eficiente
    state = make_group_state([big_donor, cheap, large])
    result = optimize_group(state, CONFIG)
    assert steps_of(result)[0] == ("D1", "A", "B", 1.0)
    cert = certificate(state, CONFIG, result)
    assert cert["checked"] is True and cert["greedy_gap"] > 0
    assert cert["best_pair_utility"] >= cert["best_single_utility"] >= result.utility_before
    assert cert["greedy_utility"] == pytest.approx(result.steps[min(2, len(result.steps)) - 1].utility_after_by_k[H])
    single = make_group_state([big_donor, cheap])
    result = optimize_group(single, CONFIG)
    cert = certificate(single, CONFIG, result)
    assert cert["checked"] is True and cert["greedy_gap"] == 0.0
    assert cert["best_single_utility"] == pytest.approx(cert["best_pair_utility"]) == pytest.approx(cert["greedy_utility"])
    many = make_group_state([big_donor, cheap, large] + [debtor(f"R{i}", 1e5, 0.0, 1e3) for i in range(4)])
    cert = certificate(many, CONFIG)
    assert cert["checked"] is False and cert["greedy_gap"] is None and cert["best_pair_utility"] is None


def test_single_subsidiary_and_unreliable_cash_statuses():
    single = build_plan(make_group_state([donor("A", 1e6)]), CONFIG, GENERATED_AT)
    assert single["status"] == STATUS_SINGLE and single["plan"]["stopped_because"] == "single_subsidiary"
    assert single["levers_evaluated"] == [] and single["plan"]["steps"] == [] and single["certificate"]["checked"] is False
    assert single["diagnosis"]["donor_candidates"] == [] and single["diagnosis"]["recipient_candidates"] == []
    assert single["certificate"]["greedy_utility"] == pytest.approx(single["baseline"]["group_utility_0_100"])
    unreliable = make_group_state([debtor("A", 6e6, 0.2, 0., tx_outflow_ma3=1e5), debtor("B", 1e5, -0.25, NEED_B),
                                   debtor("C", 1e5, 0.5, NEED_B)])
    assert not unreliable.subsidiaries.cash_reliable.any()
    plan = build_plan(unreliable, CONFIG, GENERATED_AT)
    assert plan["status"] == STATUS_NO_LEVERS and plan["plan"]["steps"] == []
    assert plan["levers_evaluated"] and all(l["reason"] == REASON_DONOR_CASH and l["feasible"] is False for l in plan["levers_evaluated"])
    assert all(l["donor_capacity"] is None for l in plan["levers_evaluated"])
    assert plan["plan"]["totals"][f"k{H}"]["group_utility_after"] == pytest.approx(plan["baseline"]["group_utility_0_100"])
    assert plan["diagnosis"]["donor_candidates"] == [] and plan["rejected_alternatives"] == []


def test_zero_inflow_recipient_drops_debt_component_without_phantom_100():
    state = make_group_state([donor("A", BUFFER_A + 8e4),
                              debtor("B", 0., 0.0, NEED_B, window_outflow_sum=1e5, ap_delay_w=0., ap_delay_count_w=10)])
    row = state.subsidiaries.loc["B"]
    assert row.debt_without_inflow_w and row.level_debt == 0.0 and row.optimizable
    result = optimize_group(state, CONFIG)
    assert steps_of(result) == [("D1", "A", "B", 1.0)]
    effect = result.steps[0].effects[H]
    assert effect.recipient_component_dropped is True and effect.recipient_components_after["debt"] is None
    assert effect.recipient_level_before < effect.recipient_level_after < 100
    assert effect.recipient_level_after == pytest.approx(0.15 * 100 / 0.6)
    plan = build_plan(state, CONFIG, GENERATED_AT)
    step = plan["plan"]["steps"][0]["effects"][f"k{H}"]
    assert step["recipient"]["component_dropped"] is True and step["recipient"]["level_after"] < 100
    assert plan["plan"]["steps"][0]["effects"]["k1"]["recipient"]["component_dropped"] is False


def test_experimental_profile_still_publishes_the_ga06_low_activity_d1():
    state = make_group_state([donor("A", BUFFER_A + 8e4),
                              debtor("B", 358., -0.99, 885., tx_outflow_ma3=2e4)])
    plan = build_plan(state, CONFIG, GENERATED_AT)
    assert plan["status"] == STATUS_PLAN
    assert plan["plan"]["steps"][0]["lever"] == "D1"
    assert plan["plan"]["steps"][0]["recipient"] == "B"
    assert not plan["config"]["production_safe"]


def test_production_profile_rejects_the_ga06_low_activity_artifact():
    config = AdvisorConfig(levers=("D1", "P", "O"), production_safe=True)
    state = make_group_state([donor("A", BUFFER_A + 8e4),
                              debtor("B", 358., -0.99, 885., tx_outflow_ma3=2e4)])
    plan = build_plan(state, config, GENERATED_AT)
    assert plan["plan"]["steps"] == []
    reasons = {item["reason"] for item in plan["levers_evaluated"] if item["recipient"] == "B"}
    assert REASON_RECIPIENT_ACTIVITY in reasons
    assert plan["config"]["production_safe"] is True


def test_production_profile_only_keeps_steps_that_improve_the_worst_without_downgrading_donor():
    config = AdvisorConfig(levers=("D1", "P", "O"), production_safe=True)
    state = make_group_state(rich_rows(), config=config)
    plan = build_plan(state, config, GENERATED_AT)
    assert plan["status"] == STATUS_PLAN and plan["plan"]["steps"]
    levels = {item["company_id"]: item["level"] for item in plan["baseline"]["subsidiaries"] if item["level"] is not None}
    baseline_signals = {item["company_id"]: item["signals"] for item in plan["baseline"]["subsidiaries"]}
    for step in plan["plan"]["steps"]:
        k1, kh = step["effects"]["k1"], step["effects"][f"k{H}"]
        assert k1["group_utility_after"] >= k1["group_utility_before"] - 1e-9
        before_min = min(levels.values())
        levels[step["donor"]] = kh["donor"]["level_after"]
        levels[step["recipient"]] = kh["recipient"]["level_after"]
        assert min(levels.values()) > before_min
        assert tramo(kh["donor"]["level_after"], config) == tramo(kh["donor"]["level_before"], config)
        assert not kh["recipient"]["component_dropped"]
        if step["lever"] in ("D1", "O"):
            signals = baseline_signals[step["recipient"]]
            assert signals["level_inflow_sum"] >= config.min_recipient_inflow_6m
            assert signals["level_inflow_sum"] / signals["window_outflow_sum"] >= config.min_recipient_inflow_outflow_ratio


def test_rejected_alternatives_carry_reasons_and_evidence_is_linked():
    plan = build_plan(make_group_state(rich_rows()), CONFIG, GENERATED_AT)
    assert plan["rejected_alternatives"]
    assert len(plan["rejected_alternatives"]) <= (len(plan["plan"]["steps"]) + 1) * CONFIG.rejected_alternatives_kept
    applied = {(s["lever"], s["donor"], s["recipient"]) for s in plan["plan"]["steps"]}
    for alternative in plan["rejected_alternatives"]:
        if (alternative["lever"], alternative["donor"], alternative["recipient"]) in applied:
            assert alternative["reason"] in ("fraction_cap", "below_min_gain", "donor_buffer", "donor_level_floor")
    for alternative in plan["rejected_alternatives"]:
        assert set(alternative) == {"lever", "donor", "recipient", "reason", f"delta_utility_k{H}"} and alternative["reason"]
    for step in plan["plan"]["steps"]:
        assert step["evidence"] and all(ev in plan["evidence"] for ev in step["evidence"])
        assert {plan["evidence"][ev]["company_id"] for ev in step["evidence"]} <= {step["donor"], step["recipient"]}
    assert plan["diagnosis"]["bottleneck"]["company_id"] == "B" and "operations" in plan["diagnosis"]["bottleneck"]["weakest_components"]
    assert plan["diagnosis"]["structural_flags"][0]["note"] == "margen 6m -0,25: no es palanca de tesoreria"


# ---------------------------------------------------------------- datos reales


@pytest.fixture(scope="module")
def real_inputs():
    if not REAL_DATA:
        pytest.skip("Sin data/processed/scores_v2")
    return load_inputs()


def _check_plan(plan):
    previous = plan["baseline"]["group_utility_0_100"]
    for step in plan["plan"]["steps"]:
        after = step["effects"][f"k{H}"]["group_utility_after"]
        assert after >= previous - 1e-9
        previous = after
    if plan["plan"]["steps"]:
        assert plan["plan"]["totals"][f"k{H}"]["group_utility_after"] == pytest.approx(previous, abs=1e-6)
    return previous


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_real_group_0064_plan_builds(real_inputs):
    state = build_group_state(real_inputs, "GROUP_0064", pd.Timestamp("2026-08-01"))
    plan = build_plan(state, CONFIG)
    assert plan["group_id"] == "GROUP_0064" and plan["coverage"]["optimizable"] >= 3
    assert {"COMP_0007", "COMP_0222", "COMP_0738"} <= {s["company_id"] for s in plan["baseline"]["subsidiaries"]}
    after = _check_plan(plan)
    print(f"\nGROUP_0064: status={plan['status']} steps={len(plan['plan']['steps'])} "
          f"G {plan['baseline']['group_utility_0_100']:.2f} -> {after:.2f} "
          f"levers={[(s['lever'], s['donor'], s['recipient'], s['fraction']) for s in plan['plan']['steps']]} "
          f"stopped={plan['plan']['stopped_because']} certificate={plan['certificate']}")
    text = plan_to_json(plan)
    assert "NaN" not in text and "Infinity" not in text


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_real_first_five_multi_subsidiary_groups(real_inputs):
    month = pd.Timestamp("2026-08-01")
    chosen = []
    for group_id in real_inputs.group_ids(month):
        state = build_group_state(real_inputs, group_id, month)
        if len(state.optimizable_ids) >= 2:
            chosen.append(state)
        if len(chosen) == 5:
            break
    assert len(chosen) == 5
    for state in chosen:
        plan = build_plan(state, CONFIG)
        assert plan["status"] in (STATUS_PLAN, STATUS_NO_LEVERS)
        after = _check_plan(plan)
        print(f"\n{state.group_id}: status={plan['status']} steps={len(plan['plan']['steps'])} "
              f"G {plan['baseline']['group_utility_0_100']:.2f} -> {after:.2f} "
              f"levers={[(s['lever'], s['donor'], s['recipient'], s['fraction']) for s in plan['plan']['steps']]} "
              f"stopped={plan['plan']['stopped_because']}")
