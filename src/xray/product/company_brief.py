"""Resumen determinista de empresa (assessment + summary) con paráfrasis LLM opcional anclada.

El pipeline calcula los hechos; este módulo solo redacta. Sin API key (o si el anclaje falla)
se sirve la plantilla. El LLM nunca calcula un número.
"""
from __future__ import annotations

from dataclasses import dataclass

from xray.group_advisor.grounding import extract_numbers, validate_grounding
from xray.group_advisor.llm import grounded_paraphrase

TRAJECTORY_ES = {
    "improving": "mejora",
    "deteriorating": "deterioro",
    "stable": "estabilidad",
}
TRAJECTORY_ASSESSMENT = {
    "improving": "Trayectoria de mejora",
    "deteriorating": "Señales de deterioro",
    "stable": "Situación estable",
}
TRAJECTORY_BODY = {
    "improving": "Frente a su propia historia, la empresa mejora de forma sostenida.",
    "deteriorating": "Frente a su propia historia, la empresa empeora de forma sostenida (no es un mes malo aislado).",
    "stable": "No hay una dirección clara frente a su propia historia.",
}
REASON_ES = {
    "optional_components_missing": "Score provisional: no hay facturas del ERP; se basa solo en el banco.",
    "trend_unavailable": "La tendencia todavía no es calculable con el histórico disponible.",
    "thin_current_month": "El mes actual tiene pocos movimientos utilizables; el score es provisional.",
    "short_history": "El histórico es inferior a 6 meses; el score es provisional.",
    "partial_currency": "Parte de la actividad está en otras monedas y no se consolida; el score es provisional.",
    "coverage_account_change": "El conjunto de cuentas activas cambió este mes; la comparación es parcial.",
    "coverage_onboarding": "Primeros meses de actividad observada; el score es provisional.",
    "ok": None,
}

# Códigos V2 (`episode`) → frase en castellano para la UI (nunca el enum crudo).
EPISODE_ES = {
    "trend_deterioration": "Deterioro de tendencia confirmado en varios meses (no es un bache puntual).",
    "trend_improvement": "Mejora de tendencia confirmada en varios meses.",
    "one_off_dip": "Bache puntual de un mes, no una tendencia.",
    "one_off_spike": "Pico puntual de un mes, no una tendencia.",
    "not_sustained_by_current_month": "La dirección del trimestre ya no se sostiene en el mes actual.",
    "none": None,
}

BRIEF_SYSTEM_PROMPT = """Eres el redactor de Embat Pulse. Recibes un JSON de hechos ya calculados y una plantilla canónica en viñetas (una idea por línea).
Reglas cerradas:
1. Usa únicamente números e ids que aparezcan en el JSON. No calcules, no estimes, no inventes.
2. No cambies el Health Score, la trayectoria ni las causas; solo puedes parafrasear.
3. Escribe en castellano claro, tono ejecutivo. Mantén UNA viñeta por línea separada por salto de línea (\\n). No numeres. No juntes todo en un solo párrafo.
4. Máximo 4 viñetas. Cada viñeta: una frase corta. No repitas el Health Score (ya se muestra aparte). No hables de cobertura ni de «score provisional» (eso va junto a la confianza del análisis).
5. Si falta un dato en el JSON, no lo completes: omítelo o di que no está evaluado.
6. No prometas predicciones ni recomendaciones ejecutables.
Tu salida se valida automáticamente: cualquier número o COMP_/GROUP_ que no esté en el JSON la descarta."""



@dataclass(frozen=True)
class CompanyBrief:
    assessment: str
    summary: str
    facts: dict
    assessment_source: str = "template"
    summary_source: str = "template"
    assessment_fallback: bool = False
    summary_fallback: bool = False


def _absorb_text_numbers(facts: dict, *texts) -> dict:
    """Incluye en el JSON de hechos cualquier número que aparezca en texto libre (p. ej. labels).

    Así etiquetas como «Recorte a [0, 100]» no rompen el validador de anclaje.
    """
    extras = list(facts.get("text_anchor_numbers") or [])
    for text in texts:
        if not text:
            continue
        for value in extract_numbers(str(text)):
            extras.append(float(value))
    if extras:
        # lista caminada por collect_numbers; deduplicar preservando orden
        seen = set()
        uniq = []
        for value in extras:
            key = round(value, 6)
            if key not in seen:
                seen.add(key)
                uniq.append(value)
        facts = {**facts, "text_anchor_numbers": uniq}
    return facts


def build_brief_facts(
    company_id,
    group_id,
    health_score,
    trajectory,
    score_status,
    score_reason,
    dependency,
    confidence=None,
    delta_vs_prev=None,
    main_driver_label=None,
    main_driver_impact=None,
    episode=None,
):
    """Documento de hechos para anclaje: incluye enteros de porcentaje usados en el texto."""
    traj = trajectory if trajectory in TRAJECTORY_ES else "stable"
    facts = {
        "company_id": company_id,
        "group_id": group_id,
        "health_score": int(health_score),
        "trajectory": traj,
        "score_status": score_status,
        "score_reason": score_reason,
        "window_months": 6,
    }
    if dependency is not None:
        pct = int(round(float(dependency) * 100))
        facts["support_dependency_ratio"] = float(dependency)
        facts["support_dependency_pct"] = pct
    if confidence is not None:
        facts["confidence"] = int(round(float(confidence)))
    if delta_vs_prev is not None:
        facts["delta_vs_prev"] = round(float(delta_vs_prev), 1)
    if main_driver_label:
        facts["main_driver_label"] = str(main_driver_label)
    if main_driver_impact is not None:
        facts["main_driver_impact"] = round(float(main_driver_impact), 1)
    if episode and str(episode) not in (None, "none", ""):
        code = str(episode)
        facts["episode"] = code
        label = EPISODE_ES.get(code)
        if label:
            facts["episode_label"] = label
    # Números incrustados en label/episodio (p. ej. «[0, 100]») deben ser anclables.
    return _absorb_text_numbers(
        facts,
        facts.get("main_driver_label"),
        facts.get("episode_label"),
        facts.get("episode"),
    )


