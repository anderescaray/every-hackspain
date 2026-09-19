import numpy as np
import pandas as pd
import pytest

from xray.score.trajectory import score_trajectory


def trajectory_panel(change=0.0, periods=10, company="C1", currency="EUR"):
    return pd.DataFrame({
        "company_id": company,
        "currency": currency,
        "month": pd.date_range("2025-01-01", periods=periods, freq="MS"),
        "tx_operating_margin_delta3": change,
    })


def test_symmetric_improvement_and_deterioration():
    up, _ = score_trajectory(trajectory_panel(0.10))
    down, _ = score_trajectory(trajectory_panel(-0.10))
    np.testing.assert_allclose((up.momentum + down.momentum).iloc[3:], 100)
    np.testing.assert_array_equal(up.momentum.isna(), down.momentum.isna())
    assert up.momentum.iloc[:3].isna().all()
    assert up.momentum.iloc[3] == pytest.approx(50 + 50 * np.tanh(1))
    assert up.trajectory.iloc[3] == down.trajectory.iloc[3] == "watch"
    assert up.trajectory.iloc[4] == "improving"
    assert down.trajectory.iloc[4] == "deteriorating"
    assert up.direction.iloc[3] == "up"
    assert down.direction.iloc[3] == "down"
    assert up.trend_months.iloc[-1] == 7
    assert down.trend_months.iloc[-1] == -7
    np.testing.assert_allclose(up.momentum_strength, down.momentum_strength)
    np.testing.assert_allclose(up.momentum_strength, abs(up.momentum - 50) * 2)


def test_constant_is_stable_only_after_observed_history():
    panel = trajectory_panel().assign(tx_operating_margin=-0.8)
    result, _ = score_trajectory(panel)
    assert result.trajectory.iloc[:3].eq("insufficient_history").all()
    assert result.direction.iloc[:3].eq("unknown").all()
    assert result.trajectory.iloc[3] == "watch"
    assert result.trajectory.iloc[4:].eq("stable").all()
    assert result.direction.iloc[3:].eq("flat").all()
    assert result.momentum.iloc[3:].eq(50).all()
    assert result.stability.iloc[5:].eq(100).all()
    assert result.trend_months.eq(0).all()


def test_first_signal_is_watch_and_recovery_does_not_rewrite_it():
    panel = trajectory_panel()
    panel.loc[4:5, "tx_operating_margin_delta3"] = -0.10
    panel.loc[6:, "tx_operating_margin_delta3"] = 0.10
    full, _ = score_trajectory(panel)
    prefix, _ = score_trajectory(panel.iloc[:5])
    pd.testing.assert_frame_equal(prefix, full.iloc[:5])
    assert full.trajectory.iloc[4] == "watch"
    assert full.trajectory.iloc[5] == "deteriorating"
    assert full.trajectory.iloc[6] == "watch"
    assert full.trend_months.iloc[6] == 1


def test_missing_calendar_months_never_compress_windows_or_persistence():
    panel = trajectory_panel(0.1).drop(index=5)
    sparse, sparse_explain = score_trajectory(panel)
    dense = trajectory_panel(0.1)
    dense.loc[5, "tx_operating_margin_delta3"] = np.nan
    dense.loc[5, "tx_usable_count"] = 0
    dense["tx_usable_count"] = dense.tx_usable_count.fillna(10)
    dense_result, _ = score_trajectory(dense)
    assert sparse.loc[6:8, "momentum"].isna().all()
    assert sparse.loc[9, "trajectory"] == "watch"
    assert sparse.loc[9, "trend_months"] == 1
    np.testing.assert_allclose(sparse.momentum, dense_result.loc[panel.index, "momentum"], equal_nan=True)
    assert set(sparse_explain.input_index).issubset(panel.index)


