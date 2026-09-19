import json

import numpy as np
import pandas as pd
import pytest

from xray.score import ScoreConfig, fit_reference_bundle, score_panel


def score_fixture():
    frames = []
    for i in range(10):
        months = pd.date_range('2025-01-01', periods=12, freq='MS')
        margin = np.linspace(-.2, .35, 12) if i % 2 == 0 else np.linspace(.35, -.2, 12)
        p = pd.DataFrame({'company_id': f'C{i}', 'group_id': f'G{i // 2}', 'currency': 'EUR',
                          'month': months, 'tx_count': 40, 'tx_usable_count': 40,
                          'tx_usable_row_share': 1., 'tx_operating_amount_share': .9,
                          'tx_company_coverage': 1., 'has_partial_currency_coverage': False,
                          'history_observed_months': np.arange(1, 13),
                          'has_sufficient_history': np.arange(1, 13) >= 6,
                          'tx_operating_margin': margin,
                          'debt_service_to_inflow_ratio': .1,
                          'tx_inflow': 100., 'debt_principal_paid': 10., 'debt_interest_paid': 0.,
                          'inv_ar_delay_median': 5., 'inv_ap_delay_median': 3.,
                          'inv_ar_paid_count': 10., 'inv_ap_paid_count': 10.,
                          'inv_ar_delay_count': 10., 'inv_ap_delay_count': 10.,
                          'inv_ar_late_paid_ratio': .2, 'inv_ap_late_paid_ratio': .1,
                          'tx_lfl_inflow_growth': 0.})
        for col in ('tx_operating_margin', 'debt_service_to_inflow_ratio'):
            p[f'{col}_ma3'] = p[col].rolling(3, min_periods=3).mean()
            p[f'{col}_delta3'] = p[col].diff(3)
            for window in (3, 6):
                p[f'{col}_slope{window}'] = p[col].rolling(window).apply(
                    lambda values: np.polyfit(np.arange(window), values, 1)[0], raw=True)
        frames.append(p)
    return pd.concat(frames, ignore_index=True)


def test_reference_groups_disjoint_and_no_future_in_reference():
    panel = score_fixture()
    bundle = fit_reference_bundle(panel)
    assert not set(bundle['reference_groups']) & set(bundle['holdout_groups'])
    assert set(bundle['reference_groups']) | set(bundle['holdout_groups']) == set(panel.group_id)
    assert len(bundle['holdout_groups']) == 1
    for reference in bundle['references']:
        assert reference['max_observed_month'] is None or pd.Timestamp(reference['max_observed_month']) < pd.Timestamp(reference['effective_from'])
    json.dumps(bundle, allow_nan=False)


def test_prefix_and_future_mutation_do_not_change_scores():
    panel = score_fixture()
    prefix = panel.loc[panel.month <= '2025-08-01'].copy()
    early, _ = score_panel(prefix, fit_reference_bundle(prefix))
    modified = panel.copy()
    modified.loc[modified.month > '2025-08-01', 'tx_operating_margin'] = -.95
    later, _ = score_panel(modified, fit_reference_bundle(modified))
    keys = ['company_id', 'currency', 'month']
    pd.testing.assert_frame_equal(early.set_index(keys).sort_index(),
                                  later.loc[later.month <= '2025-08-01'].set_index(keys).sort_index())


def test_frozen_reference_unseen_entities_and_batch_independence():
    panel = score_fixture()
    bundle = json.loads(json.dumps(fit_reference_bundle(panel)))
    unseen = panel.loc[panel.company_id.eq('C0')].assign(company_id='NEW', group_id='NEW_GROUP')
    alone, _ = score_panel(unseen, bundle)
    batch, _ = score_panel(pd.concat([panel, unseen], ignore_index=True), bundle)
    pd.testing.assert_frame_equal(alone.reset_index(drop=True),
                                  batch.loc[batch.company_id.eq('NEW')].reset_index(drop=True))
    assert alone.reference_partition.eq('unseen').all()
    assert alone.score.between(0, 100).all()


