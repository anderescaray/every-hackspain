"""Exporta los artefactos de `xray.product` al contrato del frontend (docs/frontend-data-contract.md).

Empresa: `schema_version 2.0` -> frontend/public/generated/companies/<company_id>.json
Grupo:   `schema_version 1.0` -> frontend/public/generated/groups/<group_id>.json
Cartera: `schema_version 1.0` -> frontend/public/generated/portfolio.json (frontend/types/portfolio.ts)

Solo traduce y redondea: no recalcula scores. Donde el contrato exige un número y V2 no tiene
dato, se exporta un valor neutro documentado y `health_score_model.provisional = true`
(decisión FE-01 en decisiones.md). Lo que no existe todavía (Time Borrowed, alertas,
escenarios) se exporta como `null` / `[]`, que el contrato admite y la UI muestra como ausente.
"""
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from xray.paths import PROCESSED_DIR, ROOT
from xray.product.company_brief import build_brief_facts, company_brief

FRONTEND_GENERATED = ROOT / "frontend" / "public" / "generated"
MODEL_VERSION = "financial_smoothed_v2+frontend-export-1"
# Pesos efectivos de V2 traducidos a las cuatro dimensiones del contrato (suman 1):
# score = level + 0.2·(momentum−50); level = 0.45 operación + 0.25 deuda + 0.15 cobros + 0.15 pagos.
WEIGHTS = {"momentum": 0.20, "cash_generation": 0.36, "resilience": 0.24, "debt": 0.20}
COMPONENT_DIMENSION = {"operations": "cash_generation", "debt": "debt", "collections": "resilience",
                       "payments": "resilience", "momentum": "momentum"}
TRAJECTORY = {"improving": "improving", "emerging_improvement": "improving",
              "deteriorating": "deteriorating", "emerging_deterioration": "deteriorating"}
BUCKET_CATEGORY = {"operations": "operating", "own_circulation": "circulation", "group_support": "support",
                   "uncertain": "uncertain", "unpaired_transfer": "uncertain", "financing_investment": "uncertain"}
CATEGORY_LABEL = {"operating": "Generado por la operación", "circulation": "Circulación de tesorería",
                  "support": "Apoyo interno / intragrupo", "uncertain": "Origen no identificado"}
MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
EVIDENCE_ROWS = 10
CASH_EVIDENCE_ID = "cash-movements"


def _month_label(ts):
    ts = pd.Timestamp(ts)
    return f"{MONTHS_ES[ts.month - 1]} {ts.year}"


def _period(months):
    months = [pd.Timestamp(m) for m in months]
    return f"{_month_label(min(months))} – {_month_label(max(months))}" if months else "sin periodo"


def _num(value, default=None):
    if value is None:
        return default
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return default if not math.isfinite(value) else value


def _score(value):
    value = _num(value)
    return None if value is None else int(round(min(100.0, max(0.0, value))))


def _round(value, digits=2):
    value = _num(value)
    return None if value is None else round(value, digits)


def _text(value, fallback):
    value = "" if value is None else str(value).strip()
    return (value or fallback)[:5000]


def _brief_for_company(company, last, trajectory, dependency, confidence, completer=None):
    """Assessment + summary deterministas (plantilla); LLM opcional con anclaje."""
    why = ((company.get("currencies") or {}).get("EUR") or {}).get("why_changed") or {}
    terms = sorted(why.get("terms") or [], key=lambda t: t.get("rank", 99))
    top = terms[0] if terms else {}
    facts = build_brief_facts(
        company_id=company["company_id"],
        group_id=company.get("group_id"),
        health_score=_score(last["score"]),
        trajectory=trajectory,
        score_status=last.get("score_status"),
        score_reason=last.get("score_reason"),
        dependency=dependency,
        confidence=_score(confidence) if confidence is not None else None,
        delta_vs_prev=_round(last.get("delta_vs_prev"), 1),
        main_driver_label=top.get("label") or top.get("feature"),
        main_driver_impact=_round(top.get("delta_contribution"), 1),
        episode=last.get("episode"),
    )
    return company_brief(facts, completer=completer)