def test_delay_differences_require_calendar_history_not_adjacent_rows():
    panel = trajectory_panel().drop(columns="tx_operating_margin_delta3")
    panel["inv_ar_delay_median"] = np.arange(10) * 2.0
    panel = panel.drop(index=5)
    result, explain = score_trajectory(panel)
    assert result.loc[3, "momentum"] < 50
    assert explain.loc[explain.input_index.eq(3), "value"].iloc[0] == 6
    assert result.loc[6:8, "momentum"].isna().all()
    assert result.loc[9, "trajectory"] == "watch"


@pytest.mark.parametrize("unit", ["company_id", "group_id"])
def test_units_and_currencies_are_isolated(unit):
    frames = [trajectory_panel(0.1, company="A"), trajectory_panel(-0.1, company="B"),
              trajectory_panel(-0.1, company="A", currency="USD")]
    frames = [frame.rename(columns={"company_id": unit}) for frame in frames]
    panel = pd.concat(frames, ignore_index=True).sample(frac=1, random_state=4)
    actual, _ = score_trajectory(panel, unit=unit)
    for _, part in panel.groupby([unit, "currency"]):
        expected, _ = score_trajectory(part, unit=unit)
        pd.testing.assert_frame_equal(actual.loc[part.index], expected)


def test_input_order_duplicate_index_and_input_are_preserved():
    panel = trajectory_panel(0.1).sample(frac=1, random_state=2)
    panel.index = pd.Index(["row"] * len(panel), name="original")
    before = panel.copy(deep=True)
    result, explain = score_trajectory(panel)
    pd.testing.assert_frame_equal(panel, before)
    pd.testing.assert_index_equal(result.index, panel.index)
    chronological, _ = score_trajectory(before.sort_values("month"))
    np.testing.assert_allclose(result.momentum.to_numpy()[np.argsort(panel.month.to_numpy())],
                               chronological.momentum.to_numpy(), equal_nan=True)
    contributions = explain.groupby("input_position").contribution.sum(min_count=1)
    np.testing.assert_allclose(contributions, result.momentum.iloc[contributions.index])
    assert explain.input_index.eq("row").all()


def test_prefix_and_batch_invariance_include_explanations():
    panel = trajectory_panel(0.1)
    panel["inv_ap_delay_median"] = np.arange(10, 0, -1)
    full, full_explain = score_trajectory(panel)
    prefix, prefix_explain = score_trajectory(panel.iloc[:7])
    pd.testing.assert_frame_equal(prefix, full.iloc[:7])
    pd.testing.assert_frame_equal(prefix_explain, full_explain.loc[full_explain.input_position.lt(7)].reset_index(drop=True))
    strangers = trajectory_panel(-1e6, company="OTHER")
    batch, batch_explain = score_trajectory(pd.concat([panel, strangers], ignore_index=True))
    pd.testing.assert_frame_equal(full, batch.iloc[:len(panel)])
    pd.testing.assert_frame_equal(full_explain, batch_explain.loc[batch_explain.input_position.lt(len(panel))].reset_index(drop=True))


def test_missing_columns_and_nonfinite_values_are_not_neutral_observations():
    panel = trajectory_panel().drop(columns="tx_operating_margin_delta3")
    missing, explanation = score_trajectory(panel)
    assert missing.momentum.isna().all()
    assert missing.momentum_coverage.eq(0).all()
    assert missing.trajectory.eq("insufficient_history").all()
    assert missing.stability.isna().all()
    assert explanation.empty
    panel["tx_operating_margin_delta3"] = pd.Series([pd.NA] * 10, dtype="Float64")
    panel.loc[3, "tx_operating_margin_delta3"] = np.inf
    panel.loc[4, "tx_operating_margin_delta3"] = -np.inf
    nonfinite, _ = score_trajectory(panel)
    pd.testing.assert_frame_equal(missing, nonfinite)


