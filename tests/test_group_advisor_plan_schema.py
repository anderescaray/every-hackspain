"""Esquema del plan de grupo (spec §8.1): claves y tipos de `build_plan` frente a los fixtures de WP4."""
import json
import math
from pathlib import Path

import pytest

from advisor_fixtures import make_group_state
from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.plan import STATUS_NO_LEVERS, STATUS_PLAN, STATUS_SINGLE, build_plan, plan_to_json

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = AdvisorConfig(fx_rates_to_eur={"EUR": 1.0, "USD": 1.17, "GBP": 0.86}, fx_source="approximate", fx_asof="2026-09-01")
H = CONFIG.horizon_months
GENERATED_AT = "2026-09-19T18:00:00+00:00"
# Diccionarios cuyas claves son datos (ids, monedas, hashes): se compara la estructura del primer valor, no el conjunto de claves.
DATA_KEYED = {"$.evidence", "$.inputs_sha256", "$.plan.cash_committed_by_donor", "$.baseline.consolidated_group_currency_score",
              "$.config.fx_rates_to_eur"}


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def schema_differences(actual, expected, path="$"):
    """Diferencias de claves (conjunto exacto en cada nivel) y de tipos (`None` comodín; int/float intercambiables)."""
    problems = []
    if expected is None or actual is None:
        return problems
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: {type(actual).__name__} en lugar de dict"]
        if path in DATA_KEYED:
            if actual and expected:
                problems += schema_differences(next(iter(actual.values())), next(iter(expected.values())), f"{path}[*]")
            return problems
        if set(actual) != set(expected):
            problems.append(f"{path}: claves distintas {sorted(set(actual) ^ set(expected))}")
        for key in sorted(set(actual) & set(expected)):
            problems += schema_differences(actual[key], expected[key], f"{path}.{key}")
        return problems
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: {type(actual).__name__} en lugar de list"]
        if actual and expected:
            problems += schema_differences(actual[0], expected[0], f"{path}[0]")
        return problems
    kinds = {type(actual), type(expected)}
    if kinds <= {int, float} or len(kinds) == 1:
        return problems
    return [f"{path}: {type(actual).__name__} en lugar de {type(expected).__name__}"]


