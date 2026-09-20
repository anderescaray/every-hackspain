"""D48 · Palanca O: la donante asume pagos operativos de la receptora (pagos centralizados)."""
import copy
import math

import pandas as pd
import pytest
from advisor_fixtures import derive_signals, make_group_state

from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.counterfactual import apply_o, outflow_add
from xray.group_advisor.optimizer import (REASON_DONOR_OUTFLOW, REASON_RECIPIENT_NO_OUTFLOW,
                                          REASON_RECIPIENT_OUTFLOW, WorkingState, donor_buffer, donor_reason,
                                          generate_candidates, recipient_need, recipient_reason)
from xray.group_advisor.pipeline import default_config
from xray.group_advisor.plan import build_plan
from xray.group_advisor.state import iter_group_states, load_inputs
from xray.paths import PROCESSED_DIR

REAL_DATA = (PROCESSED_DIR / "scores_v2").exists()


def row(inflow, outflow, service=math.nan):
    margin, debt, indicator = derive_signals(inflow, outflow, service)
    return {"level_inflow_sum": inflow, "window_outflow_sum": outflow, "window_debt_service_sum": service,
            "op_margin_w": margin, "debt_service_w": debt, "debt_without_inflow_w": indicator}


def test_group_external_spending_is_unchanged_only_who_pays():
    donor, recipient = row(1_200_000., 600_000.), row(300_000., 330_000.)
    a, b = apply_o(donor, recipient, 0.5, 6, 6, monthly_outflow_b_in_donor_ccy=330_000. / 6)
    assert a["window_outflow_sum"] == pytest.approx(600_000. + 165_000.)     # la donante asume la mitad
    assert b["window_outflow_sum"] == pytest.approx(165_000.)
    assert a["window_outflow_sum"] + b["window_outflow_sum"] == pytest.approx(600_000. + 330_000.)
    assert b["op_margin_w"] > recipient["op_margin_w"] and a["op_margin_w"] < donor["op_margin_w"]


def test_effect_grows_with_k():
    recipient = row(300_000., 330_000.)
    _, b1 = apply_o(row(1_000_000., 400_000.), recipient, 1.0, 1, 6, 55_000.)
    _, b3 = apply_o(row(1_000_000., 400_000.), recipient, 1.0, 3, 6, 55_000.)
    _, b6 = apply_o(row(1_000_000., 400_000.), recipient, 1.0, 6, 6, 55_000.)
    assert b1["window_outflow_sum"] == pytest.approx(330_000. * 5 / 6)       # k=1 de H=6: un sexto aplicado
    assert b3["window_outflow_sum"] == pytest.approx(165_000.)               # la mitad del régimen
    assert b6["window_outflow_sum"] == pytest.approx(0.)                     # régimen completo


def test_outflow_add_keeps_missing_data_missing_and_refuses_negative():
    assert math.isnan(outflow_add(row(100., math.nan), 10., 6, 6)["window_outflow_sum"])
    with pytest.raises(ValueError, match="negativas"):
        outflow_add(row(100., 60.), -100., 6, 6)


def test_recipient_needs_observed_operating_outflow():
    config = AdvisorConfig()
    assert recipient_reason(row(300_000., 330_000.), "O", config) is None
    assert recipient_reason(row(300_000., 0.), "O", config) == REASON_RECIPIENT_NO_OUTFLOW
    assert recipient_reason(row(300_000., math.nan), "O", config) == REASON_RECIPIENT_OUTFLOW
    assert recipient_need(row(300_000., 330_000.), "O", config) == pytest.approx(330_000. / 6)


def test_donor_distinguishes_missing_outflow_from_observed_zero():
    config = AdvisorConfig(levers=("O",))
    base = {**row(300_000., 0.), "cash_reliable": True, "tx_outflow_ma3": 0.}
    assert donor_reason(base, "O", 100_000., config) is None
    assert donor_reason({**base, "window_outflow_sum": math.nan}, "O", 100_000., config) == REASON_DONOR_OUTFLOW


def test_lever_o_is_opt_in_and_produces_candidates_when_enabled():
    rows = [{"company_id": "A", **row(2_000_000., 900_000.), "reconstructed_cash": 900_000., "runway_months": 6.,
             "tx_outflow_ma3": 150_000.},
            {"company_id": "B", **row(300_000., 360_000.), "reconstructed_cash": 20_000., "runway_months": 0.4,
             "tx_outflow_ma3": 60_000.}]
    assert AdvisorConfig().levers == ("D1", "P")                              # por defecto no cambia nada
    config = AdvisorConfig(levers=("D1", "P", "O"))
    state = make_group_state(rows, config=config)
    working = WorkingState.from_state(state, config)
    candidates = generate_candidates(state, working, config).candidates
    chosen = [c for c in candidates if c.action.lever == "O"]
    assert chosen, "con la palanca activada debe haber candidatos O"
    best = max(chosen, key=lambda c: c.delta_utility)
    assert best.action.donor == "A" and best.action.recipient == "B"
    effect = best.effects[config.horizon_months]
    assert effect.recipient_level_after > effect.recipient_level_before
    assert effect.donor_level_before - effect.donor_level_after <= config.donor_level_floor_drop


