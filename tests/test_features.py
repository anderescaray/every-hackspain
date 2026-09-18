import numpy as np
import pandas as pd
import pytest

from test_clean import GROUPS, PRODUCTS, inv, inv_frame, row, tx_frame
from xray.clean.invoices import clean_invoices
from xray.clean.log import CleaningLog
from xray.clean.transactions import clean_transactions
from xray.features import FeatureConfig, build_features


def fixture_tables(rows=None, invoices=None):
    companies = pd.DataFrame({'company_id': ['C1', 'C2'], 'group_id': ['G1', 'G1'],
                              'currency': ['EUR', 'EUR'], 'created_at': pd.to_datetime(['2024-12-01'] * 2)})
    bank = PRODUCTS.assign(type='checking', created_at=pd.Timestamp('2024-12-01'))
    debt = pd.DataFrame(columns=['product_id', 'company_id', 'currency', 'type', 'created_at',
                                 'outstanding', 'granted', 'liquidity'])
    balances = pd.DataFrame({'product_id': ['P1', 'P2', 'P3'], 'company_id': ['C1', 'C1', 'C2'],
                             'date': pd.to_datetime(['2026-09-01'] * 3), 'balance': [500., 200., 10.]})
    return {'companies': companies, 'groups': pd.DataFrame({'group_id': ['G1']}),
            'banking_products': bank, 'debt_products': debt, 'balances': balances,
            'transactions': clean_transactions(tx_frame(rows or []), PRODUCTS, GROUPS, CleaningLog()),
            'invoices': clean_invoices(inv_frame(invoices or []), CleaningLog())}


def build(tables, end='2025-06-01'):
    return build_features(tables, FeatureConfig(start_month='2025-01-01', end_month=end))


def company(result, name='C1'):
    frame = result['company_monthly_features']
    return frame.loc[frame.company_id == name].set_index('month')


def test_calendar_missingness_filters_and_zero_denominator():
    tables = fixture_tables([row(1, date='2025-02-01', amount=100),
                             row(2, date='2025-02-05', amount=80, category='uncategorized'),
                             row(3, date='2025-02-08', amount=1e9),
                             row(4, date='2025-04-01', amount=20, category='transfer')])
    panel = company(build(tables))
    assert len(panel) == 6
    assert panel.loc['2025-02-01', 'tx_inflow'] == 100
    assert panel.loc['2025-02-01', 'tx_cash_inflow'] == 180
    assert panel.loc['2025-02-01', 'tx_outflow'] == 0
    assert pd.isna(panel.loc['2025-02-01', 'tx_inflow_outflow_ratio'])
    assert panel.loc['2025-04-01', 'tx_inflow'] == 0
    assert panel.loc[['2025-01-01', '2025-03-01', '2025-05-01'], 'tx_inflow'].isna().all()
    assert panel.loc['2025-03-01', 'is_missing_after_onboarding']
    assert not panel.loc['2025-01-01', 'is_missing_after_onboarding']
    assert pd.isna(panel.loc['2025-04-01', 'tx_inflow_ma3'])


def test_invoice_asof_uses_payment_month_and_correct_days():
    tables = fixture_tables(invoices=[inv(1, issued='2025-01-01', due='2025-01-20', paid='2025-02-05'),
                                     inv(2, issued='2025-04-01', due='2025-04-30', status='pending')])
    panel = company(build(tables))
    assert panel.loc['2025-01-01', 'inv_ar_open_amount'] == 100
    assert panel.loc['2025-01-01', 'inv_ar_overdue_amount'] == 100
    assert pd.isna(panel.loc['2025-01-01', 'inv_dso_median'])
    assert panel.loc['2025-02-01', 'inv_ar_open_amount'] == 0
    assert panel.loc['2025-02-01', 'inv_dso_median'] == 35
    assert panel.loc['2025-02-01', 'inv_ar_delay_median'] == 16
    assert panel.loc['2025-03-01', 'inv_issued_amount'] == 0
    assert company(build(tables), 'C2').inv_issued_amount.isna().all()


def test_future_changes_do_not_change_historical_features():
    rows = [row(i, date=f'2025-{i:02d}-10', amount=i * 100) for i in range(1, 7)]
    invoices = [inv(1, paid='2025-05-05')]
    tables = fixture_tables(rows, invoices)
    original = build(tables)
    changed = fixture_tables(rows + [row(20, date='2025-07-01', amount=999999)],
                             invoices + [inv(20, issued='2025-07-01', due='2025-07-30', paid='2025-08-01')])
    changed['balances']['balance'] = 99999
    full = build(changed, end='2025-08-01')
    for name in ('company_monthly_features', 'group_currency_monthly_features'):
        historic = full[name].loc[full[name].month <= pd.Timestamp('2025-06-01')].reset_index(drop=True)
        pd.testing.assert_frame_equal(original[name], historic)


def test_currency_is_never_summed_and_group_excludes_intracompany_flows():
    tables = fixture_tables([row(1, amount=100), row(2, product='P2', amount=200),
                             row(3, amount=50, date='2025-01-11'),
                             row(4, company='C2', product='P3', amount=-50, date='2025-01-11', category='payment')])
    tables['banking_products'].loc[1, 'currency'] = 'USD'
    tables['transactions'].loc[tables['transactions'].product_id == 'P2', 'product_currency'] = 'USD'
    result = build(tables)
    assert company(result).loc['2025-01-01', 'tx_inflow'] == 100
    group = result['group_currency_monthly_features']
    january = group.loc[group.month == pd.Timestamp('2025-01-01')].set_index('currency')
    assert january.loc['EUR', 'tx_inflow'] == 100
    assert january.loc['USD', 'tx_inflow'] == 200