def assert_native_json(node, path="$"):
    """Solo tipos JSON nativos, sin NaN/inf, floats con ≤ 6 decimales."""
    if isinstance(node, dict):
        for key, value in node.items():
            assert isinstance(key, str), path
            assert_native_json(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            assert_native_json(value, f"{path}[{index}]")
    elif isinstance(node, bool) or node is None or isinstance(node, str):
        return
    elif isinstance(node, int):
        assert type(node) is int, path
    elif isinstance(node, float):
        assert type(node) is float and math.isfinite(node), path
        assert round(node, 6) == node, path
    else:
        raise AssertionError(f"{path}: tipo no nativo {type(node).__name__}")


def donor(cid, cash, currency="EUR", inflow=6e6, outflow=4e6):
    return {"company_id": cid, "currency": currency, "level_inflow_sum": inflow, "window_outflow_sum": outflow, "window_debt_service_sum": 0.,
            "tx_outflow_ma3": outflow / H, "reconstructed_cash": cash, "runway_months": 3.0}


def weak_recipient(cid, cash=1.2e4, runway=0.1, **extra):
    """Deuda (d = 0,3) y AP tardío con caja fiable escasa: receptora de D1 y de P."""
    row = {"company_id": cid, "level_inflow_sum": 1e5, "window_outflow_sum": 1e5 * 1.25 / 0.75, "window_debt_service_sum": 3e4,
           "ap_delay_w": 30., "ap_delay_count_w": 8, "inv_ap_overdue_amount": 6e4, "inv_ap_due_30_amount": 3e4, "inv_ap_due_60_amount": 1.5e4,
           "reconstructed_cash": cash, "runway_months": runway, "tx_outflow_ma3": 1e5 * 1.25 / 0.75 / H}
    row.update(extra)
    return row


@pytest.fixture(scope="module")
def plan_with_steps():
    buffer = 2 * (4e6 / H)
    rows = [donor("COMP_0222", buffer + 4e4), donor("COMP_0415", buffer + 2e5, currency="USD"), weak_recipient("COMP_0738"),
            {"company_id": "COMP_0911", "currency": "EUR", "score_reason": "insufficient_window_history"}]
    state = make_group_state(rows, config=CONFIG, group_id="GROUP_0064", consolidated_scores={"EUR": 63.5, "USD": 90.9})
    return build_plan(state, CONFIG, GENERATED_AT)


def test_plan_with_steps_matches_example_schema(plan_with_steps):
    example = load_fixture("advisor_plan_example.json")
    assert plan_with_steps["status"] == example["status"] == STATUS_PLAN
    assert {s["lever"] for s in plan_with_steps["plan"]["steps"]} == {"D1", "P"}
    assert any(s["amount"]["fx_applied"] is not None for s in plan_with_steps["plan"]["steps"])
    assert schema_differences(plan_with_steps, example) == []
    assert set(plan_with_steps["plan"]["steps"][0]["effects"]) == {"k1", f"k{H}"} == set(example["plan"]["steps"][0]["effects"])
    assert plan_with_steps["assumptions"][:3] == example["assumptions"][:3] and plan_with_steps["limitations"] == example["limitations"]
    assert plan_with_steps["assumptions"][3] == example["assumptions"][3]
    assert plan_with_steps["config"]["fractions"] == example["config"]["fractions"]
    assert plan_with_steps["generated_at"] == GENERATED_AT and plan_with_steps["month"] == "2026-08-01"
    assert_native_json(plan_with_steps)
    text = plan_to_json(plan_with_steps)
    assert json.loads(text) == plan_with_steps
    json.dumps(plan_with_steps, allow_nan=False)


def test_no_feasible_levers_matches_fixture_schema():
    rows = [{"company_id": "COMP_0301", "level_inflow_sum": 6e6, "window_outflow_sum": 4e6, "window_debt_service_sum": 0., "tx_outflow_ma3": 4e6 / H},
            weak_recipient("COMP_0302", cash=9e4, runway=1.1, tx_outflow_ma3=1e5), weak_recipient("COMP_0303", cash=4e4, runway=0.5)]
    state = make_group_state(rows, config=CONFIG, group_id="GROUP_0131", consolidated_scores={"EUR": 58.9})
    plan = build_plan(state, CONFIG, GENERATED_AT)
    fixture = load_fixture("advisor_plan_no_levers.json")
    assert plan["status"] == fixture["status"] == STATUS_NO_LEVERS
    assert plan["plan"]["steps"] == [] and plan["rejected_alternatives"] == [] and plan["certificate"]["checked"] is False
    assert plan["diagnosis"]["unexplained_ap_delays"] and plan["levers_evaluated"]
    assert schema_differences(plan, fixture) == []
    assert_native_json(plan)


def test_single_subsidiary_matches_fixture_schema():
    state = make_group_state([donor("COMP_0555", 9.5e4)], config=CONFIG, group_id="GROUP_0200", consolidated_scores={"EUR": 74.0})
    plan = build_plan(state, CONFIG, GENERATED_AT)
    fixture = load_fixture("advisor_plan_single.json")
    assert plan["status"] == fixture["status"] == STATUS_SINGLE
    assert plan["plan"]["stopped_because"] == fixture["plan"]["stopped_because"] == "single_subsidiary"
    assert plan["levers_evaluated"] == [] and plan["plan"]["steps"] == []
    assert schema_differences(plan, fixture) == []
    assert_native_json(plan)


def test_schema_comparator_detects_missing_and_extra_keys():
    example = load_fixture("advisor_plan_example.json")
    broken = json.loads(json.dumps(example))
    del broken["coverage"]["currencies"]
    broken["plan"]["steps"][0]["extra"] = 1
    broken["baseline"]["min_level"] = "38.1"
    problems = schema_differences(broken, example)
    assert any("$.coverage" in p for p in problems) and any("$.plan.steps[0]" in p for p in problems)
    assert any("$.baseline.min_level" in p for p in problems)
    assert schema_differences(example, example) == []
