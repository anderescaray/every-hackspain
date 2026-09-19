import numpy as np
import pandas as pd
import pytest

from advisor_fixtures import anchor_reference_state, derive_signals, make_group_state
from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.fx import FX_ASOF, FX_SOURCE, MissingFXRateError, convert, default_fx_table
from xray.group_advisor.state import (EVIDENCE_FIELDS, SIGNAL_ROW_KEYS, SUBSIDIARY_COLUMNS, build_group_state, invariants_summary,
                                      iter_group_states, load_inputs, reference_state_for, tramo_of, window_sums)
from xray.paths import PROCESSED_DIR
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.core import prepare_panel
from xray.score_v2.level import score_level
from xray.score_v2.signals import build_signals

DATASET_CURRENCIES = ("AED", "AOA", "ARS", "AUD", "BAM", "BRL", "CAD", "CHF", "CLP", "COP", "CZK", "DKK", "EUR", "GBP", "GHS",
                      "HKD", "HUF", "ILS", "INR", "JPY", "MXN", "MYR", "MZN", "NAD", "NOK", "NZD", "PEN", "PHP", "PLN", "RON",
                      "RUB", "SEK", "SGD", "THB", "TRY", "USD", "VND", "XOF", "ZAR")
REAL_DATA = (PROCESSED_DIR / "scores_v2").exists()


# ---------------------------------------------------------------- AdvisorConfig


def test_default_config_is_valid_and_matches_spec():
    config = AdvisorConfig()
    assert config.horizon_months == 6 and config.tramo_bounds == (40.0, 70.0) and config.levers == ("D1", "P")
    assert config.fx_rates_to_eur is None and config.reporting_currency == "EUR"
    assert set(config.sensitivity_r_max) == {"cut_outflow", "raise_inflow", "debt_service_cut", "ap_on_time", "ar_faster"}
    AdvisorConfig(fx_rates_to_eur=default_fx_table(), fx_source=FX_SOURCE, fx_asof=FX_ASOF, reporting_currency="USD")


@pytest.mark.parametrize("kwargs", [
    {"fractions": (0.0, 0.5)}, {"fractions": (0.5, 1.5)}, {"fractions": (0.5, 0.25)}, {"fractions": ()},
    {"sensitivity_grid": (0.01, 0.01)}, {"sensitivity_grid": (-0.1,)},
    {"utility_knots": ((0, 1.0), (40, 2.0), (70, 3.0))},           # pendientes crecientes: no cóncava
    {"utility_knots": ((0, 3.0), (40, -1.0), (70, 0.5))},          # pendiente negativa
    {"utility_knots": ((10, 3.0), (40, 2.0), (70, 1.0))},          # no empieza en 0
    {"utility_knots": ((0, 3.0), (50, 2.0), (70, 1.0))},           # incoherente con tramo_bounds
    {"tramo_bounds": (70.0, 40.0)}, {"tramo_bounds": (40.0,)},
    {"fx_rates_to_eur": {"USD": 1.1}}, {"fx_rates_to_eur": {"EUR": 1.0, "USD": -1.1}},
    {"fx_rates_to_eur": {"EUR": 1.0, "USD": float("nan")}}, {"fx_rates_to_eur": {"EUR": 1.05, "USD": 1.1}},
    {"fx_rates_to_eur": {"EUR": 1.0}, "reporting_currency": "USD"},
    {"report_k": (0, 6)}, {"report_k": (1, 7)}, {"report_k": (6, 1)}, {"report_k": ()},
    {"horizon_months": 0}, {"levers": ("D2",)}, {"subsidiary_weighting": "flow"},
    {"sensitivity_r_max": {"cut_outflow": 0.5}}, {"donor_buffer_months": -1}, {"month": "2026-08-15"},
])
def test_config_rejects_incoherent_values(kwargs):
    with pytest.raises(ValueError):
        AdvisorConfig(**kwargs)


def test_utility_slopes_may_be_flat_but_not_increasing():
    AdvisorConfig(utility_knots=((0, 2.0), (40, 2.0), (70, 1.0)))
    with pytest.raises(ValueError, match="cóncava"):
        AdvisorConfig(utility_knots=((0, 2.0), (40, 2.5), (70, 1.0)))


# ---------------------------------------------------------------- FX