def test_invoice_disappearance_is_not_improvement_and_coverage_falls():
    panel = trajectory_panel()
    panel["inv_ar_delay_median"] = np.arange(10) * 5.0
    panel.loc[6:, "inv_ar_delay_median"] = np.nan
    result, explain = score_trajectory(panel)
    assert result.loc[5, "momentum"] < 50
    assert result.loc[6:, "momentum"].eq(50).all()
    assert not result.loc[6:, "trajectory"].eq("improving").any()
    assert result.loc[6, "momentum_coverage"] < result.loc[5, "momentum_coverage"]
    assert result.loc[6, "momentum_sources_changed"]
    assert not explain.loc[explain.input_index.ge(6), "feature"].str.startswith("inv_").any()


def test_fixed_balanced_weights_explanations_and_economic_scales():
    panel = trajectory_panel(0.1).assign(
        debt_service_to_inflow_ratio_delta3=-0.1,
        inv_ar_delay_median=np.arange(10) * (-10 / 3),
        inv_ap_delay_median=np.arange(10) * (-10 / 3),
        tx_lfl_inflow_growth=0.05,
    )
    result, explain = score_trajectory(panel)
    assert result.loc[5, "momentum_coverage"] == 1
    rows = explain.loc[explain.input_index.eq(5)].set_index("feature")
    assert rows.effective_weight.to_dict() == {
        "tx_operating_margin_delta3": 0.25,
        "debt_service_to_inflow_ratio_delta3": 0.25,
        "inv_ar_delay_median_delta3": 0.125,
        "inv_ap_delay_median_delta3": 0.125,
        "tx_lfl_inflow_growth_ma3": 0.25,
    }
    np.testing.assert_allclose(rows.feature_score, 50 + 50 * np.tanh(1))
    np.testing.assert_allclose(rows.contribution, rows.feature_score * rows.effective_weight)
    sums = explain.groupby("input_index").contribution.sum()
    np.testing.assert_allclose(result.loc[sums.index, "momentum"], sums)
    assert rows.direction.eq("up").all()
    assert rows.definition.str.len().gt(20).all()
    assert {"input_index", "feature", "value", "feature_score", "effective_weight",
            "contribution", "direction", "definition"}.issubset(explain.columns)


def test_conflicting_dimensions_are_watch_not_stable():
    panel = trajectory_panel(0.1).assign(debt_service_to_inflow_ratio_delta3=0.1)
    result, _ = score_trajectory(panel)
    np.testing.assert_allclose(result.momentum.iloc[3:], 50)
    assert result.trajectory.iloc[3:].eq("watch").all()
    assert result.momentum_conflict.iloc[3:].all()


def test_new_signal_source_does_not_confirm_previous_source():
    panel = trajectory_panel(np.nan)
    panel.loc[3, "tx_operating_margin_delta3"] = 0.1
    panel.loc[4:, "debt_service_to_inflow_ratio_delta3"] = -0.1
    result, _ = score_trajectory(panel)
    assert result.loc[3, "trajectory"] == "watch"
    assert result.loc[4, "trajectory"] == "watch"
    assert result.loc[4, "trend_months"] == 1
    assert result.loc[5, "trajectory"] == "improving"


def test_onboarding_amounts_and_absolute_overdue_levels_are_ignored():
    panel = trajectory_panel().assign(tx_lfl_inflow_growth=0.0)
    expected, _ = score_trajectory(panel)
    panel["tx_inflow"] = np.geomspace(100, 1e9, len(panel))
    panel["tx_inflow_change3_scaled"] = 50
    panel["inv_ar_overdue_ratio"] = np.arange(len(panel)) / len(panel)
    panel["tx_operating_margin_slope3"] = 1000
    panel["tx_operating_margin_slope6"] = 1000
    actual, _ = score_trajectory(panel)
    pd.testing.assert_frame_equal(expected, actual)


