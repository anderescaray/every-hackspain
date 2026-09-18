from pathlib import Path

import pandas as pd

from test_clean import GROUPS, PRODUCTS, inv, inv_frame, row, tx_frame
from xray.clean.invoices import clean_invoices
from xray.clean.log import CleaningLog
from xray.clean.transactions import clean_transactions
from xray.paths import ROOT


def test_default_root_is_repository():
    assert ROOT == Path(__file__).resolve().parents[1]


def test_mirrors_require_same_known_currency():
    products = PRODUCTS.copy()
    products.loc[products.product_id == 'P2', 'currency'] = 'USD'
    t = tx_frame([row(1, amount=-500), row(2, product='P2', amount=500)])
    result = clean_transactions(t, products, GROUPS, CleaningLog())
    assert not result.is_internal_transfer.any()
    assert not result.is_intragroup.any()


def test_relative_outliers_do_not_depend_on_future():
    rows = [row(i, date='2025-01-10', amount=10, description=str(i)) for i in range(120)]
    rows += [row(120, date='2025-02-10', amount=1000)]
    prefix = clean_transactions(tx_frame(rows), PRODUCTS, GROUPS, CleaningLog())
    future = rows + [row(i, date='2025-03-10', amount=1e7) for i in range(121, 241)]
    full = clean_transactions(tx_frame(future), PRODUCTS, GROUPS, CleaningLog())
    assert prefix.iloc[-1].is_relative_outlier
    pd.testing.assert_series_equal(prefix.is_relative_outlier, full.iloc[:len(prefix)].is_relative_outlier)


def test_payment_dates_are_flagged_at_exact_extraction_boundary():
    invoices = inv_frame([inv(1, paid='2026-09-01 12:00:00'),
                          inv(2, paid='2026-09-02 00:00:00'), inv(3, paid='2024-12-30 00:00:00')])
    result = clean_invoices(invoices, CleaningLog()).set_index('operation_id')
    assert not result.loc['o1', 'is_future_payment']
    assert result.loc['o2', 'is_future_payment']
    assert result.loc['o3', 'is_payment_before_issuance']


def test_invoice_duplicates_do_not_cross_currencies():
    invoices = inv_frame([inv(1), inv(2)])
    invoices.loc[1, 'concept'] = invoices.loc[0, 'concept']
    invoices.loc[1, 'currency'] = 'USD'
    result = clean_invoices(invoices, CleaningLog())
    assert not result.is_possible_duplicate.any()
