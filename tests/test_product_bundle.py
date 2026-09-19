import pandas as pd

from xray.product.bundle import build_company, build_groups, build_portfolio, primary_currency


def scores_frame():
    rows = []
    for month, score, delta in (("2026-07-01", 60.0, None), ("2026-08-01", 65.0, 5.0)):
        rows.append(dict(company_id="C1", group_id="G1", currency="EUR", month=pd.Timestamp(month), score=score, level=score,
                         momentum=55.0, stability=80.0, trajectory="stable", episode="none", score_status="scored",
                         score_reason="ok", delta_vs_prev=delta, level_operations=score, level_debt=None,
                         level_collections=None, level_payments=None, tx_count=100))
    rows.append(dict(rows[-1], currency="USD", score=None, level=None, momentum=None, score_status="not_scored",
                     score_reason="no_usable_transactions", delta_vs_prev=None, tx_count=3))
    rows.append(dict(rows[0], company_id="C2", score=None, level=None, score_status="not_scored", score_reason="short_history", month=pd.Timestamp("2026-08-01")))
    return pd.DataFrame(rows)


def confidence_frame(scores):
    c = scores[["company_id", "currency", "month"]].copy()
    c["confidence"] = 90.0
    c["confidence_band"] = "high"
    return c


def changes_frame():
    return pd.DataFrame([dict(company_id="C1", currency="EUR", month=pd.Timestamp("2026-08-01"), prev_month=pd.Timestamp("2026-07-01"),
                              layer="level", feature="op_margin_w", component="operations", label="Generación operativa (margen 6m)",
                              rank=1, delta_contribution=5.0, value_effect=5.0, weight_effect=0.0, status="present",
                              value_prev=0.1, value_now=0.2, feature_score_prev=60.0, feature_score_now=65.0,
                              weight_prev=1.0, weight_now=1.0, reference_changed=False, sentence="x")])


def test_portfolio_uses_primary_currency_and_keeps_unscored_companies():
    scores = scores_frame()
    latest = pd.Timestamp("2026-08-01")
    assert primary_currency(scores).loc["C1"] == "EUR"
    portfolio = build_portfolio(scores, confidence_frame(scores), changes_frame(), latest)
    assert list(portfolio.company_id) == ["C1", "C2"]
    c1 = portfolio.set_index("company_id").loc["C1"]
    assert c1.currency == "EUR" and c1.currencies == ["EUR", "USD"]
    assert c1.main_signal == "Generación operativa (margen 6m)" and c1.main_signal_delta == 5.0 and c1.confidence == 90.0
    c2 = portfolio.set_index("company_id").loc["C2"]
    assert pd.isna(c2.score) and c2.score_reason == "short_history"


def test_company_payload_has_timeline_per_currency_and_top_changes():
    scores = scores_frame()
    payload = build_company("C1", scores, confidence_frame(scores), changes_frame(), pd.Timestamp("2026-08-01"))
    assert set(payload["currencies"]) == {"EUR", "USD"}
    eur = payload["currencies"]["EUR"]
    assert len(eur["timeline"]) == 2 and eur["timeline"][-1]["score"] == 65.0 and eur["timeline"][-1]["confidence"] == 90.0
    assert eur["why_changed"]["terms"][0]["feature"] == "op_margin_w"
    assert payload["currencies"]["USD"]["why_changed"]["terms"] == [] and payload["currencies"]["USD"]["timeline"][0]["score"] is None


def test_groups_aggregate_portfolio_rows():
    scores = scores_frame()
    portfolio = build_portfolio(scores, confidence_frame(scores), changes_frame(), pd.Timestamp("2026-08-01"))
    groups = build_groups(portfolio, scores)
    assert groups["G1"]["n_companies"] == 2 and groups["G1"]["n_scored"] == 1
