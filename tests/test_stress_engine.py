"""Focused V2 Stress Test contract and baseline tests; no scorer methodology change."""
import json

import numpy as np
import pandas as pd
import pytest
from test_score_v2 import company, portfolio

from xray.score_v2 import fit_reference_bundle, score_panel
from xray.stress.attribution import exact_shapley
from xray.stress.engine import build_batch_stress, build_company_stress
from xray.stress.scenarios import Scenario, Shock, apply_shocks, observed_horizon_months, scenarios


@pytest.fixture(scope="module")
def source():
    target = company("C", "GC", np.full(18, 100.), np.full(18, 80.))
    panel = pd.concat([portfolio(n_groups=12, per_group=2, n=18), target], ignore_index=True)
    reference = json.loads(json.dumps(fit_reference_bundle(panel)))
    published, _ = score_panel(panel, reference)
    month = target.month.max()
    score = published.loc[published.company_id.eq("C") & published.month.eq(month), "score"].item()
    return target, reference, score, month


def exposure(month, *, service=60, quality=None):
    months = pd.date_range(end=month, periods=6, freq="MS")
    return {"company_id": "C", "as_of": (month + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d"),
            "operating": {"quality_months": quality if quality is not None else [m.strftime("%Y-%m") for m in months]},
            "debt_service": {"status": "available" if service else "unavailable", "v2_service_6m": service}}


def test_presets_are_versioned_discrete_and_financing_is_not_invented():
    rows = scenarios(False)
    assert [s.id for s in rows[:4]] == ["collections", "margin", "financing", "adverse"]
    assert rows[2].available is False and rows[2].reason == "no_observed_debt_service"
    assert {s.factor for s in rows[3].shocks} == {"operating_inflow", "operating_outflow"}
    assert not any(s.id.startswith("observed_debt_service") for s in rows)
    assert len(rows) == 11
    delayed = scenarios(True, has_customer_delay=True, has_variable_rate=True, fx_currency="USD")
    assert delayed[0].shocks[0].factor == "customer_delay"
    assert delayed[2].shocks[0].factor == "variable_rate"
    assert delayed[3].id == "fx"
    assert [s.factor for s in next(s for s in delayed if s.id == "adverse").shocks] == [
        "operating_inflow", "operating_outflow", "customer_delay", "variable_rate", "fx_USD"]
    with pytest.raises(ValueError, match="No se combinan"):
        Scenario("bad", "preset", "x", (Shock("operating_outflow", 10), Shock("cost_payroll", 10)))


def test_engine_reconciles_frozen_baseline_and_exact_attribution(source):
    panel, reference, published, month = source
    result = build_company_stress(panel, reference, published, exposure(month), company_id="C", month=month)
    assert result["baseline_health"] == pytest.approx(published, abs=1e-9)
    assert result["status"] == "available"
    for scenario in result["scenarios"]:
        for row in scenario["results"]:
            if row["status"] != "available":
                continue
            assert row["health"] - published == pytest.approx(row["delta_points"], abs=1e-8)
            assert sum(term["points"] for term in row["score_terms"]) == pytest.approx(row["delta_points"], abs=1e-8)
            if row["observed_months"] == 6:
                attr = row["attribution"]
                assert sum(f["points"] for f in attr["factors"]) + attr["residual"] == pytest.approx(row["delta_points"], abs=1e-8)
            else:
                assert row["attribution"] is None
    assert next(s for s in result["scenarios"] if s["id"] == "collections")["results"][2]["delta_points"] < 0
    json.dumps(result, allow_nan=False)


def test_quality_gate_never_uses_nonconsecutive_history(source):
    panel, reference, published, month = source
    months = pd.date_range(end=month, periods=6, freq="MS")
    quality = [m.strftime("%Y-%m") for m in months if m != months[-2]]
    result = build_company_stress(panel, reference, published, exposure(month, quality=quality), company_id="C", month=month)
    rows = next(s for s in result["scenarios"] if s["id"] == "margin")["results"]
    assert [row["status"] for row in rows] == ["available", "insufficient_quality_months", "insufficient_quality_months"]
    assert rows[2]["health"] is None and rows[2]["attribution"] is None


def test_missing_service_and_baseline_mismatch(source):
    panel, reference, published, month = source
    result = build_company_stress(panel, reference, published, exposure(month, service=0), company_id="C", month=month)
    financing = next(s for s in result["scenarios"] if s["id"] == "financing")
    assert financing["status"] == "unavailable" and financing["results"] == []
    assert len(next(s for s in result["scenarios"] if s["id"] == "adverse")["shocks"]) == 2
    with pytest.raises(ValueError, match="baseline does not reconcile"):
        build_company_stress(panel, reference, published + 1, exposure(month), company_id="C", month=month)
    missing = build_company_stress(panel, reference, None, exposure(month), company_id="C", month=month)
    assert missing["status"] == "insufficient_data" and missing["reason"] == "v2_score_unavailable"
    assert missing["scenarios"] == [] and missing["baseline_health"] is None


def test_batch_equals_single_and_future_does_not_change_past(source):
    panel, reference, published, month = source
    exp = exposure(month)
    single = build_company_stress(panel, reference, published, exp, company_id="C", month=month)
    batch = build_batch_stress(panel, reference, [("C", published, exp)], month=month)
    assert batch["C"] == single
    future = panel.copy()
    future.loc[future.month.gt(month), "tx_inflow"] = 1e9
    assert build_company_stress(future, reference, published, exp, company_id="C", month=month) == single


def test_service_shock_changes_only_observed_principal_interest(source):
    panel, _, _, month = source
    last = tuple(pd.date_range(end=month, periods=1, freq="MS"))
    changed = apply_shocks(panel, (Shock("observed_debt_service", 20),), last)
    mask = panel.month.isin(last)
    assert changed.loc[mask, "debt_principal_paid"].to_numpy() == pytest.approx(panel.loc[mask, "debt_principal_paid"] * 1.2)
    assert changed.loc[~mask, "debt_principal_paid"].equals(panel.loc[~mask, "debt_principal_paid"])


def test_shapley_on_known_interaction_is_exact():
    shocks = (Shock("operating_inflow", -10), Shock("operating_outflow", 10))
    values = {frozenset(): 50, frozenset({"operating_inflow"}): 45,
              frozenset({"operating_outflow"}): 48,
              frozenset({"operating_inflow", "operating_outflow"}): 40}
    result = exact_shapley(shocks, values.get)
    assert result["method"] == "exact_shapley"
    assert sum(x["points"] for x in result["factors"]) == pytest.approx(-10)
    assert result["residual"] == pytest.approx(0)


def test_reconciled_cost_category_shock_is_month_specific_and_precomputed(source):
    panel, reference, published, month = source
    exp = exposure(month)
    months = pd.date_range(end=month, periods=6, freq="MS")
    exp["costs"] = {
        "category_gates": {"payroll": {"score_runnable": True}, "utilities": {"score_runnable": False}},
        "monthly_by_category": {m.strftime("%Y-%m"): {"payroll": 20.0} for m in months},
    }
    result = build_company_stress(panel, reference, published, exp, company_id="C", month=month)
    cost = next(s for s in result["scenarios"] if s["id"] == "cost_payroll:+10")
    assert cost["status"] == "available"
    assert cost["results"][2]["delta_points"] < 0
    assert not any(s["id"].startswith("cost_utilities") for s in result["scenarios"])
    changed = apply_shocks(panel, (Shock("cost_payroll", 10),), months[-1:], exp["costs"]["monthly_by_category"])
    mask = panel.month.eq(month)
    assert changed.loc[mask, "tx_outflow"].item() == pytest.approx(82)
    assert changed.loc[~mask, "tx_outflow"].equals(panel.loc[~mask, "tx_outflow"])
    with pytest.raises(ValueError, match="requires reconciled"):
        apply_shocks(panel, (Shock("cost_payroll", 10),), months[-1:])


def test_fx_only_after_material_exposure_and_exact_reaggregation(source, monkeypatch):
    from xray.stress.fx import FXStressUnavailable

    panel, reference, published, month = source
    exp = exposure(month)
    exp["fx"] = {"status": "context_only", "reason": "fixed_fx_rates_no_historical_path",
                 "score_runnable": False, "reconciliation_status": "matched",
                 "source_currency_amounts": {"EUR": 1000., "USD": 2000.},
                 "monthly_by_currency": {m.strftime("%Y-%m"): {"EUR": {"inflows": 100., "outflows": 0.},
                                                               "USD": {"inflows": 200., "outflows": 0.}}
                                         for m in pd.date_range(end=month, periods=6, freq="MS")}}
    context = {"raw_transactions": object(), "companies": object(), "banking_products": object(),
               "debt_products": object(), "config": object()}

    def exact_projection(frame, *_args, source_currency, relative_pct, window_months, **_kwargs):
        assert source_currency == "USD"
        changed = frame.copy()
        mask = changed.month.isin(window_months)
        changed.loc[mask, "tx_inflow"] *= 1 + relative_pct / 200
        total = changed.loc[mask, "tx_inflow"] + changed.loc[mask, "tx_outflow"]
        changed.loc[mask, "tx_operating_margin"] = (changed.loc[mask, "tx_inflow"] - changed.loc[mask, "tx_outflow"]) / total
        return changed, {"source_currency": source_currency}

    monkeypatch.setattr("xray.stress.engine.apply_source_currency_shock", exact_projection)
    result = build_company_stress(panel, reference, published, exp, company_id="C", month=month, fx_context=context)
    assert result["exposures"]["fx"]["stress_status"] == "available"
    assert result["exposures"]["fx"]["stress_currency"] == "USD"
    assert result["exposures"]["fx"]["score_runnable"] is True
    assert {s["id"] for s in result["scenarios"] if s["id"].startswith("fx_")} >= {"fx_USD:-10", "fx_USD:+10"}
    assert next(s for s in result["scenarios"] if s["id"] == "fx")["status"] == "available"
    assert all(r["status"] == "available" for s in result["scenarios"] if s["id"].startswith("fx_") for r in s["results"])
    assert exp["fx"]["score_runnable"] is False  # never mutate raw exposure input

    def reject(*_args, **_kwargs):
        raise FXStressUnavailable("baseline_tx_lfl_inflow_growth_does_not_reconcile")

    monkeypatch.setattr("xray.stress.engine.apply_source_currency_shock", reject)
    rejected = build_company_stress(panel, reference, published, exp, company_id="C", month=month, fx_context=context)
    assert rejected["exposures"]["fx"]["stress_status"] == "context_only"
    assert rejected["exposures"]["fx"]["stress_currency"] is None
    assert not any(s["id"].startswith("fx_") for s in rejected["scenarios"])
    exp["fx"]["source_currency_amounts"] = {"EUR": 10000., "USD": 500.}
    exp["fx"]["monthly_by_currency"] = {m.strftime("%Y-%m"): {"EUR": {"inflows": 1000., "outflows": 0.},
                                                               "USD": {"inflows": 50., "outflows": 0.}}
                                         for m in pd.date_range(end=month, periods=6, freq="MS")}
    immaterial = build_company_stress(panel, reference, published, exp, company_id="C", month=month, fx_context=context)
    assert not any(s["id"].startswith("fx_") for s in immaterial["scenarios"])


def test_debt_pressure_requires_identified_service_inside_each_horizon(source):
    panel, reference, _, month = source
    panel = panel.copy()
    recent = panel.month.ge(month - pd.DateOffset(months=2))
    panel.loc[recent, ["debt_principal_paid", "debt_interest_paid"]] = 0.
    scored, _ = score_panel(panel, reference)
    published = scored.loc[scored.company_id.eq("C") & scored.month.eq(month), "score"].item()
    result = build_company_stress(panel, reference, published, exposure(month), company_id="C", month=month)
    financing = next(s for s in result["scenarios"] if s["id"] == "financing")
    adverse = next(s for s in result["scenarios"] if s["id"] == "adverse")
    for scenario in (financing, adverse):
        assert [r["status"] for r in scenario["results"]] == ["unavailable", "unavailable", "available"]
        assert all(r["reason"] == "no_observed_service_in_horizon" for r in scenario["results"][:2])
    assert next(s for s in result["scenarios"] if s["id"] == "margin")["results"][0]["status"] == "available"


def test_fx_dominant_currency_excludes_nonquality_months(source, monkeypatch):
    panel, reference, published, month = source
    months = pd.date_range(end=month, periods=6, freq="MS")
    exp = exposure(month, quality=[m.strftime("%Y-%m") for m in months[1:]])
    exp["fx"] = {"reconciliation_status": "matched", "source_currency_amounts": {"USD": 5000., "EUR": 1000.},
                 "score_runnable": False,
                 "monthly_by_currency": {m.strftime("%Y-%m"): {"USD": {"inflows": 5000., "outflows": 0.}}
                                         if i == 0 else {"EUR": {"inflows": 1000., "outflows": 0.}}
                                         for i, m in enumerate(months)}}
    def unexpected(*_args, **_kwargs):
        raise AssertionError("Nonquality FX exposure must not trigger reaggregation")
    monkeypatch.setattr("xray.stress.engine.apply_source_currency_shock", unexpected)
    context = {"raw_transactions": object(), "companies": object(), "banking_products": object(),
               "debt_products": object(), "config": object()}
    result = build_company_stress(panel, reference, published, exp, company_id="C", month=month, fx_context=context)
    assert not any(s["id"].startswith("fx_") for s in result["scenarios"])
    assert result["exposures"]["fx"]["stress_status"] == "context_only"


def test_customer_delay_is_share_weighted_and_rate_uses_outstanding(source):
    panel, reference, published, month = source
    last = tuple(pd.date_range(end=month, periods=1, freq="MS"))
    delayed = apply_shocks(panel, (Shock("customer_delay", 30, "days"),), last, context={"top1_share": 0.5})
    mask = panel.month.isin(last)
    assert delayed.loc[mask, "inv_ar_delay_median"].to_numpy() == pytest.approx(
        panel.loc[mask, "inv_ar_delay_median"] + 15)
    rated = apply_shocks(panel, (Shock("variable_rate", 200, "bp"),), last, context={"variable_outstanding_eur": 1200})
    assert rated.loc[mask, "debt_interest_paid"].to_numpy() == pytest.approx(
        panel.loc[mask, "debt_interest_paid"] + 1200 * 0.02 / 12)
    with pytest.raises(ValueError, match="double-counting"):
        apply_shocks(panel, (Shock("operating_outflow", 10), Shock("cost_payroll", 10)), last, {"2026-01": {"payroll": 1}})


def test_engine_runs_customer_delay_and_reverse_limits(source):
    panel, reference, published, month = source
    exp = exposure(month)
    exp["collections"] = {"status": "available", "score_runnable": True, "largest_customer_share": 0.4}
    result = build_company_stress(panel, reference, published, exp, company_id="C", month=month)
    cobros = next(s for s in result["scenarios"] if s["id"] == "collections")
    assert cobros["shocks"][0]["factor"] == "customer_delay"
    assert cobros["results"][2]["status"] == "available"
    assert result["default_scenario_id"] == "adverse"
    assert result["baseline_band"] in {"green", "amber", "red"}
    assert cobros["path"]
    assert any(item["factor"] == "operating_inflow" for item in result["reverse_limits"]) or result["reverse_limits"] == []
    attr = next(s for s in result["scenarios"] if s["id"] == "adverse")["results"][2]["attribution"]
    assert abs(sum(item["points"] for item in attr["factors"]) + attr["residual"]
               - next(s for s in result["scenarios"] if s["id"] == "adverse")["results"][2]["delta_points"]) < 1e-8
    json.dumps(result, allow_nan=False)


def test_core_stress_survives_without_invoices_debt_or_fx(source):
    panel, reference, published, month = source
    result = build_company_stress(panel, reference, published, exposure(month, service=0), company_id="C", month=month)
    assert result["status"] == "available"
    assert result["baseline_health"] == pytest.approx(published, abs=1e-9)
    ids = {row["id"]: row for row in result["scenarios"]}
    assert ids["collections"]["shocks"][0]["factor"] == "operating_inflow"
    assert ids["margin"]["status"] == "available"
    assert ids["financing"]["status"] == "unavailable"
    assert ids["adverse"]["status"] == "available"
    assert "fx" not in ids
    assert all(not row["id"].startswith("fx_") for row in result["scenarios"])
    assert {factor["factor"] for factor in result["custom_factors"]} >= {"operating_inflow", "operating_outflow"}
    assert "customer_delay" not in {factor["factor"] for factor in result["custom_factors"]}


def test_thin_current_month_still_stresses_prior_v2_quality_block(source):
    panel, reference, published, month = source
    months = pd.date_range(end=month, periods=6, freq="MS")
    quality = [m.strftime("%Y-%m") for m in months[:-1]]
    result = build_company_stress(panel, reference, published, exposure(month, quality=quality), company_id="C", month=month)
    rows = next(s for s in result["scenarios"] if s["id"] == "margin")["results"]
    assert [row["status"] for row in rows] == ["available", "available", "insufficient_quality_months"]
    assert result["status"] == "available" and result["baseline_health"] == pytest.approx(published, abs=1e-9)


def test_observed_horizon_months_uses_last_quality_block_not_calendar_end():
    months = pd.date_range("2026-03-01", periods=6, freq="MS")
    keys = [stamp.strftime("%Y-%m") for stamp in months]
    assert observed_horizon_months(keys, months[-1], 6) == tuple(months)
    assert observed_horizon_months(keys[:-1], months[-1], 3) == tuple(months[-4:-1])
    assert observed_horizon_months(keys[:-1], months[-1], 6) is None
    assert observed_horizon_months(keys[:2], months[-1], 1) == (months[1],)


def test_empty_quality_is_history_not_missing_advanced_factors(source):
    panel, reference, published, month = source
    result = build_company_stress(panel, reference, published, exposure(month, quality=[]), company_id="C", month=month)
    assert result["status"] == "insufficient_data" and result["reason"] == "insufficient_quality_months"
    assert result["scenarios"] == [] and result["baseline_health"] is None