def test_snapshot_context_never_enters_model_panel():
    result = build(fixture_tables([row(1)]))
    panel = result['company_monthly_features']
    assert 'cash_balance' not in panel
    assert 'debt_total_outstanding' not in panel
    assert not any('stress' in name for name in panel.columns)
    assert 'reconstructed_liquidity_context' in result


def test_partial_extraction_month_is_rejected():
    with pytest.raises(ValueError, match='completo'):
        FeatureConfig(end_month='2026-09-01')


def test_no_infinite_values():
    result = build(fixture_tables([row(1, amount=-10, category='payment')]))
    for frame in result.values():
        assert not np.isinf(frame.select_dtypes('number').to_numpy(dtype=float)).any()


def test_rolling_slope_and_prior_zscore_are_calendar_based():
    rows = [row(i, date=f'2025-{i:02d}-10', amount=i * 10.) for i in range(1, 7)]
    panel = company(build(fixture_tables(rows)))
    assert panel.loc['2025-03-01', 'tx_inflow_ma3'] == 20
    assert panel.loc['2025-06-01', 'tx_inflow_slope6'] == 10
    assert panel.loc['2025-04-01', 'tx_inflow_delta3'] == 30
    assert panel.loc['2025-04-01', 'tx_inflow_zscore_prior6'] == pytest.approx(20 / np.std([10, 20, 30]))
    assert pd.isna(panel.loc['2025-03-01', 'tx_inflow_zscore_prior6'])


def test_unknown_product_and_ambiguous_fx_are_not_money():
    tables = fixture_tables([row(1, amount=100), row(2, product='P9', amount=9999),
                             row(3, date='2025-01-20', amount=200)])
    tables['transactions'].loc[tables['transactions'].transaction_id == 't3', 'exchange_rate'] = 1.1
    panel = company(build(tables))
    assert panel.loc['2025-01-01', 'tx_cash_inflow'] == 100
    assert panel.loc['2025-01-01', 'tx_unknown_currency_count'] == 1
    assert panel.loc['2025-01-01', 'tx_ambiguous_fx_count'] == 1
    assert panel.loc['2025-01-01', 'has_partial_currency_coverage']


def test_only_ambiguous_documents_do_not_become_zero_invoicing():
    tables = fixture_tables(invoices=[inv(1, doc='paymentDocument')])
    panel = company(build(tables))
    assert panel.inv_source_seen.all()
    assert panel.inv_issued_amount.isna().all()


def test_due_date_boundary_and_known_future_obligations():
    tables = fixture_tables(invoices=[inv(1, due='2025-01-31', status='pending'),
                                     inv(2, due='2025-02-10', status='pending'),
                                     inv(3, issued='2025-02-01', due='2025-02-10', status='pending')])
    panel = company(build(tables))
    assert panel.loc['2025-01-01', 'inv_ar_open_amount'] == 200
    assert panel.loc['2025-01-01', 'inv_ar_overdue_amount'] == 0
    assert panel.loc['2025-01-01', 'inv_ar_due_30_amount'] == 100


def test_snapshot_reconstruction_includes_extraction_day_and_internal_transfers():
    tables = fixture_tables([row(1, date='2026-08-10', amount=100),
                             row(2, date='2026-09-01', amount=40),
                             row(3, product='P2', date='2026-09-01', amount=-40, category='transfer')])
    result = build_features(tables, FeatureConfig(start_month='2026-08-01'))
    context = result['reconstructed_liquidity_context'].set_index('product_id')
    assert context.loc['P1', 'reconstructed_balance'] == 460
    assert context.loc['P2', 'is_reconstruction_unreliable']
    assert company(result).iloc[0].tx_inflow == 100


def test_like_for_like_does_not_confuse_new_account_with_growth():
    tables = fixture_tables([row(1, date='2025-01-10', amount=100),
                             row(2, date='2025-02-10', amount=110),
                             row(3, product='P2', date='2025-02-10', amount=900)])
    panel = company(build(tables))
    assert panel.loc['2025-02-01', 'tx_inflow'] == 1010
    assert panel.loc['2025-02-01', 'tx_lfl_inflow_growth'] == pytest.approx(.1)
    assert panel.loc['2025-02-01', 'tx_new_accounts'] == 1


def test_group_ratios_are_recomputed_not_averaged():
    tables = fixture_tables([row(1, amount=100), row(2, amount=-10, category='payment', date='2025-01-11'),
                             row(3, company='C2', product='P3', amount=1000),
                             row(4, company='C2', product='P3', amount=-500, category='payment', date='2025-01-11')])
    group = build(tables)['group_currency_monthly_features'].set_index('month')
    assert group.loc['2025-01-01', 'tx_inflow_outflow_ratio'] == pytest.approx(1100 / 510)


def test_model_allowlist_excludes_identifiers_snapshots_and_erp_levels():
    from xray.features import feature_catalog
    result = build(fixture_tables([row(1)]))
    features = feature_catalog(result)['model_features']
    forbidden = {'company_id', 'group_id', 'tx_counterparty_hhi', 'inv_ar_overdue_ratio',
                 'inv_ap_overdue_ratio', 'inv_ar_overdue_ratio_ma3', 'cash_balance'}
    assert not forbidden.intersection(features)
    assert 'inv_ar_overdue_ratio_delta3' in features


def test_debt_repayment_is_not_erased_by_own_account_settlement():
    tables = fixture_tables([row(1, amount=-100, category='debt_repayment'),
                             row(2, product='P2', amount=100, category='uncategorized')])
    panel = company(build(tables))
    assert panel.loc['2025-01-01', 'tx_outflow'] == 0
    assert panel.loc['2025-01-01', 'debt_principal_paid'] == 100
