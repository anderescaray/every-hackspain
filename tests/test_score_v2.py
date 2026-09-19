import json

import numpy as np
import pandas as pd
import pytest

from xray.score_v2 import ScoreV2Config, fit_reference_bundle, score_panel
from xray.score_v2.signals import build_signals, smoothed_signals
from xray.score_v2.trajectory import score_calendar

KEYS = ["company_id", "currency", "month"]


def company(company_id, group_id, inflow, outflow, months=None, start="2025-01-01", seed=0, **overrides):
    """Panel mensual sintético a partir de series de entradas y salidas operativas."""
    inflow, outflow = np.asarray(inflow, dtype=float), np.asarray(outflow, dtype=float)
    n = len(inflow)
    months = pd.date_range(start, periods=n, freq="MS") if months is None else pd.DatetimeIndex(months)
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({
        "company_id": company_id, "group_id": group_id, "currency": "EUR", "month": months,
        "tx_count": 40, "tx_usable_count": 40, "tx_usable_row_share": 1., "tx_operating_amount_share": .9,
        "tx_company_coverage": 1., "has_partial_currency_coverage": False,
        "history_observed_months": np.arange(1, n + 1), "has_sufficient_history": np.arange(1, n + 1) >= 6,
        "tx_inflow": inflow, "tx_outflow": outflow,
        "debt_principal_paid": 0.08 * inflow, "debt_interest_paid": 0.02 * inflow,
        "inv_ar_delay_median": 5. + rng.normal(0, 1, n), "inv_ar_delay_count": 10.,
        "inv_ap_delay_median": 3. + rng.normal(0, 1, n), "inv_ap_delay_count": 10.,
        "tx_new_accounts": 0,
    })
    frame["tx_operating_margin"] = (inflow - outflow) / (inflow + outflow)
    frame["tx_lfl_inflow_growth"] = pd.Series(inflow).pct_change().to_numpy()
    for key, value in overrides.items():
        frame[key] = value
    return frame


def noisy_company(company_id, group_id, margin=0.10, n=18, seed=1, scale=0.06):
    rng = np.random.default_rng(seed)
    inflow = 100 * np.exp(rng.normal(0, .05, n))
    margins = np.clip(margin + rng.normal(0, scale, n), -.9, .9)
    return company(company_id, group_id, inflow, inflow * (1 - margins) / (1 + margins), seed=seed)


def portfolio(n_groups=12, per_group=2, n=18):
    frames = []
    for g in range(n_groups):
        for k in range(per_group):
            frames.append(noisy_company(f"C{g}_{k}", f"G{g}", margin=0.10 + 0.02 * (g % 5), n=n, seed=100 * g + k))
    return pd.concat(frames, ignore_index=True)


def scored(panel, extra=None):
    full = pd.concat([panel, extra], ignore_index=True) if extra is not None else panel
    reference = fit_reference_bundle(full)
    return score_panel(full, reference)


def rows(result, company_id):
    return result.loc[result.company_id.eq(company_id)].sort_values("month").reset_index(drop=True)


# ---------------------------------------------------------------- señales


def test_inflow_cycle_100_200_100_100_has_zero_compound_growth():
    inflow = np.array([100, 100, 100, 100, 200, 100, 100, 100, 100], dtype=float)
    frame = company("C", "G", inflow, inflow * .8).set_index("month")
    signals = smoothed_signals(frame, ScoreV2Config())
    # el ciclo completo cabe en el trimestre que termina en el mes 7: +log2 - log2 + 0 = 0
    assert signals.inflow_growth_q.iloc[6] == pytest.approx(0.0, abs=1e-12)
    # y la media de retornos simples de V1 daría +16.7% para el mismo tramo
    simple = pd.Series(inflow).pct_change().rolling(3).mean().iloc[6]
    assert simple == pytest.approx(1 / 6, abs=1e-9)


def test_window_margin_aggregates_flows_instead_of_averaging_ratios():
    # un mes minúsculo con margen -1 no debe arrastrar el nivel como lo haría una media de ratios
    inflow = np.array([100, 100, 100, 100, 100, 0.], dtype=float)
    outflow = np.array([80, 80, 80, 80, 80, 1.], dtype=float)
    frame = company("C", "G", inflow, outflow).set_index("month")
    signals = smoothed_signals(frame, ScoreV2Config())
    expected = (500 - 401) / (500 + 401)
    assert signals.op_margin_w.iloc[-1] == pytest.approx(expected)
    assert frame.tx_operating_margin.tail(6).mean() < 0  # la media de ratios sería negativa


