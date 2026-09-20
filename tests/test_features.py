import numpy as np
import pandas as pd
import pytest

from test_clean import GROUPS, PRODUCTS, inv, inv_frame, row, tx_frame
from xray.clean.invoices import clean_invoices
from xray.clean.log import CleaningLog
from xray.clean.transactions import clean_transactions
from xray.features import FeatureConfig, build_features
from xray.fx import FX_TO_EUR


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
    # Enero es el primer mes con actividad real: parcial (D33), así febrero ya es un mes normal.
    tables = fixture_tables([row(0, date='2025-01-20', amount=5000),
                             row(1, date='2025-02-01', amount=100),
                             row(2, date='2025-02-05', amount=80, category='uncategorized'),
                             row(3, date='2025-02-08', amount=1e9),
                             row(4, date='2025-04-01', amount=20, category='transfer')])
    panel = company(build(tables))
    assert len(panel) == 6
    # D32: un importe enorme no se excluye por su tamaño.
    assert panel.loc['2025-02-01', 'tx_inflow'] == 1e9 + 100
    assert panel.loc['2025-02-01', 'tx_cash_inflow'] == 1e9 + 180
    assert panel.loc['2025-02-01', 'tx_outflow'] == 0
    assert pd.isna(panel.loc['2025-02-01', 'tx_inflow_outflow_ratio'])
    assert panel.loc['2025-04-01', 'tx_inflow'] == 0
    assert panel.loc[['2025-01-01', '2025-03-01', '2025-05-01'], 'tx_inflow'].isna().all()
    assert panel.loc['2025-03-01', 'is_missing_after_onboarding']
    assert not panel.loc['2025-01-01', 'is_missing_after_onboarding']
    assert pd.isna(panel.loc['2025-04-01', 'tx_inflow_ma3'])
    assert panel.is_partial_first_month.tolist() == [True] + [False] * 5


def test_first_month_of_the_extraction_is_complete_not_partial():
    rows = [row(10 * m + i, date=f'2024-{m:02d}-{2 + i:02d}', amount=1000) for m in (9, 10, 11) for i in range(6)]
    panel = company(build_features(fixture_tables(rows), FeatureConfig(start_month='2024-09-01', end_month='2024-11-01')))
    assert panel.loc['2024-09-01', 'coverage_state'] == 'onboarding'
    assert not panel.loc['2024-09-01', 'is_partial_first_month']
    assert panel.loc['2024-09-01', 'tx_inflow'] == 6000


def test_partial_first_month_keeps_counts_but_not_amounts():
    rows = [row(i, date=f'2025-01-{15 + i:02d}', amount=1000) for i in range(3)]          # alta a mitad de mes
    rows += [row(10 * m + i, date=f'2025-{m:02d}-{10 + i:02d}', amount=1000) for m in (2, 3, 4) for i in range(6)]
    panel = company(build(fixture_tables(rows)))
    assert panel.loc['2025-01-01', 'coverage_state'] == 'onboarding'
    assert panel.loc['2025-01-01', 'is_partial_first_month']
    assert panel.loc['2025-01-01', 'tx_usable_count'] == 3                               # el mes existe
    assert pd.isna(panel.loc['2025-01-01', 'tx_inflow'])                                 # pero no sus importes
    assert panel.loc['2025-02-01', 'coverage_state'] == 'ok'                             # un solo mes de onboarding
    assert panel.loc['2025-02-01', 'tx_inflow'] == 6000
    assert pd.isna(panel.loc['2025-03-01', 'tx_inflow_ma3'])                             # la ventana no usa enero
    assert panel.loc['2025-04-01', 'tx_inflow_ma3'] == 6000                              # sin crecimiento falso


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


def test_other_currencies_are_converted_to_eur_and_group_excludes_intracompany_flows():
    tables = fixture_tables([row(1, amount=100), row(2, product='P2', amount=200),
                             row(3, amount=50, date='2025-01-11'),
                             row(4, company='C2', product='P3', amount=-50, date='2025-01-11', category='payment')])
    tables['banking_products'].loc[1, 'currency'] = 'USD'
    tables['transactions'].loc[tables['transactions'].product_id == 'P2', 'product_currency'] = 'USD'
    result = build(tables)
    expected = 100 + 200 / FX_TO_EUR['USD']
    panel = company(result)
    assert panel.loc['2025-01-01', 'tx_inflow'] == pytest.approx(expected)
    assert panel.loc['2025-01-01', 'declared_currency'] == 'EUR'
    assert panel.loc['2025-01-01', 'tx_primary_currency_row_share'] == pytest.approx(2 / 3)
    group = result['group_currency_monthly_features']
    january = group.loc[group.month == pd.Timestamp('2025-01-01')].set_index('currency')
    assert list(january.index) == ['EUR']
    assert january.loc['EUR', 'tx_inflow'] == pytest.approx(expected)


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


