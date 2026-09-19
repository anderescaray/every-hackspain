import json

import numpy as np
import pandas as pd
import pytest

from xray.features.temporal import add_ratios
from xray.score.level import COMPONENT_WEIGHTS, FEATURE_SPECS, fit_reference, score_level


LEVEL_COLUMNS = [
    "level", "level_operations", "level_debt", "level_collections", "level_payments",
    "level_coverage", "level_components_available", "has_uncovered_debt_service",
]
EXPLANATION_COLUMNS = [
    "input_index", "feature", "component", "value", "feature_score", "effective_weight",
    "contribution", "direction", "definition",
]


def financial_panel():
    return pd.DataFrame({
        "company_id": ["healthy", "strained", "middle"],
        "group_id": ["g1", "g2", "g3"],
        "tx_operating_margin": [0.25, -0.25, 0.0],
        "debt_service_to_inflow_ratio": [0.0, 0.5, 0.15],
        "inv_ar_delay_median": [0.0, 60.0, 15.0],
        "inv_ap_delay_median": [-10.0, 90.0, 7.0],
    }, index=pd.Index([91, 4, 57], name="source_row"))


def empirical_panel():
    panel = pd.concat([financial_panel()] * 40, ignore_index=True)
    panel["group_id"] = np.repeat(np.arange(20), 6)
    panel["company_id"] = [f"{group}-{company}" for group, company in
                           zip(panel.group_id, panel.company_id)]
    return panel


def test_financial_order_and_output_contract():
    panel = financial_panel()
    result, explanations = score_level(panel, fit_reference(panel))
    pd.testing.assert_index_equal(result.index, panel.index)
    assert result.columns.tolist() == LEVEL_COLUMNS
    assert explanations.columns.tolist() == EXPLANATION_COLUMNS
    assert result.loc[91, "level"] > result.loc[57, "level"] > result.loc[4, "level"]
    assert result.level_coverage.eq(1.0).all()
    assert result.level_components_available.eq(4).all()
    assert pd.api.types.is_integer_dtype(result.level_components_available)
    assert result.iloc[:, :5].ge(0).all().all()
    assert result.iloc[:, :5].le(100).all().all()
    assert explanations.input_index.drop_duplicates().tolist() == panel.index.tolist()


@pytest.mark.parametrize("feature,values,increasing", [
    ("tx_operating_margin", [-1.0, -0.5, -0.25, 0.0, 0.1, 0.3, 1.0], True),
    ("debt_service_to_inflow_ratio", [0.0, 0.02, 0.1, 0.2, 0.5, 1.0, 2.0], False),
    ("inv_ar_delay_median", [-30.0, -1.0, 0.0, 7.0, 15.0, 60.0, 365.0], False),
    ("inv_ap_delay_median", [-30.0, -1.0, 0.0, 7.0, 15.0, 60.0, 365.0], False),
])
@pytest.mark.parametrize("use_reference", [False, True])
def test_each_dimension_is_monotonic(feature, values, increasing, use_reference):
    panel = pd.concat([financial_panel().iloc[[2]]] * len(values), ignore_index=True)
    panel[feature] = values
    reference = fit_reference(empirical_panel() if use_reference else pd.DataFrame())
    assert reference["features"][feature]["empirical_active"] is use_reference
    result, _ = score_level(panel, reference)
    differences = np.diff(result.level)
    assert (differences >= 0).all() if increasing else (differences <= 0).all()
    assert result.level.nunique() > 1