def test_windows_use_natural_calendar_and_do_not_bridge_gaps():
    months = pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01", "2025-08-01", "2025-09-01", "2025-10-01"])
    frame = company("C", "G", [100] * 6, [80] * 6, months=months)
    signals = build_signals(frame, ScoreV2Config())
    # en agosto la ventana natural t-5..t (marzo..agosto) solo contiene marzo y agosto: sin nivel
    assert signals.loc[frame.month.eq("2025-08-01"), "level_months"].item() == 2
    assert np.isnan(signals.loc[frame.month.eq("2025-08-01"), "op_margin_w"].item())
    assert signals.loc[frame.month.eq("2025-10-01"), "level_months"].item() == 3


def test_low_quality_months_are_excluded_from_window_but_window_still_scores():
    frame = company("C", "G", [100] * 8, [80] * 8)
    frame.loc[frame.month.eq("2025-06-01"), "tx_usable_row_share"] = .1
    signals = build_signals(frame, ScoreV2Config())
    assert signals.loc[frame.month.eq("2025-06-01"), "level_months"].item() == 5
    assert signals.op_margin_w.iloc[-1] == pytest.approx(20 / 180)


def test_signals_never_look_into_the_future():
    frame = company("C", "G", [100] * 12, [80] * 12)
    modified = frame.copy()
    modified.loc[modified.month.gt("2025-08-01"), ["tx_inflow", "tx_outflow"]] = [50., 90.]
    modified["tx_operating_margin"] = (modified.tx_inflow - modified.tx_outflow) / (modified.tx_inflow + modified.tx_outflow)
    original = build_signals(frame, ScoreV2Config())
    changed = build_signals(modified, ScoreV2Config())
    early = frame.month.le("2025-08-01").to_numpy()
    pd.testing.assert_frame_equal(original.loc[early], changed.loc[early])


# ---------------------------------------------------------------- bache frente a tendencia


def test_one_off_dip_is_flagged_but_never_confirmed_as_deterioration():
    n = 18
    inflow = np.full(n, 100.)
    outflow = np.full(n, 80.)
    outflow[11] = 140.  # un solo mes muy malo
    base = company("C", "G", inflow, outflow)
    result, _ = scored(portfolio(), base)
    c = rows(result, "C")
    dip = c.loc[c.month.eq("2025-12-01")].iloc[0]
    assert dip.is_atypical_month
    assert dip.episode == "one_off_dip"
    after = c.loc[c.month.gt("2025-12-01")]
    assert not after.trajectory.isin(["deteriorating"]).any()
    assert not after.trajectory.isin(["improving"]).any()  # la recuperación mecánica tampoco es mejora
    # mientras el trimestre arrastra el bache, el mes actual ya está en su nivel y lo dice
    assert "not_sustained_by_current_month" in set(after.episode)
    assert not after.momentum_confirmed.any()


def test_step_down_is_confirmed_as_deterioration_within_three_months():
    n = 18
    inflow = np.full(n, 100.)
    outflow = np.full(n, 80.)
    outflow[12:] = 110.  # ruptura estructural a partir del mes 13
    result, _ = scored(portfolio(), company("C", "G", inflow, outflow))
    c = rows(result, "C")
    after = c.loc[c.month.ge("2026-01-01")]
    assert "deteriorating" in set(after.trajectory.iloc[:3])
    assert after.loc[after.trajectory.eq("deteriorating"), "episode"].eq("trend_deterioration").all()
    assert after.loc[after.trajectory.eq("deteriorating"), "trend_months"].lt(0).all()
    confirmed = after.loc[after.momentum_confirmed]
    assert (confirmed.score.diff().dropna() < 0).all()  # el score no rebota mientras el deterioro está confirmado
    assert after.trajectory.iloc[-1] == "stable"  # dos trimestres en el nuevo régimen: estable a un nivel peor
    before = c.loc[c.month.eq("2025-12-01"), "score"].item()
    assert after.score.max() < before - 5 and after.level.is_monotonic_decreasing


def test_step_up_is_confirmed_as_improvement_symmetrically_and_held_by_hysteresis():
    n = 18
    inflow = np.full(n, 100.)
    outflow = np.full(n, 90.)
    outflow[12:] = 60.
    result, _ = scored(portfolio(), company("C", "G", inflow, outflow))
    c = rows(result, "C")
    after = c.loc[c.month.ge("2026-01-01")]
    assert "improving" in set(after.trajectory.iloc[:3])
    improving = after.loc[after.trajectory.eq("improving")]
    assert improving.trend_months.gt(0).all()
    assert improving.direction_held.any()  # una oscilación leve no rompe una dirección confirmada
    assert (after.score.diff().dropna() >= -3).all()