def test_unknown_product_is_not_money_but_fx_rate_column_is_ignored():
    tables = fixture_tables([row(1, amount=100), row(2, product='P9', amount=9999),
                             row(3, date='2025-01-20', amount=200)])
    tables['transactions'].loc[tables['transactions'].transaction_id == 't3', 'exchange_rate'] = 1.1
    panel = company(build(tables))
    assert panel.loc['2025-01-01', 'tx_cash_inflow'] == 300
    assert panel.loc['2025-01-01', 'tx_unknown_currency_count'] == 1
    assert 'tx_ambiguous_fx_count' not in panel
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


def test_debt_snapshot_prefers_balances_and_utilization_only_for_revolving():
    from xray.features.context import debt_snapshot
    debt = pd.DataFrame({'product_id': ['L1', 'P1', 'P2'], 'company_id': 'C1', 'currency': 'EUR',
                         'type': ['loan', 'lineofcredit', 'lineofcredit'], 'created_at': pd.Timestamp('2025-01-01'),
                         'granted': [-1000., -500., -200.], 'outstanding': [-900., -100., -50.], 'liquidity': [None, 400., 150.]})
    balances = pd.DataFrame({'product_id': ['L1', 'P1'], 'balance': [-880., -475.], 'granted': [-1000., -500.],
                             'liquidity': [None, 25.]})
    snap = debt_snapshot({'debt_products': debt, 'balances': balances}, FeatureConfig()).set_index('product_id')
    assert snap.loc['L1', 'debt_outstanding'] == 880 and snap.loc['L1', 'outstanding_source'] == 'balances'
    assert pd.isna(snap.loc['L1', 'debt_utilization'])                       # préstamo: no es tensión
    assert snap.loc['P1', 'debt_utilization'] == pytest.approx(0.95)         # póliza casi al límite
    assert snap.loc['P2', 'outstanding_source'] == 'debt_products'            # sin foto en balances
    assert snap.loc['P2', 'debt_utilization'] == pytest.approx(0.25)


def test_sentinel_balance_rule_marks_only_unexplained_huge_bank_balances():
    from xray.clean.balances import sentinel_balances
    products = pd.DataFrame({'product_id': ['A', 'B', 'C', 'L'], 'company_id': 'C1', 'currency': 'EUR',
                             'type': ['checking', 'checking', 'checking', 'loan'],
                             'kind': ['banking', 'banking', 'banking', 'debt']})
    balances = pd.DataFrame({'product_id': ['A', 'B', 'C', 'L'],
                             'balance': [99_999_990_000., 25_000_000., 1_000_208_000., -300_000_000.]})
    tx = pd.DataFrame({'product_id': ['A', 'B', 'C', 'C'], 'amount': [5000., 7_000_000., 999_999_999., -100.]})
    flags = sentinel_balances(balances, products, tx)
    assert flags.tolist() == [True, False, True, False]   # relleno, legítimo grande, ajuste técnico, préstamo real


def test_sentinel_balance_is_not_reliable_cash_nor_available_liquidity():
    from xray.features.context import liquidity_snapshot
    tables = fixture_tables([row(1, date='2026-08-10', amount=100)])
    tables['balances']['is_sentinel_balance'] = [False, True, False]      # P2 de C1 es centinela
    result = build_features(tables, FeatureConfig(start_month='2026-08-01'))
    context = result['reconstructed_liquidity_context'].set_index('product_id')
    assert context.loc['P2', 'is_reconstruction_unreliable']
    assert pd.isna(context.loc['P2', 'reconstructed_balance'])
    snap = liquidity_snapshot(tables, FeatureConfig()).set_index('company_id')
    assert snap.loc['C1', 'cash_accounts_eur'] == 500                        # P2 (200) no cuenta
    assert snap.loc['C1', 'sentinel_balances_excluded'] == 1