def test_stability_is_direction_independent_and_not_a_score_penalty():
    bad = trajectory_panel().assign(tx_operating_margin=-0.9)
    good = bad.assign(tx_operating_margin=0.9)
    bad_result, _ = score_trajectory(bad)
    good_result, _ = score_trajectory(good)
    pd.testing.assert_frame_equal(bad_result, good_result)
    volatile = trajectory_panel(0.1)
    volatile.loc[[4, 6, 8], "tx_operating_margin_delta3"] = 0.6
    result, _ = score_trajectory(volatile)
    constant, _ = score_trajectory(trajectory_panel(0.1))
    assert result.loc[9, "stability"] < constant.loc[9, "stability"]
    assert result.loc[9, "momentum"] == constant.loc[9, "momentum"]
    assert result.loc[9, "trajectory"] == "improving"


def test_empty_input_preserves_schema_and_index():
    panel = trajectory_panel().iloc[:0]
    result, explain = score_trajectory(panel)
    assert result.empty and explain.empty
    pd.testing.assert_index_equal(result.index, panel.index)
    assert {"momentum", "momentum_coverage", "trajectory", "direction", "momentum_strength",
            "trend_months", "stability"}.issubset(result.columns)
    assert pd.api.types.is_integer_dtype(result.trend_months.dtype)


@pytest.mark.parametrize("column", ["company_id", "currency", "month"])
def test_required_keys_and_null_keys_are_rejected(column):
    panel = trajectory_panel()
    with pytest.raises(ValueError, match=column):
        score_trajectory(panel.drop(columns=column))
    panel.loc[0, column] = None
    with pytest.raises(ValueError, match=column):
        score_trajectory(panel)


def test_invalid_dates_duplicate_months_and_duplicate_columns_are_rejected():
    panel = trajectory_panel()
    panel["month"] = panel.month.astype(str)
    panel.loc[0, "month"] = "not-a-date"
    with pytest.raises(ValueError, match="month"):
        score_trajectory(panel)
    panel = trajectory_panel()
    duplicate = panel.iloc[[0]].assign(month=pd.Timestamp("2025-01-20"))
    with pytest.raises(ValueError, match="[Dd]uplicat"):
        score_trajectory(pd.concat([panel, duplicate], ignore_index=True))
    with pytest.raises(ValueError, match="columns"):
        score_trajectory(pd.concat([panel, panel[["currency"]]], axis=1))


def test_malformed_present_feature_is_rejected_instead_of_silently_missing():
    panel = trajectory_panel()
    panel["tx_operating_margin_delta3"] = "bad"
    with pytest.raises(ValueError, match="tx_operating_margin_delta3"):
        score_trajectory(panel)


def test_every_prefix_including_empty_history_matches_full_output():
    panel = trajectory_panel(0.1)
    full, full_explain = score_trajectory(panel)
    for stop in range(len(panel) + 1):
        prefix, prefix_explain = score_trajectory(panel.iloc[:stop])
        pd.testing.assert_frame_equal(prefix, full.iloc[:stop])
        expected = full_explain.loc[full_explain.input_position.lt(stop)].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix_explain, expected)


@pytest.mark.parametrize("change, direction, label", [
    (0.02, "flat", "stable"), (0.021, "up", "improving"),
    (-0.02, "flat", "stable"), (-0.021, "down", "deteriorating"),
])
def test_material_direction_threshold_is_fixed_and_symmetric(change, direction, label):
    result, _ = score_trajectory(trajectory_panel(change))
    assert result.direction.iloc[-1] == direction
    assert result.trajectory.iloc[-1] == label


def test_extreme_finite_values_are_bounded_without_warnings():
    panel = trajectory_panel(1e308).assign(tx_lfl_inflow_growth=-1e308)
    result, explain = score_trajectory(panel)
    assert result.momentum.dropna().between(0, 100).all()
    assert result.momentum_coverage.between(0, 1).all()
    assert result.stability.dropna().between(0, 100).all()
    assert explain.feature_score.between(0, 100).all()
    assert not np.isinf(result.select_dtypes("number").to_numpy()).any()


