import copy
import json
import re
from pathlib import Path

import pytest

from xray.group_advisor import optimizer as optimizer_module
from xray.group_advisor import plan as plan_module
from xray.group_advisor import sensitivity as sensitivity_module
from xray.group_advisor.grounding import (ALWAYS_ALLOWED, collect_ids, collect_numbers, extract_numbers,
                                          validate_grounding)
from xray.group_advisor.llm import NarrativeResult, SYSTEM_PROMPT, llm_render
from xray.group_advisor.narrative import (CONSTRAINT_ES, PLAN_SECTIONS, REASON_ES, ROLE_ES, SCORE_REASON_ES,
                                          SENSITIVITY_SECTIONS, STOPPED_ES, fmt_num, fmt_pct, render_plan,
                                          render_sensitivity)
from xray.group_advisor.qa import INTENTS, NOT_IN_ANALYSIS, answer
from xray.score_v2 import core as score_core_module

FIXTURES = Path(__file__).parent / "fixtures"
PLAN_FIXTURES = ["advisor_plan_example", "advisor_plan_no_levers", "advisor_plan_single"]
SENS_FIXTURES = ["advisor_sensitivity_example", "advisor_sensitivity_not_scored"]
PLAN_KEYS = {"schema_version", "method", "group_id", "month", "config", "status", "reporting_currency", "coverage",
             "baseline", "diagnosis", "levers_evaluated", "plan", "rejected_alternatives", "certificate", "assumptions",
             "limitations", "evidence", "generated_at", "inputs_sha256"}
SENS_KEYS = {"schema_version", "method", "company_id", "group_id", "currency", "month", "status", "score_reason",
             "baseline", "group_context", "next_tramo_target", "levers", "ranking", "structural_note", "assumptions",
             "limitations", "evidence", "generated_at", "inputs_sha256"}


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def plan():
    return load("advisor_plan_example")


@pytest.fixture(scope="module")
def sens():
    return load("advisor_sensitivity_example")


def headings(text, titles, fmt):
    return [text.index(f"## {t}" if fmt == "markdown" else f"\n{t.upper()}\n") for t in titles]


# ------------------------------------------------------------------------------------------ fixtures

@pytest.mark.parametrize("name", PLAN_FIXTURES)
def test_plan_fixture_schema(name):
    doc = load(name)
    assert set(doc) == PLAN_KEYS and doc["method"] == "group_treasury_advisor_v1"
    assert set(doc["plan"]) == {"steps", "totals", "cash_committed_by_donor", "stopped_because"}
    assert set(doc["coverage"]) == {"subsidiaries", "optimizable", "not_scored", "with_reliable_cash",
                                    "with_debt_component", "with_ap_component", "currencies"}
    for sub in doc["baseline"]["subsidiaries"]:
        assert set(sub) == {"company_id", "currency", "level", "score", "momentum_adjustment", "tramo", "score_status",
                            "score_reason", "components", "signals", "liquidity", "ap"}


@pytest.mark.parametrize("name", SENS_FIXTURES)
def test_sensitivity_fixture_schema(name):
    doc = load(name)
    assert set(doc) == SENS_KEYS and doc["method"] == "company_sensitivity_v1"
    assert set(doc["ranking"]) == {"by_pct", "by_cash"}
    for lever in doc["levers"]:
        expected = {"lever", "type", "component", "available", "quantity", "unit", "current", "direction", "slope_now",
                    "grid", "to_next_tramo", "feasibility", "assumptions", "evidence"}
        assert set(lever) == (expected if lever["available"] else {"lever", "type", "component", "available", "reason"})


def test_plan_example_is_coherent(plan):
    steps = plan["plan"]["steps"]
    assert [s["lever"] for s in steps] == ["D1", "P"] and steps[1]["amount"]["fx_applied"] is not None
    assert plan["plan"]["totals"]["k6"]["group_utility_after"] == steps[-1]["effects"]["k6"]["group_utility_after"]
    assert plan["plan"]["totals"]["k6"]["group_utility_after"] >= plan["baseline"]["group_utility_0_100"]
    for donor, cash in plan["plan"]["cash_committed_by_donor"].items():
        assert cash["donor_ccy"] == pytest.approx(sum(s["amount"]["donor_ccy"] for s in steps if s["donor"] == donor))
    assert any(a.startswith("fx_fixed_rate:") for a in plan["assumptions"])
    assert {a["reason"] for a in plan["rejected_alternatives"]} >= {"recipient_ap_component_unavailable", "donor_buffer"}
    referenced = {ev for s in steps for ev in s["evidence"]}
    assert len(referenced) >= 3 and referenced <= set(plan["evidence"])
    assert plan["coverage"]["subsidiaries"] == 4 and plan["coverage"]["not_scored"] == 1