def test_lever_o_converts_cross_currency_amount_once():
    config = AdvisorConfig(levers=("O",), fx_rates_to_eur={"EUR": 1.0, "USD": 1.25},
                           reporting_currency="EUR", fx_source="test", fx_asof="2026-09-01")
    rows = [{"company_id": "A", "currency": "EUR", **row(2_000_000., 900_000.),
             "reconstructed_cash": 2_000_000., "runway_months": 6., "tx_outflow_ma3": 150_000.},
            {"company_id": "B", "currency": "USD", **row(300_000., 360_000.),
             "reconstructed_cash": 20_000., "runway_months": .4, "tx_outflow_ma3": 60_000.}]
    state = make_group_state(rows, config=config)
    candidates = generate_candidates(state, WorkingState.from_state(state, config), config).candidates
    candidate = next(c for c in candidates if c.action.donor == "A" and c.action.recipient == "B"
                     and c.action.fraction == .25)
    assert candidate.action.amount_recipient_ccy == pytest.approx(90_000.)
    assert candidate.action.amount_donor_ccy == pytest.approx(72_000.)  # USD / 1,25 -> EUR
    assert candidate.x_report == pytest.approx(72_000.)


def test_generate_o_candidates_is_idempotent_and_does_not_mutate_working_state():
    config = AdvisorConfig(levers=("O",))
    state = make_group_state([
        {"company_id": "A", **row(2_000_000., 900_000.), "reconstructed_cash": 900_000.,
         "runway_months": 6., "tx_outflow_ma3": 150_000.},
        {"company_id": "B", **row(300_000., 360_000.), "reconstructed_cash": 20_000.,
         "runway_months": .4, "tx_outflow_ma3": 60_000.},
    ], config=config)
    working = WorkingState.from_state(state, config)
    before_rows = {k: pd.DataFrame.from_dict(copy.deepcopy(rows), orient="index").sort_index(axis=1)
                   for k, rows in working.rows_by_k.items()}
    before_levels = copy.deepcopy(working.levels_by_k)
    before_cash = dict(working.cash)
    first = generate_candidates(state, working, config)
    second = generate_candidates(state, working, config)
    first_keys = [(c.action, c.delta_utility, c.efficiency) for c in first.candidates]
    second_keys = [(c.action, c.delta_utility, c.efficiency) for c in second.candidates]
    assert first_keys == second_keys
    for k, rows in working.rows_by_k.items():
        pd.testing.assert_frame_equal(pd.DataFrame.from_dict(rows, orient="index").sort_index(axis=1), before_rows[k])
        assert working.levels_by_k[k] == pytest.approx(before_levels[k], nan_ok=True)
    assert working.cash == before_cash
    assert not working.fraction_used and not working.assumed_service


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_real_o_plans_respect_cumulative_donor_buffer_and_level_floor():
    """Replay de R2/R5 sobre todos los planes reales, no solo sobre fixtures felices."""
    config = default_config(levers=("D1", "P", "O"))
    inputs = load_inputs(PROCESSED_DIR, config)
    checked_steps = o_steps = 0
    for state in iter_group_states(inputs, pd.Timestamp("2026-08-01"), config):
        plan = build_plan(state, config)
        rows = {cid: state.subsidiaries.loc[cid].to_dict() for cid in state.subsidiaries.index}
        baseline = {item["company_id"]: item["level"] for item in plan["baseline"]["subsidiaries"]
                    if item["level"] is not None}
        cash = {cid: float(row["reconstructed_cash"]) for cid, row in rows.items()
                if bool(row.get("cash_reliable")) and pd.notna(row.get("reconstructed_cash"))}
        assumed = dict.fromkeys(rows, 0.0)
        for step in plan["plan"]["steps"]:
            checked_steps += 1
            o_steps += step["lever"] == "O"
            donor = step["donor"]
            amount = float(step["amount"]["donor_ccy"])
            cash[donor] -= amount
            if step["lever"] in ("D1", "O"):
                assumed[donor] += amount / config.horizon_months
            buffer = donor_buffer(rows[donor], assumed[donor], config)
            assert cash[donor] >= buffer - 1e-5, (plan["group_id"], step["step"], cash[donor], buffer)
            donor_after = float(step["effects"]["k6"]["donor"]["level_after"])
            assert donor_after >= baseline[donor] - config.donor_level_floor_drop - 1e-6, (
                plan["group_id"], step["step"], donor_after, baseline[donor])
    assert checked_steps > 0 and o_steps > 0