def test_multiindex_labels_are_preserved_in_explanations():
    panel = trajectory_panel(0.1)
    panel.index = pd.MultiIndex.from_arrays([["source"] * len(panel), np.arange(len(panel))],
                                           names=["source", "row"])
    result, explain = score_trajectory(panel)
    pd.testing.assert_index_equal(result.index, panel.index)
    assert explain.input_index.iloc[0] == ("source", 3)


@pytest.mark.parametrize("invalid_month", [123, pd.Timestamp("2025-01-01", tz="UTC")])
def test_numeric_or_timezone_aware_dates_are_rejected(invalid_month):
    panel = trajectory_panel().assign(month=invalid_month)
    with pytest.raises(ValueError, match="month"):
        score_trajectory(panel)


@pytest.mark.parametrize("feature, value", [
    ("tx_operating_margin_delta3", -0.1),
    ("debt_service_to_inflow_ratio_delta3", 0.1),
    ("tx_lfl_inflow_growth", -0.05),
])
@pytest.mark.parametrize("thin_count", [1, 4, np.nan])
def test_thin_bank_month_invalidates_whole_window_and_signed_persistence(feature, value, thin_count):
    panel = trajectory_panel(periods=11).drop(columns="tx_operating_margin_delta3")
    panel[feature] = value
    panel["tx_usable_count"] = 5.0
    panel.loc[5, "tx_usable_count"] = thin_count
    result, explain = score_trajectory(panel)
    assert result.loc[4, "trajectory"] == "deteriorating"
    assert result.loc[4, "trend_months"] == -2
    assert result.loc[5:8, "momentum"].isna().all()
    assert result.loc[5:8, "momentum_coverage"].eq(0).all()
    assert result.loc[5:8, "trend_months"].eq(0).all()
    assert result.loc[5:8, "trajectory"].eq("insufficient_history").all()
    assert result.loc[9, "trajectory"] == "watch"
    assert result.loc[9, "trend_months"] == -1
    assert result.loc[10, "trajectory"] == "deteriorating"
    assert result.loc[10, "trend_months"] == -2
    assert not explain.input_position.between(5, 8).any()


@pytest.mark.parametrize("bad_value", [False, pd.NA])
def test_core_quality_gate_excludes_all_blocks_and_resets_confirmation(bad_value):
    panel = trajectory_panel(0.1, periods=11).assign(
        tx_usable_count=5,
        debt_service_to_inflow_ratio_delta3=-0.1,
        tx_lfl_inflow_growth=0.05,
        inv_ar_delay_median=np.arange(11) * (-10 / 3),
        inv_ap_delay_median=np.arange(11) * (-10 / 3),
        inv_ar_delay_count=5,
        inv_ap_delay_count=5,
    )
    panel["score_input_usable"] = pd.Series(True, index=panel.index, dtype="boolean")
    panel.loc[5, "score_input_usable"] = bad_value
    result, explain = score_trajectory(panel)
    assert result.loc[4, "momentum_coverage"] == 1
    assert result.loc[4, "trend_months"] == 2
    assert result.loc[5:8, "momentum"].isna().all()
    assert result.loc[5:8, "momentum_signal_count"].eq(0).all()
    assert not result.loc[5:8, "momentum_confirmed"].any()
    assert result.loc[5:8, "trend_months"].eq(0).all()
    assert result.loc[5:8, "stability"].isna().all()
    assert result.loc[9, "trajectory"] == "watch"
    assert result.loc[9, "trend_months"] == 1
    assert result.loc[10, "trajectory"] == "improving"
    assert result.loc[10, "trend_months"] == 2
    assert not explain.input_position.between(5, 8).any()