def test_other_fixtures_are_coherent(sens):
    no_levers, single, not_scored = load("advisor_plan_no_levers"), load("advisor_plan_single"), load("advisor_sensitivity_not_scored")
    assert no_levers["status"] == "no_feasible_levers" and no_levers["plan"]["steps"] == []
    assert no_levers["plan"]["totals"]["k6"]["group_utility_after"] == no_levers["baseline"]["group_utility_0_100"]
    assert {lv["reason"] for lv in no_levers["levers_evaluated"]} >= {"donor_cash_unreliable", "recipient_not_liquidity_constrained"}
    assert single["coverage"]["subsidiaries"] == 1 and single["plan"]["steps"] == []
    unreachable = [lv for lv in sens["levers"] if lv["available"] and not lv["to_next_tramo"]["reachable"]]
    assert unreachable and all(lv["to_next_tramo"]["rel_change_needed"] is None for lv in unreachable)
    assert sens["group_context"] == {"has_group_plan": True, "role": "recipient", "steps": [1]}
    assert not_scored["status"] == "not_scored" and not_scored["levers"] == [] and not_scored["baseline"]["level"] is None


# ----------------------------------------------------------------------------------------- narrativa

@pytest.mark.parametrize("fmt", ["markdown", "text"])
def test_render_plan_sections_in_order(plan, fmt):
    text = render_plan(plan, fmt)
    positions = headings(text, PLAN_SECTIONS, fmt)
    assert positions == sorted(positions)
    assert "escenario mecánico bajo supuestos explícitos" in text.lower()
    assert "asume 100 % de las cuotas de deuda de COMP_0738" in text
    assert "68.445 USD (= 58.500 EUR a 1,17)" in text
    assert "Los importes no cambian, solo la fecha." in text


@pytest.mark.parametrize("name", ["advisor_plan_no_levers", "advisor_plan_single"])
@pytest.mark.parametrize("fmt", ["markdown", "text"])
def test_render_plan_without_plan_uses_status_template(name, fmt):
    text = render_plan(load(name), fmt)
    positions = headings(text, ("Resumen", "Cobertura de datos", "Supuestos y límites"), fmt)
    assert positions == sorted(positions) and "Plan paso a paso" not in text
    if name == "advisor_plan_no_levers":
        assert "COMP_0301: caja reconstruida del donante no fiable" in text
        assert "COMP_0302" in text and "higiene ERP" in text
    else:
        assert "una sola filial puntuada (COMP_0555" in text


@pytest.mark.parametrize("fmt", ["markdown", "text"])
def test_render_sensitivity_sections_in_order(sens, fmt):
    text = render_sensitivity(sens, fmt)
    positions = headings(text, SENSITIVITY_SECTIONS, fmt)
    assert positions == sorted(positions)
    assert "Para pasar a verde:" in text and " o un " in text
    assert "Si las salidas operativas bajaran un 5 %" in text
    assert "Si la cuota mensual de deuda bajara de 5.400 EUR a 5.130 EUR" in text
    assert "debt_service_cut (cuota mensual de deuda) no alcanza verde" in text


def test_render_sensitivity_not_scored():
    text = render_sensitivity(load("advisor_sensitivity_not_scored"))
    assert "## Dónde estás" in text and "## Supuestos y límites" in text and "historial insuficiente" in text
    assert "Qué mueve más" not in text


def test_render_sensitivity_without_group_plan(sens):
    doc = dict(sens, group_context={"has_group_plan": False, "role": "none", "steps": []})
    assert "Papel en el grupo" not in render_sensitivity(doc)


def test_render_rejects_unknown_format(plan):
    with pytest.raises(ValueError):
        render_plan(plan, "html")