def test_three_month_preference_and_explicit_current_fallback():
    panel = financial_panel()
    panel["tx_operating_margin_ma3"] = [0.05, np.nan, np.inf]
    panel["debt_service_to_inflow_ratio_ma3"] = [0.1, 0.2, np.nan]
    panel["inv_ar_delay_median_ma3"] = [7.0, np.nan, 5.0]
    _, explanations = score_level(panel, fit_reference(pd.DataFrame()))
    chosen = explanations.set_index(["input_index", "component"])
    assert chosen.loc[(91, "operations"), "feature"] == "tx_operating_margin_ma3"
    assert chosen.loc[(91, "operations"), "value"] == 0.05
    assert chosen.loc[(4, "operations"), "feature"] == "tx_operating_margin"
    assert chosen.loc[(57, "operations"), "feature"] == "tx_operating_margin"
    assert chosen.loc[(91, "collections"), "feature"] == "inv_ar_delay_median_ma3"
    assert "3" in chosen.loc[(91, "operations"), "definition"]
    assert "fallback" in chosen.loc[(4, "operations"), "definition"].lower()
    assert chosen.loc[(91, "operations"), "direction"] == "higher_is_better"
    assert chosen.loc[(91, "debt"), "direction"] == "lower_is_better"


def test_unobserved_debt_is_not_inferred_as_zero():
    panel = pd.DataFrame({
        "tx_operating_margin": [0.1, 0.1],
        "tx_inflow": [0.0, 100.0],
        "debt_principal_paid": [0.0, 0.0],
        "debt_interest_paid": [0.0, 0.0],
        "debt_service_to_inflow_ratio": [np.nan, 0.0],
    })
    result, explanations = score_level(panel, fit_reference(panel))
    assert np.isnan(result.loc[0, "level_debt"])
    assert result.loc[1, "level_debt"] == 100.0
    assert result.loc[0, "level_coverage"] == 0.45
    assert result.loc[1, "level_coverage"] == 0.7
    assert result.loc[0, "level_components_available"] == 1
    assert result.loc[0, "level"] == result.loc[0, "level_operations"]
    assert not ((explanations.input_index == 0) & (explanations.component == "debt")).any()


@pytest.mark.parametrize("reference_values", [[0.0] * 20, [0.0] * 18 + [0.1, 0.2], [0.1, 0.2, 0.5]])
def test_zero_debt_remains_good_even_with_tied_reference(reference_values):
    reference = fit_reference(pd.DataFrame({"debt_service_to_inflow_ratio": reference_values}))
    result, _ = score_level(pd.DataFrame({"debt_service_to_inflow_ratio": [0.0, 0.0, 0.1]}), reference)
    assert result.level_debt.iloc[0] == result.level_debt.iloc[1] == 100.0
    assert result.level_debt.iloc[2] < 100.0


def test_early_and_ontime_payment_have_same_score():
    panel = pd.DataFrame({"inv_ap_delay_median": [-60.0, -15.0, 0.0, 20.0]})
    result, _ = score_level(panel, fit_reference(panel))
    assert result.level_payments.iloc[:3].eq(100.0).all()
    assert result.level_payments.iloc[3] < 100.0


def test_missing_and_nonfinite_features_do_not_produce_infinity_or_fabricated_health():
    panel = pd.DataFrame({
        "tx_operating_margin": pd.Series([pd.NA, "invalid", np.inf, -np.inf], dtype=object),
        "debt_service_to_inflow_ratio": [np.nan, np.inf, -np.inf, -0.1],
        "inv_ar_delay_median": [np.inf, -np.inf, np.nan, np.nan],
    })
    reference = fit_reference(panel)
    json.dumps(reference, allow_nan=False)
    result, explanations = score_level(panel, reference)
    assert result.iloc[:, :5].isna().all().all()
    assert result.level_coverage.eq(0).all()
    assert result.level_components_available.eq(0).all()
    assert not np.isinf(result.to_numpy(dtype=float)).any()
    assert explanations.empty


@pytest.mark.parametrize("index", [pd.Index([], dtype=int), pd.Index([9, 2]), pd.Index(["z", "a"])])
def test_empty_or_absent_columns_preserve_rows(index):
    panel = pd.DataFrame(index=index)
    reference = fit_reference(panel)
    assert isinstance(reference, dict)
    json.dumps(reference, allow_nan=False)
    result, explanations = score_level(panel, reference)
    pd.testing.assert_index_equal(result.index, panel.index)
    assert result.columns.tolist() == LEVEL_COLUMNS
    assert explanations.columns.tolist() == EXPLANATION_COLUMNS
    assert result.level.isna().all()
    assert result.level_coverage.eq(0).all()
    assert result.level_components_available.eq(0).all()
    assert explanations.empty


