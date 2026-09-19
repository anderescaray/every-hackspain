"""Esquema de `company_sensitivity` frente a los fixtures de WP4 (`tests/fixtures/advisor_sensitivity_*.json`).

Se comparan claves (conjunto exacto por nivel) y compatibilidad de tipos (`None` compatible con todo;
`int`/`float` intercambiables; `bool` distinto de número). Las listas se comparan por su primer elemento,
salvo `levers`, donde una palanca disponible se compara con la primera disponible del fixture y una no
disponible con la primera no disponible. `evidence` (raíz) e `inputs_sha256` tienen claves libres: se
compara el esquema de su primer valor.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from advisor_fixtures import anchor_reference_state, make_group_state
from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.sensitivity import company_sensitivity

FIXTURES = Path(__file__).parent / "fixtures"
FREE_KEY_PATHS = {"$.evidence", "$.inputs_sha256"}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _kind(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    raise AssertionError(f"tipo no JSON: {type(value).__name__}")


def assert_same_schema(actual, expected, path="$"):
    kind_a, kind_e = _kind(actual), _kind(expected)
    if "null" in (kind_a, kind_e):
        return
    assert kind_a == kind_e, f"{path}: {kind_a} frente a {kind_e} del fixture"
    if kind_e == "dict":
        if path in FREE_KEY_PATHS:
            if actual and expected:
                assert_same_schema(next(iter(actual.values())), next(iter(expected.values())), f"{path}[*]")
            return
        assert set(actual) == set(expected), f"{path}: claves distintas {set(actual) ^ set(expected)}"
        for key in expected:
            assert_same_schema(actual[key], expected[key], f"{path}.{key}")
    elif kind_e == "list":
        if path == "$.levers":
            for available in (True, False):
                mine = [lv for lv in actual if lv.get("available") is available]
                theirs = [lv for lv in expected if lv.get("available") is available]
                if mine and theirs:
                    assert_same_schema(mine[0], theirs[0], f"{path}[available={available}]")
        elif actual and expected:
            assert_same_schema(actual[0], expected[0], f"{path}[0]")


@pytest.fixture(scope="module")
def state():
    rows = [
        # Como COMP_0007 en el fixture: sin ERP, deuda pequeña, ámbar; cut_outflow alcanza 70, debt_service_cut no.
        {"company_id": "COMP_A", "level_inflow_sum": 540000., "window_outflow_sum": 730600., "window_debt_service_sum": 32400.,
         "reconstructed_cash": 25000., "tx_outflow_ma3": 121766.7, "momentum_adjustment": -4.8, "score_reason": "trend_unavailable"},
        # Con ERP y caja: las cinco palancas disponibles, ap_on_time con factibilidad.
        {"company_id": "COMP_B", "level_inflow_sum": 600000., "window_outflow_sum": 500000., "window_debt_service_sum": 120000.,
         "ap_delay_w": 20., "ap_delay_count_w": 12., "ar_delay_w": 40., "ar_delay_count_w": 8., "reconstructed_cash": 90000.,
         "tx_outflow_ma3": 80000., "inv_ap_overdue_amount": 8000., "inv_ap_due_30_amount": 5000., "inv_ap_due_60_amount": 2000.},
        {"company_id": "COMP_C", "score_reason": "insufficient_window_history"},
    ]
    return make_group_state(rows, reference_state=anchor_reference_state(), config=AdvisorConfig(), group_id="GROUP_TEST")


def test_sensitivity_matches_example_fixture_schema(state):
    expected = load("advisor_sensitivity_example.json")
    for company_id in ("COMP_A", "COMP_B"):
        doc = company_sensitivity(state, company_id)
        assert doc["status"] == "sensitivity"
        assert_same_schema(doc, expected)
        assert_same_schema(expected, doc)  # simétrico: el fixture tampoco tiene claves que falten en la salida
    doc = company_sensitivity(state, "COMP_A")
    mine = {lv["lever"]: lv for lv in doc["levers"]}
    theirs = {lv["lever"]: lv for lv in expected["levers"]}
    assert set(mine) == set(theirs) == {"cut_outflow", "raise_inflow", "debt_service_cut", "ap_on_time", "ar_faster"}
    for lever in mine:
        assert mine[lever]["available"] == theirs[lever]["available"]
        assert_same_schema(mine[lever], theirs[lever], f"$.levers[{lever}]")
    assert mine["cut_outflow"]["to_next_tramo"]["reachable"] and not mine["debt_service_cut"]["to_next_tramo"]["reachable"]
    assert mine["cut_outflow"]["slope_now"]["level_per_pct"] == pytest.approx(theirs["cut_outflow"]["slope_now"]["level_per_pct"], abs=1e-3)
    assert mine["cut_outflow"]["to_next_tramo"]["rel_change_needed"] == pytest.approx(theirs["cut_outflow"]["to_next_tramo"]["rel_change_needed"], abs=1e-3)


def test_all_levers_available_document_matches_fixture_lever_schema(state):
    expected = load("advisor_sensitivity_example.json")
    doc = company_sensitivity(state, "COMP_B")
    reference_lever = next(lv for lv in expected["levers"] if lv["available"])
    for lever in doc["levers"]:
        assert lever["available"]
        assert_same_schema(lever, reference_lever, f"$.levers[{lever['lever']}]")
        assert set(lever["grid"][0]) == set(reference_lever["grid"][0])
    ap = next(lv for lv in doc["levers"] if lv["lever"] == "ap_on_time")
    assert isinstance(ap["feasibility"]["feasible_alone"], bool) and isinstance(ap["feasibility"]["cash_needed"], float)


def test_not_scored_matches_fixture_schema(state):
    expected = load("advisor_sensitivity_not_scored.json")
    doc = company_sensitivity(state, "COMP_C")
    assert doc["status"] == "not_scored" and doc["score_reason"] == "insufficient_window_history"
    assert_same_schema(doc, expected)
    assert_same_schema(expected, doc)
    assert doc["levers"] == [] and doc["ranking"] == {"by_pct": [], "by_cash": []} and doc["baseline"]["level"] is None


def test_schema_comparator_detects_differences():
    with pytest.raises(AssertionError):
        assert_same_schema({"a": 1}, {"a": 1, "b": 2})
    with pytest.raises(AssertionError):
        assert_same_schema({"a": "x"}, {"a": 1})
    with pytest.raises(AssertionError):
        assert_same_schema({"a": True}, {"a": 1})
    assert_same_schema({"a": None, "b": 1}, {"a": [1], "b": 2.5})
    assert_same_schema({"a": np.float64(1.0).item()}, {"a": 1})
