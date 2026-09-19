import copy
import json
import math

import numpy as np
import pandas as pd
import pytest

from xray.group_advisor.counterfactual import (
    LEVEL_INPUT_COLUMNS, PRIMITIVES, SIGNAL_BASE, SIGNAL_DERIVED, Action, ActionEffect, ap_delay_scale,
    apply_d1, apply_p, ar_delay_scale, component_scores, debt_service_add, debt_service_scale, derive,
    evaluate_action, inflow_scale, level_from_signals, outflow_scale)
from xray.paths import PROCESSED_DIR
from xray.score.level import COMPONENT_WEIGHTS
from xray.score_v2.level import fit_reference

H = 6
REF = fit_reference(pd.DataFrame())  # anclas puras: notas = interpolación lineal de las anclas de V1


def row(inflow=600., outflow=400., service=180., ar=10., ap=30.):
    return derive({"level_inflow_sum": inflow, "window_outflow_sum": outflow, "window_debt_service_sum": service,
                   "ar_delay_w": ar, "ap_delay_w": ap})


def same(a, b):
    """Igualdad de filas tratando NaN == NaN."""
    if a.keys() != b.keys():
        return False
    for key in a:
        x, y = a[key], b[key]
        if isinstance(x, float) and isinstance(y, float) and math.isnan(x) and math.isnan(y):
            continue
        if x != y:
            return False
    return True


def level(signal_row):
    return level_from_signals({"x": signal_row}, REF).loc["x"]


def action(lever, fraction=1.0, psi=None):
    return Action(lever=lever, donor="a", recipient="b", donor_currency="EUR", recipient_currency="EUR",
                  fraction=fraction, amount_recipient_ccy=0., amount_donor_ccy=0., fx_applied=None, psi=psi)


# ---------------------------------------------------------------- derive


def test_derive_reproduces_hand_computed_signals():
    r = row(inflow=600., outflow=400., service=60.)
    assert r["op_margin_w"] == pytest.approx(0.2)
    assert r["debt_service_w"] == pytest.approx(0.1)
    assert r["debt_without_inflow_w"] is False
    assert set(SIGNAL_BASE) | set(SIGNAL_DERIVED) <= r.keys()
    uncovered = row(inflow=0., outflow=400., service=60.)
    assert math.isnan(uncovered["debt_service_w"]) and uncovered["debt_without_inflow_w"] is True
    assert uncovered["op_margin_w"] == pytest.approx(-1.0)
    silent = row(inflow=0., outflow=400., service=0.)
    assert math.isnan(silent["debt_service_w"]) and silent["debt_without_inflow_w"] is False
    empty = row(inflow=0., outflow=0., service=0.)
    assert math.isnan(empty["op_margin_w"])
    unknown = derive({"level_inflow_sum": None, "window_outflow_sum": 400., "window_debt_service_sum": None})
    assert math.isnan(unknown["op_margin_w"]) and math.isnan(unknown["debt_service_w"])
    assert unknown["debt_without_inflow_w"] is False


# ---------------------------------------------------------------- primitivas


@pytest.mark.parametrize("name", sorted(PRIMITIVES))
@pytest.mark.parametrize("k", [1, 3, H])
def test_zero_parameter_is_identity(name, k):
    base = row()
    assert same(PRIMITIVES[name](base, 0.0, k, H), base)


def test_debt_service_scale_minus_one_at_horizon_gives_full_debt_score():
    scaled = debt_service_scale(row(), -1, H, H)
    assert scaled["debt_service_w"] == 0.0 and scaled["window_debt_service_sum"] == 0.0
    assert level(scaled)["level_debt"] == 100.0
    assert level(row())["level_debt"] == 40.0  # ancla (0.3, 40) sin tocar el resto


def test_recipient_level_is_monotone_in_phi_and_in_k():
    by_phi = [level(debt_service_scale(row(), phi, H, H))["level"] for phi in (-0.25, -0.5, -0.75, -1.0)]
    assert all(later >= earlier for earlier, later in zip(by_phi, by_phi[1:]))
    assert by_phi[-1] > by_phi[0]
    by_k = [level(debt_service_scale(row(), -1.0, k, H))["level"] for k in range(1, H + 1)]
    assert all(later >= earlier for earlier, later in zip(by_k, by_k[1:]))
    assert by_k[-1] > by_k[0]


def test_debt_service_add_makes_donor_level_non_increasing_in_k():
    base = level(row())["level"]
    by_k = [level(debt_service_add(row(), 20., k, H))["level"] for k in range(1, H + 1)]
    assert all(later <= earlier for earlier, later in zip([base] + by_k, by_k))
    assert by_k[-1] < base
    assert debt_service_add(row(), 20., H, H)["window_debt_service_sum"] == pytest.approx(180. + 6 * 20.)


