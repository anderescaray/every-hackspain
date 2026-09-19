"""V2: ajuste estacional del crecimiento y consumo de `coverage_state` (FE10)."""
import json

import numpy as np
import pandas as pd
import pytest

from test_score_v2 import company, rows
from xray.score_v2 import ScoreV2Config, fit_reference_bundle, score_panel
from xray.score_v2.signals import smoothed_signals

CONFIG = ScoreV2Config(seasonal_min_rows=20)


def seasonal_company(company_id, group_id, n=20, august=0.7, seed=0):
    """Entradas planas salvo agosto (×august): el patrón real del dataset (hallazgos §3)."""
    months = pd.date_range("2025-01-01", periods=n, freq="MS")
    rng = np.random.default_rng(seed)
    inflow = 100 * np.exp(rng.normal(0, .02, n)) * np.where(months.month == 8, august, 1.0)
    return company(company_id, group_id, inflow, inflow * .8, months=months, seed=seed)


def seasonal_portfolio(n_groups=20, per_group=2, **kwargs):
    return pd.concat([seasonal_company(f"C{g}_{k}", f"G{g}", seed=100 * g + k, **kwargs)
                      for g in range(n_groups) for k in range(per_group)], ignore_index=True)


def test_reference_learns_the_august_dip_and_removes_it_from_growth():
    panel = seasonal_portfolio()
    reference = fit_reference_bundle(panel, CONFIG)
    aug_2026 = next(e for e in reference["references"] if e["effective_from"] == "2026-08-01")["seasonal_growth"]
    assert aug_2026["factors"]["8"] == pytest.approx(np.log(0.7), abs=0.03)     # agosto cae
    assert aug_2026["factors"]["9"] == pytest.approx(-np.log(0.7), abs=0.03)    # septiembre recupera
    assert abs(aug_2026["factors"]["5"]) < 0.03
    assert aug_2026["support"]["8"] >= CONFIG.seasonal_min_rows
    scores, _ = score_panel(panel, reference)
    august = rows(scores, "C0_0").set_index("month").loc["2026-08-01"]
    assert august.inflow_growth_q_raw == pytest.approx(np.log(0.7), abs=0.08)   # sin ajuste: caída del 30 %
    assert abs(august.inflow_growth_q) < 0.08                                   # ajustado: nada que señalar
    assert august.inflow_growth_seasonal_factor == pytest.approx(np.log(0.7), abs=0.03)
    assert august.trajectory in ("stable", "mixed_signals")


def test_without_adjustment_august_looks_like_deterioration():
    panel = seasonal_portfolio()
    raw = ScoreV2Config(seasonal_adjustment=False)
    scores, _ = score_panel(panel, fit_reference_bundle(panel, raw))
    august = rows(scores, "C0_0").set_index("month").loc["2026-08-01"]
    assert august.inflow_growth_change_z < -1.0
    assert "inflow_growth_seasonal_factor" in scores and august.isna().inflow_growth_seasonal_factor


def test_first_year_has_no_factor_for_unseen_months_and_adjustment_is_zero():
    panel = seasonal_portfolio()
    reference = fit_reference_bundle(panel, CONFIG)
    aug_2025 = next(e for e in reference["references"] if e["effective_from"] == "2025-08-01")["seasonal_growth"]
    assert aug_2025["factors"]["8"] == 0.0 and aug_2025["support"]["8"] == 0
    scores, _ = score_panel(panel, reference)
    first = rows(scores, "C0_0").set_index("month").loc["2025-08-01"]
    assert first.inflow_growth_seasonal_factor == 0.0


def test_seasonal_factors_are_frozen_serializable_and_used_for_unseen_entities():
    panel = seasonal_portfolio()
    reference = fit_reference_bundle(panel, CONFIG)
    restored = json.loads(json.dumps(reference))
    new = seasonal_company("NEW", "G_UNSEEN", seed=999)
    alone, _ = score_panel(new, restored)
    together, _ = score_panel(pd.concat([panel, new], ignore_index=True), restored)
    a, b = rows(alone, "NEW"), rows(together, "NEW")
    pd.testing.assert_series_equal(a.score, b.score)
    assert a.set_index("month").loc["2026-08-01", "inflow_growth_seasonal_factor"] == pytest.approx(np.log(0.7), abs=0.03)


def test_growth_is_not_measured_into_or_out_of_onboarding_months():
    inflow = np.array([30, 100, 100, 100, 100, 100, 100, 100, 100.])   # mes 0 parcial (backfill a mitad de mes)
    frame = company("C", "G", inflow, inflow * .8, coverage_state=["onboarding", "onboarding"] + ["ok"] * 7)
    signals = smoothed_signals(frame.set_index("month"), ScoreV2Config())
    assert signals.inflow_growth_m1.iloc[:3].isna().all()      # ni hacia el mes 1 ni desde él
    assert signals.inflow_growth_m1.iloc[3] == pytest.approx(0.0, abs=1e-9)
    naive = smoothed_signals(frame.drop(columns="coverage_state").set_index("month"), ScoreV2Config())
    assert naive.inflow_growth_m1.iloc[1] == pytest.approx(np.log(100 / 30))   # sin FE10 parecería +233 %


def test_onboarding_and_account_change_months_are_provisional_with_reason():
    base = pd.concat([company(f"C{g}_{k}", f"G{g}", np.full(12, 100.), np.full(12, 80.), seed=g) for g in range(12) for k in range(2)],
                     ignore_index=True)
    states = ["onboarding", "onboarding"] + ["ok"] * 5 + ["account_change"] + ["ok"] * 4
    target = company("T", "GT", np.full(12, 100.), np.full(12, 80.), coverage_state=states)
    panel = pd.concat([base, target], ignore_index=True)
    scores, _ = score_panel(panel, fit_reference_bundle(panel))
    t = rows(scores, "T").set_index("month")
    assert t.coverage_state.tolist() == states
    scored = t[t.score.notna()]
    assert (scored.loc[scored.coverage_state.eq("account_change"), "score_reason"] == "coverage_account_change").all()
    assert (scored.loc[scored.coverage_state.eq("account_change"), "score_status"] == "provisional").all()
    assert scored.loc[scored.coverage_state.eq("account_change"), "level"].notna().all()   # el nivel sigue siendo válido
    assert (scored.loc["2025-12-01", "score_status"] == "scored") or scored.loc["2025-12-01", "score_reason"] != "coverage_account_change"


def test_config_rejects_bad_seasonal_min_rows():
    with pytest.raises(ValueError):
        ScoreV2Config(seasonal_min_rows=0)