def test_empty_reference_uses_financial_anchors():
    panel = pd.DataFrame({
        "tx_operating_margin": [0.0], "debt_service_to_inflow_ratio": [0.15],
        "inv_ar_delay_median": [15.0], "inv_ap_delay_median": [30.0],
    })
    result, _ = score_level(panel, fit_reference(pd.DataFrame()))
    assert result.iloc[0].level_operations == 55.0
    assert result.iloc[0].level_debt == 70.0
    assert result.iloc[0].level_collections == 65.0
    assert result.iloc[0].level_payments == 40.0
    assert result.iloc[0].level == pytest.approx(58.0)


def test_ratios_make_scores_invariant_to_common_monetary_scale():
    amounts = pd.DataFrame({
        "tx_inflow": [100.0, 200.0], "tx_outflow": [80.0, 240.0],
        "tx_fixed_cost": [30.0, 100.0], "debt_principal_paid": [10.0, 40.0],
        "debt_interest_paid": [1.0, 4.0], "tx_fees_paid": [1.0, 2.0],
        "inv_ar_due_30_amount": [20.0, 30.0], "inv_issued_amount": [90.0, 210.0],
        "inv_ap_due_30_amount": [10.0, 40.0], "inv_received_amount": [85.0, 250.0],
    })
    panel = add_ratios(amounts)
    scaled = add_ratios(amounts * 10000)
    reference = fit_reference(panel)
    original_score, original_explanations = score_level(panel, reference)
    scaled_score, scaled_explanations = score_level(scaled, reference)
    pd.testing.assert_frame_equal(original_score, scaled_score)
    pd.testing.assert_frame_equal(original_explanations, scaled_explanations)


def test_frozen_reference_is_independent_of_batch_and_identity():
    reference = fit_reference(empirical_panel())
    panel = financial_panel().iloc[[2]].assign(company_id="unseen", group_id="unseen-group")
    original, original_explanations = score_level(panel, reference)
    others = financial_panel().iloc[:2].copy()
    others["tx_operating_margin"] = [-1.0, 1.0]
    others["debt_service_to_inflow_ratio"] = [20.0, 0.0]
    batch = pd.concat([others, panel]).iloc[::-1]
    together, explanations = score_level(batch, reference)
    pd.testing.assert_frame_equal(original, together.loc[panel.index])
    pd.testing.assert_frame_equal(original_explanations, explanations.loc[
        explanations.input_index.isin(panel.index)].reset_index(drop=True))
    renamed, _ = score_level(panel.assign(company_id="other", group_id="other"), reference)
    pd.testing.assert_frame_equal(original, renamed)


@pytest.mark.parametrize("sort_keys", [False, True])
@pytest.mark.parametrize("empirical", [False, True])
def test_json_roundtrip_constants_and_reference_are_small_and_native(sort_keys, empirical):
    json.dumps(FEATURE_SPECS, allow_nan=False)
    json.dumps(COMPONENT_WEIGHTS, allow_nan=False)
    reference = fit_reference(empirical_panel() if empirical else financial_panel())
    serialized = json.dumps(reference, allow_nan=False, sort_keys=sort_keys)
    assert len(serialized) < 20000
    restored = json.loads(serialized)
    panel = financial_panel()
    first = score_level(panel, reference)
    second = score_level(panel, restored)
    for original, reloaded in zip(first, second):
        pd.testing.assert_frame_equal(original, reloaded)
    assert sum(COMPONENT_WEIGHTS.values()) == 1.0
    assert COMPONENT_WEIGHTS == {"operations": 0.45, "debt": 0.25, "collections": 0.15, "payments": 0.15}