def test_default_fx_table_covers_dataset_currencies_with_eur_one():
    table = default_fx_table()
    assert table["EUR"] == 1.0
    assert isinstance(FX_SOURCE, str) and FX_SOURCE and pd.notna(pd.Timestamp(FX_ASOF))  # fuente documentada con fecha
    assert set(DATASET_CURRENCIES) <= set(table)
    assert all(rate > 0 for rate in table.values())
    table["EUR"] = 2.0
    assert default_fx_table()["EUR"] == 1.0  # copia, no la constante


def test_convert_identity_round_trip_and_missing_currency():
    table = default_fx_table()
    assert convert(1234.5, "EUR", "EUR", table) == (1234.5, 1.0)
    assert convert(10.0, "XYZ", "XYZ", None) == (10.0, 1.0)  # misma moneda no consulta la tabla
    usd, rate = convert(1000.0, "EUR", "USD", table)
    assert rate == pytest.approx(table["USD"]) and usd == pytest.approx(1000.0 * table["USD"])
    back, back_rate = convert(usd, "USD", "EUR", table)
    assert back == pytest.approx(1000.0) and back_rate == pytest.approx(1 / table["USD"])
    gbp, gbp_rate = convert(100.0, "USD", "GBP", table)
    assert gbp == pytest.approx(100.0 / table["USD"] * table["GBP"]) and gbp_rate == pytest.approx(table["GBP"] / table["USD"])
    with pytest.raises(ValueError, match="XYZ"):
        convert(1.0, "EUR", "XYZ", table)
    with pytest.raises(MissingFXRateError) as info:
        convert(1.0, "XYZ", "EUR", table)
    assert info.value.currency == "XYZ"
    with pytest.raises(MissingFXRateError):
        convert(1.0, "EUR", "USD", None)


# ---------------------------------------------------------------- make_group_state / GroupState


def test_group_state_columns_order_index_and_signal_row():
    state = make_group_state([
        {"company_id": "B", "level_inflow_sum": 600., "window_outflow_sum": 400., "window_debt_service_sum": 60.,
         "ar_delay_w": 5., "ap_delay_w": 3., "reconstructed_cash": 1000., "runway_months": 2.5},
        {"company_id": "A", "level_inflow_sum": 300., "window_outflow_sum": 350.},
    ])
    frame = state.subsidiaries
    assert tuple(frame.columns) == SUBSIDIARY_COLUMNS
    assert list(frame.index) == ["A", "B"] and frame.index.name == "company_id"
    assert state.month == pd.Timestamp("2026-08-01") and state.group_id == "GROUP_TEST"
    row = state.signal_row("B")
    assert tuple(row) == SIGNAL_ROW_KEYS
    assert row["op_margin_w"] == pytest.approx(0.2) and row["debt_service_w"] == pytest.approx(0.1)
    assert row["debt_without_inflow_w"] is False and row["level_inflow_sum"] == 600.
    assert frame.loc["B", "monthly_debt_service"] == pytest.approx(10.)
    assert frame.loc["A", "op_margin_w"] == pytest.approx(-50 / 650) and np.isnan(frame.loc["A", "debt_service_w"])
    assert np.isnan(frame.loc["A", "monthly_debt_service"]) and np.isnan(frame.loc["A", "inv_ap_overdue_amount"])
    assert frame.optimizable.tolist() == [True, True] and frame.debt_without_inflow_w.dtype == bool
    assert 0 < frame.loc["B", "level_debt"] <= 100. and np.isnan(frame.loc["A", "level_debt"])
    assert frame.loc["B", "level_coverage"] == 1.0 and frame.loc["A", "level_coverage"] == pytest.approx(0.45)
    assert (frame.level == frame.score).all()  # momentum_adjustment 0 por defecto
    assert frame.score_status.tolist() == ["scored", "scored"]
    assert state.invariants_report()["ok"]
    with pytest.raises(KeyError):
        state.signal_row("Z")


