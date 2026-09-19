import pandas as pd

from test_clean import inv
from test_features import build, company, fixture_tables


def test_delay_count_excludes_invalid_due_dates_and_is_asof():
    tables = fixture_tables(invoices=[
        inv(1, amount=100, due='2025-01-20', paid='2025-02-05'),
        inv(2, amount=100, due='2024-12-20', paid='2025-02-05'),
        inv(3, amount=-100, due='2025-01-20', paid='2025-02-05'),
        inv(4, amount=-100, due='2027-01-20', paid='2025-02-05'),
    ])
    p = company(build(tables))
    for side in ('ar', 'ap'):
        assert p.loc['2025-01-01', f'inv_{side}_delay_count'] == 0
        assert p.loc['2025-02-01', f'inv_{side}_paid_count'] == 2
        assert p.loc['2025-02-01', f'inv_{side}_delay_count'] == 1
        assert p.loc['2025-02-01', f'inv_{side}_delay_median'] == 16
        assert p.loc['2025-03-01', f'inv_{side}_delay_count'] == 0
    assert pd.isna(company(build(tables), 'C2').iloc[0].inv_ar_delay_count)
