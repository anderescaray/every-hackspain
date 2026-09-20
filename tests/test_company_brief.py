"""Resumen determinista de empresa + paráfrasis LLM anclada (sin red)."""
from xray.group_advisor.grounding import validate_grounding
from xray.group_advisor.llm import grounded_paraphrase
from xray.product.company_brief import (
    build_brief_facts,
    build_report_facts,
    company_brief,
    compose_summary,
    render_assessment,
    render_summary,
)


class FakeCompleter:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.text


def _facts(**overrides):
    base = build_brief_facts(
        "COMP_0001",
        "GROUP_0001",
        64,
        "deteriorating",
        "provisional",
        "thin_current_month",
        0.35,
        confidence=81,
        delta_vs_prev=-3.2,
        main_driver_label="Margen operativo",
        main_driver_impact=-4.3,
        episode="one_off_dip",
    )
    base.update(overrides)
    return base


def test_templates_ground_and_include_core_facts():
    facts = _facts()
    assessment = render_assessment(facts)
    summary = render_summary(facts)
    assert validate_grounding(assessment, facts).ok
    assert validate_grounding(summary, facts).ok
    assert "Señales de deterioro" in assessment and "dependencia de apoyo" in assessment
    assert "Health Score" not in summary
    assert "35 %" in summary and "-4,3 pts" in summary
    assert "6 meses" in summary and "Bache puntual" in summary
    assert "one_off_dip" not in summary
    assert summary.count("\n") >= 2  # viñetas


def test_summary_bullets_are_clear_spanish():
    facts = build_brief_facts(
        "COMP_0764", "GROUP_0022", 33, "deteriorating", "provisional",
        "optional_components_missing", None,
        main_driver_label="Generación operativa",
        main_driver_impact=-0.5,
        episode="trend_deterioration",
    )
    summary = render_summary(facts)
    lines = summary.split("\n")
    assert lines[0].startswith("La caja del negocio")
    assert "se ve débil" in lines[0]
    assert "empeora de forma sostenida" in lines[1]
    assert "Health Score" not in summary
    assert "solo en el banco" not in summary  # cobertura va en el bloque de confianza
    assert "trend_deterioration" not in summary
    assert validate_grounding(summary, facts).ok


def test_company_brief_without_llm_is_template():
    brief = company_brief(_facts())
    assert brief.assessment_source == "template" and brief.summary_source == "template"
    assert brief.assessment_fallback is False


def test_company_brief_keeps_grounded_llm_paraphrase():
    facts = _facts()
    assessment_t = render_assessment(facts)
    summary_t = render_summary(facts)
    assessment_llm = "Señales de deterioro · evidencia parcial · dependencia de apoyo"
    summary_llm = summary_t.replace("empeora de forma sostenida", "se deteriora de forma sostenida")
    assert validate_grounding(assessment_llm, facts).ok
    assert validate_grounding(summary_llm, facts).ok

    class Sequenced:
        def __init__(self):
            self.n = 0

        def complete(self, system, user):
            self.n += 1
            return assessment_llm if self.n == 1 else summary_llm

    brief = company_brief(facts, completer=Sequenced())
    assert brief.assessment_source == "llm" and brief.assessment == assessment_llm
    assert brief.summary_source == "llm" and "se deteriora de forma sostenida" in brief.summary
    assert brief.assessment_fallback is False and brief.summary_fallback is False


def test_company_brief_rejects_oversized_assessment_paraphrase():
    facts = _facts()
    summary_t = render_summary(facts)
    long_assessment = ("Señales de deterioro. " * 20) + "Health Score no inventado"

    class Sequenced:
        def __init__(self):
            self.n = 0

        def complete(self, system, user):
            self.n += 1
            return long_assessment if self.n == 1 else summary_t

    brief = company_brief(facts, completer=Sequenced())
    assert brief.assessment_source == "template" and brief.assessment_fallback is True
    assert brief.summary_source == "llm"

def test_grounded_paraphrase_falls_back_on_invented_number():
    facts = _facts()
    template = render_summary(facts)
    result = grounded_paraphrase(facts, template, FakeCompleter("Health Score 99: inventado."))
    assert result.fallback is True and result.source == "template" and result.text == template
    assert 99.0 in result.grounding.unmatched_numbers


def test_grounded_paraphrase_accepts_anchored_rewrite():
    facts = _facts()
    template = render_assessment(facts)
    rewrite = "Señales de deterioro con evidencia parcial y dependencia de apoyo"
    result = grounded_paraphrase(facts, template, FakeCompleter(rewrite))
    assert result.source == "llm" and result.fallback is False and result.text == rewrite