def test_tramo_cuts_are_exact_at_40_and_70():
    state = make_group_state([
        {"company_id": "R", "level": 39.99}, {"company_id": "A", "level": 40.0}, {"company_id": "G", "level": 70.0},
        {"company_id": "N", "level": np.nan}, {"company_id": "Z", "level": 100.0},
    ])
    tramo = state.subsidiaries.tramo
    assert tramo.to_dict() == {"A": "amber", "G": "green", "N": "none", "R": "red", "Z": "green"}
    assert state.subsidiaries.optimizable.to_dict() == {"A": True, "G": True, "N": False, "R": True, "Z": True}
    assert state.subsidiaries.loc["N", "score_status"] == "not_scored" and state.optimizable_ids == ["A", "G", "R", "Z"]
    bounds = AdvisorConfig().tramo_bounds
    assert [tramo_of(x, bounds) for x in (0., 39.999, 40., 69.999, 70., 100., float("nan"), None)] == \
        ["red", "red", "amber", "amber", "green", "green", "none", "none"]


def test_unreliable_cash_is_nan_and_reliable_cash_is_kept():
    state = make_group_state([
        {"company_id": "A", "reconstructed_cash": 500., "cash_reliable": False, "runway_months": 0.4},
        {"company_id": "B", "reconstructed_cash": 700.},
        {"company_id": "C"},
    ])
    frame = state.subsidiaries
    assert frame.cash_reliable.tolist() == [False, True, False]
    assert np.isnan(frame.loc["A", "reconstructed_cash"]) and frame.loc["A", "runway_months"] == 0.4
    assert frame.loc["B", "reconstructed_cash"] == 700. and np.isnan(frame.loc["C", "reconstructed_cash"])
    assert frame.cash_reliable.dtype == bool


def test_evidence_is_deterministic_by_company_and_field():
    rows = [{"company_id": "B", "reconstructed_cash": 10., "inv_ar_open_amount": 3., "level_inflow_sum": 100., "window_outflow_sum": 80.},
            {"company_id": "A", "runway_months": 1.5, "inv_ap_due_30_amount": 20.}]
    state = make_group_state(rows)
    assert list(state.evidence) == [f"ev_{i:04d}" for i in range(1, 7)]
    entries = list(state.evidence.values())
    assert [(e["company_id"], e["field"]) for e in entries] == [
        ("A", "runway_months"), ("A", "inv_ap_due_30_amount"),
        ("B", "reconstructed_cash"), ("B", "inv_ar_open_amount"), ("B", "window_outflow_sum"), ("B", "level_inflow_sum")]
    assert [e["value"] for e in entries] == [1.5, 20., 10., 3., 80., 100.]
    assert all(set(e) == {"source", "company_id", "field", "month", "value"} and e["month"] == "2026-08-01" for e in entries)
    assert set(e["field"] for e in entries) <= set(EVIDENCE_FIELDS)
    assert make_group_state(rows[::-1]).evidence == state.evidence  # el orden de entrada no importa


def test_explicit_level_overrides_signals_and_momentum_adds_to_score():
    state = make_group_state([{"company_id": "A", "level": 50., "momentum_adjustment": 3., "level_inflow_sum": 100., "window_outflow_sum": 10.}])
    row = state.subsidiaries.loc["A"]
    assert row.level == 50. and row.score == 53. and row.tramo == "amber" and row.op_margin_w == pytest.approx(90 / 110)


def test_debt_without_inflow_indicator_from_sums():
    state = make_group_state([{"company_id": "A", "level_inflow_sum": 0., "window_outflow_sum": 50., "window_debt_service_sum": 12.}])
    row = state.signal_row("A")
    assert row["debt_without_inflow_w"] is True and np.isnan(row["debt_service_w"]) and row["op_margin_w"] == -1.
    assert state.subsidiaries.loc["A", "level_debt"] == 0.
    assert state.invariants_report()["ok"]


# ---------------------------------------------------------------- reference_state_for


def fake_reference():
    entries = [("2026-06-01", "2026-05-01", "jun"), ("2026-07-01", "2026-06-01", "jul"), ("2026-08-01", "2026-07-01", "aug")]
    return {"anchor_reference": {"marker": "anchor"},
            "references": [{"effective_from": start, "max_observed_month": observed, "rows": 10, "state": {"marker": marker}}
                           for start, observed, marker in entries]}