@pytest.mark.parametrize("side", ["ar", "ap"])
@pytest.mark.parametrize("delay_count", [1, 4, np.nan])
def test_exact_delay_sample_gate_does_not_use_total_paid_count(side, delay_count):
    panel = trajectory_panel(periods=11).drop(columns="tx_operating_margin_delta3")
    panel[f"inv_{side}_delay_median"] = np.arange(11) * 4.0
    panel[f"inv_{side}_delay_count"] = 5.0
    panel[f"inv_{side}_paid_count"] = 100
    panel.loc[5, f"inv_{side}_delay_count"] = delay_count
    result, explain = score_trajectory(panel)
    assert result.loc[4, "trajectory"] == "deteriorating"
    assert result.loc[5:8, "momentum"].isna().all()
    assert result.loc[5:8, "momentum_coverage"].eq(0).all()
    assert result.loc[9, "trajectory"] == "watch"
    assert result.loc[10, "trajectory"] == "deteriorating"
    assert not explain.input_position.between(5, 8).any()


@pytest.mark.parametrize("side", ["ar", "ap"])
def test_exact_delay_count_is_authoritative_and_optional_legacy_is_preserved(side):
    panel = trajectory_panel().drop(columns="tx_operating_margin_delta3")
    panel[f"inv_{side}_delay_median"] = np.arange(10) * 4.0
    legacy, legacy_explain = score_trajectory(panel)
    small_paid = panel.assign(**{f"inv_{side}_paid_count": 1})
    small_result, small_explain = score_trajectory(small_paid)
    pd.testing.assert_frame_equal(legacy, small_result)
    pd.testing.assert_frame_equal(legacy_explain, small_explain)
    exact = panel.assign(**{f"inv_{side}_delay_count": 5, f"inv_{side}_paid_count": 0})
    exact_result, exact_explain = score_trajectory(exact)
    pd.testing.assert_frame_equal(legacy, exact_result)
    pd.testing.assert_frame_equal(legacy_explain, exact_explain)


def test_valid_quality_gates_are_not_health_signals_and_leave_formulas_unchanged():
    panel = trajectory_panel(0.1).assign(
        debt_service_to_inflow_ratio_delta3=-0.1,
        tx_lfl_inflow_growth=0.05,
        inv_ar_delay_median=np.arange(10) * (-10 / 3),
        inv_ap_delay_median=np.arange(10) * (-10 / 3),
    )
    expected, expected_explain = score_trajectory(panel)
    for count in (5, 100):
        gated = panel.assign(score_input_usable=True, tx_usable_count=count,
                             inv_ar_delay_count=count, inv_ap_delay_count=count)
        actual, actual_explain = score_trajectory(gated)
        pd.testing.assert_frame_equal(expected, actual)
        pd.testing.assert_frame_equal(expected_explain, actual_explain)
    quality_only = panel[["company_id", "currency", "month"]].assign(
        score_input_usable=True, tx_usable_count=100, inv_ar_delay_count=100, inv_ap_delay_count=100)
    absent, explanation = score_trajectory(quality_only)
    assert absent.momentum.isna().all()
    assert absent.trajectory.eq("insufficient_history").all()
    assert explanation.empty


def test_quality_gated_outputs_and_explanations_are_prefix_invariant():
    panel = trajectory_panel(0.1, periods=14).assign(
        score_input_usable=True,
        tx_usable_count=5,
        debt_service_to_inflow_ratio_delta3=-0.1,
        tx_lfl_inflow_growth=0.05,
        inv_ar_delay_median=np.arange(14) * (-10 / 3),
        inv_ap_delay_median=np.arange(14) * (-10 / 3),
        inv_ar_delay_count=5,
        inv_ap_delay_count=5,
    )
    panel.loc[4, "score_input_usable"] = False
    panel.loc[6, "tx_usable_count"] = 4
    panel.loc[9, "inv_ar_delay_count"] = 1
    panel.loc[10, "inv_ap_delay_count"] = 4
    full, full_explain = score_trajectory(panel)
    for stop in range(len(panel) + 1):
        prefix, prefix_explain = score_trajectory(panel.iloc[:stop])
        pd.testing.assert_frame_equal(prefix, full.iloc[:stop])
        expected = full_explain.loc[full_explain.input_position.lt(stop)].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix_explain, expected)