def test_fmt_num():
    assert fmt_num(42000.0) == "42.000"
    assert fmt_num(0.078, 3) == "0,078"
    assert fmt_num(57.2) == "57,2"
    assert fmt_num(-0.8, 2) == "-0,8"
    assert fmt_num(1234.5) == "1.234,5"
    assert fmt_num(7020, unit="EUR") == "7.020 EUR"
    assert fmt_num(3, 0) == "3" and fmt_num(1.17, 4) == "1,17"
    assert fmt_num(None) == "n/d" and fmt_num(float("nan")) == "n/d"
    assert fmt_pct(0.05) == "5 %" and fmt_pct(0.0768) == "7,7 %"


# ------------------------------------------------------------------------------------------ anclaje

def test_extract_numbers():
    assert extract_numbers("1.234,5 EUR y 42 % y −0,80") == [1234.5, 42.0, -0.8]
    assert extract_numbers("-0,80; 7.020 EUR; 0,078; 57,2.") == [-0.8, 7020.0, 0.078, 57.2]
    assert extract_numbers("COMP_0738 ev_0001 2026-08-01 6m k=6 entre 40 y 70") == [6.0, 40.0, 70.0]


def test_collect_numbers_and_ids(plan):
    numbers = collect_numbers(plan)
    assert 102900.0 in numbers and 1.17 in numbers and True not in {type(n) is bool for n in numbers}
    ids = collect_ids(plan)
    assert {"GROUP_0064", "COMP_0738", "D1", "P"} <= ids and "COMP_9999" not in ids


@pytest.mark.parametrize("name", PLAN_FIXTURES)
@pytest.mark.parametrize("fmt", ["markdown", "text"])
def test_plan_templates_are_grounded(name, fmt):
    doc = load(name)
    result = validate_grounding(render_plan(doc, fmt), doc)
    assert result.ok, (result.unmatched_numbers, result.unmatched_ids)


@pytest.mark.parametrize("name", SENS_FIXTURES)
@pytest.mark.parametrize("fmt", ["markdown", "text"])
def test_sensitivity_templates_are_grounded(name, fmt):
    doc = load(name)
    result = validate_grounding(render_sensitivity(doc, fmt), doc)
    assert result.ok, (result.unmatched_numbers, result.unmatched_ids)


def test_grounding_rejects_invented_number(plan):
    assert not any(abs(n - 93.7) <= 0.05 or abs(n * 100 - 93.7) <= 0.05 for n in collect_numbers(plan))
    result = validate_grounding("El nivel de COMP_0738 sube 93,7 puntos.", plan)
    assert not result.ok and result.unmatched_numbers == [93.7] and result.unmatched_ids == []


def test_grounding_rejects_invented_id(plan):
    result = validate_grounding("COMP_9999 asume la deuda; nivel 36,9.", plan)
    assert not result.ok and result.unmatched_ids == ["COMP_9999"] and result.unmatched_numbers == []


def test_grounding_accepts_percent_as_fraction_and_whitelist(plan):
    assert validate_grounding("Fracción 75 % en el paso 2; k=6; 10.000 EUR; tramo 40 y 70.", plan).ok
    assert ALWAYS_ALLOWED == frozenset({1, 6, 10000, 100, 40, 70})


# ---------------------------------------------------------------------------------------------- Q&A

@pytest.mark.parametrize("intent,args,expected", [
    ("why_not_more", {"recipient": "COMP_0738"}, "colchón de caja del donante"),
    ("why_not_pair", {"donor": "COMP_0415", "recipient": "COMP_0222"}, "componente de pagos (AP) de la receptora no disponible"),
    ("what_changes_for", {"company_id": "COMP_0738"}, "36,9 → 39"),
    ("what_is_assumed", {}, "fx_fixed_rate: tabla approximate"),
    ("what_data_missing", {}, "sin nivel 1"),
    ("is_it_optimal", {}, "mejor par compatible 87,8"),
])
def test_answer_plan_intents(plan, intent, args, expected):
    text = answer(plan, intent, **args)
    assert expected in text and text != NOT_IN_ANALYSIS.format(entity="GROUP_0064", month="2026-08")
    assert validate_grounding(text, plan).ok