def test_reference_state_for_picks_latest_effective_before_month():
    reference = fake_reference()
    assert reference_state_for(reference, "2026-06-01")["marker"] == "jun"
    assert reference_state_for(reference, "2026-07-01")["marker"] == "jul"
    assert reference_state_for(reference, pd.Timestamp("2026-08-01"))["marker"] == "aug"
    assert reference_state_for(reference, "2026-11-01")["marker"] == "aug"
    assert reference_state_for(reference, "2026-05-01")["marker"] == "anchor"


def test_reference_state_for_rejects_reference_that_saw_the_month():
    reference = fake_reference()
    reference["references"][-1]["max_observed_month"] = "2026-08-01"
    with pytest.raises(ValueError, match="futuro"):
        reference_state_for(reference, "2026-08-01")
    reference["references"][-1]["max_observed_month"] = None
    assert reference_state_for(reference, "2026-08-01")["marker"] == "aug"
    reference["references"].reverse()
    with pytest.raises(ValueError, match="ordenado"):
        reference_state_for(reference, "2026-08-01")


def test_anchor_reference_state_has_no_empirical_component():
    state = anchor_reference_state()
    assert state["version"] == 2 and not any(spec["empirical_active"] for spec in state["features"].values())


# ---------------------------------------------------------------- invariantes sobre fixture sintética con build_signals


def synthetic_company(company_id, group_id, inflow, outflow, principal, interest, start="2025-09-01", **overrides):
    n = len(inflow)
    frame = pd.DataFrame({
        "company_id": company_id, "group_id": group_id, "currency": "EUR",
        "month": pd.date_range(start, periods=n, freq="MS"),
        "tx_inflow": np.asarray(inflow, dtype=float), "tx_outflow": np.asarray(outflow, dtype=float),
        "debt_principal_paid": np.asarray(principal, dtype=float), "debt_interest_paid": np.asarray(interest, dtype=float),
        "tx_lfl_inflow_growth": 0.0, "has_sufficient_history": np.arange(1, n + 1) >= 6,
        "tx_count": 40, "tx_usable_count": 40, "tx_usable_row_share": 1.0, "tx_operating_amount_share": 0.9, "tx_company_coverage": 1.0,
        "inv_ar_delay_median": np.linspace(4., 8., n), "inv_ar_delay_count": 10.,
        "inv_ap_delay_median": np.linspace(2., 5., n), "inv_ap_delay_count": 10.,
    })
    frame["tx_operating_margin"] = (frame.tx_inflow - frame.tx_outflow) / (frame.tx_inflow + frame.tx_outflow)
    for key, value in overrides.items():
        frame[key] = value
    return frame


def synthetic_panel():
    k = np.arange(10)
    a = synthetic_company("C_A", "G", 100 + 5 * k, 80 + 3 * k, np.full(10, 8.), np.full(10, 2.))
    b = synthetic_company("C_B", "G", 200 + 10 * k, 230 - 4 * k, 5 + k, np.full(10, 1.))
    b.loc[6, "tx_usable_row_share"] = 0.1                            # mes sin calidad dentro de la ventana
    return prepare_panel(pd.concat([a, b], ignore_index=True), ScoreV2Config())


def test_window_sums_reproduce_build_signals_derivatives():
    config = ScoreV2Config()
    panel = synthetic_panel()
    signals, sums = build_signals(panel, config), window_sums(panel, config)
    assert list(sums.columns) == ["window_outflow_sum", "window_debt_service_sum"] and sums.index.equals(panel.index)
    for company_id in ("C_A", "C_B"):
        last = panel.index[panel.company_id.eq(company_id)][-1]
        inflow, outflow, service = signals.level_inflow_sum[last], sums.window_outflow_sum[last], sums.window_debt_service_sum[last]
        margin, debt, indicator = derive_signals(inflow, outflow, service)
        assert margin == pytest.approx(signals.op_margin_w[last], rel=1e-12)
        assert debt == pytest.approx(signals.debt_service_w[last], rel=1e-12)
        assert indicator == bool(signals.debt_without_inflow_w[last])
    rows_b = panel.index[panel.company_id.eq("C_B")]
    last_b = rows_b[-1]
    quality_months = panel.loc[rows_b[-6:]].drop(index=rows_b[6])
    assert sums.window_outflow_sum[last_b] == pytest.approx(quality_months.tx_outflow.sum())
    assert sums.window_debt_service_sum[last_b] == pytest.approx((quality_months.debt_principal_paid + quality_months.debt_interest_paid).sum())
    assert signals.level_months[last_b] == 5
    report = invariants_summary(pd.concat([signals[["level_inflow_sum", "op_margin_w", "debt_service_w", "debt_without_inflow_w"]], sums], axis=1))
    assert report["ok"] and report["margin_checked"] == report["margin_ok"] > 0 and report["debt_checked"] == report["debt_ok"] > 0