def test_outflow_scale_moves_margin_only_and_inflow_scale_moves_both():
    base = row()
    cut = outflow_scale(base, -0.5, H, H)
    assert cut["op_margin_w"] > base["op_margin_w"] and cut["op_margin_w"] == pytest.approx((600 - 200) / 800)
    assert cut["debt_service_w"] == base["debt_service_w"]
    assert cut["level_inflow_sum"] == base["level_inflow_sum"]
    raised = inflow_scale(base, 0.5, H, H)
    assert raised["op_margin_w"] > base["op_margin_w"] and raised["op_margin_w"] == pytest.approx((900 - 400) / 1300)
    assert raised["debt_service_w"] < base["debt_service_w"] and raised["debt_service_w"] == pytest.approx(180 / 900)
    partial = inflow_scale(base, 0.5, 3, H)
    assert partial["level_inflow_sum"] == pytest.approx(600 * 1.25)


def test_inflow_to_zero_with_debt_activates_indicator_and_zero_debt_score():
    starved = inflow_scale(row(), -1, H, H)
    assert starved["level_inflow_sum"] == 0.0 and starved["window_debt_service_sum"] == 180.
    assert math.isnan(starved["debt_service_w"]) and starved["debt_without_inflow_w"] is True
    scored = level(starved)
    assert scored["level_debt"] == 0.0 and bool(scored["has_uncovered_debt_service"])
    assert scored["level_components_available"] == 4 and scored["level_coverage"] == pytest.approx(1.0)


def test_zero_inflow_and_zero_service_drops_debt_component_and_renormalizes():
    before = row(inflow=0., outflow=400., service=60.)
    scored_before = level(before)
    assert scored_before["level_debt"] == 0.0 and scored_before["level_components_available"] == 4
    after = debt_service_scale(before, -1, H, H)
    assert math.isnan(after["debt_service_w"]) and after["debt_without_inflow_w"] is False
    scored_after = level(after)
    assert math.isnan(scored_after["level_debt"]) and not bool(scored_after["has_uncovered_debt_service"])
    assert scored_after["level_components_available"] == scored_before["level_components_available"] - 1
    remaining = {c: scored_after[f"level_{c}"] for c in COMPONENT_WEIGHTS if c != "debt"}
    expected = sum(COMPONENT_WEIGHTS[c] * s for c, s in remaining.items()) / sum(COMPONENT_WEIGHTS[c] for c in remaining)
    assert scored_after["level"] == pytest.approx(expected)
    assert scored_after["level_coverage"] == pytest.approx(1 - COMPONENT_WEIGHTS["debt"])
    assert 0.0 < scored_after["level"] < 100.0  # ni 0 ni 100 fantasma


def test_nan_base_signal_stays_nan_and_indicator_is_false():
    base = derive({"level_inflow_sum": 600., "window_outflow_sum": 400., "window_debt_service_sum": math.nan,
                   "ar_delay_w": math.nan, "ap_delay_w": 30.})
    assert math.isnan(base["debt_service_w"]) and base["debt_without_inflow_w"] is False
    added = debt_service_add(base, 20., H, H)
    assert math.isnan(added["window_debt_service_sum"]) and math.isnan(added["debt_service_w"])
    assert math.isnan(ar_delay_scale(base, 1.0, H, H)["ar_delay_w"])
    scored = level(base)
    assert math.isnan(scored["level_debt"]) and math.isnan(scored["level_collections"])
    assert scored["level_components_available"] == 2


def test_parameters_and_steps_are_validated():
    base = row()
    for k in (0, H + 1, 1.5, True):
        with pytest.raises(ValueError):
            inflow_scale(base, 0.1, k, H)
    with pytest.raises(ValueError):
        inflow_scale(base, 0.1, 1, 0)
    with pytest.raises(ValueError):
        inflow_scale(base, -1.01, 1, H)
    with pytest.raises(ValueError):
        outflow_scale(base, math.nan, 1, H)
    with pytest.raises(ValueError):
        debt_service_scale(base, -2, 1, H)
    for psi in (-0.1, 1.1):
        with pytest.raises(ValueError):
            ap_delay_scale(base, psi, 1, H)
        with pytest.raises(ValueError):
            ar_delay_scale(base, psi, 1, H)
    with pytest.raises(ValueError, match="negativo"):
        debt_service_add(base, -31., H, H)
    assert debt_service_add(base, -30., H, H)["window_debt_service_sum"] == 0.0
    with pytest.raises(ValueError):
        apply_d1(base, base, 1.5, H, H, 30.)
    with pytest.raises(ValueError):
        apply_d1(base, base, 0.5, H, H, -1.)


