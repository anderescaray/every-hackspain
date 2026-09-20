"""Resumen determinista de empresa + paráfrasis LLM anclada (sin red)."""
from xray.group_advisor.grounding import validate_grounding
from xray.group_advisor.llm import grounded_paraphrase
from xray.product.company_brief import (
    build_brief_facts,
    company_brief,
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