def _dimensions(last):
    health = _score(last.get("score"))
    coll, pay = _num(last.get("level_collections")), _num(last.get("level_payments"))
    resilience = None if coll is None and pay is None else float(np.nanmean([v for v in (coll, pay) if v is not None]))
    raw = {"momentum": _num(last.get("momentum")), "cash_generation": _num(last.get("level_operations")),
           "resilience": resilience, "debt": _num(last.get("level_debt"))}
    provisional = any(v is None for v in raw.values()) or last.get("score_status") != "scored"
    return {k: (_score(v) if v is not None else health) for k, v in raw.items()}, provisional


def _drivers(why_changed):
    terms = (why_changed or {}).get("terms") or []
    drivers = []
    for term in sorted(terms, key=lambda t: t.get("rank", 99))[:20]:
        impact = _round(term.get("delta_contribution"), 1)
        if impact is None:
            continue
        dimension = COMPONENT_DIMENSION.get(term.get("component"), "cash_generation")
        drivers.append({
            "id": f"{term.get('layer', 'x')}-{term.get('feature', 'x')}"[:100], "driver": _text(term.get("label"), "Señal"),
            "affected_dimensions": [dimension], "impact": impact,
            "direction": "positive" if impact > 0 else "negative" if impact < 0 else "neutral",
            "explanation": _text(term.get("sentence"), "Cambio de contribución entre meses consecutivos."),
            "evidence_count": 0, "evidence_refs": [],
        })
    return drivers


def _cash_truth(company_id, group_id, cash, confidence, evidence_rows):
    buckets = {b["bucket"]: b for b in (cash or {}).get("buckets", [])}
    window = (cash or {}).get("window_months") or []
    period = _period(window)
    agg = {c: {"gross": 0.0, "in": 0.0, "out": 0.0, "n": 0} for c in CATEGORY_LABEL}
    for name, b in buckets.items():
        cat = BUCKET_CATEGORY.get(name, "uncertain")
        agg[cat]["gross"] += _num(b.get("amount_abs"), 0.0)
        agg[cat]["in"] += _num(b.get("amount_in"), 0.0)
        agg[cat]["out"] += _num(b.get("amount_out"), 0.0)
        agg[cat]["n"] += int(b.get("n_tx") or 0)
    total = sum(a["gross"] for a in agg.values())
    apparent = sum(a["in"] - a["out"] for a in agg.values())
    has_evidence = len(evidence_rows) > 0
    refs = [CASH_EVIDENCE_ID] if has_evidence else []
    explain = {
        "operating": "Neto de entradas y salidas identificadas como operación (categoría bancaria o AI) en los últimos seis meses.",
        "circulation": "Traslados emparejados entre cuentas de la misma empresa: mueven dinero, no lo generan. Neto cero por construcción.",
        "support": "Transferencias espejo con otras sociedades del grupo (D05). Apoyo o tesorería interna, no venta externa.",
        "uncertain": "Sin categoría fiable, traspasos sin pareja, financiación e inversión. Se publica como bruto sin atribuir.",
    }
    components = []
    for cat in ("operating", "circulation", "support", "uncertain"):
        a = agg[cat]
        net = 0.0 if cat == "circulation" else None if cat == "uncertain" else round(a["in"] - a["out"], 2)
        conf = None if cat == "uncertain" else _score(confidence)
        components.append({"category": cat, "label": CATEGORY_LABEL[cat], "gross_movement": round(a["gross"], 2),
                           "net_amount": net, "explanation": explain[cat], "confidence": conf,
                           "evidence_refs": refs if a["n"] > 0 else []})
    if group_id is None and agg["support"]["gross"] > 0:
        components[2]["label"] = "Financiación o apoyo externo"
    own = buckets.get("own_circulation")
    own_count = int(own.get("n_tx") or 0) // 2 if own else 0
    own_amount = round(_num(own.get("amount_in"), 0.0), 2) if own else 0.0
    if (own_amount == 0) != (own_count == 0):
        own_amount, own_count = 0.0, 0
    op_net, sup_net = components[0]["net_amount"], components[2]["net_amount"]
    if agg["support"]["gross"] > 0 and abs(sup_net) > abs(op_net):
        headline = "Poca caja del negocio frente al apoyo recibido." if sup_net > 0 else "La empresa aporta más de lo que genera."
    elif op_net >= 0:
        headline = "La operación identificada genera caja neta."
    else:
        headline = "La operación identificada consume caja neta."
    explanation = (f"En {period} la operación identificada aporta {op_net:,.0f} € netos y el apoyo intragrupo {sup_net:,.0f} €; "
                   f"la circulación entre cuentas propias tiene neto cero y {agg['uncertain']['gross']:,.0f} € brutos quedan sin atribuir. "
                   "No es saldo bancario ni prueba de solvencia.").replace(",", ".")
    return {
        "period": period, "total_gross_movement": round(total, 2), "apparent_net": round(apparent, 2),
        "own_account_circulation": {"transferred_amount": own_amount, "transfer_count": own_count,
                                    "explanation": "Traslados emparejados entre cuentas propias (D04), contados una vez por traslado; excluye otras sociedades y movimientos sin pareja.",
                                    "confidence": _score(confidence), "evidence_refs": refs if own_count else []},
        "account_flows": None, "components": components, "headline": headline, "explanation": explanation,
        "confidence": _score(confidence), "evidence_refs": refs,
        "evidence_summary": [f"{agg[c]['n']} movimientos · {CATEGORY_LABEL[c]}" for c in CATEGORY_LABEL if agg[c]["n"]][:20],
        "correction": None, "comparison": None,
    }