def test_bigger_break_gives_bigger_standardized_change():
    n = 18
    inflow = np.full(n, 100.)
    small, big = np.full(n, 80.), np.full(n, 80.)
    small[12:], big[12:] = 95., 125.
    cfg = ScoreV2Config()
    z_small = smoothed_signals(company("C", "G", inflow, small).set_index("month"), cfg).op_margin_change_z
    z_big = smoothed_signals(company("C", "G", inflow, big).set_index("month"), cfg).op_margin_change_z
    assert z_big.iloc[14] < z_small.iloc[14] < 0


def test_stable_company_has_no_direction_and_smooth_score():
    result, _ = scored(portfolio(), noisy_company("C", "G", seed=7, scale=0.02))
    c = rows(result, "C").dropna(subset=["momentum"])
    assert c.trajectory.isin(["stable", "mixed_signals"]).all()
    assert c.score.diff().abs().max() < 5


def test_momentum_is_neutral_for_constant_company():
    frame = company("C", "G", [100.] * 12, [80.] * 12, inv_ar_delay_median=5., inv_ap_delay_median=3.)
    signals = smoothed_signals(frame.set_index("month"), ScoreV2Config())
    result, *_ = score_calendar(signals, ScoreV2Config())
    assert result.momentum.dropna().eq(50).all()
    assert result.trajectory.iloc[-1] == "stable"


# ---------------------------------------------------------------- pipeline, contrato y referencia


def test_reference_bundle_is_serializable_and_groups_are_disjoint():
    panel = portfolio()
    bundle = fit_reference_bundle(panel)
    assert not set(bundle["reference_groups"]) & set(bundle["holdout_groups"])
    assert set(bundle["reference_groups"]) | set(bundle["holdout_groups"]) == set(panel.group_id)
    for reference in bundle["references"]:
        assert reference["max_observed_month"] is None or pd.Timestamp(reference["max_observed_month"]) < pd.Timestamp(reference["effective_from"])
    json.dumps(bundle, allow_nan=False)


def test_prefix_and_future_mutation_do_not_change_scores():
    panel = portfolio()
    prefix = panel.loc[panel.month <= "2025-12-01"].copy()
    early, _ = score_panel(prefix, fit_reference_bundle(prefix))
    modified = panel.copy()
    modified.loc[modified.month > "2025-12-01", ["tx_inflow", "tx_outflow"]] = [10., 90.]
    later, _ = score_panel(modified, fit_reference_bundle(modified))
    pd.testing.assert_frame_equal(early.set_index(KEYS).sort_index(),
                                  later.loc[later.month <= "2025-12-01"].set_index(KEYS).sort_index())


def test_frozen_reference_unseen_entities_and_batch_independence():
    panel = portfolio()
    bundle = json.loads(json.dumps(fit_reference_bundle(panel)))
    unseen = panel.loc[panel.company_id.eq("C0_0")].assign(company_id="NEW", group_id="NEW_GROUP")
    alone, _ = score_panel(unseen, bundle)
    batch, _ = score_panel(pd.concat([panel, unseen], ignore_index=True), bundle)
    pd.testing.assert_frame_equal(alone.reset_index(drop=True), batch.loc[batch.company_id.eq("NEW")].reset_index(drop=True))
    assert alone.reference_partition.eq("unseen").all()
    assert alone.score.dropna().between(0, 100).all()


def test_score_decomposition_is_exact_and_bounded():
    result, explanation = scored(portfolio())
    assert result.score.dropna().between(0, 100).all()
    assert np.allclose(result.score.dropna(), (result.level + result.momentum_adjustment + result.clipping_adjustment).dropna())
    sums = explanation.groupby(KEYS).final_contribution.sum()
    scores = result.set_index(KEYS).score.dropna()
    np.testing.assert_allclose(sums.reindex(scores.index), scores, atol=1e-8)
    assert set(explanation.layer) <= {"level", "momentum", "boundary"}
    assert explanation.loc[explanation.layer.eq("momentum"), "standardized_value"].notna().all()


def test_first_two_months_are_not_scored_and_no_fifty_is_invented():
    result, _ = scored(portfolio())
    c = rows(result, "C0_0")
    assert c.score_status.iloc[:2].eq("not_scored").all()
    assert c.score_reason.iloc[:2].eq("insufficient_window_history").all()
    assert c.score.iloc[:2].isna().all()
    assert c.momentum.iloc[:2].isna().all()