# ---------------------------------------------------------------- nivel


def test_level_from_signals_keeps_insertion_order_and_derives_base_only_rows():
    base_only = {c: row()[c] for c in SIGNAL_BASE}
    result = level_from_signals({"z": row(), "a": base_only, "m": row(ap=math.nan)}, REF)
    assert list(result.index) == ["z", "a", "m"]
    assert result.at["a", "level"] == result.at["z", "level"]
    assert math.isnan(result.at["m", "level_payments"]) and result.at["m", "level_components_available"] == 3
    assert list(result.columns) == ["level", "level_operations", "level_debt", "level_collections", "level_payments",
                                    "level_coverage", "level_components_available", "has_uncovered_debt_service"]
    assert level_from_signals({}, REF).empty
    assert component_scores(result.loc["m"]) == {"operations": 85.0, "debt": 40.0, "collections": 77.5, "payments": None}


# ---------------------------------------------------------------- composiciones


def test_apply_p_leaves_donor_untouched_and_full_psi_gives_full_payments_score():
    paid = apply_p(row(), 1.0, H, H)
    assert paid["ap_delay_w"] == 0.0 and level(paid)["level_payments"] == 100.0
    assert same({k: v for k, v in paid.items() if k != "ap_delay_w"}, {k: v for k, v in row().items() if k != "ap_delay_w"})
    rows = {"a": row(service=60.), "b": row()}
    effect = evaluate_action(rows, REF, action("P", psi=0.5), H, H)
    assert effect.donor_level_before == effect.donor_level_after
    assert effect.donor_signal_before == effect.donor_signal_after == rows["a"]["ap_delay_w"]
    assert effect.recipient_signal_before == 30. and effect.recipient_signal_after == pytest.approx(15.)
    assert effect.recipient_level_after > effect.recipient_level_before
    assert not effect.recipient_component_dropped and not effect.donor_hits_zero_inflow_indicator
    assert effect.donor_components_after == component_scores(level(rows["a"]))


def test_k_one_effect_is_strictly_smaller_than_k_horizon():
    rows = {"a": row(service=60.), "b": row()}
    for act, monthly in ((action("D1", fraction=1.0), 30.), (action("P", psi=1.0), None)):
        short = evaluate_action(rows, REF, act, 1, H, monthly_service_b_in_donor_ccy=monthly)
        regime = evaluate_action(rows, REF, act, H, H, monthly_service_b_in_donor_ccy=monthly)
        assert short.k == 1 and regime.k == H
        delta_short = short.recipient_level_after - short.recipient_level_before
        delta_regime = regime.recipient_level_after - regime.recipient_level_before
        assert 0 < abs(delta_short) < abs(delta_regime)
        if act.lever == "D1":
            assert abs(short.donor_level_after - short.donor_level_before) < abs(regime.donor_level_after - regime.donor_level_before)


def test_inputs_are_never_mutated():
    rows = {"a": row(service=60.), "b": row()}
    frozen = copy.deepcopy(rows)
    for name in PRIMITIVES:
        PRIMITIVES[name](rows["b"], 0.5, 2, H)
    apply_d1(rows["a"], rows["b"], 0.75, 3, H, 30.)
    apply_p(rows["b"], 0.5, 3, H)
    evaluate_action(rows, REF, action("D1", fraction=1.0), H, H, monthly_service_b_in_donor_ccy=30.)
    evaluate_action(rows, REF, action("P", psi=1.0), H, H)
    assert rows == frozen


def test_d1_through_evaluate_action_equals_its_two_primitives():
    rows = {"a": row(service=60.), "b": row()}
    phi, monthly, k = 0.5, 30., 4
    effect = evaluate_action(rows, REF, action("D1", fraction=phi), k, H, monthly_service_b_in_donor_ccy=monthly)
    row_a, row_b = apply_d1(rows["a"], rows["b"], phi, k, H, monthly)
    assert same(row_a, debt_service_add(rows["a"], phi * monthly, k, H))
    assert same(row_b, debt_service_scale(rows["b"], -phi, k, H))
    manual = level_from_signals({"a": row_a, "b": row_b}, REF)
    assert effect.donor_level_after == manual.at["a", "level"]
    assert effect.recipient_level_after == manual.at["b", "level"]
    assert effect.donor_components_after == component_scores(manual.loc["a"])
    assert effect.recipient_components_after == component_scores(manual.loc["b"])
    assert effect.donor_signal_after == pytest.approx((60 + k * phi * monthly) / 600)
    assert effect.recipient_signal_after == pytest.approx(0.3 * (1 - k * phi / H))
    assert effect.recipient_level_after > effect.recipient_level_before
    assert effect.donor_level_after < effect.donor_level_before
    # la suma del servicio de la ventana del grupo no cambia
    assert row_a["window_debt_service_sum"] + row_b["window_debt_service_sum"] == pytest.approx(60. + 180.)


