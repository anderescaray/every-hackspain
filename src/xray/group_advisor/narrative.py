"""Narrativa determinista del advisor: plantillas en castellano desde los JSON de la spec §8 (§9.1).

`render_plan` y `render_sensitivity` reciben el `dict` del JSON y devuelven texto (`markdown` o
`text`). Ningún número se calcula aquí salvo `fraction * 100` para mostrar porcentajes: todo lo
demás se lee del JSON y pasa por `fmt_num`, de modo que `grounding.validate_grounding` acepta
cualquier render. Tampoco se cuentan contrapartes (las listas largas se truncan con «y otras», sin
«N más»): ese conteo sería un número que no existe en el JSON (el número de pasos sí existe: es el
`step` del último).

Pulido GA-07: etiquetas completas para todos los códigos del motor, frase del donante distinta en
D1 y P, «Palancas evaluadas no factibles» agrupadas por la filial que bloquea, papel en el grupo
(`group_context`) y `feasibility.covered_by_group_plan`.
"""
import math

TRAMO_ES = {"red": "rojo", "amber": "ámbar", "green": "verde", "none": "sin tramo"}
COMPONENT_ES = {"operations": "operaciones", "debt": "deuda", "collections": "cobros", "payments": "pagos"}
LEVER_ES = {
    "D1": "asunción del servicio de deuda", "P": "financiación del pago a proveedores en plazo",
    "O": "asunción de pagos operativos (pagos centralizados)",
    "cut_outflow": "salidas operativas", "raise_inflow": "entradas operativas",
    "debt_service_cut": "cuota mensual de deuda", "ap_on_time": "retraso medio de pago a proveedores",
    "ar_faster": "retraso medio de cobro a clientes",
}
# Motivos por par (`optimizer.py`: `donor_reason`, `recipient_reason`, R1–R5, alternativas), por palanca de
# sensibilidad (`sensitivity.py`: `lever_available`) y motivos de V2. `tests/test_group_advisor_narrative.py`
# comprueba que todo literal de motivo de esos módulos tiene etiqueta aquí.
REASON_ES = {
    # donante (precondiciones)
    "donor_cash_unreliable": "caja reconstruida del donante no fiable",
    "donor_outflow_unavailable": "salidas medias del donante no disponibles",
    "donor_no_inflow": "donante sin entradas operativas en la ventana",
    "donor_debt_service_unavailable": "servicio de deuda del donante no observado en la ventana (no puede asumir cuotas)",
    # donante (restricciones R2/R5 e indicador)
    "donor_buffer": "el colchón de caja del donante no cubre el importe",
    "donor_level_floor": "el nivel del donante bajaría más de lo permitido",
    "donor_would_hit_zero_inflow_indicator": "el donante quedaría con deuda sin entradas operativas (indicador de V2)",
    # receptora
    "recipient_no_debt_service": "la receptora no tiene servicio de deuda en la ventana",
    "recipient_ap_component_unavailable": "componente de pagos (AP) de la receptora no disponible",
    "recipient_no_ap_delay": "la receptora ya paga a proveedores en plazo (retraso AP cero o negativo)",
    "recipient_no_ap_need": "la receptora no tiene AP vencido ni próximo",
    "recipient_no_operating_outflow": "la receptora no tiene pagos operativos observados en la ventana",
    "recipient_margin_unavailable": "el margen operativo de la receptora no es evaluable",
    "recipient_cash_unreliable": "caja reconstruida de la receptora no fiable",
    "recipient_not_liquidity_constrained": "la receptora no está restringida por liquidez (retraso AP por política de pago o higiene ERP)",
    "recipient_level_unavailable": "el nivel de la receptora no es evaluable tras la acción",
    # par / plan
    "fx_rate_unavailable": "moneda sin tipo de cambio en la tabla fija",
    "fraction_cap": "la necesidad de la receptora ya está cubierta al completo",
    "need_fully_covered": "la necesidad de la receptora ya está cubierta al completo",
    "lower_efficiency": "menor eficiencia (puntos de G por caja) que el paso elegido",
    "below_min_gain": "ganancia de utilidad por debajo del mínimo",
    # sensibilidad de empresa (`lever_available`)
    "no_operating_outflow": "sin salidas operativas observadas en la ventana",
    "no_operating_inflow": "sin entradas operativas observadas en la ventana",
    "no_debt_service_observed": "sin servicio de deuda observado en la ventana",
    "debt_without_inflow_indicator": "deuda sin entradas operativas (indicador de V2): la cuota solo actúa al anularse",
    "ap_component_unavailable": "componente de pagos no disponible (retraso AP no observable)",
    "ar_component_unavailable": "componente de cobros no disponible (retraso AR no observable)",
    "ap_delay_already_zero": "ya paga a proveedores en plazo (retraso AP cero o negativo)",
    "ar_delay_already_zero": "ya cobra a clientes en plazo (retraso AR cero o negativo)",
    # alias históricos de los fixtures de WP4
    "no_debt_service": "sin servicio de deuda observado en la ventana",
    "no_outflow": "sin salidas operativas en la ventana",
    "no_inflow": "sin entradas operativas en la ventana",
}
CONSTRAINT_ES = {
    "donor_buffer": "colchón de caja del donante", "need_fully_covered": "necesidad cubierta al completo",
    "donor_level_floor": "suelo de nivel del donante", "fraction_cap": "fracción máxima por receptora",
}
STOPPED_ES = {
    "no_candidate_above_min_gain": "ningún candidato adicional supera la ganancia mínima de utilidad",
    "max_steps_reached": "se alcanzó el número máximo de pasos",
    "max_steps": "se alcanzó el número máximo de pasos",
    "no_feasible_candidates": "no hay candidatos factibles",
    "single_subsidiary": "grupo con una sola filial puntuada",
}
# `score_reason` de V2 (`xray.score_v2.core`): motivos de no puntuación y de estado provisional.
SCORE_REASON_ES = {
    "ok": "puntuada sin reservas",
    "no_usable_transactions": "sin transacciones utilizables en el mes",
    "incomplete_group_coverage": "cobertura incompleta de sociedades con movimientos en el mes",
    "insufficient_window_history": "historial insuficiente en la ventana",
    "insufficient_components": "componentes insuficientes para un nivel",
    "thin_current_month": "mes actual con pocos movimientos (provisional)",
    "short_history": "historial corto (provisional)",
    "trend_unavailable": "trayectoria no disponible",
    "optional_components_missing": "componentes opcionales (facturas) ausentes",
    "partial_currency": "cobertura parcial de moneda",
    "no_operating_flows": "sin flujos operativos en la ventana",
}
ROLE_ES = {"recipient": "receptora", "donor": "donante", "both": "donante y receptora", "none": "sin papel"}
MECHANICAL_NOTICE = ("Escenario mecánico bajo supuestos explícitos: no es una recomendación ejecutable ni una "
                     "predicción; dice qué haría el nivel V2 si los flujos cambiaran como se describe y se sostuvieran.")