@pytest.mark.parametrize("intent,args,expected", [
    ("what_moves_most", {"by": "pct"}, "raise_inflow: 0,48"),
    ("what_moves_most", {"by": "cash"}, "debt_service_cut: 1,32"),
    ("how_to_reach_tramo", {}, "Para pasar a verde: un 29,7 % menos de salidas operativas"),
    ("group_role", {}, "receptora; pasos 1"),
    ("what_is_assumed", {}, "biseccion por palanca aislada"),
    ("what_data_missing", {}, "ap_on_time: componente de pagos no disponible"),
])
def test_answer_sensitivity_intents(sens, intent, args, expected):
    text = answer(sens, intent, **args)
    assert expected in text
    assert validate_grounding(text, sens).ok


def test_answer_fixed_sentence(plan, sens):
    fixed_plan = "Ese dato no forma parte del análisis de GROUP_0064 para 2026-08."
    fixed_sens = "Ese dato no forma parte del análisis de COMP_0007 para 2026-08."
    assert answer(plan, "what_is_the_weather") == fixed_plan
    assert answer(plan, "what_moves_most", by="pct") == fixed_plan
    assert answer(plan, "why_not_pair", donor="COMP_0001", recipient="COMP_0002") == fixed_plan
    assert answer(plan, "what_changes_for", company_id="COMP_9999") == fixed_plan
    assert answer(sens, "is_it_optimal") == fixed_sens
    assert answer(sens, "what_moves_most", by="magic") == fixed_sens
    assert answer(load("advisor_sensitivity_not_scored"), "how_to_reach_tramo") == \
        "Ese dato no forma parte del análisis de COMP_0911 para 2026-08."
    assert len(INTENTS) == 9 and len(set(INTENTS)) == 9


# ---------------------------------------------------------------------------------------------- LLM

