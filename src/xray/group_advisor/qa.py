"""Q&A determinista sobre el JSON del plan o de la sensibilidad (spec §9.2).

Cada intención lee solo las rutas de la tabla §9.2 y compone la respuesta con `fmt_num`; no
calcula nada. Intención desconocida, documento sin ese dato o intención del otro ámbito devuelven
la frase fija `NOT_IN_ANALYSIS`.
"""
from xray.group_advisor.narrative import (COMPONENT_ES, CONSTRAINT_ES, REASON_ES, ROLE_ES, TRAMO_ES, _label,
                                          _tramo_target_name, fmt_num, fmt_pct, tramo_sentence)

INTENTS = ("why_not_more", "why_not_pair", "what_changes_for", "what_is_assumed", "what_data_missing",
           "is_it_optimal", "what_moves_most", "how_to_reach_tramo", "group_role")
PLAN_METHOD, SENSITIVITY_METHOD = "group_treasury_advisor_v1", "company_sensitivity_v1"
NOT_IN_ANALYSIS = "Ese dato no forma parte del análisis de {entity} para {month}."


def _kind(doc):
    method = doc.get("method")
    return "plan" if method == PLAN_METHOD else "sensitivity" if method == SENSITIVITY_METHOD else None


def _entity(doc):
    return doc.get("group_id") if _kind(doc) == "plan" else doc.get("company_id")


def not_in_analysis(doc):
    """Frase fija de la spec para intención no soportada o dato inexistente."""
    return NOT_IN_ANALYSIS.format(entity=_entity(doc) or "la entidad", month=str(doc.get("month") or "n/d")[:7])


def _join(lines):
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------- plan

def _why_not_more(doc, recipient=None, **_):
    if recipient is None:
        return not_in_analysis(doc)
    lines = []
    for step in doc.get("plan", {}).get("steps", []):
        if step.get("recipient") == recipient:
            constraints = ", ".join(_label(CONSTRAINT_ES, c) for c in step.get("binding_constraints", [])) or "ninguna"
            lines.append(f"Paso {fmt_num(step['step'], 0)} ({step['lever']}, desde {step['donor']}): restricción activa "
                         f"{constraints}; fracción aplicada {fmt_pct(step.get('fraction'))}.")
    for lv in doc.get("levers_evaluated", []):
        if lv.get("recipient") == recipient and not lv.get("feasible"):
            lines.append(f"{lv['lever']} desde {lv['donor']} no factible: {_label(REASON_ES, lv.get('reason'))}.")
    return _join(lines) if lines else not_in_analysis(doc)


def _why_not_pair(doc, donor=None, recipient=None, **_):
    if donor is None or recipient is None:
        return not_in_analysis(doc)
    lines = []
    for alt in doc.get("rejected_alternatives", []):
        if alt.get("donor") == donor and alt.get("recipient") == recipient:
            delta = alt.get("delta_utility_k6")
            suffix = f" (ΔG en régimen {fmt_num(delta, 2)})" if delta is not None else ""
            lines.append(f"{alt['lever']}: {_label(REASON_ES, alt.get('reason'))}{suffix}.")
    for lv in doc.get("levers_evaluated", []):
        if lv.get("donor") == donor and lv.get("recipient") == recipient and lv.get("reason"):
            line = f"{lv['lever']} evaluada: {_label(REASON_ES, lv['reason'])}."
            if line not in lines:
                lines.append(line)
    return _join(lines) if lines else not_in_analysis(doc)


def _what_changes_for(doc, company_id=None, **_):
    subs = {s["company_id"]: s for s in doc.get("baseline", {}).get("subsidiaries", [])}
    if company_id not in subs:
        return not_in_analysis(doc)
    sub = subs[company_id]
    lines = [f"{company_id}: nivel actual {fmt_num(sub.get('level'))} ({TRAMO_ES.get(sub.get('tramo'), sub.get('tramo'))})."]
    for step in doc.get("plan", {}).get("steps", []):
        for role, label in (("recipient", "receptora"), ("donor", "donante")):
            if step.get(role) != company_id:
                continue
            k1, k6 = step["effects"]["k1"][role], step["effects"]["k6"][role]
            lines.append(f"Paso {fmt_num(step['step'], 0)} ({step['lever']}, {label}): nivel {fmt_num(k1['level_before'])} → "
                         f"{fmt_num(k1['level_after'])} al próximo cierre (k=1) y {fmt_num(k6['level_before'])} → "
                         f"{fmt_num(k6['level_after'])} en régimen (k=6).")
    if len(lines) == 1:
        lines.append("No participa en ningún paso del plan.")
    return _join(lines)


def _is_it_optimal(doc, **_):
    cert = doc.get("certificate")
    if not cert:
        return not_in_analysis(doc)
    if not cert.get("checked"):
        return ("No se calculó certificado: el greedy determinista no garantiza el óptimo global. "
                f"Utilidad alcanzada {fmt_num(cert.get('greedy_utility'))}.")
    return (f"Certificado por enumeración: mejor acción única {fmt_num(cert.get('best_single_utility'))}, mejor par "
            f"compatible {fmt_num(cert.get('best_pair_utility'))}, greedy {fmt_num(cert.get('greedy_utility'))}; brecha "
            f"{fmt_num(cert.get('greedy_gap'), 2)}. Sin garantía de óptimo global más allá de pares.")