def _evidence_group(evidence_rows, period):
    if not len(evidence_rows):
        return []
    rows = []
    for r in evidence_rows.itertuples(index=False):
        rows.append({"kind": "transaction", "id": str(r.transaction_id), "account_id": None,
                     "transaction_date": pd.Timestamp(r.date).strftime("%Y-%m-%d"), "amount": round(float(r.amount), 2),
                     "category": BUCKET_CATEGORY.get(r.bucket, "uncertain"),
                     "description": _text(getattr(r, "description", None), "Sin concepto")[:200]})
    return [{"id": CASH_EVIDENCE_ID, "title": "Muestra de movimientos clasificados", "period": period,
             "explanation": "Hasta diez movimientos representativos por empresa, uno o varios por categoría; no es la conciliación completa.",
             "confidence": None, "total_count": int(evidence_rows.attrs.get("total_count", len(rows))), "rows": rows}]


def _simulation(scenarios=None, health_score=None, has_invoices=True):
    from xray.product.whatif import LEVERS, METHODOLOGY
    inputs = [{"key": key, "label": spec["label"], "unit": spec["unit"], "baseline": spec["baseline"], "min": spec["min"],
               "max": spec["max"], "step": spec["step"], "explanation": spec["explanation"]} for key, spec in LEVERS.items()]
    if scenarios is None or not len(scenarios):
        return {"inputs": inputs, "scenarios": [], "example_id": None,
                "methodology": "Los escenarios precalculados todavía no están disponibles para esta empresa: el simulador muestra ausencia en lugar de estimar. Escenario, no predicción."}
    keys = ("customer_term", "collection_delay", "supplier_term", "internal_support")
    single = {}   # efecto de cada palanca sola, para desglosar combinaciones
    for r in scenarios.itertuples(index=False):
        changed = [k for k in keys if int(getattr(r, k)) != 0]
        if len(changed) == 1:
            single[(changed[0], int(getattr(r, changed[0])))] = round(float(r.delta), 1)
    out, best = [], None
    for r in scenarios.itertuples(index=False):
        changed = [k for k in keys if int(getattr(r, k)) != 0]
        points = round(float(r.delta), 1)
        fmt = lambda k: f"{LEVERS[k]['label']}: {int(getattr(r, k)):+d} {'%' if LEVERS[k]['unit'] == '%' else 'días'}"
        if not changed:
            label, explanation, impacts = "Situación actual", "Sin cambios: coincide con el Health Score publicado.", []
        else:
            label = " · ".join(fmt(k) for k in changed)
            impacts = [{"key": k, "label": LEVERS[k]["label"], "points": single.get((k, int(getattr(r, k))), 0.0)} for k in changed]
            if points == 0 and all(k in ("collection_delay", "supplier_term") for k in changed) and not has_invoices:
                explanation = "Sin efecto: la empresa no tiene facturas en la ventana, así que el retraso de cobro/pago no forma parte de su score."
            elif points == 0:
                explanation = "Sin efecto apreciable sobre el score con la referencia actual."
            else:
                explanation = f"Cambio sostenido seis meses; el Health Score pasa de {int(round(r.base_score))} a {int(round(r.score))} ({points:+.1f} puntos)."
                if len(changed) > 1:
                    explanation += " Los puntos por palanca son los efectos de cada una por separado; el conjunto no es aditivo."
        out.append({"id": r.scenario_id, "label": label, "inputs": {k: int(getattr(r, k)) for k in keys},
                    "health_score": _score(r.score), "impacts": impacts, "explanation": explanation})
        if len(changed) == 1 and (best is None or abs(points) > abs(best[1])):
            best = (r.scenario_id, points)
    if health_score is not None:
        out = [s for s in out if s["id"] != "base" or s["health_score"] == health_score]
    return {"inputs": inputs, "scenarios": out, "example_id": best[0] if best and best[1] != 0 else None, "methodology": METHODOLOGY}