def test_missing_month_is_not_scored_or_replaced_by_fifty():
    p = score_fixture()
    missing = (p.company_id == 'C0') & (p.month == '2025-07-01')
    p.loc[missing, ['tx_count', 'tx_usable_count']] = 0
    result, _ = score_panel(p, fit_reference_bundle(p))
    row = result.loc[missing].iloc[0]
    assert pd.isna(row.score)
    assert row.score_status == 'not_scored'
    assert row.trajectory == 'insufficient_history'
    assert row.score_reason == 'no_usable_transactions'


def test_score_decomposition_and_bounds():
    p = score_fixture()
    result, explanation = score_panel(p, fit_reference_bundle(p))
    assert result.score.dropna().between(0, 100).all()
    assert np.allclose(result.score.dropna(), (result.level + result.momentum_adjustment + result.clipping_adjustment).dropna())
    assert not np.isinf(result.select_dtypes('number').to_numpy(dtype=float)).any()
    sums = explanation.groupby(['company_id', 'currency', 'month']).final_contribution.sum()
    scores = result.set_index(['company_id', 'currency', 'month']).score.dropna()
    np.testing.assert_allclose(sums.reindex(scores.index), scores, atol=1e-8)


def test_shuffled_inputs_return_same_order_and_scores():
    p = score_fixture()
    reference = fit_reference_bundle(p)
    original, _ = score_panel(p, reference)
    shuffled = p.sample(frac=1, random_state=10)
    predicted, _ = score_panel(shuffled, reference)
    keys = ['company_id', 'currency', 'month']
    pd.testing.assert_frame_equal(predicted[keys].reset_index(drop=True), shuffled[keys].reset_index(drop=True))
    pd.testing.assert_frame_equal(original.set_index(keys).sort_index(), predicted.set_index(keys).sort_index())


def test_duplicate_keys_are_rejected():
    p = score_fixture()
    with pytest.raises(ValueError, match='duplicad'):
        fit_reference_bundle(pd.concat([p, p.iloc[[0]]], ignore_index=True))


def test_no_snapshots_or_text_events_are_consumed():
    p = score_fixture()
    ref = fit_reference_bundle(p)
    original, _ = score_panel(p, ref)
    p['cash_balance'] = 1e12
    p['stress_embargo_count'] = 1000
    p['debt_total_outstanding'] = 1e12
    changed, _ = score_panel(p, ref)
    pd.testing.assert_frame_equal(original, changed)


def test_level_rolling_average_does_not_reuse_bad_quality_months():
    p = score_fixture()
    p.loc[p.company_id.eq('C0') & p.month.eq('2025-05-01'), 'tx_usable_row_share'] = .1
    result, terms = score_panel(p, fit_reference_bundle(p))
    june = result.loc[result.company_id.eq('C0') & result.month.eq('2025-06-01')].iloc[0]
    assert june.level_operations == pytest.approx(65.)
    june_terms = terms.loc[terms.company_id.eq('C0') & terms.month.eq('2025-06-01') & terms.layer.eq('level')]
    assert 'tx_operating_margin' in set(june_terms.feature)
    assert 'tx_operating_margin_ma3' not in set(june_terms.feature)


def test_missing_core_feature_is_schema_error_not_optional_missingness():
    p = score_fixture()
    reference = fit_reference_bundle(p)
    with pytest.raises(ValueError, match='debt_service_to_inflow_ratio'):
        score_panel(p.drop(columns=['debt_service_to_inflow_ratio']), reference)


def test_missing_optional_invoice_fields_are_allowed_but_not_healthy():
    p = score_fixture()
    reference = fit_reference_bundle(p)
    without_erp = p.drop(columns=[col for col in p if col.startswith('inv_')])
    scores, _ = score_panel(without_erp, reference)
    assert scores.level_collections.isna().all()
    assert scores.level_payments.isna().all()
    assert scores.level_coverage.le(.7).all()
    assert scores.score_status.eq('provisional').all()