def _what_data_missing_plan(doc):
    cov, diag = doc.get("coverage", {}), doc.get("diagnosis", {})
    lines = [f"Filiales {fmt_num(cov.get('subsidiaries'), 0)}: sin nivel {fmt_num(cov.get('not_scored'), 0)}; con caja "
             f"reconstruida fiable {fmt_num(cov.get('with_reliable_cash'), 0)}; con componente de deuda "
             f"{fmt_num(cov.get('with_debt_component'), 0)}; con componente de pagos (AP) {fmt_num(cov.get('with_ap_component'), 0)}."]
    for item in diag.get("unexplained_ap_delays", []):
        lines.append(f"{item.get('company_id')}: {item.get('note') or 'retraso AP no explicado por liquidez'}.")
    for flag in diag.get("structural_flags", []):
        lines.append(f"{flag.get('company_id')} ({_label(COMPONENT_ES, flag.get('component'))}): {flag.get('note')}.")
    for alt in doc.get("rejected_alternatives", []):
        if alt.get("reason") and ("unavailable" in alt["reason"] or "unreliable" in alt["reason"]):
            lines.append(f"{alt['lever']} {alt['donor']} → {alt['recipient']}: {_label(REASON_ES, alt['reason'])}.")
    return _join(lines)


# -------------------------------------------------------------------------------------- sensibilidad

def _what_data_missing_sens(doc):
    lines = [f"{lv['lever']}: {_label(REASON_ES, lv.get('reason'))}." for lv in doc.get("levers", []) if not lv.get("available")]
    return _join(lines) if lines else "Todas las palancas son evaluables."


def _what_moves_most(doc, by="pct", **_):
    if by not in ("pct", "cash"):
        return not_in_analysis(doc)
    ranking = doc.get("ranking", {}).get(f"by_{by}", [])
    slopes = {lv["lever"]: lv.get("slope_now", {}) for lv in doc.get("levers", []) if lv.get("available")}
    if not ranking:
        return not_in_analysis(doc)
    key, unit = ("level_per_pct", "por cada 1 % de cambio relativo") if by == "pct" else ("level_per_10k", "por cada 10.000 de equivalente de caja")
    lines = [f"Ranking {unit} (k=6):"]
    for lid in ranking:
        lines.append(f"- {lid}: {fmt_num(slopes.get(lid, {}).get(key), 2)} puntos de nivel {unit}.")
    return _join(lines)


def _how_to_reach_tramo(doc, **_):
    if not any(lv.get("available") for lv in doc.get("levers", [])):
        return not_in_analysis(doc)
    lines = [tramo_sentence(doc)]
    target = doc.get("next_tramo_target")
    if target is None:  # ya en el tramo más alto: nada que «no alcanzar»
        return _join(lines)
    tramo = _tramo_target_name(target)
    for lv in doc.get("levers", []):
        tnt = lv.get("to_next_tramo")
        if lv.get("available") and tnt and not tnt.get("reachable"):
            lines.append(f"- {lv['lever']} no alcanza {tramo} por sí sola dentro de los límites evaluados.")
    return _join(lines)


def _group_role(doc, **_):
    ctx = doc.get("group_context") or {}
    if ctx.get("has_group_plan") is None:
        return not_in_analysis(doc)
    if not ctx.get("has_group_plan"):
        return f"{doc.get('company_id')} no forma parte de ningún plan de grupo para {str(doc.get('month') or 'n/d')[:7]}."
    steps = ", ".join(fmt_num(s, 0) for s in ctx.get("steps") or []) or "ninguno"
    return f"Papel de {doc.get('company_id')} en el plan de grupo {doc.get('group_id')}: {_label(ROLE_ES, ctx.get('role'))}; pasos {steps}."


# ------------------------------------------------------------------------------------------ entrada

def _what_is_assumed(doc, **_):
    lines = [f"- {a}" for a in doc.get("assumptions", [])] + [f"- {l}" for l in doc.get("limitations", [])]
    return _join(lines) if lines else not_in_analysis(doc)


def _what_data_missing(doc, **_):
    return _what_data_missing_plan(doc) if _kind(doc) == "plan" else _what_data_missing_sens(doc)


_HANDLERS = {
    "plan": {"why_not_more": _why_not_more, "why_not_pair": _why_not_pair, "what_changes_for": _what_changes_for,
             "what_is_assumed": _what_is_assumed, "what_data_missing": _what_data_missing, "is_it_optimal": _is_it_optimal},
    "sensitivity": {"what_is_assumed": _what_is_assumed, "what_data_missing": _what_data_missing,
                    "what_moves_most": _what_moves_most, "how_to_reach_tramo": _how_to_reach_tramo, "group_role": _group_role},
}


def answer(doc, intent, **args):
    """Respuesta determinista a una de las `INTENTS`; frase fija si no aplica al documento."""
    handler = _HANDLERS.get(_kind(doc), {}).get(intent)
    if handler is None:
        return not_in_analysis(doc)
    return handler(doc, **args)
