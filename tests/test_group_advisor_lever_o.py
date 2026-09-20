"""D48 · Palanca O: la donante asume pagos operativos de la receptora (pagos centralizados)."""
import math

import pytest
from advisor_fixtures import derive_signals, make_group_state

from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.counterfactual import apply_o, outflow_add
from xray.group_advisor.optimizer import (REASON_RECIPIENT_NO_OUTFLOW, generate_candidates, recipient_need,
                                          recipient_reason, WorkingState)


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
    assert recipient_need(row(300_000., 330_000.), "O", config) == pytest.approx(330_000. / 6)


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
