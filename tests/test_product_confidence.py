import numpy as np
import pandas as pd
import pytest

from xray.product.confidence import PARTIAL_CURRENCY_CAP, cash_certainty, compute_confidence


def score_row(month, **kw):
    base = dict(company_id="C1", currency="EUR", month=pd.Timestamp(month), level_months=6, level_coverage=1.0,
                tx_usable_row_share=1.0, month_quality_ok=True, has_momentum=True, momentum_coverage=1.0,
                has_partial_currency_coverage=False, tx_count=50, score_status="scored")
    base.update(kw)
    return base


def test_full_evidence_gives_100_and_missing_sources_redistribute_weight():
    out = compute_confidence(pd.DataFrame([score_row("2026-01-01")]))
    assert out.confidence.item() == 100 and out.confidence_band.item() == "high"
    assert np.isnan(out.sub_cash_certainty.item())  # sin features no se inventa certeza de caja


def test_thin_history_and_no_trend_lower_confidence_with_limiting_factor():
    out = compute_confidence(pd.DataFrame([score_row("2026-01-01", level_months=3, has_momentum=False, momentum_coverage=np.nan)]))
    # history 50 (peso 25), coverage 100 (25), quality 100 (15), trend 0 (15): (1250+2500+1500)/80 = 65.6
    assert out.confidence.item() == pytest.approx(65.6, abs=0.1)
    assert out.confidence_band.item() == "medium" and out.limiting_factor.item() == "trend"


def test_partial_currency_caps_and_no_transactions_zeroes():
    rows = [score_row("2026-01-01", has_partial_currency_coverage=True),
            score_row("2026-02-01", tx_count=0, level_months=0, level_coverage=0, month_quality_ok=False, has_momentum=False)]
    out = compute_confidence(pd.DataFrame(rows))
    assert out.confidence.iloc[0] == PARTIAL_CURRENCY_CAP
    assert out.confidence.iloc[1] == 0 and out.confidence_band.iloc[1] == "low"


def test_cash_certainty_uses_only_past_window():
    features = pd.DataFrame({
        "company_id": "C1", "currency": "EUR",
        "month": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
        "tx_uncategorized_amount": [0.0, 50.0, 0.0],
        "tx_cash_inflow": [100.0, 50.0, 100.0], "tx_cash_outflow": [0.0, 0.0, 0.0],
    })
    cc = cash_certainty(features, window=2).set_index("month").cash_certainty
    assert cc.loc["2026-01-01"] == 1.0            # nada sin categoría
    assert cc.loc["2026-02-01"] == pytest.approx(1 - 50 / 150)
    assert cc.loc["2026-03-01"] == pytest.approx(1 - 50 / 150)  # ventana ene-feb no, feb-mar: 50/150
    scores = pd.DataFrame([score_row("2026-02-01")])
    out = compute_confidence(scores, features)
    # cash 66.7 con peso 20 sobre 100 total: 80 + 0.2*66.7 = 93.3
    assert out.confidence.item() == pytest.approx(93.3, abs=0.1)
    assert out.limiting_factor.item() == "cash_certainty"
