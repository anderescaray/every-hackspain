"""Resumen determinista de empresa (assessment + summary) con redacción LLM opcional anclada.

El pipeline calcula los hechos; este módulo solo redacta. Sin API key (o si el anclaje falla)
se sirve la plantilla. El LLM nunca calcula un número.

Dos modos de LLM, ambos validados con `validate_grounding`:
  - `company_brief(..., completer=...)`: parafrasea las plantillas (assessment y summary).
  - `compose_summary(detail, ...)`: escribe las viñetas leyendo el informe completo de la ficha.
El export usa el segundo para el resumen bajo el Health Score.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from xray.group_advisor.grounding import collect_numbers, extract_numbers, validate_grounding
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


# ---------------------------------------------------------------------------
# Viñetas compuestas a partir del informe completo de la ficha (no paráfrasis)
# ---------------------------------------------------------------------------

REPORT_SYSTEM_PROMPT = """Eres el analista de Embat Pulse. Recibes el informe completo de UNA empresa en JSON (todo lo que la ficha muestra: Health Score y sus dimensiones, trayectoria, historia mensual, factores del cambio con su impacto en puntos, origen de la caja con sus importes y la confianza del análisis) y un resumen de referencia generado por plantilla.
Tu tarea: escribir las viñetas del resumen ejecutivo que va debajo del Health Score. No parafrasees la plantilla: léela como referencia y escribe TU resumen a partir del informe, eligiendo lo que de verdad explica el estado de esta empresa.
Reglas cerradas:
1. Usa únicamente números e identificadores que aparezcan en el JSON. No calcules, no sumes, no restes, no estimes, no redondees distinto. Si quieres decir una variación, usa una que ya esté en el JSON.
2. Entre 3 y 4 viñetas, UNA por línea, separadas por salto de línea. Sin guiones, sin numeración, sin títulos, sin markdown.
3. Cada viñeta es una frase corta y concreta, en castellano, tono ejecutivo. Nada de relleno ni de consejos genéricos.
4. No repitas el Health Score como cifra suelta (ya se muestra al lado) ni hables de cobertura, confianza o «provisional» (eso va en su propio bloque).
5. Formato castellano: miles con punto y decimales con coma («1.234,5»), con el código de moneda tras el importe. Puedes redondear un importe a euros enteros, a miles o a millones; a nada más.
6. La dirección la pones con las palabras (sube, baja, resta, aporta, mejora, empeora) y tiene que coincidir con el signo del número o con el campo `direction`/`trajectory` del informe. Nunca escribas «resta -4,3»: o el signo o el verbo, no los dos.
7. Prioriza: de dónde sale la caja y si el negocio la genera, qué factor ha movido el score y en qué dirección, qué dice la trayectoria, y cualquier dependencia o concentración relevante del informe.
8. Si un dato no está en el JSON, no lo completes ni lo insinúes: omítelo. No prometas predicciones, no recomiendes acciones, no hables de impago ni de solvencia.
Tu salida se valida automáticamente: cualquier número o identificador que no exista en el informe la descarta y se sirve la plantilla."""

REPORT_MIN_BULLETS = 2
REPORT_MAX_BULLETS = 4
REPORT_MAX_BULLET_CHARS = 240


def build_report_facts(detail: dict) -> dict:
    """Informe podado que se entrega al LLM: la ficha entera menos lo pesado o hipotético.

    Se quitan las filas de evidencia (ruido y tamaño), los escenarios del simulador (son
    hipótesis, no estado observado) y el propio `summary` (va aparte como referencia), y se
    recortan los flujos por cuenta. Todo lo que queda es anclaje válido para `validate_grounding`.
    """
    doc = {k: v for k, v in detail.items()
           if k not in ("evidence", "simulation", "summary", "schema_version", "source")}
    cash = doc.get("cash_truth")
    if isinstance(cash, dict):
        doc["cash_truth"] = {k: v for k, v in cash.items() if k != "account_flows"}
    for key in ("alerts", "time_borrowed"):
        value = doc.get(key)
        if not value or (isinstance(value, dict) and not any(value.values())):
            doc.pop(key, None)
    return doc


def _presentation_forms(value: float) -> set:
    """Formas en que la ficha ya muestra un importe: exacto, sin céntimos, en miles y en millones.

    `money()` del frontend imprime «1,2 M€» donde el dato es 1.234.567,89, así que el resumen
    tiene que poder decir lo mismo. Solo se derivan del valor real; no se acepta ningún otro.
    """
    forms = {value, round(value, 1), float(round(value))}
    if abs(value) >= 1000:
        forms.add(float(round(value, -3)))
        forms.add(round(value / 1000, 1))
    if abs(value) >= 100_000:
        forms.add(round(value / 1_000_000, 1))
        forms.add(round(value / 1_000_000, 2))
    return forms


def _anchor_doc(doc: dict) -> dict:
    """Informe más las magnitudes sin signo y los redondeos de presentación de sus propios números.

    Dos permisos, los dos acotados al informe y sin crear cifras nuevas:

    - **Signo.** El validador exige el número tal cual. En castellano la dirección la lleva el
      verbo («resta 4,3 puntos», «cae 45.000 EUR»), así que exigir «-4,3» obligaría a escribir
      mal; se aceptan los valores absolutos y la regla 5 del prompt obliga a que el verbo
      concuerde con el signo o con `direction`/`trajectory`, que el validador no comprueba.
    - **Redondeo.** Un importe del informe lleva céntimos y ningún resumen ejecutivo los escribe.
      Se aceptan las formas de `_presentation_forms`, las mismas que ya pinta la ficha.

    Lo que sigue prohibido es lo importante: cualquier número que no salga de un valor del
    informe —una variación calculada, un porcentaje deducido, una cifra recordada— lo tumba.
    """
    anchors = set()
    for number in collect_numbers(doc):
        anchors |= _presentation_forms(number)
        anchors |= _presentation_forms(abs(number))
    return {**doc, "_presentation_anchors": sorted(anchors)}


def _clean_bullets(text: str) -> list:
    """Normaliza la salida del LLM a viñetas: una por línea, sin marcadores ni Health Score suelto."""
    bullets = []
    for raw in str(text).split("\n"):
        line = raw.strip()
        line = re.sub(r"^(?:[-•*•]|\d+[.)])\s+", "", line)
        line = line.strip().strip("*").strip()
        if not line or len(line) > REPORT_MAX_BULLET_CHARS:
            continue
        if re.match(r"^(Health Score|Resumen|Viñetas)\b", line, flags=re.IGNORECASE):
            continue
        if line not in bullets:
            bullets.append(line)
    return bullets[:REPORT_MAX_BULLETS]


def compose_summary(detail: dict, template_summary: str, completer) -> tuple:
    """Viñetas escritas por el LLM sobre el informe completo. Devuelve `(texto, origen, fallback)`.

    Cualquier fallo —red, respuesta vacía, formato o un número que no esté en el informe—
    sirve la plantilla determinista. El LLM nunca calcula.
    """
    if completer is None:
        return template_summary, "template", False
    doc = build_report_facts(detail)
    user = "\n".join([
        "Informe de la empresa (única fuente de hechos):",
        json.dumps(doc, ensure_ascii=False, sort_keys=True, default=str),
        "",
        "Resumen de referencia generado por plantilla (no lo copies; es solo el suelo de calidad):",
        template_summary,
        "",
        f"Escribe entre {REPORT_MIN_BULLETS + 1} y {REPORT_MAX_BULLETS} viñetas, una por línea, solo con hechos del informe.",
    ])
    try:
        text = completer.complete(REPORT_SYSTEM_PROMPT, user)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("respuesta vacía del completer")
    except Exception:
        return template_summary, "template", True
    bullets = _clean_bullets(text)
    if len(bullets) < REPORT_MIN_BULLETS:
        return template_summary, "template", True
    candidate = "\n".join(bullets)
    if not validate_grounding(candidate, _anchor_doc(doc)).ok:
        return template_summary, "template", True
    return candidate, "llm", False