def test_stable_without_dependency_omits_support_clause():
    facts = build_brief_facts("COMP_0002", None, 70, "stable", "scored", "ok", 0.1)
    summary = render_summary(facts)
    assert "apoyo intragrupo" not in summary
    assert validate_grounding(summary, facts).ok


def test_label_with_bracket_zero_is_absorbable():
    """Labels tipo «Recorte a [0, 100]» metían un 0 no anclado y tumbaron el export."""
    facts = build_brief_facts(
        "COMP_0141", "GROUP_0001", 100, "improving", "provisional",
        "optional_components_missing", 0.05,
        main_driver_label="Recorte a [0, 100]",
        main_driver_impact=-8.3,
    )
    assert 0.0 in facts["text_anchor_numbers"]
    brief = company_brief(facts)
    assert "Recorte a [0, 100]" in brief.summary
    assert validate_grounding(brief.summary, brief.facts).ok


def test_episode_uses_spanish_label_not_raw_enum():
    facts = build_brief_facts(
        "COMP_0764", "GROUP_0022", 33, "deteriorating", "provisional", "ok", None,
        episode="trend_deterioration",
    )
    assert "deterioro de tendencia" in facts["episode_label"].lower()
    summary = render_summary(facts)
    assert "trend_deterioration" not in summary
    assert "Deterioro de tendencia" in summary
    assert validate_grounding(summary, facts).ok


# --- Viñetas compuestas desde el informe completo de la ficha (sin red) --------------------

def _detail():
    """Ficha reducida con la forma del contrato 2.0 que consume `compose_summary`."""
    return {
        "schema_version": "2.0",
        "source": "generated",
        "company_id": "COMP_0001",
        "group_id": "GROUP_0001",
        "as_of": "2026-08-31",
        "health_score": 64,
        "confidence": 81,
        "trajectory": "deteriorating",
        "assessment": "Señales de deterioro",
        "summary": "plantilla previa",
        "dimensions": {"cash_generation": 58.0, "resilience": 72.0, "debt": 40.0, "momentum": 33.0},
        "history": [{"month": "2026-07-31", "health_score": 71}, {"month": "2026-08-31", "health_score": 64}],
        "drivers": [{"id": "d1", "driver": "Margen operativo", "impact": -4.3, "direction": "negative",
                     "explanation": "Baja el margen de seis meses.", "affected_dimensions": ["cash_generation"],
                     "evidence_refs": ["ev_0001"]}],
        "cash_truth": {
            "period": "marzo–agosto 2026", "headline": "La caja viene del apoyo del grupo",
            "explanation": "El neto operativo es negativo.", "confidence": 81,
            "apparent_net": 120000.0, "total_gross_movement": 980000.0,
            "components": [{"category": "operating", "label": "Generación operativa", "net_amount": -45000.0,
                            "gross_movement": 500000.0, "confidence": 81, "explanation": "Cobros menos pagos.",
                            "evidence_refs": ["ev_0001"]}],
            "account_flows": {"accounts": [{"id": "ACC_1", "label": "muy largo"}]},
            "evidence_summary": ["120 movimientos"], "evidence_refs": ["ev_0001"],
        },
        "evidence": [{"id": "ev_0001", "rows": [{"id": "TX_1", "amount": 999999.0}]}],
        "simulation": {"inputs": [], "scenarios": [{"id": "s1", "health_score": 88}], "methodology": "x"},
        "alerts": [],
        "time_borrowed": {"ar": None, "ap": None},
    }


def test_report_facts_drop_evidence_scenarios_and_keep_the_report():
    doc = build_report_facts(_detail())
    assert "evidence" not in doc and "simulation" not in doc and "summary" not in doc
    assert "alerts" not in doc and "time_borrowed" not in doc
    assert "account_flows" not in doc["cash_truth"]
    assert doc["health_score"] == 64 and doc["drivers"][0]["impact"] == -4.3
    assert doc["cash_truth"]["components"][0]["net_amount"] == -45000.0


def test_compose_summary_keeps_grounded_bullets_from_the_report():
    completer = FakeCompleter(
        "- El neto operativo de la ventana es de -45.000 EUR: la caja no la genera el negocio.\n"
        "2) El Margen operativo resta 4,3 puntos, el mayor cambio del mes.\n"
        "* La puntuación baja de 71 a 64 y la trayectoria es de deterioro.\n"
    )
    text, source, fallback = compose_summary(_detail(), "plantilla", completer)
    assert source == "llm" and fallback is False
    lines = text.split("\n")
    assert len(lines) == 3
    assert not any(line.startswith(("-", "*", "2)")) for line in lines)
    assert "-45.000 EUR" in lines[0]
    # El informe entero viajó en el prompt, no solo los hechos del brief.
    _system, user = completer.calls[0]
    assert "cash_truth" in user and "980000" in user.replace(".0", "")