def company_detail(company, cash_summary_row, evidence_rows, scenarios=None, completer=None):
    """Traduce `product/companies/{id}.json` (una moneda) al contrato 2.0. Devuelve None sin score alguno."""
    currency = "EUR"
    block = (company.get("currencies") or {}).get(currency)
    if not block:
        return None
    timeline = [t for t in block.get("timeline", []) if _num(t.get("score")) is not None]
    if not timeline:
        return None
    timeline.sort(key=lambda t: t["month"])
    last = timeline[-1]
    as_of = (pd.Timestamp(last["month"]) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    dimensions, provisional = _dimensions(last)
    trajectory = TRAJECTORY.get(last.get("trajectory"), "stable")
    dependency = _num(cash_summary_row.get("support_dependency_ratio")) if cash_summary_row is not None else None
    confidence = (block.get("confidence") or {}).get("confidence")
    cash = _cash_truth(company["company_id"], company.get("group_id"), block.get("cash_truth"), confidence, evidence_rows)
    brief = _brief_for_company(company, last, trajectory, dependency, confidence, completer=completer)
    return {
        "schema_version": "2.0", "source": "generated", "company_id": company["company_id"],
        "group_id": company.get("group_id"), "as_of": as_of, "currency": currency,
        "health_score": _score(last["score"]), "dimensions": dimensions,
        "health_score_model": {"version": MODEL_VERSION, "provisional": bool(provisional), "weights": WEIGHTS},
        "assessment": brief.assessment,
        "confidence": _score(confidence), "trajectory": trajectory,
        "summary": brief.summary,
        "history": [{"month": pd.Timestamp(t["month"]).strftime("%Y-%m-%d"), "health_score": _score(t["score"])} for t in timeline[-24:]],
        "drivers_period": f"{_month_label(last['month'])} · cambio frente al mes anterior",
        "drivers": _drivers(block.get("why_changed")),
        "cash_truth": cash, "time_borrowed": {"ar": None, "ap": None}, "alerts": [],
        "evidence": _evidence_group(evidence_rows, cash["period"]),
        "simulation": _simulation(scenarios, _score(last["score"]), has_invoices=_num(last.get("level_collections")) is not None
                                  or _num(last.get("level_payments")) is not None),
    }


def _advisor_recommendations(plan):
    """Adapta únicamente planes `production_safe` a revisiones del contrato GroupDetail 1.0."""
    config = plan.get("config") or {} if plan else {}
    if not plan or plan.get("status") != "plan" or not config.get("production_safe"):
        return []
    horizon = int(config.get("horizon_months") or 6)
    kh = f"k{horizon}"
    recommendations = []
    titles = {
        "D1": "Revisar la redistribución del servicio de deuda",
        "P": "Revisar financiación para pagar proveedores en plazo",
        "O": "Revisar la centralización de pagos operativos",
    }
    types = {"D1": "funding_structure", "P": "liquidity_distribution", "O": "liquidity_distribution"}
    activity_floor = f"{float(config.get('min_recipient_inflow_6m') or 10_000):,.0f}".replace(",", ".")
    ratio = float(config.get("min_recipient_inflow_outflow_ratio") or 0.01)
    for step in plan.get("plan", {}).get("steps") or []:
        effect = (step.get("effects") or {}).get(kh) or {}
        recipient, donor = effect.get("recipient") or {}, effect.get("donor") or {}
        amount = _num((step.get("amount") or {}).get("reporting_ccy"))
        before_g, after_g = _num(effect.get("group_utility_before")), _num(effect.get("group_utility_after"))
        rb, ra = _num(recipient.get("level_before")), _num(recipient.get("level_after"))
        db, da = _num(donor.get("level_before")), _num(donor.get("level_after"))
        lever = step.get("lever")
        donor_id, recipient_id = step.get("donor"), step.get("recipient")
        if lever not in titles or None in (amount, before_g, after_g, rb, ra, db, da, donor_id, recipient_id):
            continue
        amount_text = f"{amount:,.0f} EUR".replace(",", ".")
        recommendations.append({
            "id": f"advisor-{int(step['step']):02d}-{lever.lower()}",
            "type": types[lever],
            "priority": "high" if rb < 40 else "medium",
            "title": f"{titles[lever]} para {recipient_id}",
            "explanation": (
                f"Escenario mecánico que sube el nivel mínimo del grupo: {donor_id} asumiría {amount_text} "
                f"de {recipient_id}. En régimen, el nivel de la receptora pasaría de {rb:.1f} a {ra:.1f}; "
                f"el de la donante, de {db:.1f} a {da:.1f}. ΔG {after_g - before_g:+.2f}."
            ),
            "period": f"{_month_label(plan['month'])} · horizonte {horizon} meses",
            "confidence": None,
            "signals": [
                {"source": "health", "observation": f"La receptora gana {ra - rb:.1f} puntos de nivel en régimen."},
                {"source": "liquidity", "observation": f"La donante compromete {amount_text} respetando su colchón de caja."},
                {"source": "resilience", "observation": f"La donante cambia {da - db:+.1f} puntos y conserva su tramo."},
            ],
            "review_steps": [
                "Confirmar saldos, cobros y pagos previstos con el tesorero de ambas sociedades.",
                "Validar fiscalidad, acuerdos intragrupo, covenants y capacidad legal para ejecutar la operación.",
                "Aprobar, ajustar o descartar el escenario; X Ray no mueve fondos ni genera órdenes bancarias.",
            ],
            "constraints": [
                "Escenario mecánico, no predicción ni recomendación ejecutable.",
                "Perfil seguro: actividad mínima, mejora no negativa a un mes, donante sin bajar de tramo y mejora de la peor filial.",
                f"Umbral de actividad no calibrado: al menos {activity_floor} EUR "
                f"de entradas en {horizon} meses y ratio entradas/salidas ≥ {100 * ratio:.0f}%.",
            ],
            "company_refs": [recipient_id, donor_id],
            "relation_refs": [],
            "evidence_refs": [],
        })
    return recommendations[:30]


def group_detail(group, member_details, cash_summary, advisor_plan=None):
    """Grupo válido 1.0; solo incorpora escenarios del advisor con perfil seguro explícito."""
    members = []
    for row in group.get("companies", []):
        detail = member_details.get(row["company_id"])
        summary = cash_summary.get(row["company_id"], {})
        dims = detail["dimensions"] if detail else {k: None for k in WEIGHTS}
        role = {"net_receiver": "receiver", "net_provider": "provider", "balanced": "both"}.get(summary.get("support_role"), "none_identified")
        if not summary:
            role = "unknown"
        ratio = _num(summary.get("support_dependency_ratio"))
        attention = "high" if (ratio or 0) >= 0.5 else "medium" if (ratio or 0) >= 0.3 or (detail and detail["trajectory"] == "deteriorating") else "low"
        members.append({
            "company_id": row["company_id"], "health_score": detail["health_score"] if detail else None,
            "dimensions": dims, "trajectory": detail["trajectory"] if detail else None, "role": role,
            "available_liquidity": None, "identified_debt": None, "obligations_due": None,
            "cash_generation_net": _round(summary.get("operations_in_6m")) if summary else None,
            "internal_received": _round(summary.get("support_in_6m")) if summary else None,
            "internal_provided": _round(summary.get("support_out_6m")) if summary else None,
            "confidence": detail["confidence"] if detail else None, "attention": attention,
            "summary": (detail["assessment"] if detail else "Sin score publicado para el último mes."),
            "outlook": {"status": "insufficient", "horizon": "próximo trimestre", "summary": "Sin perspectiva respaldada por evidencia.",
                        "funding_need": None, "confidence": None, "evidence_refs": []},
            "evidence_refs": [],
        })
    as_of = max((d["as_of"] for d in member_details.values()), default=None)
    latest = pd.Timestamp(group.get("latest_month") or as_of or "2026-08-01")
    metric = lambda what: {"value": None, "covered_company_ids": [], "explanation": f"{what} no consolidado en esta versión: no se suman posiciones entre sociedades.", "evidence_refs": []}
    recommendations = _advisor_recommendations(advisor_plan)
    limitations = ["No se presume que la caja sea fungible entre sociedades.",
                   "La ausencia de relaciones observadas no demuestra que no existan."]
    if recommendations:
        limitations += ["Los escenarios del advisor requieren aprobación humana; no ejecutan operaciones.",
                        "Los umbrales del perfil seguro son conservadores y no están calibrados con resultados reales."]
    else:
        limitations.insert(1, "No hay un plan de tesorería que supere las guardas de producción.")
    return {
        "schema_version": "1.0", "source": "generated", "group_id": group["group_id"],
        "as_of": (latest + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d"), "period": f"seis meses hasta {_month_label(latest)}", "currency": "EUR",
        "summary": f"{len(members)} sociedades observadas en el dataset; roles de apoyo derivados de transferencias espejo intragrupo (D05).",
        "coverage": {"known_company_count": None, "confidence": None, "explanation": "Perímetro observado en el dataset; no se conoce el perímetro jurídico completo."},
        "available_liquidity": metric("Liquidez disponible"), "identified_debt": metric("Deuda identificada"),
        "obligations": {**metric("Obligaciones"), "horizon": "30 días"},
        "limitations": limitations,
        "members": members[:50], "insights": [], "alerts": [], "concentration": [], "recent_changes": [],
        "relations": [], "recommendations": recommendations, "evidence": [],
    }


REASON_LABEL = {
    "ok": None, "no_usable_transactions": "Sin movimientos utilizables", "insufficient_window_history": "Historial insuficiente",
    "insufficient_components": "Componentes insuficientes", "incomplete_group_coverage": "Cobertura de filiales incompleta",
    "optional_components_missing": "Sin facturas (componentes opcionales)", "trend_unavailable": "Tendencia no calculable",
    "thin_current_month": "Mes actual con pocos movimientos", "short_history": "Historial corto", "partial_currency": "Moneda parcial",
    "coverage_account_change": "Cambio de cuentas activas", "coverage_onboarding": "Primeros meses de actividad",
}


def portfolio_items(portfolio_rows, details, cash_summary):
    """Una fila por empresa para la cartera: score/trayectoria de V2, señal principal, apoyo y prioridad de atención."""
    items = []
    for row in portfolio_rows:
        cid = row["company_id"]
        v2 = row.get("trajectory")
        trajectory = TRAJECTORY.get(v2) if v2 in TRAJECTORY else ("stable" if v2 in ("stable", "mixed_signals") else None)
        stage = None if trajectory is None else ("emerging" if str(v2).startswith("emerging") else "confirmed")
        status = row.get("score_status") or "not_scored"
        health = _score(row.get("score")) if status != "not_scored" else None
        summary = cash_summary.get(cid) or {}
        ratio = _num(summary.get("support_dependency_ratio"))
        attention = "low"
        if (trajectory == "deteriorating" and stage == "confirmed") or (ratio or 0) >= 0.5:
            attention = "high"
        elif trajectory == "deteriorating" or (ratio or 0) >= 0.3 or (health is not None and health < 35):
            attention = "medium"
        items.append({
            "company_id": cid, "group_id": row.get("group_id"), "health_score": health, "delta_vs_prev": _round(row.get("delta_vs_prev"), 1),
            "trajectory": trajectory, "trajectory_stage": stage, "confidence": _round(row.get("confidence"), 0),
            "score_status": status, "status_reason": REASON_LABEL.get(row.get("score_reason"), row.get("score_reason") or None),
            "main_signal": row.get("main_signal") or None, "main_signal_impact": _round(row.get("main_signal_delta"), 1),
            "support_dependency_ratio": None if ratio is None else round(min(1.0, max(0.0, ratio)), 3),
            "attention": attention, "has_detail": cid in details,
        })
    return items


def portfolio_export(portfolio, details, cash_summary):
    latest = pd.Timestamp(portfolio["latest_month"])
    items = portfolio_items(portfolio["companies"], details, cash_summary)
    scored = sum(1 for i in items if i["health_score"] is not None)
    return {
        "schema_version": "1.0", "source": "generated", "as_of": (latest + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d"),
        "period": f"24 meses hasta {_month_label(latest)}", "currency": "EUR",
        "summary": (f"{len(items)} empresas observadas, {scored} con Health Score en {_month_label(latest)}. "
                    "La atención combina trayectoria confirmada y dependencia de apoyo intragrupo; las empresas sin puntuar se muestran con su motivo."),
        "items": items,
    }


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, allow_nan=False)
    os.replace(tmp, path)


def _sample_evidence(evidence, company_id, window):
    rows = evidence.loc[(evidence.company_id == company_id) & evidence.month.isin(window)]
    total = len(rows)
    if not total:
        return rows
    # una muestra por categoría primero, después las de mayor importe
    rows = rows.assign(abs_amount=rows.amount.abs()).sort_values("abs_amount", ascending=False)
    picked = rows.groupby("bucket", sort=False).head(2)
    rest = rows.loc[~rows.index.isin(picked.index)]
    sample = pd.concat([picked, rest]).head(EVIDENCE_ROWS).drop(columns="abs_amount")
    sample.attrs["total_count"] = total
    return sample


def run(product_dir=PROCESSED_DIR / "product", out_dir=FRONTEND_GENERATED, verbose=True,
        advisor_dir=PROCESSED_DIR / "advisor_production", completer=None, llm_companies=None):
    """Exporta el contrato del frontend.

    `completer`: si se pasa, parafrasea assessment/summary solo para empresas en `llm_companies`
    (o todas si `llm_companies` es None). Sin completer, todo es plantilla determinista.
    Los grupos solo incorporan planes de `advisor_dir` generados con `--production-safe`.
    """
    product_dir, out_dir, advisor_dir = Path(product_dir), Path(out_dir), Path(advisor_dir)
    say = print if verbose else (lambda *a, **k: None)
    llm_set = None if llm_companies is None else {str(c) for c in llm_companies}
    portfolio = json.loads((product_dir / "portfolio.json").read_text(encoding="utf-8"))
    latest = pd.Timestamp(portfolio["latest_month"])
    summary = pd.read_parquet(product_dir / "cash_truth_summary.parquet")
    summary = summary[summary.month.eq(latest) & summary.currency.eq("EUR")].set_index("company_id")
    evidence_path = product_dir / "evidence" / "cash_truth_tx.parquet"
    evidence = pd.read_parquet(evidence_path) if evidence_path.exists() else pd.DataFrame(columns=["company_id", "currency", "month", "bucket", "transaction_id", "date", "amount", "category", "description"])
    evidence = evidence[evidence.currency.eq("EUR")]
    whatif_path = product_dir / "whatif_scenarios.parquet"
    whatif = pd.read_parquet(whatif_path) if whatif_path.exists() else None
    if whatif is not None:
        whatif = whatif[whatif.month.eq(latest)]
        whatif_groups = {cid: frame for cid, frame in whatif.groupby("company_id", sort=False)}
    else:
        whatif_groups = {}
    details, written, skipped, llm_used = {}, 0, 0, 0
    for file in sorted((product_dir / "companies").glob("COMP_*.json")):
        company = json.loads(file.read_text(encoding="utf-8"))
        block = (company.get("currencies") or {}).get("EUR") or {}
        window = [pd.Timestamp(m) for m in (block.get("cash_truth") or {}).get("window_months", [])]
        rows = _sample_evidence(evidence, company["company_id"], window) if window else evidence.iloc[:0]
        summary_row = summary.loc[company["company_id"]].to_dict() if company["company_id"] in summary.index else None
        use_llm = completer is not None and (llm_set is None or company["company_id"] in llm_set)
        detail = company_detail(
            company, summary_row, rows, whatif_groups.get(company["company_id"]),
            completer=completer if use_llm else None,
        )
        if detail is None:
            skipped += 1
            continue
        if use_llm:
            llm_used += 1
        details[company["company_id"]] = detail
        _write_json(out_dir / "companies" / f"{company['company_id']}.json", detail)
        written += 1
    groups = 0
    cash_by_company = {cid: row for cid, row in summary.to_dict(orient="index").items()}
    for file in sorted((product_dir / "groups").glob("GROUP_*.json")):
        group = json.loads(file.read_text(encoding="utf-8"))
        group.setdefault("latest_month", portfolio["latest_month"])
        plan_path = advisor_dir / "group_plans" / f"{group['group_id']}.json"
        advisor_plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None
        _write_json(out_dir / "groups" / f"{group['group_id']}.json",
                    group_detail(group, details, cash_by_company, advisor_plan))
        groups += 1
    _write_json(out_dir / "portfolio.json", portfolio_export(portfolio, details, cash_by_company))
    manifest = {"model_version": MODEL_VERSION, "latest_month": portfolio["latest_month"], "companies_written": written,
                "companies_without_score": skipped, "groups_written": groups, "weights": WEIGHTS,
                "companies_with_scenarios": len(whatif_groups),
                "llm_companies_attempted": llm_used,
                "product_manifest_sha256": _sha(product_dir / "_product_manifest.json"),
                "advisor_manifest_sha256": _sha(advisor_dir / "_advisor_manifest.json")}
    _write_json(out_dir / "_frontend_export_manifest.json", manifest)
    say(f"  empresas {written} (sin score: {skipped}) · grupos {groups} · portfolio {len(portfolio['companies'])} -> {out_dir}")
    if completer is not None:
        say(f"  LLM intentado en {llm_used} empresas (fallback a plantilla si el anclaje falla)")
    return manifest


def _sha(path: Path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