PLAN_SECTIONS = ("Resumen", "Diagnóstico", "Plan paso a paso", "Por qué no más / por qué no otras",
                 "Supuestos y límites", "Cobertura de datos")
SENSITIVITY_SECTIONS = ("Dónde estás", "Qué mueve más tu nivel", "Qué mueve más por cada 10.000",
                        "Cuánto para cambiar de tramo", "Papel en el grupo", "Palancas no evaluables",
                        "Supuestos y límites")
FORMATS = ("markdown", "text")


def fmt_num(value, decimals=1, unit=None):
    """Número en castellano: miles «.», decimal «,», sin decimales innecesarios; `unit` como sufijo."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/d"
    rounded = round(float(value), decimals)
    if rounded == 0:
        rounded = 0.0
    text = f"{rounded:,.{decimals}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return f"{text} {unit.strip()}" if unit else text


def fmt_pct(fraction, decimals=1):
    """Fracción 0–1 mostrada como porcentaje (única derivación permitida en la narrativa)."""
    return "n/d" if fraction is None else fmt_num(fraction * 100, decimals, "%")


def _label(table, code):
    return table.get(code, code) if code is not None else "n/d"


def _tramo_name(level, bounds):
    if level is None:
        return TRAMO_ES["none"]
    low, high = bounds
    return TRAMO_ES["red" if level < low else "amber" if level < high else "green"]


def _tramo_target_name(target):
    return "n/d" if target is None else ("verde" if target >= 70 else "ámbar")


def _compose(title, sections, fmt):
    if fmt not in FORMATS:
        raise ValueError(f"fmt debe ser uno de {FORMATS}, no {fmt!r}")
    blocks = [f"# {title}" if fmt == "markdown" else title.upper()]
    for heading, lines in sections:
        head = f"## {heading}" if fmt == "markdown" else heading.upper()
        blocks.append("\n".join([head, ""] + lines if fmt == "markdown" else [head] + lines))
    return "\n\n".join(blocks) + "\n"


def _month(doc):
    return str(doc.get("month") or "n/d")[:7]


def _money(value, ccy, decimals=1):
    return fmt_num(value, decimals, ccy)


def _amount_text(amount, donor_ccy, recipient_ccy):
    """Importe en moneda del donante y, si es cruzado, el original de la receptora y el tipo aplicado."""
    text = _money(amount.get("donor_ccy"), donor_ccy)
    if amount.get("fx_applied") is not None:
        text += f" (= {_money(amount.get('recipient_ccy'), recipient_ccy)} a {fmt_num(amount['fx_applied'], 4)})"
    return text


# ----------------------------------------------------------------------------------------------- plan

def _subsidiaries(plan):
    return {s["company_id"]: s for s in plan.get("baseline", {}).get("subsidiaries", [])}


def _bounds(plan):
    return tuple(plan.get("config", {}).get("tramo_bounds") or (40.0, 70.0))


def _final_levels(plan):
    final = {}
    for step in plan.get("plan", {}).get("steps", []):
        k6 = step.get("effects", {}).get("k6", {})
        for role in ("recipient", "donor"):
            level = k6.get(role, {}).get("level_after")
            if level is not None:
                final[step[role]] = level
    return final


def _business_phrase(step, subs, horizon):
    donor, recipient = step["donor"], step["recipient"]
    donor_ccy = subs.get(donor, {}).get("currency", "")
    recipient_ccy = subs.get(recipient, {}).get("currency", "")
    amount = _amount_text(step["amount"], donor_ccy, recipient_ccy)
    fraction = fmt_pct(step["fraction"])
    if step["lever"] == "D1":
        monthly = _money(subs.get(recipient, {}).get("signals", {}).get("monthly_debt_service"), recipient_ccy)
        return (f"{donor} asume {fraction} de las cuotas de deuda de {recipient} ({monthly} al mes durante "
                f"{fmt_num(horizon, 0)} meses, {amount} comprometido). El servicio externo del grupo no cambia; "
                "se traslada a quien puede llevarlo.")
    if step["lever"] == "P":
        return (f"{donor} financia a {recipient} con {amount} para pagar a proveedores en plazo ({fraction} de la "
                "necesidad de AP vencido y próximo no cubierta por caja). Los importes no cambian, solo la fecha.")
    return f"{donor} → {recipient}: palanca {step['lever']} por {amount}."


def _donor_tail(step, d6):
    """Cierre de la frase del donante: en D1 asume servicio (su nivel sí se mueve); en P solo compromete caja."""
    if step["lever"] != "D1":
        return "El donante no pierde nivel (la salida intragrupo no cuenta como operativa); pierde caja."
    before, after = fmt_num(d6.get("level_before")), fmt_num(d6.get("level_after"))
    movement = f"se mantiene en {after}" if before == after else f"pasa de {before} a {after}"
    return f"El donante asume servicio: su nivel {movement} (k=6); además compromete caja."


def _effects_lines(step, reporting_ccy):
    k1, k6 = step["effects"]["k1"], step["effects"]["k6"]
    r1, r6 = k1["recipient"], k6["recipient"]
    lines = [f"- Efecto en {step['recipient']} (receptora): nivel {fmt_num(r1['level_before'])} → "
             f"{fmt_num(r1['level_after'])} al próximo cierre (k=1) y {fmt_num(r6['level_before'])} → "
             f"{fmt_num(r6['level_after'])} en régimen (k=6); score en régimen {fmt_num(r6.get('score_after'))}; "
             f"componente {_label(COMPONENT_ES, r6.get('component'))}: señal {fmt_num(r6.get('signal_before'), 3)} → "
             f"{fmt_num(r6.get('signal_after'), 3)}."]
    if r6.get("component_dropped"):
        lines.append("- Aviso: el componente de deuda de la receptora deja de estar disponible (sin servicio y sin "
                     "entradas); el nivel se renormaliza.")
    d1, d6 = k1["donor"], k6["donor"]
    donor_line = (f"- Efecto en {step['donor']} (donante): nivel {fmt_num(d1['level_before'])} → "
                  f"{fmt_num(d1['level_after'])} (k=1) y {fmt_num(d6['level_before'])} → {fmt_num(d6['level_after'])} (k=6)")
    # Solo D1 mueve una señal del donante (`debt_service_w`); en P el JSON trae `null` (GA-04) y no se imprime nada.
    if step["lever"] == "D1" and d6.get("signal_after") is not None:
        donor_line += f"; señal de deuda {fmt_num(d6.get('signal_before'), 3)} → {fmt_num(d6['signal_after'], 3)}"
    lines.append(f"{donor_line}. {_donor_tail(step, d6)}")
    lines.append(f"- Utilidad de grupo G: {fmt_num(k6['group_utility_before'])} → {fmt_num(k6['group_utility_after'])} "
                 f"en régimen (k=1: {fmt_num(k1['group_utility_before'])} → {fmt_num(k1['group_utility_after'])}); "
                 f"eficiencia {fmt_num(step.get('efficiency_per_10k'), 2)} puntos de G por cada 10.000 {reporting_ccy}.")
    return lines


def _evidence_lines(ids, evidence):
    lines = []
    for ev_id in ids:
        ev = evidence.get(ev_id)
        if ev is None:
            lines.append(f"- Evidencia {ev_id}: no descrita en el JSON.")
            continue
        lines.append(f"- Evidencia {ev_id}: {ev.get('field')} de {ev.get('company_id')} = {fmt_num(ev.get('value'), 3)} "
                     f"(fuente {ev.get('source')}).")
    return lines


def _summary_plan(plan):
    cov, base, totals = plan["coverage"], plan["baseline"], plan["plan"]["totals"]
    subs, bounds = _subsidiaries(plan), _bounds(plan)
    n_steps = len(plan["plan"]["steps"])
    lines = [f"Grupo {plan['group_id']}, mes {_month(plan)}: {fmt_num(cov['optimizable'], 0)} filiales optimizables "
             f"de {fmt_num(cov['subsidiaries'], 0)}; {fmt_num(n_steps, 0)} {'paso propuesto' if n_steps == 1 else 'pasos propuestos'}.",
             f"Utilidad de grupo G: {fmt_num(base['group_utility_0_100'])} → {fmt_num(totals['k6']['group_utility_after'])} "
             f"en régimen (k=6); al próximo cierre (k=1) {fmt_num(totals['k1']['group_utility_after'])}. "
             f"Nivel mínimo {fmt_num(base['min_level'])} → {fmt_num(totals['k6']['min_level_after'])}."]
    changes = []
    for cid, level in sorted(_final_levels(plan).items()):
        before = subs.get(cid, {})
        if before.get("tramo") and TRAMO_ES.get(before["tramo"]) != _tramo_name(level, bounds):
            changes.append(f"{cid} ({TRAMO_ES.get(before['tramo'], before['tramo'])} → {_tramo_name(level, bounds)}, "
                           f"nivel {fmt_num(before.get('level'))} → {fmt_num(level)})")
    lines.append("Cambian de tramo en régimen: " + ("; ".join(changes) + "." if changes else "ninguna filial."))
    committed = plan["plan"].get("cash_committed_by_donor", {})
    if committed:
        parts = []
        for donor, cash in sorted(committed.items()):
            ccy = subs.get(donor, {}).get("currency", "")
            part = f"{donor} {_money(cash.get('donor_ccy'), ccy)}"
            if ccy and ccy != plan.get("reporting_currency"):
                part += f" (= {_money(cash.get('reporting_ccy'), plan.get('reporting_currency'))})"
            parts.append(part)
        lines.append("Caja comprometida por donante: " + "; ".join(parts) + ".")
    lines.append(MECHANICAL_NOTICE)
    return lines


def _diagnosis_lines(plan):
    diag, subs = plan.get("diagnosis", {}), _subsidiaries(plan)
    lines = []
    bott = diag.get("bottleneck") or {}
    if bott.get("company_id"):
        weakest = ", ".join(_label(COMPONENT_ES, c) for c in bott.get("weakest_components", [])) or "n/d"
        lines.append(f"Cuello de botella: {bott['company_id']} (nivel {fmt_num(bott.get('level'))}); "
                     f"componentes más débiles: {weakest}.")
    for cid, s in sorted(subs.items()):
        if s.get("level") is None:
            lines.append(f"- {cid} ({s.get('currency')}): sin nivel ({_label(SCORE_REASON_ES, s.get('score_reason'))}).")
            continue
        comps = ", ".join(f"{COMPONENT_ES[c]} {fmt_num(s['components'].get(c))}" for c in COMPONENT_ES)
        liq = s.get("liquidity", {})
        cash = (f"caja reconstruida {_money(liq.get('reconstructed_cash'), s.get('currency'))}"
                f"{' (fiable)' if liq.get('reliable') else ' (no fiable)'}")
        lines.append(f"- {cid} ({s.get('currency')}): nivel {fmt_num(s['level'])}, tramo "
                     f"{TRAMO_ES.get(s.get('tramo'), s.get('tramo'))}; componentes {comps}; {cash}.")
    for flag in diag.get("structural_flags", []):
        lines.append(f"- Estructural en {flag.get('company_id')} ({_label(COMPONENT_ES, flag.get('component'))}): "
                     f"{flag.get('note')}")
    for item in diag.get("unexplained_ap_delays", []):
        lines.append(f"- {item.get('company_id')}: {item.get('note') or 'retraso AP no explicado por liquidez'}.")
    donors = ", ".join(diag.get("donor_candidates", [])) or "ninguna"
    recipients = ", ".join(diag.get("recipient_candidates", [])) or "ninguna"
    lines.append(f"Donantes candidatas: {donors}. Receptoras candidatas: {recipients}.")
    return lines


def _steps_lines(plan):
    subs = _subsidiaries(plan)
    horizon = plan.get("config", {}).get("horizon_months", 6)
    evidence = plan.get("evidence", {})
    lines = []
    for step in plan["plan"]["steps"]:
        lines.append(f"Paso {fmt_num(step['step'], 0)} · {step['lever']} ({_label(LEVER_ES, step['lever'])})")
        lines.append(f"- {_business_phrase(step, subs, horizon)}")
        lines.extend(_effects_lines(step, plan.get("reporting_currency", "")))
        constraints = ", ".join(_label(CONSTRAINT_ES, c) for c in step.get("binding_constraints", [])) or "ninguna"
        lines.append(f"- Restricción activa: {constraints}.")
        lines.extend(_evidence_lines(step.get("evidence", []), evidence))
    return lines or ["Sin pasos."]


MAX_LISTED_COUNTERPARTS = 8
DONOR_SIDE_REASONS = ("fx_rate_unavailable",)


def _reason_side(code):
    """`donor` si el motivo lo pone el donante (o el par de monedas), `recipient` si la receptora, `pair` si no se sabe."""
    if code is None:
        return "pair"
    if code.startswith("donor_") or code in DONOR_SIDE_REASONS:
        return "donor"
    if code.startswith("recipient_") or code in ("fraction_cap", "need_fully_covered"):
        return "recipient"
    return "pair"


def _unique(values):
    """El único valor no nulo de `values` (comparado tras redondear a 6 decimales), o `None` si hay varios o ninguno."""
    seen = {round(float(v), 6): v for v in values if v is not None}
    return next(iter(seen.values())) if len(seen) == 1 else None


def _infeasible_groups(plan):
    """Pares no factibles de `levers_evaluated` agrupados por `(palanca, filial que bloquea, motivo)`.

    Motivos del donante (`donor_*`, `fx_rate_unavailable`) se agrupan por donante con la lista de receptoras;
    motivos de la receptora (`recipient_*`, `fraction_cap`) por receptora con la lista de donantes; el resto queda
    par a par. Orden: palanca (según aparece), lado (donante, receptora, par), id de la filial que bloquea, motivo.
    """
    groups, lever_order = {}, {}
    for lv in plan.get("levers_evaluated", []):
        lever_order.setdefault(lv["lever"], len(lever_order))
        if lv.get("feasible"):
            continue
        side = _reason_side(lv.get("reason"))
        anchor = lv["donor"] if side == "donor" else lv["recipient"] if side == "recipient" else (lv["donor"], lv["recipient"])
        key = (lv["lever"], side, anchor, lv.get("reason"))
        groups.setdefault(key, []).append(lv)
    rank = {"donor": 0, "recipient": 1, "pair": 2}
    return dict(sorted(groups.items(), key=lambda item: (lever_order[item[0][0]], rank[item[0][1]], str(item[0][2]), item[0][3] or "")))


def _counterpart_text(lv, side):
    """Contraparte con su importe propio entre paréntesis: la receptora con su necesidad, el donante con su capacidad."""
    if side == "donor":
        need = lv.get("need_recipient_ccy")
        return lv["recipient"] + (f" (necesidad {_money(need, lv.get('recipient_currency'))})" if need is not None else "")
    return lv["donor"]


def _infeasible_lines(plan):
    """«Palancas evaluadas no factibles» agrupadas; nunca cuenta contrapartes (los conteos no están en el JSON)."""
    groups = _infeasible_groups(plan)
    if not groups:
        return []
    lines = ["Palancas evaluadas no factibles:"]
    for (lever, side, anchor, code), pairs in groups.items():
        label = _label(REASON_ES, code)
        if side == "pair":
            donor, recipient = anchor
            lv = pairs[0]
            detail = []
            if lv.get("need_recipient_ccy") is not None:
                detail.append(f"necesidad {_money(lv['need_recipient_ccy'], lv.get('recipient_currency'))}")
            if lv.get("donor_capacity") is not None:
                detail.append(f"capacidad del donante {_money(lv['donor_capacity'], lv.get('donor_currency'))}")
            extra = f" ({'; '.join(detail)})" if detail else ""
            lines.append(f"- {lever} {donor} → {recipient}: {label}{extra}.")
            continue
        if side == "donor":
            capacity = _unique(lv.get("donor_capacity") for lv in pairs)
            own = f" (capacidad {_money(capacity, pairs[0].get('donor_currency'))})" if capacity is not None else ""
            head, who = f"{lever} desde {anchor}", "receptoras"
        else:
            need = _unique(lv.get("need_recipient_ccy") for lv in pairs)
            own = f" (necesidad {_money(need, pairs[0].get('recipient_currency'))})" if need is not None else ""
            head, who = f"{lever} hacia {anchor}", "donantes"
        listed = [_counterpart_text(lv, side) for lv in pairs[:MAX_LISTED_COUNTERPARTS]]
        if len(pairs) > MAX_LISTED_COUNTERPARTS:
            listed.append("y otras")
        lines.append(f"- {head}: {label}{own} → {who}: {', '.join(listed)}.")
    return lines


def _why_not_lines(plan):
    lines = [f"El plan se detuvo porque {_label(STOPPED_ES, plan['plan'].get('stopped_because'))}."]
    rejected = plan.get("rejected_alternatives", [])
    if rejected:
        lines.append("Alternativas rechazadas:")
        for alt in rejected:
            delta = alt.get("delta_utility_k6")
            suffix = f" (ΔG en régimen {fmt_num(delta, 2)})" if delta is not None else ""
            lines.append(f"- {alt['lever']} {alt['donor']} → {alt['recipient']}: {_label(REASON_ES, alt.get('reason'))}{suffix}.")
    lines.extend(_infeasible_lines(plan))
    cert = plan.get("certificate", {})
    if cert.get("checked"):
        lines.append(f"Certificado por enumeración: mejor acción única {fmt_num(cert.get('best_single_utility'))}, "
                     f"mejor par compatible {fmt_num(cert.get('best_pair_utility'))}, greedy {fmt_num(cert.get('greedy_utility'))}; "
                     f"brecha {fmt_num(cert.get('greedy_gap'), 2)}. Sin garantía de óptimo global más allá de pares.")
    else:
        lines.append("Certificado no calculado (más filiales optimizables que el límite exhaustivo o sin plan); "
                     "el greedy no garantiza el óptimo global.")
    return lines


def _assumption_lines(doc):
    lines = [f"- {a}" for a in doc.get("assumptions", [])] + [f"- {l}" for l in doc.get("limitations", [])]
    return lines or ["- Sin supuestos declarados en el JSON."]


def _coverage_lines(plan):
    cov, subs = plan["coverage"], _subsidiaries(plan)
    lines = [f"Filiales {fmt_num(cov['subsidiaries'], 0)}; optimizables {fmt_num(cov['optimizable'], 0)}; sin nivel "
             f"{fmt_num(cov['not_scored'], 0)}; con caja reconstruida fiable {fmt_num(cov['with_reliable_cash'], 0)}; "
             f"con componente de deuda {fmt_num(cov['with_debt_component'], 0)}; con componente de pagos (AP) "
             f"{fmt_num(cov['with_ap_component'], 0)}; monedas {', '.join(cov.get('currencies', [])) or 'n/d'}."]
    for cid, s in sorted(subs.items()):
        if s.get("level") is None:
            lines.append(f"- {cid}: sin nivel V2 ({_label(SCORE_REASON_ES, s.get('score_reason'))}); no entra en G ni en las acciones.")
        elif not s.get("liquidity", {}).get("reliable"):
            lines.append(f"- {cid}: caja reconstruida no fiable; no puede actuar como donante.")
    consolidated = plan.get("baseline", {}).get("consolidated_group_currency_score") or {}
    if consolidated:
        scores = "; ".join(f"{ccy} {fmt_num(v)}" for ccy, v in sorted(consolidated.items()))
        lines.append(f"Consolidado grupo-moneda V2 (no cambia con D1, no se recalcula con P): {scores}.")
    return lines


def _reasons_by_company(plan):
    reasons = {}
    for lv in plan.get("levers_evaluated", []):
        if lv.get("feasible") or not lv.get("reason"):
            continue
        code = lv["reason"]
        targets = [lv["donor"]] if code.startswith("donor_") else [lv["recipient"]] if code.startswith("recipient_") \
            else [lv["donor"], lv["recipient"]]
        for cid in targets:
            reasons.setdefault(cid, {})[code] = None
    return reasons


def _status_summary(plan):
    cov, base, diag = plan["coverage"], plan["baseline"], plan.get("diagnosis", {})
    subs = _subsidiaries(plan)
    if plan["status"] == "single_subsidiary":
        only = next(iter(subs.values()), {})
        lines = [f"Grupo {plan['group_id']}, mes {_month(plan)}: una sola filial puntuada ({only.get('company_id', 'n/d')}, "
                 f"nivel {fmt_num(only.get('level'))}, tramo {TRAMO_ES.get(only.get('tramo'), 'n/d')}). El plan de grupo "
                 "no aplica: consulta la sensibilidad de la empresa."]
    else:
        bott = diag.get("bottleneck") or {}
        lines = [f"Grupo {plan['group_id']}, mes {_month(plan)}: {fmt_num(cov['optimizable'], 0)} filiales optimizables "
                 f"de {fmt_num(cov['subsidiaries'], 0)}, pero ninguna palanca de tesorería intragrupo es factible con "
                 f"los datos disponibles. Utilidad de grupo G {fmt_num(base['group_utility_0_100'])}; nivel mínimo "
                 f"{fmt_num(base['min_level'])} ({bott.get('company_id', 'n/d')}).",
                 "Motivos por filial:"]
        reasons = _reasons_by_company(plan)
        for item in diag.get("unexplained_ap_delays", []):
            own = reasons.setdefault(item.get("company_id"), {})
            if "recipient_not_liquidity_constrained" not in own:
                own[item.get("note") or "retraso AP no explicado por liquidez"] = None
        for cid in sorted(subs):
            if cid in reasons:
                lines.append(f"- {cid}: " + "; ".join(_label(REASON_ES, code) for code in reasons[cid]) + ".")
            elif subs[cid].get("level") is None:
                lines.append(f"- {cid}: sin nivel ({_label(SCORE_REASON_ES, subs[cid].get('score_reason'))}).")
            elif cid in diag.get("recipient_candidates", []):
                lines.append(f"- {cid}: receptora candidata sin donante factible.")
            else:
                lines.append(f"- {cid}: sin motivo específico registrado.")
    lines.append(MECHANICAL_NOTICE)
    return lines


def render_plan(plan, fmt="markdown"):
    """Narrativa del plan de grupo (spec §9.1). Sin plan: plantilla por `status` con motivos por filial."""
    title = f"Plan de grupo {plan['group_id']} — {_month(plan)}"
    if plan.get("status") != "plan":
        sections = [("Resumen", _status_summary(plan)), ("Cobertura de datos", _coverage_lines(plan)),
                    ("Supuestos y límites", _assumption_lines(plan))]
        return _compose(title, sections, fmt)
    sections = [("Resumen", _summary_plan(plan)), ("Diagnóstico", _diagnosis_lines(plan)),
                ("Plan paso a paso", _steps_lines(plan)), ("Por qué no más / por qué no otras", _why_not_lines(plan)),
                ("Supuestos y límites", _assumption_lines(plan)), ("Cobertura de datos", _coverage_lines(plan))]
    return _compose(title, sections, fmt)


# ---------------------------------------------------------------------------------------- sensibilidad

def _lever_map(sens):
    return {lv["lever"]: lv for lv in sens.get("levers", [])}


def _quantity_phrase(lever, value, ccy, decimals=1):
    unit = lever.get("unit")
    return fmt_num(value, decimals, "días") if unit in ("days", "días") else _money(value, unit or ccy, decimals)


def _grid_row(lever):
    grid = lever.get("grid") or []
    return min(grid, key=lambda g: abs(g["rel_change"] - 0.05)) if grid else None


def lever_scenario_phrase(lever, baseline_level, ccy):
    """Frase de negocio literal de la spec §9.1 para una fila de la rejilla (la más cercana al 5 %)."""
    row = _grid_row(lever)
    if row is None:
        return None
    pct, before, after = fmt_pct(row["rel_change"]), fmt_num(baseline_level), fmt_num(row["level_after_k6"])
    q_before, q_after = _quantity_phrase(lever, lever.get("current"), ccy), _quantity_phrase(lever, row.get("quantity_after"), ccy)
    tail = f"y todo lo demás siguiera igual, el nivel pasaría de {before} a {after} en régimen."
    lid = lever["lever"]
    if lid == "cut_outflow":
        return f"Si las salidas operativas bajaran un {pct} (hasta {q_after} al mes) {tail}"
    if lid == "raise_inflow":
        return f"Si las entradas operativas subieran un {pct} {tail}"
    if lid == "debt_service_cut":
        return f"Si la cuota mensual de deuda bajara de {q_before} a {q_after} (renegociación o plazo más largo) {tail}"
    if lid in ("ap_on_time", "ar_faster"):
        who = "pago a proveedores" if lid == "ap_on_time" else "cobro a clientes"
        return (f"Si el retraso medio de {who} bajara de {fmt_num(lever.get('current'))} a "
                f"{fmt_num(row.get('quantity_after'))} días {tail}")
    return f"Si {_label(LEVER_ES, lid)} cambiara un {pct} {tail}"


def tramo_change_phrase(lever, ccy):
    """Fragmento «{frase_i}» de la frase de cambio de tramo para una palanca alcanzable."""
    tnt = lever.get("to_next_tramo") or {}
    if not tnt.get("reachable"):
        return None
    pct, lid = fmt_pct(tnt.get("rel_change_needed")), lever["lever"]
    q_now, q_need = _quantity_phrase(lever, lever.get("current"), ccy), _quantity_phrase(lever, tnt.get("quantity_needed"), ccy)
    if lid == "cut_outflow":
        return f"un {pct} menos de salidas operativas ({q_now} → {q_need} al mes)"
    if lid == "raise_inflow":
        return f"un {pct} más de entradas operativas ({q_now} → {q_need} al mes)"
    if lid == "debt_service_cut":
        return f"una cuota mensual de deuda de {q_need} (desde {q_now}, un {pct} menos)"
    if lid == "ap_on_time":
        return f"un retraso medio de pago a proveedores de {fmt_num(tnt.get('quantity_needed'))} días (desde {fmt_num(lever.get('current'))})"
    if lid == "ar_faster":
        return f"un retraso medio de cobro a clientes de {fmt_num(tnt.get('quantity_needed'))} días (desde {fmt_num(lever.get('current'))})"
    return f"{lid}: {pct} ({q_need})"


def top_tramo_sentence(sens):
    """Frase para una filial sin siguiente tramo (`next_tramo_target` nulo: ya está en el tramo más alto)."""
    current = TRAMO_ES.get((sens.get("baseline") or {}).get("tramo"), "actual")
    return f"Ya está en el tramo más alto ({current}); no hay siguiente tramo que alcanzar."


def tramo_sentence(sens):
    """Frase «Para pasar a {tramo}: … o …» o la de imposibilidad, según `levers[*].to_next_tramo`."""
    ccy, target = sens.get("currency", ""), sens.get("next_tramo_target")
    if target is None:
        return top_tramo_sentence(sens)
    tramo = _tramo_target_name(target)
    phrases = [p for p in (tramo_change_phrase(lv, ccy) for lv in sens.get("levers", []) if lv.get("available")) if p]
    if not phrases:
        return f"Ninguna palanca por sí sola alcanza {tramo} dentro de los límites evaluados."
    return f"Para pasar a {tramo}: " + " o ".join(phrases) + "."


def _where_lines(sens):
    base = sens["baseline"]
    comps = ", ".join(f"{COMPONENT_ES[c]} {fmt_num(base['components'].get(c))}" for c in COMPONENT_ES)
    lines = [f"{sens['company_id']} ({sens.get('group_id')}), mes {_month(sens)}: nivel {fmt_num(base['level'])}, tramo "
             f"{TRAMO_ES.get(base.get('tramo'), base.get('tramo'))}; score {fmt_num(base.get('score'))} (ajuste de momentum "
             f"{fmt_num(base.get('momentum_adjustment'))}).",
             f"Componentes: {comps}."]
    if sens.get("structural_note"):
        lines.append(f"Qué arrastra: {sens['structural_note']}")
    else:
        available = {c: v for c, v in base["components"].items() if v is not None}
        if available:
            weakest = min(available, key=available.get)
            lines.append(f"Componente más bajo: {COMPONENT_ES.get(weakest, weakest)} ({fmt_num(available[weakest])}).")
    if sens.get("next_tramo_target") is not None:
        lines.append(f"Siguiente tramo: {_tramo_target_name(sens['next_tramo_target'])} (nivel {fmt_num(sens['next_tramo_target'], 0)}).")
    liq = base.get("liquidity", {})
    if liq.get("reconstructed_cash") is not None:
        lines.append(f"Caja reconstruida {_money(liq['reconstructed_cash'], sens.get('currency'))} "
                     f"({'fiable' if liq.get('reliable') else 'no fiable'}); colchón {_money(liq.get('buffer'), sens.get('currency'))}; "
                     f"exceso {_money(liq.get('excess_cash'), sens.get('currency'))}.")
    return lines


def _by_pct_lines(sens):
    levers, ccy, base_level = _lever_map(sens), sens.get("currency", ""), sens["baseline"].get("level")
    ranking = [lid for lid in sens.get("ranking", {}).get("by_pct", []) if lid in levers][:3]
    if not ranking:
        return ["Ninguna palanca evaluable."]
    lines = ["Ranking por 1 % de cambio relativo en la dirección buena, en régimen (k=6):"]
    for lid in ranking:
        lv, slope = levers[lid], levers[lid].get("slope_now", {})
        line = (f"- {lid} ({_label(LEVER_ES, lid)}, {'negocio' if lv.get('type') == 'business' else 'tesorería'}): "
                f"{fmt_num(slope.get('level_per_pct'), 2)} puntos de nivel por cada 1 %; pendiente válida hasta "
                f"{_quantity_phrase(lv, slope.get('valid_until'), ccy)} (ahora {_quantity_phrase(lv, lv.get('current'), ccy)})")
        if slope.get("slope_after") is not None:
            line += f", después {fmt_num(slope['slope_after'], 2)} por 1 %"
        lines.append(line + ".")
        phrase = lever_scenario_phrase(lv, base_level, ccy)
        if phrase:
            lines.append(f"  {phrase}")
    return lines


def _by_cash_lines(sens):
    levers, ccy = _lever_map(sens), sens.get("currency", "")
    ranking = [lid for lid in sens.get("ranking", {}).get("by_cash", []) if lid in levers]
    if not ranking:
        return ["Ninguna palanca evaluable tiene equivalente de caja."]
    lines = [f"Ranking por cada 10.000 {ccy} de equivalente de caja, en régimen (k=6); solo palancas con equivalente:"]
    for lid in ranking[:3]:
        lv, slope = levers[lid], levers[lid].get("slope_now", {})
        row = _grid_row(lv)
        example = (f" (p. ej. {fmt_pct(row['rel_change'])} equivale a {_money(row.get('cash_equivalent'), ccy)} en la ventana)"
                   if row and row.get("cash_equivalent") is not None else "")
        lines.append(f"- {lid} ({_label(LEVER_ES, lid)}): {fmt_num(slope.get('level_per_10k'), 2)} puntos de nivel por cada "
                     f"10.000 {ccy}{example}.")
    return lines


def _tramo_lines(sens):
    lines = [tramo_sentence(sens)]
    target, ccy = sens.get("next_tramo_target"), sens.get("currency", "")
    tramo = _tramo_target_name(target)
    for lv in sens.get("levers", []):
        if not lv.get("available"):
            continue
        tnt = lv.get("to_next_tramo") or {}
        if not tnt.get("reachable"):
            if target is not None:  # sin siguiente tramo no hay nada que «no alcanzar»
                lines.append(f"- {lv['lever']} ({_label(LEVER_ES, lv['lever'])}) no alcanza {tramo} por sí sola dentro de los límites evaluados.")
        elif tnt.get("cash_equivalent") is not None:
            lines.append(f"- {lv['lever']}: equivalente de caja {_money(tnt['cash_equivalent'], ccy)} en la ventana.")
        verdict = feasibility_verdict(lv)
        if verdict:
            feas = lv.get("feasibility") or {}
            lines.append(f"- {lv['lever']}: {verdict} (caja necesaria {_money(feas.get('cash_needed'), ccy)}; exceso propio "
                         f"{_money(feas.get('own_excess_cash'), ccy)}).")
    lines.append("Cada palanca se evalúa aislada; las combinaciones no se exploran.")
    return lines


def _steps_phrase(steps):
    """«el paso 1» / «los pasos 1 y 2» / «los pasos 1, 2 y 3»; cadena vacía sin pasos."""
    labels = [fmt_num(s, 0) for s in steps or []]
    if not labels:
        return ""
    if len(labels) == 1:
        return f"el paso {labels[0]}"
    return f"los pasos {', '.join(labels[:-1])} y {labels[-1]}"


def _covering_steps(lever):
    """Pasos del plan que cubren la palanca, solo si `feasibility` los declara (claves opcionales); si no, vacío.

    No se usa `group_context.steps` como sustituto: es la unión de todos los pasos de la filial (también los de D1 o
    como donante) y citarlos como «el paso que cubre el AP» sería impreciso.
    """
    feas = lever.get("feasibility") or {}
    for key in ("group_plan_steps", "covered_by_steps", "covered_by_step", "group_plan_step"):
        value = feas.get(key)
        if value is not None:
            return list(value) if isinstance(value, (list, tuple)) else [value]
    return []


def feasibility_verdict(lever):
    """Veredicto de `feasibility` (§6.2.5): caja propia, plan de grupo (`covered_by_group_plan`, opcional) o financiación.

    «Paso P» se escribe con el nombre de la palanca (`LEVER_ES["P"]`): la letra suelta no existe como id en el JSON de
    sensibilidad y el validador de anclaje la rechazaría.
    """
    feas = lever.get("feasibility") or {}
    covered = bool(feas.get("covered_by_group_plan"))
    if feas.get("feasible_alone") is None and not covered:
        return None
    parts = []
    if feas.get("feasible_alone"):
        parts.append("alcanzable con caja propia")
    if covered:
        steps = _steps_phrase(_covering_steps(lever))
        detail = f"paso de {LEVER_ES['P']}" + (f", {steps}" if steps else "")
        parts.append(f"cubierta por el plan de grupo ({detail})")
    if not parts:
        parts.append("requiere financiación externa o del grupo")
    return "; ".join(parts)


def group_role_sentence(sens):
    """Frase del papel de la filial en el plan de su grupo (`group_context`: `role`, `steps`); `None` sin plan."""
    ctx = sens.get("group_context") or {}
    if not ctx.get("has_group_plan"):
        return None
    gid, role = sens.get("group_id"), ctx.get("role")
    steps = _steps_phrase(ctx.get("steps"))
    where = f" en {steps}" if steps else ""
    if role == "recipient":
        return f"En el plan de grupo {gid}, esta filial recibe apoyo{where}."
    if role == "donor":
        return f"En el plan de grupo {gid}, esta filial actúa como donante{where}."
    if role == "both":
        return f"En el plan de grupo {gid}, esta filial actúa como donante y receptora{where}."
    return f"El grupo {gid} tiene plan pero esta filial no participa en ningún paso."


def _group_role_lines(sens):
    ctx = sens.get("group_context") or {}
    lines = [group_role_sentence(sens)]
    if ctx.get("role") in ("recipient", "donor", "both"):
        lines.append("El detalle del importe y del efecto está en el plan del grupo.")
    return lines


def _unavailable_lines(sens):
    lines = [f"- {lv['lever']} ({_label(LEVER_ES, lv['lever'])}): {_label(REASON_ES, lv.get('reason'))}."
             for lv in sens.get("levers", []) if not lv.get("available")]
    return lines or ["Todas las palancas son evaluables."]


def render_sensitivity(sens, fmt="markdown"):
    """Narrativa de la sensibilidad de empresa (spec §9.1). `not_scored`: motivo y límites."""
    title = f"Qué mueve el nivel de {sens['company_id']} — {_month(sens)}"
    if sens.get("status") != "sensitivity" or sens.get("baseline", {}).get("level") is None:
        lines = [f"{sens['company_id']} ({sens.get('group_id')}), mes {_month(sens)}: sin nivel V2 "
                 f"({_label(SCORE_REASON_ES, sens.get('score_reason'))}). No hay sensibilidad que calcular: sin nivel no "
                 "hay palancas.", MECHANICAL_NOTICE]
        return _compose(title, [("Dónde estás", lines), ("Supuestos y límites", _assumption_lines(sens))], fmt)
    sections = [("Dónde estás", _where_lines(sens)), ("Qué mueve más tu nivel", _by_pct_lines(sens)),
                ("Qué mueve más por cada 10.000", _by_cash_lines(sens)), ("Cuánto para cambiar de tramo", _tramo_lines(sens))]
    if (sens.get("group_context") or {}).get("has_group_plan"):
        sections.append(("Papel en el grupo", _group_role_lines(sens)))
    sections += [("Palancas no evaluables", _unavailable_lines(sens)),
                 ("Supuestos y límites", _assumption_lines(sens) + [f"- {MECHANICAL_NOTICE}"])]
    return _compose(title, sections, fmt)