def test_window_sums_follow_natural_calendar_and_v2_masks():
    config = ScoreV2Config()
    months = pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01", "2025-08-01", "2025-09-01", "2025-10-01"])
    gapped = synthetic_company("C", "G", [100] * 6, [80] * 6, [8] * 6, [2] * 6)
    gapped["month"] = months
    panel = prepare_panel(gapped, config)
    sums, signals = window_sums(panel, config), build_signals(panel, config)
    august = panel.index[panel.month.eq("2025-08-01")][0]
    assert np.isnan(sums.window_outflow_sum[august]) and np.isnan(signals.level_inflow_sum[august])
    october = panel.index[panel.month.eq("2025-10-01")][0]
    assert sums.window_outflow_sum[october] == 240. and sums.window_debt_service_sum[october] == 30.
    # principal no observado en un mes de la ventana: V2 deja debt_service_w NaN y la suma S también
    partial = synthetic_company("D", "G", [100] * 8, [80] * 8, [8] * 8, [2] * 8)
    partial.loc[5, "debt_principal_paid"] = np.nan
    panel = prepare_panel(partial, config)
    sums, signals = window_sums(panel, config), build_signals(panel, config)
    assert np.isnan(signals.debt_service_w.iloc[-1]) and np.isnan(sums.window_debt_service_sum.iloc[-1])
    assert sums.window_outflow_sum.iloc[-1] == 480. and signals.level_inflow_sum.iloc[-1] == 600.
    assert np.isnan(sums.window_debt_service_sum.iloc[-1]) and not np.isnan(sums.window_debt_service_sum.iloc[3])


def test_group_state_from_synthetic_signals_reproduces_v2_level():
    config = ScoreV2Config()
    panel = synthetic_panel()
    signals, sums = build_signals(panel, config), window_sums(panel, config)
    last = panel.groupby("company_id").tail(1)
    rows = [{"company_id": cid, "level_inflow_sum": signals.level_inflow_sum[i], "window_outflow_sum": sums.window_outflow_sum[i],
             "window_debt_service_sum": sums.window_debt_service_sum[i], "ar_delay_w": signals.ar_delay_w[i], "ap_delay_w": signals.ap_delay_w[i]}
            for i, cid in zip(last.index, last.company_id)]
    state = make_group_state(rows)
    expected, _ = score_level(signals.loc[last.index].set_index(last.company_id.to_numpy()), anchor_reference_state())
    np.testing.assert_allclose(state.subsidiaries.level.to_numpy(), expected.level.sort_index().to_numpy(), atol=1e-9)
    assert state.invariants_report()["ok"]


# ---------------------------------------------------------------- datos reales