def _fmt_signed(value: float) -> str:
    """Un decimal en castellano (coma), con signo explícito si es positivo."""
    text = f"{float(value):.1f}".replace(".", ",")
    if value > 0 and not text.startswith("+"):
        return "+" + text
    return text


def render_assessment(facts: dict) -> str:
    parts = [TRAJECTORY_ASSESSMENT[facts["trajectory"]]]
    if facts.get("score_status") == "provisional":
        parts.append("evidencia parcial")
    dep = facts.get("support_dependency_pct")
    if dep is not None and facts.get("support_dependency_ratio", 0) >= 0.3:
        parts.append("dependencia de apoyo")
    return " · ".join(parts)


def render_summary(facts: dict) -> str:
    """Resumen en viñetas (una por línea) para el campo blanco de la ficha.

    No incluye el Health Score (ya está en el bloque hero) ni la nota de cobertura
    (va junto a Confianza / Cobertura de datos en la UI).
    """
    score = facts["health_score"]
    window = facts["window_months"]
    if score < 40:
        cash_line = f"La caja del negocio de los últimos {window} meses se ve débil."
    elif score >= 70:
        cash_line = f"La caja del negocio de los últimos {window} meses se ve sólida."
    else:
        cash_line = f"La caja del negocio de los últimos {window} meses está en zona intermedia."
    bullets = [
        cash_line,
        TRAJECTORY_BODY[facts["trajectory"]],
    ]
    dep = facts.get("support_dependency_pct")
    if dep is not None and facts.get("support_dependency_ratio", 0) >= 0.3:
        bullets.append(
            f"El apoyo intragrupo recibido supone el {dep} % de las entradas identificadas en {window} meses."
        )
    impact = facts.get("main_driver_impact")
    label = facts.get("main_driver_label")
    if label and impact is not None:
        bullets.append(f"Principal cambio reciente: {label} ({_fmt_signed(impact)} pts).")
    episode_label = facts.get("episode_label")
    if episode_label:
        bullets.append(episode_label)
    return "\n".join(bullets)


def company_brief(facts: dict, completer=None) -> CompanyBrief:
    """Plantillas ancladas; si hay `completer`, parafrasea assessment y summary por separado."""
    facts = dict(facts)
    assessment_t = render_assessment(facts)
    summary_t = render_summary(facts)
    facts = _absorb_text_numbers(facts, assessment_t, summary_t)
    for label, text in (("assessment", assessment_t), ("summary", summary_t)):
        grounded = validate_grounding(text, facts)
        if grounded.ok:
            continue
        # Último recurso: quitar el driver de texto libre (labels con rangos tipo [0, 100]).
        if label == "summary" and facts.get("main_driver_label"):
            facts = {k: v for k, v in facts.items() if k not in ("main_driver_label", "main_driver_impact")}
            summary_t = render_summary(facts)
            facts = _absorb_text_numbers(facts, summary_t)
            grounded = validate_grounding(summary_t, facts)
        if not grounded.ok:
            raise ValueError(f"plantilla {label} no anclada: {grounded.unmatched_numbers} / {grounded.unmatched_ids}")
    if completer is None:
        return CompanyBrief(assessment_t, summary_t, facts)

    a = grounded_paraphrase(
        facts, assessment_t, completer, system_prompt=BRIEF_SYSTEM_PROMPT, mode="paraphrase",
    )
    s = grounded_paraphrase(
        facts, summary_t, completer, system_prompt=BRIEF_SYSTEM_PROMPT, mode="paraphrase",
    )
    # Assessment must stay short for the UI hero line.
    if a.source == "llm" and len(a.text) <= 240:
        assessment, assessment_source, assessment_fallback = a.text, "llm", False
    else:
        assessment, assessment_source, assessment_fallback = assessment_t, "template", a.source == "llm" or a.fallback
    return CompanyBrief(
        assessment=assessment,
        summary=s.text,
        facts=facts,
        assessment_source=assessment_source,
        summary_source=s.source,
        assessment_fallback=assessment_fallback,
        summary_fallback=s.fallback,
    )


def maybe_paraphrase_texts(assessment: str, summary: str, facts: dict, completer):
    """Parafrasea textos ya renderizados (p. ej. tras export) manteniendo el mismo anclaje."""
    a = grounded_paraphrase(facts, assessment, completer, system_prompt=BRIEF_SYSTEM_PROMPT)
    s = grounded_paraphrase(facts, summary, completer, system_prompt=BRIEF_SYSTEM_PROMPT)
    return a, s