def test_explanations_reconcile_exactly_and_reweight_only_present_components():
    panel = financial_panel()
    panel.loc[4, "inv_ar_delay_median"] = np.nan
    panel.loc[57, ["tx_operating_margin", "debt_service_to_inflow_ratio"]] = np.nan
    result, explanations = score_level(panel, fit_reference(panel))
    totals = explanations.groupby("input_index", sort=False).contribution.sum().reindex(panel.index)
    np.testing.assert_array_equal(result.level, totals)
    weights = explanations.groupby("input_index", sort=False).effective_weight.sum()
    np.testing.assert_allclose(weights, 1.0, rtol=0, atol=1e-15)
    np.testing.assert_allclose(explanations.contribution,
                               explanations.effective_weight * explanations.feature_score, rtol=0, atol=0)
    assert result.loc[4, "level_coverage"] == pytest.approx(0.85)
    assert result.loc[57, "level_coverage"] == pytest.approx(0.30)
    assert result.level_components_available.tolist() == [4, 3, 2]
    assert explanations.feature.is_unique is False


def test_reference_balances_groups_instead_of_holding_size():
    panel = pd.DataFrame({
        "group_id": np.repeat(np.arange(20), 5),
        "company_id": np.repeat(np.arange(20), 5),
        "tx_operating_margin": np.repeat(np.linspace(-0.4, 0.4, 20), 5),
    })
    many_subsidiaries = pd.concat([panel.iloc[:5]] * 200, ignore_index=True)
    many_subsidiaries["company_id"] = np.repeat(np.arange(200) + 100, 5)
    expanded = pd.concat([many_subsidiaries, panel.iloc[5:]], ignore_index=True)
    target = pd.DataFrame({"tx_operating_margin": [-0.3, 0.0, 0.15, 0.3]})
    references = [fit_reference(sample) for sample in [panel, expanded]]
    assert all(ref["features"]["tx_operating_margin"]["empirical_active"] for ref in references)
    balanced, _ = score_level(target, references[0])
    large_holding, _ = score_level(target, references[1])
    pd.testing.assert_frame_equal(balanced, large_holding)


def test_reference_balances_companies_and_observation_history_within_group():
    panel = empirical_panel()
    repeated_history = pd.concat([panel.iloc[:1]] * 200 + [panel.iloc[1:]], ignore_index=True)
    target = pd.DataFrame({"tx_operating_margin": [-0.3, 0.0, 0.15, 0.3]})
    references = [fit_reference(sample) for sample in [panel, repeated_history]]
    assert all(ref["features"]["tx_operating_margin"]["empirical_active"] for ref in references)
    original, _ = score_level(target, references[0])
    repeated, _ = score_level(target, references[1])
    pd.testing.assert_frame_equal(original, repeated)


def test_reference_does_not_depend_on_row_order_or_identifier_spelling():
    panel = financial_panel()
    altered = panel.iloc[::-1].copy()
    altered["company_id"] = ["new1", "new2", "new3"]
    altered["group_id"] = ["group-x", "group-y", "group-z"]
    result, _ = score_level(panel, fit_reference(panel))
    reordered, _ = score_level(panel, fit_reference(altered))
    pd.testing.assert_frame_equal(result, reordered)


def test_non_score_columns_and_eligibility_are_ignored():
    panel = financial_panel()
    reference = fit_reference(panel)
    decorated = panel.assign(
        cash_balance=-1e10, debt_total_outstanding=1e10, inv_ar_overdue_ratio=1.0,
        inv_ap_overdue_ratio=1.0, inv_dso_median=365.0, inv_dpo_median=365.0,
        tx_counterparty_hhi=1.0, stress_events_count=100, erp_id="bad",
        tx_inflow_outflow_ratio=0.0, is_training_eligible=False,
    )
    assert fit_reference(decorated) == reference
    for expected, actual in zip(score_level(panel, reference), score_level(decorated, reference)):
        pd.testing.assert_frame_equal(expected, actual)


def test_input_and_reference_are_not_mutated():
    panel = financial_panel()
    copy = panel.copy(deep=True)
    reference = fit_reference(panel)
    frozen = json.dumps(reference, sort_keys=True, allow_nan=False)
    score_level(panel, reference)
    pd.testing.assert_frame_equal(panel, copy)
    assert json.dumps(reference, sort_keys=True, allow_nan=False) == frozen