@pytest.fixture(scope="module")
def real_inputs():
    if not REAL_DATA:
        pytest.skip("Sin data/processed/scores_v2")
    return load_inputs()


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_load_inputs_verifies_hashes_and_horizon(real_inputs):
    hashes = real_inputs.inputs_sha256
    assert {"company_monthly_features.parquet", "_feature_manifest.json", "scores_v2/company_monthly_scores.parquet",
            "scores_v2/group_currency_monthly_scores.parquet", "company_currency_liquidity_context.parquet",
            "scores_v2/_company_score_reference.json"} <= set(hashes)
    assert all(len(digest) == 64 for digest in hashes.values())
    assert real_inputs.config_v2.level_window == AdvisorConfig().horizon_months
    assert real_inputs.signals.index.equals(real_inputs.panel.index) and real_inputs.window_sums.index.equals(real_inputs.panel.index)
    with pytest.raises(ValueError, match="horizon_months"):
        load_inputs(config=AdvisorConfig(horizon_months=3, report_k=(1, 3)))


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_group_0064_state_matches_scores_v2(real_inputs):
    month = pd.Timestamp("2026-08-01")
    state = build_group_state(real_inputs, "GROUP_0064", month)
    # Las filiales concretas dependen de la versión de los datos (D32 consolidó monedas): se exige
    # el núcleo conocido y coherencia con los artefactos, no una lista literal.
    assert {"COMP_0007", "COMP_0222", "COMP_0738"} <= set(state.optimizable_ids)
    assert tuple(state.subsidiaries.columns) == SUBSIDIARY_COLUMNS
    assert state.subsidiaries.index.is_monotonic_increasing and state.subsidiaries.group_id.eq("GROUP_0064").all()
    scores = real_inputs.scores
    expected = scores.loc[scores.group_id.eq("GROUP_0064") & scores.month.eq(month)].set_index("company_id").sort_index()
    np.testing.assert_allclose(state.subsidiaries.level.to_numpy(), expected.level.to_numpy(), atol=1e-9)
    np.testing.assert_allclose(state.subsidiaries.score.to_numpy(), expected.score.to_numpy(), atol=1e-9)
    group_scores = real_inputs.group_scores
    consolidated = group_scores.loc[group_scores.group_id.eq("GROUP_0064") & group_scores.month.eq(month)].set_index("currency").score
    assert set(state.consolidated_scores) == set(consolidated.index)
    for currency, value in consolidated.items():
        assert (state.consolidated_scores[currency] is None) == pd.isna(value)
        if not pd.isna(value):
            assert state.consolidated_scores[currency] == pytest.approx(value, abs=1e-9)
    assert state.subsidiaries.loc[["COMP_0738", "COMP_0007", "COMP_0222"], "tramo"].tolist() == ["red", "amber", "green"]
    assert state.subsidiaries.loc["COMP_0738", "op_margin_w"] == pytest.approx(-0.80, abs=0.02)
    optimizable = state.subsidiaries.loc[state.subsidiaries.optimizable]
    recomputed, _ = score_level(optimizable, state.reference_state)
    np.testing.assert_allclose(recomputed.level.to_numpy(), optimizable.level.to_numpy(), atol=1e-9)
    assert state.invariants_report()["ok"]
    assert list(state.evidence) == [f"ev_{i:04d}" for i in range(1, len(state.evidence) + 1)]
    assert state.subsidiaries.loc["COMP_0007", "cash_reliable"] and state.subsidiaries.loc["COMP_0007", "reconstructed_cash"] > 0
    assert state.inputs_sha256 == real_inputs.inputs_sha256
    assert state.subsidiaries.loc[~state.subsidiaries.optimizable, "score_status"].eq("not_scored").all()
    with pytest.raises(ValueError, match="no tiene filas"):
        build_group_state(real_inputs, "GROUP_9999", month)


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_all_groups_august_2026_levels_and_invariants(real_inputs):
    month = pd.Timestamp("2026-08-01")
    states = list(iter_group_states(real_inputs, month))
    assert [s.group_id for s in states] == sorted(s.group_id for s in states) and len(states) == 250
    frame = pd.concat([s.subsidiaries for s in states])
    scores = real_inputs.scores.loc[real_inputs.scores.month.eq(month)].set_index("company_id")
    assert len(frame) == len(scores) and frame.index.is_unique
    np.testing.assert_allclose(frame.level.to_numpy(), scores.level.reindex(frame.index).to_numpy(), atol=1e-9)
    assert int(frame.optimizable.sum()) == int(scores.level.notna().sum()) > 900
    optimizable = frame.loc[frame.optimizable]
    report = invariants_summary(optimizable)
    checked = report["margin_checked"] + report["debt_checked"]
    passed = report["margin_ok"] + report["debt_ok"]
    assert checked > 0 and passed / checked >= 0.99  # GA-01 documenta el porcentaje real (100% el 19-09-2026)
    assert report["indicator_ok"] == len(optimizable)
    assert optimizable.tramo.isin(["red", "amber", "green"]).all() and frame.loc[~frame.optimizable, "tramo"].eq("none").all()
    assert frame.loc[~frame.cash_reliable, "reconstructed_cash"].isna().all()
    for state in states[:5]:
        rows = state.subsidiaries.loc[state.subsidiaries.optimizable]
        if len(rows):
            recomputed, _ = score_level(rows, state.reference_state)
            np.testing.assert_allclose(recomputed.level.to_numpy(), rows.level.to_numpy(), atol=1e-9)