def test_d1_requires_monthly_service_and_p_requires_psi():
    rows = {"a": row(), "b": row()}
    with pytest.raises(ValueError, match="monthly_service"):
        evaluate_action(rows, REF, action("D1"), H, H)
    with pytest.raises(ValueError, match="psi"):
        evaluate_action(rows, REF, action("P"), H, H)
    with pytest.raises(ValueError):
        evaluate_action(rows, REF, action("D2"), H, H)
    with pytest.raises(KeyError):
        evaluate_action({"a": row()}, REF, action("P", psi=1.), H, H)
    assert isinstance(evaluate_action(rows, REF, action("P", psi=1.), H, H), ActionEffect)


def test_recipient_component_dropped_and_donor_zero_inflow_indicator():
    rows = {"a": row(inflow=0., outflow=400., service=0.), "b": row(inflow=0., outflow=400., service=60.)}
    effect = evaluate_action(rows, REF, action("D1", fraction=1.0), H, H, monthly_service_b_in_donor_ccy=10.)
    assert effect.recipient_component_dropped
    assert effect.recipient_components_after["debt"] is None
    assert math.isnan(effect.recipient_signal_before) and math.isnan(effect.recipient_signal_after)
    assert effect.donor_hits_zero_inflow_indicator
    assert effect.donor_components_after["debt"] == 0.0
    assert effect.donor_level_after < effect.donor_level_before
    partial = evaluate_action(rows, REF, action("D1", fraction=0.5), H, H, monthly_service_b_in_donor_ccy=10.)
    assert not partial.recipient_component_dropped  # S_b sigue > 0: indicador activo, nota 0, componente presente
    healthy = evaluate_action({"a": row(service=60.), "b": row()}, REF, action("D1", fraction=1.0), H, H,
                              monthly_service_b_in_donor_ccy=30.)
    assert not healthy.recipient_component_dropped and not healthy.donor_hits_zero_inflow_indicator


# ---------------------------------------------------------------- datos reales


@pytest.mark.skipif(not (PROCESSED_DIR / "scores_v2").exists(), reason="requiere data/processed/scores_v2")
def test_level_from_signals_reproduces_v2_levels_for_real_companies():
    from xray.score_v2 import ScoreV2Config
    from xray.score_v2.core import prepare_panel
    from xray.score_v2.signals import build_signals

    month = pd.Timestamp("2026-08-01")
    reference = json.loads((PROCESSED_DIR / "scores_v2" / "_company_score_reference.json").read_text(encoding="utf-8"))
    scores = pd.read_parquet(PROCESSED_DIR / "scores_v2" / "company_monthly_scores.parquet")
    august = scores.loc[scores.month.eq(month) & scores.level.notna()].sort_values("company_id")
    chosen = pd.concat([august.head(20), august.loc[august.has_uncovered_debt_service]]).drop_duplicates("company_id")
    assert len(chosen) >= 20
    config = ScoreV2Config(**reference["config"])
    panel = pd.read_parquet(PROCESSED_DIR / "company_monthly_features.parquet")
    prepared = prepare_panel(panel.loc[panel.company_id.isin(chosen.company_id)], config)
    signals = build_signals(prepared, config)  # por empresa-moneda: restringir el panel no cambia sus señales
    keys = ["company_id", "currency", "month"]
    signals[keys] = prepared[keys]
    current = signals.merge(chosen[keys], on=keys, validate="one_to_one").set_index("company_id")
    rows = {cid: {c: current.at[cid, c] for c in LEVEL_INPUT_COLUMNS} for cid in chosen.company_id}
    candidates = [item for item in reference["references"] if pd.Timestamp(item["effective_from"]) <= month]
    state = max(candidates, key=lambda item: pd.Timestamp(item["effective_from"]))
    assert pd.Timestamp(state["max_observed_month"]) < month
    result = level_from_signals(rows, state["state"])
    expected = chosen.set_index("company_id")
    assert list(result.index) == list(expected.index)
    for column in ("level", "level_operations", "level_debt", "level_collections", "level_payments", "level_coverage"):
        np.testing.assert_allclose(result[column].to_numpy(dtype=float), expected[column].to_numpy(dtype=float), atol=1e-6)
    assert (result.level_components_available.to_numpy() == expected.level_components_available.to_numpy()).all()
    assert (result.has_uncovered_debt_service.to_numpy() == expected.has_uncovered_debt_service.to_numpy()).all()
    assert result.has_uncovered_debt_service.any() and result.level_components_available.lt(4).any()