def test_duplicate_score_index_is_rejected_but_reference_index_can_repeat():
    panel = financial_panel()
    panel.index = [1, 1, 2]
    reference = fit_reference(panel)
    with pytest.raises(ValueError, match="(?i)index|indice"):
        score_level(panel, reference)


def test_multiindex_and_string_index_are_preserved():
    for index in [pd.Index(["third", "first", "second"], name="row"),
                  pd.MultiIndex.from_tuples([("a", 3), ("b", 1), ("a", 2)], names=["entity", "time"])]:
        panel = financial_panel().set_axis(index)
        result, explanations = score_level(panel, fit_reference(panel))
        pd.testing.assert_index_equal(result.index, index)
        assert explanations.input_index.drop_duplicates().tolist() == index.tolist()


def test_nullable_numeric_inputs_work_without_infinity():
    panel = pd.DataFrame({
        "tx_operating_margin": pd.Series([0.1, pd.NA], dtype="Float64"),
        "debt_service_to_inflow_ratio": pd.Series([0.0, pd.NA], dtype="Float64"),
    })
    result, _ = score_level(panel, fit_reference(panel))
    assert result.loc[0, "level"] > 0
    assert np.isnan(result.loc[1, "level"])
    assert not np.isinf(result.to_numpy(dtype=float)).any()


def test_empirical_blend_has_explicit_fixed_formula():
    panel = pd.DataFrame({"tx_operating_margin": [-0.25, 0.25] * 50,
                          "debt_service_to_inflow_ratio": [0.0, 0.2] * 50,
                          "group_id": np.repeat(np.arange(20), 5)})
    reference = fit_reference(panel)
    assert reference["empirical_min_rows"] == 100
    assert reference["empirical_min_groups"] == 20
    assert reference["features"]["tx_operating_margin"]["empirical_active"]
    assert reference["features"]["debt_service_to_inflow_ratio"]["empirical_active"]
    target = pd.DataFrame({"tx_operating_margin": [0.0], "debt_service_to_inflow_ratio": [0.1]})
    result, _ = score_level(target, reference)
    assert result.loc[0, "level_operations"] == pytest.approx(0.7 * 55 + 0.3 * 50)
    assert result.loc[0, "level_debt"] == pytest.approx(0.7 * 80 + 0.3 * 50)
    assert reference["features"]["tx_operating_margin"]["reference_low"] == -0.25
    assert reference["features"]["tx_operating_margin"]["reference_high"] == 0.25


def test_extreme_finite_ratios_cannot_overflow_reference_or_rescue_full_debt_burden():
    panel = pd.DataFrame({"debt_service_to_inflow_ratio": [0.0, 1.0, 1e100, 1e308]})
    reference = fit_reference(panel)
    json.dumps(reference, allow_nan=False)
    result, explanations = score_level(panel, reference)
    assert result.level.iloc[0] == 100.0
    assert result.level.iloc[1:].eq(0.0).all()
    assert not np.isinf(result.to_numpy(dtype=float)).any()
    assert not np.isinf(explanations.select_dtypes("number").to_numpy()).any()


def test_reference_quantiles_resist_sparse_extremes_and_keep_atom_ties():
    panel = pd.DataFrame({"debt_service_to_inflow_ratio": [0.0] * 99 + [1e308]})
    reference = fit_reference(panel)
    spec = reference["features"]["debt_service_to_inflow_ratio"]
    assert spec["reference_low"] == spec["reference_high"] == 0.0
    result, _ = score_level(pd.DataFrame({"debt_service_to_inflow_ratio": [0.15]}), reference)
    assert result.level.iloc[0] == 70.0


def test_near_constant_reference_does_not_magnify_numerical_noise():
    panel = pd.DataFrame({"debt_service_to_inflow_ratio": [0.0, 1e-320]})
    target = pd.DataFrame({"debt_service_to_inflow_ratio": [0.0, 5e-321, 1e-320]})
    result, _ = score_level(target, fit_reference(panel))
    anchors, _ = score_level(target, fit_reference(pd.DataFrame()))
    pd.testing.assert_frame_equal(result, anchors)


