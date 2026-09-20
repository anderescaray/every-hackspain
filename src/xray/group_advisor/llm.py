"""Adaptador LLM con validador de anclaje y caída a plantilla (spec §9.3).

Sin proveedor real ni red: `Completer` es un protocolo (`complete(system, user) -> str`) que WP6
implementará; aquí solo se construye el prompt, se valida la respuesta con `validate_grounding` y,
si falla o el completer lanza, se sirve la plantilla determinista. El LLM nunca calcula.
"""
import json
from dataclasses import dataclass
from typing import Protocol

from xray.group_advisor.grounding import GroundingResult, validate_grounding
from xray.group_advisor.narrative import render_plan, render_sensitivity
from xray.group_advisor.qa import PLAN_METHOD, SENSITIVITY_METHOD, answer, not_in_analysis


class Completer(Protocol):
    def complete(self, system: str, user: str) -> str: ...


SYSTEM_PROMPT = """Eres el redactor del advisor de tesorería de Embat X-Ray. Recibes un JSON producido por un motor determinista y una plantilla canónica ya redactada a partir de él. Reglas cerradas:
1. Usa únicamente números que aparezcan literalmente en el JSON (o una fracción del JSON expresada como porcentaje). No calcules, no sumes, no redondees de forma distinta, no estimes.
2. No propongas acciones fuera de `plan.steps` o de `levers`; no cambies importes, fracciones, pasos ni papeles de donante/receptora.
3. Cita los ids de evidencia (`ev_xxxx`) cuando menciones un dato que los tenga; nombra las filiales por su `company_id` y el grupo por su `group_id`.
4. Todo importe convertido va acompañado de su importe original y del tipo de cambio aplicado.
5. Escribe en castellano, con separador de miles «.» y decimal «,», y con el código de moneda tras cada importe.
6. Mantén el aviso «escenario mecánico bajo supuestos explícitos»: no es una recomendación ejecutable ni una predicción.
7. Si te preguntan por algo que no está en el JSON, responde exactamente: «Ese dato no forma parte del análisis de {entidad} para {mes}.»
8. No inventes salud financiera ni tranquilices por falta de datos: si un dato falta, dilo con su motivo.
Tu salida se valida automáticamente: cualquier número o identificador que no exista en el JSON hace que se descarte y se sirva la plantilla."""


@dataclass
class NarrativeResult:
    text: str
    source: str  # "llm" | "template"
    grounding: GroundingResult
    fallback: bool


def _canonical(doc, mode, intent, args, fmt):
    if mode == "qa":
        return answer(doc, intent, **args) if intent else not_in_analysis(doc)
    method = doc.get("method")
    if method == PLAN_METHOD:
        return render_plan(doc, fmt)
    if method == SENSITIVITY_METHOD:
        return render_sensitivity(doc, fmt)
    raise ValueError(f"documento sin `method` reconocido: {method!r}")


def build_user_prompt(doc, template, mode="paraphrase", question=None):
    """Mensaje de usuario: JSON serializado, plantilla canónica de referencia y, en `qa`, la pregunta."""
    parts = ["JSON del motor (única fuente de hechos):", json.dumps(doc, ensure_ascii=False, sort_keys=True),
             "", "Plantilla canónica (referencia; puedes parafrasearla sin alterar ningún dato):", template, ""]
    if mode == "qa":
        parts += ["Pregunta del usuario:", question or "(sin pregunta)", "",
                  "Responde solo con hechos del JSON; si no están, usa la frase fija."]
    else:
        parts.append("Parafrasea la plantilla manteniendo sus secciones, todos sus números e identificadores.")
    return "\n".join(parts)


def llm_render(doc, completer, mode="paraphrase", question=None, intent=None, fmt="markdown", **args):
    """Paráfrasis o Q&A vía `completer`, validada con `validate_grounding`; plantilla si falla o lanza."""
    if mode not in ("paraphrase", "qa"):
        raise ValueError(f"mode debe ser 'paraphrase' o 'qa', no {mode!r}")
    template = _canonical(doc, mode, intent, args, fmt)
    return grounded_paraphrase(doc, template, completer, system_prompt=SYSTEM_PROMPT, mode=mode, question=question)


def grounded_paraphrase(doc, template, completer, system_prompt=None, mode="paraphrase", question=None):
    """Paráfrasis genérica: el LLM solo reescribe `template` anclado a `doc`; si falla, devuelve la plantilla."""
    system = system_prompt or SYSTEM_PROMPT
    user = build_user_prompt(doc, template, mode, question)
    try:
        text = completer.complete(system, user)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("respuesta vacía del completer")
    except Exception:
        return NarrativeResult(template, "template", validate_grounding(template, doc), True)
    grounding = validate_grounding(text, doc)
    if grounding.ok:
        return NarrativeResult(text, "llm", grounding, False)
    return NarrativeResult(template, "template", grounding, True)