def test_compose_summary_falls_back_when_the_model_invents_a_number():
    completer = FakeCompleter(
        "La caja operativa cae un 37,5 % interanual.\n"
        "El margen resta 4,3 puntos.\n"
    )
    text, source, fallback = compose_summary(_detail(), "plantilla", completer)
    assert (text, source, fallback) == ("plantilla", "template", True)


def test_compose_summary_falls_back_on_network_error_or_thin_output():
    text, source, fallback = compose_summary(_detail(), "plantilla", FakeCompleter(error=RuntimeError("timeout")))
    assert (text, source, fallback) == ("plantilla", "template", True)
    text, source, fallback = compose_summary(_detail(), "plantilla", FakeCompleter("Una sola viñeta."))
    assert (text, source, fallback) == ("plantilla", "template", True)


def test_compose_summary_without_completer_is_the_template():
    assert compose_summary(_detail(), "plantilla", None) == ("plantilla", "template", False)


def test_compose_summary_accepts_magnitudes_but_not_new_numbers():
    ok = FakeCompleter(
        "El Margen operativo resta 4,3 puntos del Health Score.\n"
        "La generación operativa es negativa: 45.000 EUR de salida neta en la ventana.\n"
        "La trayectoria es de deterioro frente a su propia historia.\n"
    )
    text, source, _ = compose_summary(_detail(), "plantilla", ok)
    assert source == "llm" and "4,3 puntos" in text
    invented = FakeCompleter("El margen resta 4,9 puntos.\nLa caja cae.\n")
    assert compose_summary(_detail(), "plantilla", invented)[1] == "template"


def test_compose_summary_allows_presentation_rounding_only():
    detail = _detail()
    detail["cash_truth"]["components"][0]["net_amount"] = -79979.49
    rounded = FakeCompleter(
        "La generación operativa deja una salida neta de 80.000 EUR en la ventana.\n"
        "El Margen operativo resta 4,3 puntos.\n"
        "La trayectoria es de deterioro.\n"
    )
    assert compose_summary(detail, "plantilla", rounded)[1] == "llm"
    nearby = FakeCompleter(
        "La generación operativa deja una salida neta de 85.000 EUR en la ventana.\n"
        "El Margen operativo resta 4,3 puntos.\n"
        "La trayectoria es de deterioro.\n"
    )
    assert compose_summary(detail, "plantilla", nearby)[1] == "template"


class SequencedCompleter:
    """Devuelve una respuesta distinta por llamada y guarda los prompts recibidos."""

    def __init__(self, *texts):
        self.texts, self.prompts = list(texts), []

    def complete(self, system, user):
        self.prompts.append(user)
        return self.texts[min(len(self.prompts) - 1, len(self.texts) - 1)]


def test_compose_summary_retries_once_naming_the_invented_figures():
    invented = ("El apoyo interno representa el 37 % de las entradas.\n"
                "El margen resta 4,3 puntos.\n"
                "La trayectoria es de deterioro.\n")
    corrected = ("El apoyo interno pesa sobre las entradas del periodo.\n"
                 "El margen resta 4,3 puntos.\n"
                 "La trayectoria es de deterioro.\n")
    completer = SequencedCompleter(invented, corrected)
    text, source, fallback = compose_summary(_detail(), "plantilla", completer)
    assert (source, fallback) == ("llm", False)
    assert "37" not in text
    assert len(completer.prompts) == 2
    # El segundo intento nombra la cifra rechazada en vez de repetir el encargo a ciegas.
    assert "37" in completer.prompts[1] and "no existen en el informe" in completer.prompts[1]


def test_compose_summary_gives_up_after_the_retry():
    completer = SequencedCompleter("El apoyo es del 37 % de las entradas.\nEl margen resta 4,3 puntos.\nDeterioro.\n")
    text, source, fallback = compose_summary(_detail(), "plantilla", completer)
    assert (text, source, fallback) == ("plantilla", "template", True)
    assert len(completer.prompts) == 2  # el original y un único reintento


def test_compose_summary_can_run_without_retries():
    completer = SequencedCompleter("El apoyo es del 37 % de las entradas.\nEl margen resta 4,3 puntos.\nDeterioro.\n")
    assert compose_summary(_detail(), "plantilla", completer, retries=0)[1] == "template"
    assert len(completer.prompts) == 1