def test_all_component_subsets_have_bounded_exactly_reconciled_score():
    rows = []
    features = list(FEATURE_SPECS)
    for mask in range(16):
        rows.append({feature: (1.0 if feature == "tx_operating_margin" else 0.0)
                     for offset, feature in enumerate(features) if mask & (1 << offset)})
    panel = pd.DataFrame(rows)
    result, explanations = score_level(panel, fit_reference(pd.DataFrame()))
    assert np.isnan(result.loc[0, "level"])
    assert result.level.iloc[1:].le(100.0).all()
    assert result.level.iloc[1:].ge(100.0 - 1e-12).all()
    totals = explanations.groupby("input_index", sort=False).contribution.sum()
    np.testing.assert_array_equal(result.loc[totals.index, "level"], totals)


def test_missing_group_ids_and_company_only_reference_are_supported():
    panel = financial_panel()
    panel.loc[91, "group_id"] = None
    reference = fit_reference(panel)
    json.dumps(reference, allow_nan=False)
    with_missing, _ = score_level(panel, reference)
    assert with_missing.level.notna().all()
    company_only = panel.drop(columns="group_id")
    repeated = pd.concat([company_only.iloc[:1]] * 50 + [company_only.iloc[1:]], ignore_index=True)
    original, _ = score_level(company_only, fit_reference(company_only))
    expanded, _ = score_level(company_only, fit_reference(repeated))
    pd.testing.assert_frame_equal(original, expanded)


@pytest.mark.parametrize("empirical", [False, True])
def test_debt_service_without_inflow_is_explicit_zero_with_coverage(empirical):
    panel = pd.DataFrame({
        "tx_operating_margin": [0.1] * 4,
        "tx_inflow": [0.0] * 4,
        "debt_principal_paid": [10.0, 0.0, 10.0, 1e308],
        "debt_interest_paid": [0.0, 2.0, 2.0, 1e308],
        "debt_service_to_inflow_ratio": [np.nan, np.inf, 0.0, np.nan],
        "debt_service_to_inflow_ratio_ma3": [0.0, 0.1, 0.0, np.nan],
    }, index=pd.Index([81, 23, 42, 7], name="source_row"))
    original = panel.copy(deep=True)
    reference = fit_reference(empirical_panel() if empirical else pd.DataFrame())
    reference = json.loads(json.dumps(reference, allow_nan=False))
    result, explanations = score_level(panel, reference)
    pd.testing.assert_frame_equal(panel, original)
    pd.testing.assert_index_equal(result.index, panel.index)
    assert result.has_uncovered_debt_service.dtype == bool
    assert result.has_uncovered_debt_service.all()
    assert result.level_debt.eq(0.0).all()
    assert result.level_coverage.eq(0.7).all()
    assert result.level_components_available.eq(2).all()
    np.testing.assert_allclose(result.level, result.level_operations * 0.45 / 0.7)
    debt = explanations.loc[explanations.component.eq("debt")]
    assert debt.feature.eq("debt_service_without_inflow").all()
    assert debt.value.eq(1.0).all()
    assert debt.feature_score.eq(0.0).all()
    assert debt.contribution.eq(0.0).all()
    np.testing.assert_allclose(debt.effective_weight, 0.25 / 0.7)
    assert debt.definition.str.contains("Indicador").all()
    assert debt.definition.str.contains("tx_inflow == 0").all()
    assert debt.definition.str.contains("no es un ratio").all()
    totals = explanations.groupby("input_index").contribution.sum().reindex(panel.index)
    np.testing.assert_array_equal(result.level, totals)
    np.testing.assert_allclose(explanations.groupby("input_index").effective_weight.sum(), 1.0)
    assert not np.isinf(explanations.select_dtypes("number").to_numpy()).any()
    for index in panel.index:
        alone = score_level(panel.loc[[index]], reference)
        pd.testing.assert_frame_equal(alone[0], result.loc[[index]])
        pd.testing.assert_frame_equal(alone[1], explanations.loc[
            explanations.input_index.eq(index)].reset_index(drop=True))
    debt_reference = fit_reference(panel)["features"]["debt_service_to_inflow_ratio"]
    assert debt_reference["reference_rows"] == 0
    assert debt_reference["reference_low"] is None
    assert debt_reference["reference_high"] is None


