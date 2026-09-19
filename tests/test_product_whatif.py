"""What-if: misma función y referencia que V2; base idéntica al score publicado; palancas coherentes."""
import json

import numpy as np
import pandas as pd
import pytest

from test_score_v2 import company, noisy_company, portfolio
from xray.product.frontend_export import _simulation
from xray.product.whatif import ZERO, apply_scenario, build_whatif, scenario_grid
from xray.score_v2 import fit_reference_bundle, score_panel


@pytest.fixture(scope="module")
def fitted():
    panel = pd.concat([portfolio(n_groups=12, per_group=2, n=18), noisy_company("T", "GT", margin=0.10, n=18, seed=7)], ignore_index=True)
    reference = json.loads(json.dumps(fit_reference_bundle(panel)))
    return panel, reference


def test_grid_is_the_full_factorial_with_a_zero_base():
    grid = scenario_grid()
    assert len(grid) == 81 and ("base", ZERO) in grid
    assert len({sid for sid, _ in grid}) == len(grid)
    assert {tuple(i.values()) for _, i in grid} == {(a, b, c, d) for a in (-20, 0, 20) for b in (0, 30, 60) for c in (0, 30, 60) for d in (-20, 0, 20)}


def test_apply_scenario_touches_only_the_window_and_recomputes_margin_and_growth():
    frame = company("C", "G", np.full(8, 100.0), np.full(8, 80.0))
    window = pd.date_range("2025-05-01", periods=3, freq="MS")
    out = apply_scenario(frame, {**ZERO, "customer_term": -20}, window)
    assert (out.loc[~out.month.isin(window), "tx_inflow"] == 100).all()
    assert (out.loc[out.month.isin(window), "tx_inflow"] == 80).all()
    assert out.loc[out.month.isin(window), "tx_operating_margin"].eq(0).all()
    first = out.loc[out.month.eq(window[0]), "tx_lfl_inflow_growth"].item()
    assert first == pytest.approx(0.8 - 1)      # 100 -> 80 entre abril y mayo
    delayed = apply_scenario(frame, {**ZERO, "collection_delay": 30}, window)
    assert (delayed.loc[delayed.month.isin(window), "inv_ar_delay_median"] - frame.loc[frame.month.isin(window), "inv_ar_delay_median"]).eq(30).all()


def test_base_scenario_reproduces_published_score_and_levers_move_in_the_right_direction(fitted):
    panel, reference = fitted
    published, _ = score_panel(panel, reference)
    month = panel.month.max()
    result = build_whatif(panel, reference, ["T"], month, window=6, verbose=False)
    base = result.loc[result.scenario_id.eq("base"), "score"].item()
    assert base == pytest.approx(published.loc[published.company_id.eq("T") & published.month.eq(month), "score"].item(), abs=1e-9)
    by = result.set_index("scenario_id").delta
    assert by["customer_term:-20"] < 0 < by["customer_term:+20"]
    assert by["internal_support:+20"] < 0 < by["internal_support:-20"]
    assert by["collection_delay:+60"] <= by["collection_delay:+30"] <= 0
    assert by["supplier_term:+60"] <= 0
    assert by["customer_term:-20|internal_support:+20"] < by["customer_term:-20"]   # la combinación empeora más que una sola palanca


def test_simulation_export_matches_contract_and_marks_zero_effects():
    scenarios = pd.DataFrame([
        {"scenario_id": "base", "customer_term": 0, "collection_delay": 0, "supplier_term": 0, "internal_support": 0, "score": 61.4, "base_score": 61.4, "delta": 0.0},
        {"scenario_id": "customer_term:-20", "customer_term": -20, "collection_delay": 0, "supplier_term": 0, "internal_support": 0, "score": 55.2, "base_score": 61.4, "delta": -6.2},
        {"scenario_id": "collection_delay:+30", "customer_term": 0, "collection_delay": 30, "supplier_term": 0, "internal_support": 0, "score": 61.4, "base_score": 61.4, "delta": 0.0},
        {"scenario_id": "customer_term:-20|collection_delay:+30", "customer_term": -20, "collection_delay": 30, "supplier_term": 0, "internal_support": 0, "score": 54.0, "base_score": 61.4, "delta": -7.4},
    ])
    sim = _simulation(scenarios, 61, has_invoices=False)
    assert [s["id"] for s in sim["scenarios"]] == ["base", "customer_term:-20", "collection_delay:+30", "customer_term:-20|collection_delay:+30"]
    assert sim["scenarios"][0]["health_score"] == 61 and sim["scenarios"][0]["impacts"] == []
    assert sim["scenarios"][1]["impacts"] == [{"key": "customer_term", "label": "Entradas operativas", "points": -6.2}]
    assert "no tiene facturas" in sim["scenarios"][2]["explanation"]
    combo = sim["scenarios"][3]
    assert combo["label"] == "Entradas operativas: -20 % · Retraso de cobro a clientes: +30 días" and combo["health_score"] == 54
    assert [i["points"] for i in combo["impacts"]] == [-6.2, 0.0] and "no es aditivo" in combo["explanation"]
    assert sim["example_id"] == "customer_term:-20"
    assert {i["key"] for i in sim["inputs"]} == set(ZERO)
    empty = _simulation(None, 61)
    assert empty["scenarios"] == [] and empty["example_id"] is None