class FakeCompleter:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def complete(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.reply(user) if callable(self.reply) else self.reply


def test_llm_render_falls_back_on_invented_number(plan):
    completer = FakeCompleter("El grupo GROUP_0064 mejora 93,7 puntos con el plan.")
    result = llm_render(plan, completer)
    assert isinstance(result, NarrativeResult) and result.fallback and result.source == "template"
    assert result.text == render_plan(plan) and result.grounding.unmatched_numbers == [93.7]
    system, user = completer.calls[0]
    assert system == SYSTEM_PROMPT and '"group_id": "GROUP_0064"' in user and "## Resumen" in user


def test_llm_render_keeps_grounded_text(sens):
    canonical = render_sensitivity(sens)
    result = llm_render(sens, FakeCompleter(canonical))
    assert result.source == "llm" and not result.fallback and result.text == canonical and result.grounding.ok


def test_llm_render_falls_back_on_exception(plan):
    result = llm_render(plan, FakeCompleter(error=RuntimeError("sin red")))
    assert result.fallback and result.source == "template" and result.text == render_plan(plan)
    result = llm_render(plan, FakeCompleter("   "))
    assert result.fallback and result.source == "template"


def test_llm_render_qa_mode(sens):
    completer = FakeCompleter("La palanca que más mueve por 1 % es raise_inflow con 0,48 puntos.")
    result = llm_render(sens, completer, mode="qa", question="¿Qué mueve más mi nivel?", intent="what_moves_most", by="pct")
    assert result.source == "llm" and "¿Qué mueve más mi nivel?" in completer.calls[0][1]
    invented = llm_render(sens, FakeCompleter("Sube 12,3 puntos."), mode="qa", intent="what_moves_most", by="pct")
    assert invented.fallback and invented.text == answer(sens, "what_moves_most", by="pct")


# ------------------------------------------------------------------------------- WP5b · pulido (GA-07)

def _source(module):
    return Path(module.__file__).read_text(encoding="utf-8")


def engine_reason_codes():
    """Literales de motivo del motor, leídos del código fuente para que un código nuevo sin etiqueta rompa el test.

    - `optimizer.py` / `plan.py`: constantes de módulo `REASON_* = "..."`, `STOP_* = "..."`, `BINDING_* = "..."`.
    - `sensitivity.py`: `LEVER_SPECS[*].unavailable_reason`, tuplas `False, "..."` y `f"{prefix}_..."` (ap/ar).
    Si el motor cambia la forma de declarar los motivos, hay que actualizar estos patrones (la aserción de mínimos
    detecta que el barrido se ha quedado vacío).
    """
    constant = re.compile(r'^(REASON|STOP|BINDING)_[A-Z_]+ = "([a-z_]+)"', re.M)
    found = {"reason": set(), "stop": set(), "binding": set(), "sensitivity": set()}
    for module in (optimizer_module, plan_module):
        for kind, code in constant.findall(_source(module)):
            found[kind.lower()].add(code)
    src = _source(sensitivity_module)
    found["sensitivity"] |= set(re.findall(r'(?:return|\()False, "([a-z_]+)"', src))
    found["sensitivity"] |= {f"{p}_{s}" for s in re.findall(r'\(False, f"\{prefix\}_([a-z_]+)"\)', src) for p in ("ap", "ar")}
    found["sensitivity"] |= {spec.unavailable_reason for spec in sensitivity_module.LEVER_SPECS.values()}
    return found


def test_reason_labels_cover_every_engine_code():
    found = engine_reason_codes()
    assert {"donor_buffer", "recipient_no_ap_delay", "lower_efficiency", "below_min_gain", "fx_rate_unavailable",
            "donor_would_hit_zero_inflow_indicator", "recipient_level_unavailable", "donor_debt_service_unavailable"} <= found["reason"]
    assert {"max_steps_reached", "no_feasible_candidates", "no_candidate_above_min_gain", "single_subsidiary"} <= found["stop"]
    assert {"need_fully_covered", "donor_buffer", "donor_level_floor", "fraction_cap"} <= found["binding"]
    assert {"no_operating_outflow", "no_operating_inflow", "no_debt_service_observed", "debt_without_inflow_indicator",
            "ap_component_unavailable", "ar_component_unavailable", "ap_delay_already_zero", "ar_delay_already_zero"} <= found["sensitivity"]
    assert found["reason"] <= set(REASON_ES), found["reason"] - set(REASON_ES)
    assert found["sensitivity"] <= set(REASON_ES), found["sensitivity"] - set(REASON_ES)
    assert found["stop"] <= set(STOPPED_ES), found["stop"] - set(STOPPED_ES)
    assert found["binding"] <= set(CONSTRAINT_ES), found["binding"] - set(CONSTRAINT_ES)
    # Los códigos usados por los fixtures de WP4 también tienen etiqueta y ninguna etiqueta es el propio código.
    for name in PLAN_FIXTURES:
        doc = load(name)
        used = {lv["reason"] for lv in doc["levers_evaluated"]} | {a["reason"] for a in doc["rejected_alternatives"]}
        assert used - {None} <= set(REASON_ES) and doc["plan"]["stopped_because"] in STOPPED_ES
    assert all(label and label != code for code, label in REASON_ES.items())


def test_score_reason_labels_cover_v2_codes():
    src = _source(score_core_module)
    body = src[src.index("def entry_reasons"):]
    body = body[:body.index("\ndef ")]
    codes = set(re.findall(r', "([a-z_]+)"\)', body))
    codes |= set(re.findall(r'^\s*reason\.loc\[[^\n]*\] = "([a-z_]+)"', src, re.M))
    codes |= set(re.findall(r'reason\.replace\("", "([a-z_]+)"\)', src))
    assert {"no_usable_transactions", "incomplete_group_coverage", "insufficient_window_history", "insufficient_components",
            "thin_current_month", "short_history", "trend_unavailable", "optional_components_missing", "partial_currency",
            "ok"} <= codes
    assert codes <= set(SCORE_REASON_ES), codes - set(SCORE_REASON_ES)
    assert ROLE_ES["both"] == "donante y receptora"


def _step_lines(text, step):
    block = text.split(f"Paso {step} · ")[1].split("\nPaso ")[0]
    return block.splitlines()


def test_donor_sentence_depends_on_lever(plan):
    text = render_plan(plan)
    d1 = next(line for line in _step_lines(text, 1) if "(donante)" in line)
    p = next(line for line in _step_lines(text, 2) if "(donante)" in line)
    assert "señal de deuda 0 → 0,056" in d1
    assert d1.endswith("El donante asume servicio: su nivel pasa de 97,9 a 94 (k=6); además compromete caja.")
    assert "no pierde nivel por transferir" not in d1
    assert p.endswith("El donante no pierde nivel (la salida intragrupo no cuenta como operativa); pierde caja.")
    assert "señal" not in p and "asume servicio" not in p
    assert "null" not in text and "n/d → n/d" not in text
    # D1 con el nivel del donante sin cambio en régimen: «se mantiene en».
    doc = copy.deepcopy(plan)
    doc["plan"]["steps"][0]["effects"]["k6"]["donor"]["level_after"] = 97.9
    line = next(line for line in _step_lines(render_plan(doc), 1) if "(donante)" in line)
    assert "su nivel se mantiene en 97,9 (k=6)" in line and validate_grounding(render_plan(doc), doc).ok


def test_p_step_never_prints_donor_signal(plan):
    doc = copy.deepcopy(plan)
    for k in ("k1", "k6"):  # variante GA-03: `ap_delay_w` del donante antes = después
        doc["plan"]["steps"][1]["effects"][k]["donor"].update(signal_before=12.0, signal_after=12.0)
    text = render_plan(doc)
    p = next(line for line in _step_lines(text, 2) if "(donante)" in line)
    assert "señal" not in p and "12" not in p
    assert validate_grounding(text, doc).ok


def _pair(lever, donor, recipient, reason, need=None, capacity=None, donor_ccy="EUR", recipient_ccy="EUR"):
    return {"lever": lever, "donor": donor, "recipient": recipient, "donor_currency": donor_ccy, "recipient_currency": recipient_ccy,
            "fx_applied": None, "feasible": False, "need_recipient_ccy": need, "donor_capacity": capacity, "reason": reason}


def _infeasible_section(text):
    return text.split("Palancas evaluadas no factibles:")[1].split("\nCertificado")[0]


def test_infeasible_levers_grouped_by_blocking_side(plan):
    doc = copy.deepcopy(plan)
    doc["levers_evaluated"] = [
        _pair("D1", "COMP_0222", "COMP_0738", "donor_buffer", need=102900.0, capacity=0.0),
        _pair("D1", "COMP_0222", "COMP_0415", "donor_buffer", need=5000.0, capacity=0.0, recipient_ccy="USD"),
        _pair("D1", "COMP_0415", "COMP_0738", "donor_cash_unreliable", need=102900.0, capacity=None, donor_ccy="USD"),
        _pair("P", "COMP_0222", "COMP_0415", "recipient_ap_component_unavailable", need=None, capacity=128000.0, recipient_ccy="USD"),
        _pair("P", "COMP_0738", "COMP_0415", "recipient_ap_component_unavailable", need=None, capacity=0.0, recipient_ccy="USD"),
        _pair("P", "COMP_0415", "COMP_0222", "recipient_not_liquidity_constrained", need=0.0, capacity=79666.7, donor_ccy="USD"),
    ]
    doc["baseline"]["subsidiaries"][1]["signals"]["monthly_debt_service"] = 5000.0  # ancla el importe 5.000
    text = render_plan(doc)
    section = _infeasible_section(text)
    lines = [line for line in section.splitlines() if line.startswith("- ")]
    assert lines == [
        "- D1 desde COMP_0222: el colchón de caja del donante no cubre el importe (capacidad 0 EUR) → receptoras: "
        "COMP_0738 (necesidad 102.900 EUR), COMP_0415 (necesidad 5.000 USD).",
        "- D1 desde COMP_0415: caja reconstruida del donante no fiable → receptoras: COMP_0738 (necesidad 102.900 EUR).",
        "- P hacia COMP_0222: la receptora no está restringida por liquidez (retraso AP por política de pago o higiene ERP) "
        "(necesidad 0 EUR) → donantes: COMP_0415.",
        "- P hacia COMP_0415: componente de pagos (AP) de la receptora no disponible → donantes: COMP_0222, COMP_0738.",
    ]  # orden: palanca, lado que bloquea (donante antes que receptora), id
    assert "D1 COMP_0222 → COMP_0738: el colchón" not in section
    assert "Alternativas rechazadas:" in text
    assert "- P COMP_0222 → COMP_0738: el colchón de caja del donante no cubre el importe (ΔG en régimen 1,5)." in text
    result = validate_grounding(text, doc)
    assert result.ok, (result.unmatched_numbers, result.unmatched_ids)
    assert validate_grounding(render_plan(doc, "text"), doc).ok


def test_infeasible_group_truncates_without_counting(plan):
    doc = copy.deepcopy(plan)
    extra = [f"COMP_09{i:02d}" for i in range(1, 11)]
    doc["diagnosis"]["recipient_candidates"] = list(extra)
    doc["levers_evaluated"] = [_pair("D1", "COMP_0222", cid, "donor_buffer", need=None, capacity=0.0) for cid in extra]
    text = render_plan(doc)
    lines = [line for line in _infeasible_section(text).splitlines() if line.startswith("- ")]
    assert len(lines) == 1 and lines[0].endswith(", ".join(extra[:8]) + ", y otras.")
    assert "COMP_0909" not in lines[0] and " 10 " not in lines[0] and "10 receptoras" not in lines[0]
    assert validate_grounding(text, doc).ok
    # Capacidades distintas dentro del grupo no se citan (nunca se suma ni se elige una).
    doc["levers_evaluated"][0]["donor_capacity"] = 12.5
    assert "capacidad" not in _infeasible_section(render_plan(doc))


def test_no_feasible_levers_status_uses_labels():
    doc = copy.deepcopy(load("advisor_plan_no_levers"))
    doc["levers_evaluated"][1]["reason"] = "donor_debt_service_unavailable"
    doc["levers_evaluated"][3]["reason"] = "recipient_no_ap_delay"
    doc["plan"]["stopped_because"] = "max_steps_reached"
    text = render_plan(doc)
    assert "COMP_0302: servicio de deuda del donante no observado en la ventana (no puede asumir cuotas)" in text
    assert "ya paga a proveedores en plazo" in text and "recipient_no_ap_delay" not in text
    assert validate_grounding(text, doc).ok
    plan_doc = copy.deepcopy(load("advisor_plan_example"))
    plan_doc["plan"]["stopped_because"] = "max_steps_reached"
    assert "El plan se detuvo porque se alcanzó el número máximo de pasos." in render_plan(plan_doc)


@pytest.mark.parametrize("role,steps,expected", [
    ("recipient", [1], "En el plan de grupo GROUP_0064, esta filial recibe apoyo en el paso 1."),
    ("donor", [1, 2], "En el plan de grupo GROUP_0064, esta filial actúa como donante en los pasos 1 y 2."),
    ("both", [1, 2, 3], "En el plan de grupo GROUP_0064, esta filial actúa como donante y receptora en los pasos 1, 2 y 3."),
    ("none", [], "El grupo GROUP_0064 tiene plan pero esta filial no participa en ningún paso."),
])
def test_group_role_sentences(sens, role, steps, expected):
    doc = copy.deepcopy(sens)
    doc["group_context"] = {"has_group_plan": True, "role": role, "steps": steps}
    text = render_sensitivity(doc)
    section = text.split("## Papel en el grupo")[1].split("\n## ")[0]
    assert expected in section
    assert ("El detalle del importe" in section) == (role != "none")
    assert validate_grounding(text, doc).ok and validate_grounding(render_sensitivity(doc, "text"), doc).ok
    if role == "both":
        assert "donante y receptora" in answer(doc, "group_role")


@pytest.mark.parametrize("has_plan", [False, None])
def test_group_role_section_hidden_without_plan(sens, has_plan):
    doc = copy.deepcopy(sens)
    doc["group_context"] = {"has_group_plan": has_plan, "role": None, "steps": []}
    text = render_sensitivity(doc)
    assert "Papel en el grupo" not in text and validate_grounding(text, doc).ok


def _with_ap_lever(sens, feasibility, group_context=None):
    doc = copy.deepcopy(sens)
    template = next(lv for lv in doc["levers"] if lv["lever"] == "debt_service_cut")
    ap = copy.deepcopy(template)
    ap.update(lever="ap_on_time", component="payments", quantity="ap_delay_w", unit="days", current=20.0,
              feasibility=feasibility)
    doc["levers"] = [lv for lv in doc["levers"] if lv["lever"] != "ap_on_time"] + [ap]
    if group_context is not None:
        doc["group_context"] = group_context
    return doc


def _ap_feasibility_line(doc):
    text = render_sensitivity(doc)
    result = validate_grounding(text, doc)
    assert result.ok, (result.unmatched_numbers, result.unmatched_ids)
    return next(line for line in text.splitlines() if line.startswith("- ap_on_time: ") and "caja necesaria" in line)


def test_feasibility_covered_by_group_plan(sens):
    base = {"feasible_alone": False, "cash_needed": 90000.0, "own_excess_cash": 0.0, "note": "requiere financiacion"}
    covered = _with_ap_lever(sens, dict(base, covered_by_group_plan=True),
                             {"has_group_plan": True, "role": "recipient", "steps": [1, 2]})
    line = _ap_feasibility_line(covered)  # sin número de paso: `group_context.steps` mezcla D1/P y donante/receptora
    assert line == ("- ap_on_time: cubierta por el plan de grupo (paso de financiación del pago a proveedores en plazo) "
                    "(caja necesaria 90.000 EUR; exceso propio 0 EUR).")
    assert "(paso P)" not in line  # la letra suelta no está en el JSON de sensibilidad y el anclaje la rechazaría
    explicit = _with_ap_lever(sens, dict(base, covered_by_group_plan=True, group_plan_steps=[2]),
                              {"has_group_plan": True, "role": "both", "steps": [1, 2]})
    assert "cubierta por el plan de grupo (paso de financiación del pago a proveedores en plazo, el paso 2)" in _ap_feasibility_line(explicit)
    not_covered = _with_ap_lever(sens, dict(base, covered_by_group_plan=False))
    assert _ap_feasibility_line(not_covered) == ("- ap_on_time: requiere financiación externa o del grupo "
                                                 "(caja necesaria 90.000 EUR; exceso propio 0 EUR).")
    legacy = _with_ap_lever(sens, base)  # sin la clave: se tolera
    assert "requiere financiación externa o del grupo" in _ap_feasibility_line(legacy)
    own = _with_ap_lever(sens, dict(base, feasible_alone=True, own_excess_cash=90000.0, note="alcanzable con caja propia"))
    assert _ap_feasibility_line(own).startswith("- ap_on_time: alcanzable con caja propia (")
    unknown = _with_ap_lever(sens, {"feasible_alone": None, "cash_needed": None, "own_excess_cash": None, "note": "caja no fiable"})
    assert not any(line.startswith("- ap_on_time: ") and "caja necesaria" in line for line in render_sensitivity(unknown).splitlines())


def test_top_tramo_has_nothing_to_reach(sens):
    doc = copy.deepcopy(sens)
    doc["next_tramo_target"] = None
    doc["baseline"].update(level=88.2, tramo="green")
    for lv in doc["levers"]:
        if lv.get("available"):
            lv["to_next_tramo"] = {"target": None, "rel_change_needed": None, "quantity_needed": None, "reachable": False,
                                   "cash_equivalent": None}
    text = render_sensitivity(doc)
    section = text.split("## Cuánto para cambiar de tramo")[1].split("\n## ")[0]
    assert "Ya está en el tramo más alto (verde); no hay siguiente tramo que alcanzar." in section
    assert "n/d" not in section and "no alcanza" not in section and "Siguiente tramo" not in text
    assert validate_grounding(text, doc).ok
    assert answer(doc, "how_to_reach_tramo") == "Ya está en el tramo más alto (verde); no hay siguiente tramo que alcanzar."


def test_coverage_lists_unscored_with_translated_reason(plan):
    doc = copy.deepcopy(plan)
    doc["baseline"]["subsidiaries"][3]["score_reason"] = "no_usable_transactions"
    text = render_plan(doc)
    coverage = text.split("## Cobertura de datos")[1]
    assert "- COMP_0911: sin nivel V2 (sin transacciones utilizables en el mes); no entra en G ni en las acciones." in coverage
    assert "no_usable_transactions" not in text and "insufficient_window_history" not in render_plan(plan)
    assert "- COMP_0911 (EUR): sin nivel (sin transacciones utilizables en el mes)." in text.split("## Diagnóstico")[1]
    assert "1 paso propuesto" not in text and "2 pasos propuestos" in text
    assert validate_grounding(text, doc).ok
    not_scored = copy.deepcopy(load("advisor_sensitivity_not_scored"))
    not_scored["score_reason"] = "incomplete_group_coverage"
    assert "cobertura incompleta" in render_sensitivity(not_scored)