def test_zero_inflow_with_zero_or_unknown_service_does_not_fabricate_health():
    panel = pd.DataFrame({
        "tx_inflow": [0.0] * 7,
        "debt_principal_paid": [0.0, np.nan, 1.0, 0.0, np.inf, pd.NA, "invalid"],
        "debt_interest_paid": [0.0, np.nan, np.nan, np.nan, 0.0, 1.0, 0.0],
        "debt_service_to_inflow_ratio": [0.0] * 7,
        "debt_service_to_inflow_ratio_ma3": [0.0] * 7,
    })
    for candidate in [panel, panel.drop(columns="debt_interest_paid")]:
        result, explanations = score_level(candidate, fit_reference(candidate))
        assert result.level_debt.isna().all()
        assert result.level.isna().all()
        assert result.level_coverage.eq(0.0).all()
        assert result.level_components_available.eq(0).all()
        assert not result.has_uncovered_debt_service.any()
        assert explanations.empty


def test_uncovered_debt_never_improves_as_inflow_falls_to_zero():
    panel = pd.DataFrame({
        "tx_inflow": [100.0, 50.0, 10.0, 0.0],
        "debt_principal_paid": [10.0] * 4,
        "debt_interest_paid": [0.0] * 4,
        "debt_service_to_inflow_ratio": [0.1, 0.2, 1.0, np.nan],
        "tx_operating_margin": [0.1] * 4,
    })
    result, _ = score_level(panel, fit_reference(empirical_panel()))
    assert (np.diff(result.level) <= 0).all()
    assert result.level_debt.iloc[-1] == 0.0
    assert result.has_uncovered_debt_service.tolist() == [False, False, False, True]
    assert result.level_coverage.eq(0.7).all()


@pytest.mark.parametrize("rows,groups,spread,active", [
    (99, 20, 0.5, False), (100, 19, 0.5, False),
    (100, 20, 0.5, True), (101, 21, 0.5, True),
    (100, 20, 0.0, False), (100, 20, 1e-13, False),
])
def test_empirical_requires_minimum_valid_rows_groups_and_spread(rows, groups, spread, active):
    panel = pd.DataFrame({
        "tx_operating_margin": np.resize([0.0, spread], rows),
        "group_id": np.arange(rows) % groups,
    })
    reference = fit_reference(panel)
    spec = reference["features"]["tx_operating_margin"]
    assert reference["empirical_min_rows"] == 100
    assert reference["empirical_min_groups"] == 20
    assert spec["reference_rows"] == rows
    assert spec["reference_groups"] == groups
    assert spec["empirical_active"] is active
    assert spec["reference_low"] == 0.0
    assert spec["reference_high"] == spread
    target = pd.DataFrame({"tx_operating_margin": [0.1]})
    actual, _ = score_level(target, json.loads(json.dumps(reference, allow_nan=False)))
    if active:
        assert actual.level_operations.iloc[0] == pytest.approx(0.7 * 75.0 + 0.3 * 20.0)
    else:
        assert actual.level_operations.iloc[0] == 75.0


def test_empirical_gates_are_per_component_and_ignore_invalid_rows():
    panel = empirical_panel()
    panel.loc[99:, "debt_service_to_inflow_ratio"] = np.nan
    panel.loc[panel.group_id.eq(19), "inv_ar_delay_median"] = np.inf
    reference = fit_reference(panel)
    specs = reference["features"]
    assert specs["tx_operating_margin"]["empirical_active"]
    assert specs["inv_ap_delay_median"]["empirical_active"]
    assert specs["debt_service_to_inflow_ratio"]["reference_rows"] == 99
    assert not specs["debt_service_to_inflow_ratio"]["empirical_active"]
    assert specs["inv_ar_delay_median"]["reference_rows"] == 114
    assert specs["inv_ar_delay_median"]["reference_groups"] == 19
    assert not specs["inv_ar_delay_median"]["empirical_active"]


