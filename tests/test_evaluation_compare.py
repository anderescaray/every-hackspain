import numpy as np
import pandas as pd
import pytest

from xray.evaluation.compare import (auc, future_liquidity_stress, future_stress, group_bootstrap_auc_difference,
                                     lead_time, liquidity_stress_onsets, spearman, stability, stress_onsets, stress_recoveries)


def months(n, start="2025-01-01"):
    return pd.date_range(start, periods=n, freq="MS")


def test_auc_matches_known_values():
    y = pd.Series([0, 0, 1, 1])
    assert auc(y, pd.Series([.1, .2, .8, .9])) == 1.0
    assert auc(y, pd.Series([.9, .8, .2, .1])) == 0.0
    assert auc(y, pd.Series([.5, .5, .5, .5])) == 0.5
    assert auc(pd.Series([1, 1]), pd.Series([.1, .2])) is None


def test_spearman_is_rank_based():
    a = pd.Series([1, 2, 3, 4, 5])
    assert spearman(a, a.pow(3)) == pytest.approx(1.0)
    assert spearman(a, -a) == pytest.approx(-1.0)
    assert spearman(a, pd.Series([1, 1, 1, 1, 1])) is None


def test_future_stress_censors_unobserved_future_and_normalizes_by_exposure():
    m = months(6)
    events = pd.DataFrame({"company_id": "C", "group_id": "G", "month": m,
                           "stress_unpaid_count": [0, 0, 2, 0, np.nan, 0], "stress_embargo_count": [0, 0, 0, 1, np.nan, 0]})
    features = pd.DataFrame({"company_id": "C", "month": m, "tx_all_currency_count": [10, 10, 10, 10, 0, 10]})
    out = future_stress(events, features, 2).set_index("month")
    assert out.loc[m[0], "future_any_2"] == 1.0  # eventos en t+2
    assert out.loc[m[0], "future_rate_2"] == pytest.approx(2 / 20)
    assert np.isnan(out.loc[m[2], "future_any_2"])  # t+2 sin registro observable -> censura
    assert np.isnan(out.loc[m[4], "future_any_2"])  # futuro fuera de ventana
    assert out.loc[m[3], "future_any_2"] is not None


def test_stress_onsets_require_six_clean_observed_months():
    m = months(10)
    counts = [0, 0, 0, 0, 0, 0, 3, 0, 0, 1]
    events = pd.DataFrame({"company_id": "C", "group_id": "G", "month": m, "stress_unpaid_count": counts})
    onsets = stress_onsets(events)
    assert onsets.onset.tolist() == [m[6]]  # el evento del mes 10 no viene tras seis meses limpios
    recoveries = stress_recoveries(pd.DataFrame({"company_id": "C", "group_id": "G", "month": months(9),
                                                 "stress_unpaid_count": [1, 0, 0, 0, 0, 0, 0, 0, 0]}))
    assert recoveries.recovery.tolist() == [months(9)[1]]


def test_liquidity_onsets_and_future_negative_cash():
    m = months(9)
    liquidity = pd.DataFrame({"company_id": "C", "currency": "EUR", "month": m,
                              "reconstructed_cash": [5, 5, 5, 5, 5, 5, -1, 2, np.nan],
                              "cash_runway_months_retrospective": 1.0})
    assert liquidity_stress_onsets(liquidity).onset.tolist() == [m[6]]
    future = future_liquidity_stress(liquidity, 2).set_index("month")
    assert future.loc[m[4], "future_liquidity_stress_2"] == 1.0
    assert future.loc[m[0], "future_liquidity_stress_2"] == 0.0
    assert np.isnan(future.loc[m[6], "future_liquidity_stress_2"])  # t+2 sin caja observada


def test_lead_time_uses_first_flag_in_lookback_window_only():
    m = months(12)
    scores = pd.DataFrame({"company_id": "C", "month": m})
    flags = pd.Series([False] * 12)
    flags[[1, 5, 6]] = True  # el mes 1 está fuera de la ventana de 6 meses previa al ancla (mes 9)
    anchors = pd.DataFrame({"company_id": ["C", "D"], "onset": [m[9], m[9]]})
    out = lead_time(scores, flags, anchors, "onset")
    assert out["anchors"] == 2 and out["detected_within_lookback"] == 1
    assert out["lead_months"]["median"] == 4.0  # ancla 2025-10 − primera señal en ventana 2025-06


def test_group_bootstrap_difference_is_reproducible_and_bounded():
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({"group_id": np.repeat([f"G{i}" for i in range(20)], 10)})
    frame["y"] = rng.integers(0, 2, len(frame))
    frame["a"] = rng.normal(size=len(frame))
    frame["b"] = frame.y + rng.normal(scale=.5, size=len(frame))
    first = group_bootstrap_auc_difference(frame, "y", "a", "b", "group_id", n=50)
    second = group_bootstrap_auc_difference(frame, "y", "a", "b", "group_id", n=50)
    assert first == second
    assert first["ci95"][0] > 0  # b es claramente mejor que a


def test_stability_reports_flips_and_extremes():
    m = months(4)
    scores = pd.DataFrame({"company_id": "C", "currency": "EUR", "month": m, "score": [10., 100., np.nan, 0.],
                           "trajectory": ["stable", "improving", "insufficient_history", "deteriorating"],
                           "score_status": ["scored", "scored", "not_scored", "scored"],
                           "delta_vs_prev": [np.nan, 90., np.nan, np.nan]})
    out = stability(scores)
    assert out["scored_rows"] == 3 and out["exact_extremes"] == 2
    assert out["label_flip_rate"] == 1.0
    assert out["abs_monthly_delta"]["p50"] == 90.0