def test_thin_current_month_is_scored_from_window_but_provisional():
    panel = portfolio()
    thin = panel.company_id.eq("C0_0") & panel.month.eq("2026-03-01")
    panel.loc[thin, ["tx_count", "tx_usable_count"]] = 2
    result, _ = scored(panel)
    row = result.loc[thin].iloc[0]
    assert row.score_status == "provisional"
    assert row.score_reason == "thin_current_month"
    assert pd.notna(row.score)
    assert not row.month_quality_ok


def test_month_without_transactions_is_not_scored():
    panel = portfolio()
    missing = panel.company_id.eq("C0_0") & panel.month.eq("2026-03-01")
    panel.loc[missing, ["tx_count", "tx_usable_count"]] = 0
    result, _ = scored(panel)
    row = result.loc[missing].iloc[0]
    assert pd.isna(row.score) and row.score_status == "not_scored" and row.score_reason == "no_usable_transactions"


def test_erp_disappearance_fades_out_over_the_window_without_score_jump():
    panel = portfolio()
    target = panel.company_id.eq("C0_0") & panel.month.ge("2026-01-01")
    panel.loc[target, ["inv_ar_delay_median", "inv_ap_delay_median"]] = np.nan
    panel.loc[target, ["inv_ar_delay_count", "inv_ap_delay_count"]] = 0
    result, _ = scored(panel)
    c = rows(result, "C0_0")
    jan = c.loc[c.month.eq("2026-01-01")].iloc[0]
    assert pd.notna(jan.level_collections)  # todavía hay 5 meses de pagos en la ventana
    last = c.iloc[-1]
    assert pd.isna(last.level_collections) and last.component_mask == "1100"  # junio: ventana sin ERP
    assert c.delta_vs_prev.abs().max() < 8


def test_missing_optional_invoice_fields_are_allowed_but_not_healthy():
    panel = portfolio().drop(columns=[c for c in portfolio().columns if c.startswith("inv_")])
    result, _ = scored(panel)
    assert result.level_collections.isna().all() and result.level_payments.isna().all()
    assert result.loc[result.score.notna(), "level_coverage"].le(.7).all()
    assert result.loc[result.score.notna(), "score_status"].eq("provisional").all()


def test_missing_core_feature_is_schema_error():
    panel = portfolio()
    with pytest.raises(ValueError, match="tx_outflow"):
        fit_reference_bundle(panel.drop(columns=["tx_outflow"]))


def test_delay_median_without_count_is_rejected():
    panel = portfolio().drop(columns=["inv_ar_delay_count"])
    with pytest.raises(ValueError, match="inv_ar_delay_count"):
        fit_reference_bundle(panel)


def test_debt_service_without_inflow_scores_zero_not_a_ratio():
    n = 12
    frame = company("C", "G", np.zeros(n), np.full(n, 50.), tx_operating_margin=-1., tx_lfl_inflow_growth=np.nan)
    frame["debt_principal_paid"], frame["debt_interest_paid"] = 10., 1.
    result, terms = scored(portfolio(), frame)
    c = rows(result, "C").dropna(subset=["score"])
    assert c.level_debt.eq(0).all() and c.has_uncovered_debt_service.all()
    features = terms.loc[terms.company_id.eq("C") & terms.layer.eq("level"), "feature"]
    assert "debt_without_inflow_w" in set(features)


def test_snapshots_and_text_events_are_not_consumed():
    panel = portfolio()
    reference = fit_reference_bundle(panel)
    original, _ = score_panel(panel, reference)
    panel["cash_balance"], panel["stress_embargo_count"], panel["debt_total_outstanding"] = 1e12, 1000, 1e12
    changed, _ = score_panel(panel, reference)
    pd.testing.assert_frame_equal(original, changed)


def test_shuffled_inputs_keep_order_and_values():
    panel = portfolio()
    reference = fit_reference_bundle(panel)
    original, _ = score_panel(panel, reference)
    shuffled = panel.sample(frac=1, random_state=3)
    predicted, _ = score_panel(shuffled, reference)
    pd.testing.assert_frame_equal(predicted[KEYS].reset_index(drop=True), shuffled[KEYS].reset_index(drop=True))
    pd.testing.assert_frame_equal(original.set_index(KEYS).sort_index(), predicted.set_index(KEYS).sort_index())


def test_config_rejects_incoherent_windows():
    with pytest.raises(ValueError):
        ScoreV2Config(level_window=4, momentum_window=3)
    with pytest.raises(ValueError):
        ScoreV2Config(direction_z=5, z_clip=4)
    with pytest.raises(ValueError):
        ScoreV2Config(level_min_months=7)
    with pytest.raises(ValueError):
        ScoreV2Config(hysteresis=0)
    assert ScoreV2Config().direction_threshold == pytest.approx(50 * np.tanh(0.75))