@pytest.mark.parametrize("ids", ["absent", "missing", "nineteen_and_missing"])
def test_unknown_group_ids_do_not_satisfy_empirical_group_minimum(ids):
    panel = empirical_panel()
    if ids == "absent":
        panel = panel.drop(columns="group_id")
    elif ids == "missing":
        panel["group_id"] = None
    else:
        panel.loc[panel.group_id.eq(19), "group_id"] = np.nan
    reference = fit_reference(panel)
    for spec in reference["features"].values():
        assert spec["reference_rows"] == 120
        assert spec["reference_groups"] == (19 if ids == "nineteen_and_missing" else 0)
        assert not spec["empirical_active"]


@pytest.mark.parametrize("side,component", [("ar", "collections"), ("ap", "payments")])
def test_current_invoice_delay_requires_exact_count_if_available(side, component):
    feature = f"inv_{side}_delay_median"
    count = f"inv_{side}_delay_count"
    panel = pd.DataFrame({
        feature: [15.0] * 10,
        count: pd.Series([0, 4, 5, 10, pd.NA, np.inf, -1, "invalid", "5", 4.9], dtype=object),
        f"inv_{side}_paid_count": [999] * 10,
    })
    result, explanations = score_level(panel, fit_reference(panel))
    expected = pd.Series([False, False, True, True, False, False, False, False, True, False])
    pd.testing.assert_series_equal(result[f"level_{component}"].notna(), expected, check_names=False)
    assert result.loc[expected, f"level_{component}"].eq(65.0).all()
    assert result.loc[~expected, "level"].isna().all()
    assert result.loc[~expected, "level_coverage"].eq(0.0).all()
    assert explanations.input_index.tolist() == [2, 3, 8]
    assert fit_reference(panel)["features"][feature]["reference_rows"] == 3
    assert explanations.definition.str.contains(count).all()
    compatibility = panel.drop(columns=count)
    compatible, _ = score_level(compatibility, fit_reference(compatibility))
    assert compatible[f"level_{component}"].eq(65.0).all()
    paid_count_only, _ = score_level(compatibility.assign(**{f"inv_{side}_paid_count": 0}),
                                     fit_reference(compatibility))
    pd.testing.assert_frame_equal(compatible, paid_count_only)


@pytest.mark.parametrize("side", ["ar", "ap"])
def test_exact_delay_count_filters_empirical_reference_support(side):
    feature = f"inv_{side}_delay_median"
    panel = empirical_panel()
    panel[f"inv_{side}_delay_count"] = 5
    panel.loc[99:, f"inv_{side}_delay_count"] = 4
    spec = fit_reference(panel)["features"][feature]
    assert spec["reference_rows"] == 99
    assert not spec["empirical_active"]


@pytest.mark.parametrize("side,component", [("ar", "collections"), ("ap", "payments")])
def test_current_delay_count_is_not_used_to_validate_three_month_window(side, component):
    feature = f"inv_{side}_delay_median"
    panel = pd.DataFrame({
        feature: [30.0] * 4,
        f"{feature}_ma3": [7.0, 7.0, np.nan, np.nan],
        f"inv_{side}_delay_count": [0, 5, 0, 5],
    })
    result, explanations = score_level(panel, fit_reference(pd.DataFrame()))
    assert result[f"level_{component}"].iloc[:2].eq(85.0).all()
    assert np.isnan(result[f"level_{component}"].iloc[2])
    assert result[f"level_{component}"].iloc[3] == 40.0
    assert explanations.feature.tolist() == [f"{feature}_ma3", f"{feature}_ma3", feature]
    assert explanations.definition.iloc[:2].str.contains("no valida").all()