def test_technical_placeholder_movement_stays_in_flows_but_breaks_prior_cash():
    rows = [row(0, date='2026-07-10', amount=5000), row(1, date='2026-08-05', amount=100),
            row(2, date='2026-08-20', amount=999_999_999, category='uncategorized')]
    tables = fixture_tables(rows)
    assert tables['transactions'].is_technical_placeholder.tolist() == [False, False, True]
    result = build_features(tables, FeatureConfig(start_month='2026-07-01', end_month='2026-08-01'))
    context = result['reconstructed_liquidity_context'].set_index(['product_id', 'month'])
    assert context.loc[('P1', pd.Timestamp('2026-07-01')), 'is_reconstruction_unreliable']   # el ajuste es posterior
    assert company(result).loc['2026-08-01', 'tx_cash_inflow'] == 100 + 999_999_999         # D32: sigue en los flujos


def _paid_invoices(start_id, months, late_days):
    rows = []
    for m in months:
        for k in range(12):
            due = pd.Timestamp(f'2025-{m:02d}-{10 + k:02d}')
            rows.append(inv(start_id + 100 * m + k, issued=f'2025-{m:02d}-01', due=str(due.date()),
                            paid=str((due + pd.Timedelta(days=late_days)).date())))
    return rows


def test_filler_payment_dates_make_delay_unmeasurable_only_once_history_shows_it():
    # D39: 12 facturas al mes pagadas exactamente al vencimiento; con >= 30 en el historial ya no es medible.
    panel = company(build(fixture_tables([row(1)], invoices=_paid_invoices(0, (1, 2, 3, 4), late_days=0))))
    assert panel.loc['2025-01-01', 'inv_ar_delay_median'] == 0                 # 12 en el historial: aún medible
    assert not panel.loc['2025-02-01', 'inv_ar_payment_date_filler']           # 24
    assert panel.loc['2025-03-01', 'inv_ar_payment_date_filler']               # 36 -> relleno
    assert pd.isna(panel.loc['2025-03-01', 'inv_ar_delay_median'])             # NaN, nunca un 0 falso
    assert panel.loc['2025-03-01', 'inv_ar_delay_count'] == 12                 # los conteos se conservan


def test_real_late_payments_are_never_treated_as_filler():
    panel = company(build(fixture_tables([row(1)], invoices=_paid_invoices(0, (1, 2, 3, 4), late_days=3))))
    assert not panel.inv_ar_payment_date_filler.any()
    assert panel.loc['2025-04-01', 'inv_ar_delay_median'] == 3


def test_filler_detection_does_not_look_at_the_future():
    rows = _paid_invoices(0, (1, 2, 3, 4), late_days=0)
    short = company(build(fixture_tables([row(1)], invoices=[r for r in rows if r[3] < '2025-03-01']), end='2025-02-01'))
    full = company(build(fixture_tables([row(1)], invoices=rows)))
    assert short.inv_ar_payment_date_filler.tolist() == full.inv_ar_payment_date_filler.tolist()[:2]
    assert short.inv_ar_delay_median.tolist() == full.inv_ar_delay_median.tolist()[:2]


def test_dormant_zero_balance_account_does_not_block_company_cash():
    # D46: cuenta sin movimientos y saldo 0 -> fiable en 0; con saldo distinto de 0 sigue sin saberse.
    tables = fixture_tables([row(1, date='2026-08-10', amount=100)])          # solo P1 tiene movimientos
    tables['balances'].loc[tables['balances'].product_id.eq('P2'), 'balance'] = 0.
    result = build_features(tables, FeatureConfig(start_month='2026-08-01'))
    context = result['reconstructed_liquidity_context'].set_index('product_id')
    assert not context.loc['P2', 'is_reconstruction_unreliable'] and context.loc['P2', 'reconstructed_balance'] == 0
    liquidity = result['company_currency_liquidity_context'].set_index(['company_id', 'month'])
    assert liquidity.loc[('C1', pd.Timestamp('2026-08-01')), 'reconstruction_coverage'] == 1

    tables2 = fixture_tables([row(1, date='2026-08-10', amount=100)])         # P2 con saldo 200 y sin movimientos
    ctx2 = build_features(tables2, FeatureConfig(start_month='2026-08-01'))['reconstructed_liquidity_context'].set_index('product_id')
    assert ctx2.loc['P2', 'is_reconstruction_unreliable']
