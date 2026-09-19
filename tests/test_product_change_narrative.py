import numpy as np
import pandas as pd
import pytest

from xray.product.change_narrative import compute_changes, top_changes, validate_changes


def scores_frame(rows):
    df = pd.DataFrame(rows, columns=["company_id", "currency", "month", "score", "reference_effective_from"])
    df["month"] = pd.to_datetime(df.month)
    df["reference_effective_from"] = pd.to_datetime(df.reference_effective_from)
    prev = df[["company_id", "currency", "month", "score"]].copy()
    prev["month"] += pd.offsets.MonthBegin(1)
    df = df.merge(prev.rename(columns={"score": "score_prev"}), on=["company_id", "currency", "month"], how="left")
    df["delta_vs_prev"] = df.score - df.score_prev
    return df.drop(columns="score_prev")


def term(company, month, layer, feature, value, fs, w, contribution=None, component="operations"):
    contribution = fs * w if contribution is None else contribution
    return dict(company_id=company, currency="EUR", month=pd.Timestamp(month), layer=layer, feature=feature,
                component=component, value=value, feature_score=fs, effective_weight=w, final_contribution=contribution)


def test_level_delta_splits_into_value_and_weight_effects():
    # Mes 1: margen 60×0.5 + deuda 80×0.5 = 70. Mes 2: margen 40×0.6 + deuda 80×0.4 = 56.
    scores = scores_frame([("C1", "EUR", "2026-01-01", 70.0, "2026-01-01"), ("C1", "EUR", "2026-02-01", 56.0, "2026-01-01")])
    terms = pd.DataFrame([
        term("C1", "2026-01-01", "level", "op_margin_w", 0.10, 60.0, 0.5),
        term("C1", "2026-01-01", "level", "debt_service_w", 0.05, 80.0, 0.5, component="debt"),
        term("C1", "2026-02-01", "level", "op_margin_w", -0.05, 40.0, 0.6),
        term("C1", "2026-02-01", "level", "debt_service_w", 0.05, 80.0, 0.4, component="debt"),
    ])
    out = compute_changes(scores, terms)
    assert len(out) == 2 and (out.month == pd.Timestamp("2026-02-01")).all()
    margin = out.set_index("feature").loc["op_margin_w"]
    assert margin.delta_contribution == pytest.approx(24 - 30)
    assert margin.value_effect == pytest.approx((40 - 60) * 0.5)      # -10
    assert margin.weight_effect == pytest.approx(40 * (0.6 - 0.5))    # +4
    assert margin["rank"] == 2 and margin.status == "present" and not margin.reference_changed  # deuda cae 40→32 (−8), manda
    assert "+0.10 → -0.05" in margin.sentence
    assert out.delta_contribution.sum() == pytest.approx(-14)


def test_appearing_term_is_pure_weight_effect_and_reference_change_is_flagged():
    scores = scores_frame([("C1", "EUR", "2026-01-01", 60.0, "2026-01-01"), ("C1", "EUR", "2026-02-01", 70.0, "2026-02-01")])
    terms = pd.DataFrame([
        term("C1", "2026-01-01", "level", "op_margin_w", 0.1, 60.0, 1.0),
        term("C1", "2026-02-01", "level", "op_margin_w", 0.1, 60.0, 0.75),
        term("C1", "2026-02-01", "level", "ar_delay_w", 3.0, 100.0, 0.25, component="collections"),
    ])
    out = compute_changes(scores, terms).set_index("feature")
    ar = out.loc["ar_delay_w"]
    assert ar.status == "appeared" and ar.value_effect == 0 and ar.weight_effect == pytest.approx(25)
    assert "disponible desde este mes" in ar.sentence
    assert out.loc["op_margin_w"].weight_effect == pytest.approx(60 * -0.25)
    assert out.reference_changed.all()


def test_momentum_and_clipping_terms_are_value_effects_and_disappearance_is_weight():
    scores = scores_frame([("C1", "EUR", "2026-01-01", 50.0, "2026-01-01"), ("C1", "EUR", "2026-02-01", 48.0, "2026-01-01")])
    terms = pd.DataFrame([
        term("C1", "2026-01-01", "level", "op_margin_w", 0.0, 50.0, 1.0),
        term("C1", "2026-01-01", "momentum", "op_margin_qoq", 0.02, 55.0, 0.8, contribution=1.0, component="momentum"),
        term("C1", "2026-01-01", "boundary", "score_clipping", -1.0, np.nan, 0.0, contribution=-1.0, component="boundary"),
        term("C1", "2026-02-01", "level", "op_margin_w", 0.0, 50.0, 1.0),
        term("C1", "2026-02-01", "momentum", "op_margin_qoq", -0.03, 44.0, 0.8, contribution=-2.0, component="momentum"),
    ])
    out = compute_changes(scores, terms).set_index("feature")
    assert out.loc["op_margin_qoq"].value_effect == pytest.approx(-3) and out.loc["op_margin_qoq"].weight_effect == 0
    clip = out.loc["score_clipping"]
    assert clip.status == "disappeared" and clip.weight_effect == pytest.approx(1.0) and clip.value_effect == 0


def test_non_consecutive_months_are_not_compared():
    scores = scores_frame([("C1", "EUR", "2026-01-01", 60.0, "2026-01-01"), ("C1", "EUR", "2026-03-01", 70.0, "2026-01-01")])
    terms = pd.DataFrame([term("C1", "2026-01-01", "level", "op_margin_w", 0.1, 60.0, 1.0),
                          term("C1", "2026-03-01", "level", "op_margin_w", 0.2, 70.0, 1.0)])
    assert compute_changes(scores, terms).empty


def test_validation_rejects_inconsistent_terms():
    scores = scores_frame([("C1", "EUR", "2026-01-01", 60.0, "2026-01-01"), ("C1", "EUR", "2026-02-01", 70.0, "2026-01-01")])
    terms = pd.DataFrame([term("C1", "2026-01-01", "level", "op_margin_w", 0.1, 60.0, 1.0),
                          term("C1", "2026-02-01", "level", "op_margin_w", 0.2, 65.0, 1.0)])  # suma 5, score dice 10
    with pytest.raises(ValueError, match="delta_vs_prev"):
        compute_changes(scores, terms)


def test_top_changes_aggregates_the_rest():
    scores = scores_frame([("C1", "EUR", "2026-01-01", 50.0, "2026-01-01"), ("C1", "EUR", "2026-02-01", 62.0, "2026-01-01")])
    rows = [term("C1", "2026-01-01", "level", f, 0.0, 50.0, 0.25) for f in ("op_margin_w", "debt_service_w", "ar_delay_w", "ap_delay_w")]
    rows += [term("C1", "2026-02-01", "level", f, 0.0, s, 0.25) for f, s in
             (("op_margin_w", 70.0), ("debt_service_w", 62.0), ("ar_delay_w", 58.0), ("ap_delay_w", 58.0))]
    out = top_changes(compute_changes(scores, pd.DataFrame(rows)), k=2)
    assert list(out.feature) == ["op_margin_w", "debt_service_w", "other"]
    assert out.loc[out.feature == "other", "delta_contribution"].item() == pytest.approx(2 + 2)
    assert out.delta_contribution.sum() == pytest.approx(12)
