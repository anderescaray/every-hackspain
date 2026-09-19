import math

import pandas as pd

from xray.fx import FX_TO_EUR, to_eur


def test_eur_is_identity_and_rates_positive():
    assert FX_TO_EUR["EUR"] == 1.0
    assert all(rate > 0 and math.isfinite(rate) for rate in FX_TO_EUR.values())
    assert to_eur(250.0, "EUR") == 250.0


def test_series_conversion_and_pegs():
    amount = pd.Series([1.95583, 655.957, 100.0])
    currency = pd.Series(["BAM", "XOF", "EUR"])
    assert to_eur(amount, currency).round(9).tolist() == [1.0, 1.0, 100.0]


def test_unknown_or_missing_currency_is_nan_not_eur():
    out = to_eur(pd.Series([10.0, 10.0]), pd.Series(["XXX", None]))
    assert out.isna().all()
    assert math.isnan(to_eur(10.0, "XXX"))
