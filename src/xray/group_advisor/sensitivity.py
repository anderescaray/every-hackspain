"""Sensibilidad de empresa `company_sensitivity_v1` (spec `docs/group-optimization.md` §6, §8.2).

Para cada empresa puntuada evalúa cinco palancas **aisladas** sobre su fila de señales de ventana con la
función exacta de nivel de V2 (`counterfactual.level_from_signals`) y la referencia congelada del mes:
`cut_outflow`, `raise_inflow` (negocio: solo sensibilidad, nunca recomendación), `debt_service_cut`,
`ap_on_time`, `ar_faster` (tesorería). Por palanca: disponibilidad con motivo, rejilla en la dirección buena
(k=1 y k=H), pendiente actual por diferencia finita (por 1 %, por unidad natural y por 10.000 de equivalente
de caja), siguiente nudo de la señal (anclas ∪ referencia empírica) convertido a magnitud, cuánto hace falta
para el siguiente tramo (búsqueda monótona en `r ∈ [0, r_max]`) y factibilidad con caja propia (`ap_on_time`).

Todo `r` es un cambio relativo respecto a la magnitud actual; la pendiente «por 1 %» es por un 1 % de esa
magnitud. Momentum no se simula: `score' = clip(L' + momentum_adjustment, 0, 100)`. La salida es un `dict`
con tipos nativos JSON (NaN → `None`; floats a 6 decimales, o 6 cifras significativas si |x| < 1e-3 para no
perder la pendiente por unidad monetaria) con la estructura exacta de `tests/fixtures/advisor_sensitivity_*.json`.
"""
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from xray.group_advisor import counterfactual as cf
from xray.group_advisor.config import SENSITIVITY_LEVERS, AdvisorConfig
from xray.group_advisor.state import GroupState, iter_group_states, tramo_of

METHOD = "company_sensitivity_v1"
SCHEMA_VERSION = 1
MIN_DELAY_COUNT = 5          # mismo soporte mínimo que V2 (`min_delay_count`) para retrasos AR/AP
KNOT_RTOL = 1e-9             # «estrictamente en la dirección buena» con tolerancia relativa
SEARCH_POINTS = 16           # puntos por ronda de la búsqueda monótona (una llamada a score_level por ronda)
LEVER_ASSUMPTIONS = ("estacionariedad", "las demas magnitudes no cambian")
ASSUMPTIONS = ("estacionariedad de flujos, cuotas y numero de pagos en la ventana",
               "cada palanca se evalua aislada; las demas magnitudes no cambian",
               "momentum no simulado: el score contrafactual mantiene el ajuste del baseline",
               "las palancas de negocio (salidas y entradas operativas) son sensibilidad con todo lo demas igual, no recomendacion")
LIMITATIONS = ("sensibilidad mecanica sobre el nivel V2, no recomendacion ejecutable ni prediccion",
               "las palancas de negocio no incorporan el coste de vender mas ni de recortar",
               "biseccion por palanca aislada; combinaciones no exploradas",
               "caja reconstruida hacia atras desde la foto final; no es saldo observado y sin fiabilidad no hay factibilidad",
               "fiscalidad, legal, covenants y reaccion de clientes/proveedores: fuera de los datos, fuera del modelo",
               "nada contrastado con Embat ni con la nota oculta del leaderboard")
FEASIBILITY_NOTES = {"cut_outflow": "decision de negocio; sensibilidad, no recomendacion",
                     "raise_inflow": "decision de negocio; sensibilidad, no recomendacion",
                     "debt_service_cut": "renegociacion con el acreedor", "ar_faster": "gestion de cobro con clientes"}


@dataclass(frozen=True)
class LeverSpec:
    type: str
    component: str
    primitive: str
    quantity: str
    unit_kind: str          # "money" | "days"
    direction: str          # "decrease" | "increase"
    signal_key: str         # señal de V2 cuyas anclas dan los nudos
    sign: float             # parámetro de la primitiva = sign · r
    base_key: str           # columna de la que sale la magnitud (suma de ventana o retraso)
    unavailable_reason: str
    evidence_fields: tuple


LEVER_SPECS = {
    "cut_outflow": LeverSpec("business", "operations", "outflow_scale", "monthly_operating_outflow", "money", "decrease",
                             "op_margin_w", -1.0, "window_outflow_sum", "no_operating_outflow",
                             ("window_outflow_sum", "level_inflow_sum")),
    "raise_inflow": LeverSpec("business", "operations", "inflow_scale", "monthly_operating_inflow", "money", "increase",
                              "op_margin_w", 1.0, "level_inflow_sum", "no_operating_inflow",
                              ("level_inflow_sum", "window_outflow_sum", "window_debt_service_sum")),
    "debt_service_cut": LeverSpec("treasury", "debt", "debt_service_scale", "monthly_debt_service", "money", "decrease",
                                  "debt_service_w", -1.0, "window_debt_service_sum", "no_debt_service_observed",
                                  ("window_debt_service_sum", "level_inflow_sum")),
    "ap_on_time": LeverSpec("treasury", "payments", "ap_delay_scale", "ap_delay_w", "days", "decrease",
                            "ap_delay_w", 1.0, "ap_delay_w", "ap_component_unavailable",
                            ("inv_ap_overdue_amount", "inv_ap_due_30_amount", "inv_ap_due_60_amount", "reconstructed_cash", "runway_months")),
    "ar_faster": LeverSpec("treasury", "collections", "ar_delay_scale", "ar_delay_w", "days", "decrease",
                           "ar_delay_w", 1.0, "ar_delay_w", "ar_component_unavailable", ("inv_ar_open_amount",)),
}
assert tuple(LEVER_SPECS) == SENSITIVITY_LEVERS


# ---------------------------------------------------------------- utilidades


def _num(value):
    return cf._num(value)


def _finite(value):
    return not math.isnan(_num(value))


def _get(sub_row, key):
    return _num(sub_row[key]) if key in sub_row.index else math.nan


def _text(value):
    return None if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value)


def _spec(lever):
    if lever not in LEVER_SPECS:
        raise ValueError(f"Palanca de sensibilidad desconocida: {lever!r}")
    return LEVER_SPECS[lever]


def _r_cap(lever, config):
    """`r_max` de la palanca acotado al dominio de su primitiva (las de disminución no admiten r > 1)."""
    r_max = float(config.sensitivity_r_max[lever])
    return r_max if _spec(lever).direction == "increase" else min(r_max, 1.0)


def _round(value):
    if not math.isfinite(value):
        return None
    rounded = round(value, 6) if abs(value) >= 1e-3 else float(f"{value:.6g}")
    return 0.0 if rounded == 0 else rounded


def _clean(node):
    """Tipos nativos JSON: numpy → Python, NaN/inf → None, floats redondeados; recursivo en dict/list/tuple."""
    if node is None or isinstance(node, str):
        return node
    if isinstance(node, (bool, np.bool_)):
        return bool(node)
    if isinstance(node, (int, np.integer)):
        return int(node)
    if isinstance(node, (float, np.floating)):
        return _round(float(node))
    if isinstance(node, dict):
        return {str(key): _clean(value) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_clean(value) for value in node]
    if isinstance(node, pd.Timestamp):
        return str(node.date())
    raise TypeError(f"Valor no serializable en la sensibilidad: {type(node).__name__}")


# ---------------------------------------------------------------- palancas: disponibilidad, aplicación, magnitudes


def lever_available(sub_row, signal_row, lever, reference_state=None):
    """`(disponible, motivo)` según §6.1: `O > 0`, `I > 0`, `S > 0` (con `I > 0`), retraso finito, válido, > 0 y con soporte."""
    spec = _spec(lever)
    inflow, outflow, service = (_num(signal_row.get(c)) for c in cf.SIGNAL_BASE[:3])
    if lever == "cut_outflow":
        return (True, None) if outflow > 0 else (False, spec.unavailable_reason)
    if lever == "raise_inflow":
        return (True, None) if inflow > 0 else (False, spec.unavailable_reason)
    if lever == "debt_service_cut":
        if not service > 0:
            return False, spec.unavailable_reason
        return (True, None) if inflow > 0 else (False, "debt_without_inflow_indicator")
    prefix = "ap" if lever == "ap_on_time" else "ar"
    delay, count = _num(signal_row.get(f"{prefix}_delay_w")), _get(sub_row, f"{prefix}_delay_count_w")
    if math.isnan(delay) or (not math.isnan(count) and count < MIN_DELAY_COUNT):
        return False, spec.unavailable_reason
    if reference_state is not None:
        feature = reference_state["features"][spec.signal_key]
        low, high = feature.get("valid_min"), feature.get("valid_max")
        if (low is not None and delay < low) or (high is not None and delay > high):
            return False, spec.unavailable_reason
    return (True, None) if delay > 0 else (False, f"{prefix}_delay_already_zero")


def apply_lever(signal_row, lever, r, k, horizon):
    """Fila tras `k` meses con la palanca sostenida a cambio relativo `r ≥ 0` en la dirección buena."""
    spec = _spec(lever)
    return cf.PRIMITIVES[spec.primitive](signal_row, spec.sign * float(r), k, horizon)


def level_at(signal_row, reference_state):
    return float(cf.level_from_signals({"x": signal_row}, reference_state).level.iloc[0])


def _levels(signal_row, lever, rs, k, horizon, reference_state):
    """Niveles en `k` para cada `r` de `rs`, en una sola llamada a `score_level`."""
    rows = {str(i): apply_lever(signal_row, lever, r, k, horizon) for i, r in enumerate(rs)}
    return cf.level_from_signals(rows, reference_state).level.to_numpy(dtype=float)


def quantity_now(signal_row, lever, horizon):
    """Magnitud mostrada: mensual (`suma de ventana / H`) para dinero, días para retrasos."""
    spec = _spec(lever)
    base = _num(signal_row.get(spec.base_key))
    return base / horizon if spec.unit_kind == "money" else base


def quantity_after(quantity, lever, r):
    return quantity * (1.0 - r) if _spec(lever).direction == "decrease" else quantity * (1.0 + r)


def cash_equivalent(sub_row, lever, r):
    """§6.2.1: `r·O`, `r·S`, `r·(V + D30)` (NaN omitidos; None si ambos NaN); sin equivalente para `raise_inflow` y `ar_faster`."""
    if lever == "cut_outflow":
        base = _get(sub_row, "window_outflow_sum")
    elif lever == "debt_service_cut":
        base = _get(sub_row, "window_debt_service_sum")
    elif lever == "ap_on_time":
        terms = [v for v in (_get(sub_row, "inv_ap_overdue_amount"), _get(sub_row, "inv_ap_due_30_amount")) if not math.isnan(v)]
        base = sum(terms) if terms else math.nan
    else:
        return None
    return None if math.isnan(base) else float(r) * base


# ---------------------------------------------------------------- pendiente, nudos, tramo, rejilla


def _signal_knots(reference_state, feature):
    spec = reference_state["features"][feature]
    knots = {float(anchor[0]) for anchor in spec["anchors"]}
    if spec.get("empirical_active") and spec.get("reference_low") is not None and spec.get("reference_high") is not None:
        knots |= {float(spec["reference_low"]), float(spec["reference_high"])}
    return sorted(knots)


def knot_quantities(signal_row, lever, reference_state, horizon):
    """Nudos de la señal convertidos a la magnitud de la palanca (§6.2.3), ordenados, sin infinitos.

    Margen con `I` fijo (`cut_outflow`): `O* = I·(1−m*)/(1+m*)`; con `O` fijo (`raise_inflow`): `I* = O·(1+m*)/(1−m*)`
    y además los nudos del servicio de deuda `I* = S/d*` porque `d = S/I` también se mueve; `debt_service_cut`:
    `S* = d*·I`; retrasos: identidad. Dinero en mensual (`/H`).
    """
    spec = _spec(lever)
    inflow, outflow, service = (_num(signal_row.get(c)) for c in cf.SIGNAL_BASE[:3])
    out = []
    if lever == "cut_outflow":
        out = [inflow * (1.0 - m) / (1.0 + m) / horizon for m in _signal_knots(reference_state, "op_margin_w") if m > -1.0]
    elif lever == "raise_inflow":
        out = [outflow * (1.0 + m) / (1.0 - m) / horizon for m in _signal_knots(reference_state, "op_margin_w") if m < 1.0]
        if service > 0:
            out += [service / d / horizon for d in _signal_knots(reference_state, "debt_service_w") if d > 0]
    elif lever == "debt_service_cut":
        out = [d * inflow / horizon for d in _signal_knots(reference_state, "debt_service_w")]
    else:
        out = list(_signal_knots(reference_state, spec.signal_key))
    return sorted({q for q in out if math.isfinite(q)})


def next_knot(sub_row, signal_row, lever, reference_state, config):
    """`(valid_until, slope_after)`: primer nudo estrictamente en la dirección buena y pendiente por 1 % justo después.

    `None, None` si no hay nudo alcanzable con `r ≤ r_max`; `slope_after=None` si el nudo se alcanza justo en
    `r_max` (no hay dominio detrás para la diferencia finita).
    """
    spec, horizon, eps = _spec(lever), config.horizon_months, config.finite_difference_eps
    now = quantity_now(signal_row, lever, horizon)
    knots = knot_quantities(signal_row, lever, reference_state, horizon)
    if spec.direction == "decrease":
        candidates = [q for q in knots if q < now * (1.0 - KNOT_RTOL)]
        target = max(candidates) if candidates else None
    else:
        candidates = [q for q in knots if q > now * (1.0 + KNOT_RTOL)]
        target = min(candidates) if candidates else None
    if target is None:
        return None, None
    r_knot = abs(target - now) / now
    cap = _r_cap(lever, config)
    if r_knot > cap:
        return None, None
    if r_knot + eps > cap:
        return target, None
    before, after = _levels(signal_row, lever, [r_knot, r_knot + eps], horizon, horizon, reference_state)
    return target, (after - before) / eps / 100.0


def slope_now(sub_row, signal_row, lever, reference_state, config):
    """Pendiente actual por diferencia finita `ε` en k=H: por 1 % de `r`, por unidad natural y por 10.000 de caja."""
    horizon, eps = config.horizon_months, config.finite_difference_eps
    base, bumped = _levels(signal_row, lever, [0.0, eps], horizon, horizon, reference_state)
    slope = (bumped - base) / eps
    now = quantity_now(signal_row, lever, horizon)
    per_cash = cash_equivalent(sub_row, lever, 1.0)
    valid_until, slope_after = next_knot(sub_row, signal_row, lever, reference_state, config)
    return {"level_per_pct": slope / 100.0, "level_per_unit": slope / now,
            "level_per_10k": slope * 10000.0 / per_cash if per_cash is not None and per_cash > 0 else None,
            "valid_until": valid_until, "slope_after": slope_after}


def _min_r_reaching(evaluate, lo, hi, target, tol, points=SEARCH_POINTS):
    """Mínimo `r` con `L(r) ≥ target` para `L` monótona no decreciente, dados `L(lo) < target ≤ L(hi)`.

    Búsqueda por rondas de `points` puntos (una evaluación vectorizada por ronda) hasta `hi − lo ≤ tol`;
    devuelve `hi`, que cumple `L(hi − tol) ≤ L(lo) < target ≤ L(hi)`.
    """
    while hi - lo > tol:
        inner = np.linspace(lo, hi, points + 1)[1:-1]
        values = evaluate(inner)
        above = np.flatnonzero(values >= target)
        if len(above):
            j = int(above[0])
            lo, hi = (float(inner[j - 1]) if j else lo), float(inner[j])
        else:
            lo = float(inner[-1])
    return hi


def next_tramo_target(level, config):
    """Primera frontera de `tramo_bounds` estrictamente mayor que el nivel; None si no la hay (o sin nivel)."""
    level = _num(level)
    if math.isnan(level):
        return None
    return next((float(b) for b in config.tramo_bounds if b > level), None)


def to_next_tramo(sub_row, signal_row, lever, reference_state, config):
    """§6.2.4: `r*` mínimo con `L(r*) ≥ objetivo` en k=H dentro de `[0, r_max]`, magnitud resultante y equivalente de caja."""
    horizon = config.horizon_months
    target = next_tramo_target(_get(sub_row, "level"), config)
    result = {"target": target, "rel_change_needed": None, "quantity_needed": None, "reachable": False, "cash_equivalent": None}
    if target is None:
        return result
    cap = _r_cap(lever, config)
    base, top = _levels(signal_row, lever, [0.0, cap], horizon, horizon, reference_state)
    if not top >= target:
        return result
    if base >= target:
        r_star = 0.0
    else:
        r_star = _min_r_reaching(lambda rs: _levels(signal_row, lever, rs, horizon, horizon, reference_state),
                                 0.0, cap, target, config.bisection_tol)
    result.update(rel_change_needed=r_star, quantity_needed=quantity_after(quantity_now(signal_row, lever, horizon), lever, r_star),
                  reachable=True, cash_equivalent=cash_equivalent(sub_row, lever, r_star))
    return result


def grid(sub_row, signal_row, lever, reference_state, config):
    """Rejilla `config.sensitivity_grid` (≤ r_max): magnitud, nivel en cada `k` de `report_k` (y H), score en k=H, caja."""
    horizon = config.horizon_months
    ks = sorted(set(config.report_k) | {horizon})
    rs = [float(r) for r in config.sensitivity_grid if r <= _r_cap(lever, config)]
    levels = {k: _levels(signal_row, lever, rs, k, horizon, reference_state) for k in ks}
    momentum = _get(sub_row, "momentum_adjustment")
    momentum = 0.0 if math.isnan(momentum) else momentum
    now = quantity_now(signal_row, lever, horizon)
    rows = []
    for i, r in enumerate(rs):
        entry = {"rel_change": r, "quantity_after": quantity_after(now, lever, r)}
        for k in ks:
            entry[f"level_after_k{k}"] = float(levels[k][i])
        entry[f"score_after_k{horizon}"] = float(np.clip(levels[horizon][i] + momentum, 0.0, 100.0))
        entry["cash_equivalent"] = cash_equivalent(sub_row, lever, r)
        rows.append(entry)
    return rows


# ---------------------------------------------------------------- liquidez, factibilidad, ranking, nota


def liquidity(sub_row, config):
    """Caja reconstruida (solo si fiable), colchón `B_i = max(κ·(O3 + s), D30 + D60)` con NaN omitidos y exceso `max(0, C − B)`."""
    kappa = float(config.donor_buffer_months)
    flows = [v for v in (_get(sub_row, "tx_outflow_ma3"), _get(sub_row, "monthly_debt_service")) if not math.isnan(v)]
    payables = [v for v in (_get(sub_row, "inv_ap_due_30_amount"), _get(sub_row, "inv_ap_due_60_amount")) if not math.isnan(v)]
    candidates = ([kappa * sum(flows)] if flows else []) + ([sum(payables)] if payables else [])
    buffer = max(candidates) if candidates else None
    cash = _get(sub_row, "reconstructed_cash")
    reliable = bool(sub_row["cash_reliable"]) and not math.isnan(cash) if "cash_reliable" in sub_row.index else not math.isnan(cash)
    excess = max(0.0, cash - buffer) if reliable and buffer is not None else None
    return {"reconstructed_cash": cash if reliable else None, "reliable": reliable, "buffer": buffer, "excess_cash": excess}


def feasibility(sub_row, lever, config):
    """§6.2.5 para `ap_on_time` (caja necesaria = pagar todo el AP vencido y a 30 días); nota fija para las demás."""
    liq = liquidity(sub_row, config)
    excess = liq["excess_cash"]
    if lever != "ap_on_time":
        return {"feasible_alone": None, "cash_needed": None, "own_excess_cash": excess, "note": FEASIBILITY_NOTES[lever]}
    needed = cash_equivalent(sub_row, lever, 1.0)
    if excess is None:
        note = "caja no fiable" if not liq["reliable"] else "colchon no calculable: salidas medias y vencimientos no observados"
        return {"feasible_alone": None, "cash_needed": needed, "own_excess_cash": None, "note": note}
    if needed is None:
        return {"feasible_alone": None, "cash_needed": None, "own_excess_cash": excess, "note": "AP vencido y proximo no observados"}
    feasible = excess >= needed
    return {"feasible_alone": bool(feasible), "cash_needed": needed, "own_excess_cash": excess,
            "note": "alcanzable con caja propia" if feasible else "requiere financiacion"}


def _sort_key(lever, metric):
    value = _num(lever["slope_now"][metric])
    return (-(value if not math.isnan(value) else -math.inf), lever["lever"])


def ranking(levers):
    """`by_pct`: disponibles por `level_per_pct` desc; `by_cash`: disponibles con `level_per_10k` por ese valor desc; empate por nombre."""
    available = [lv for lv in levers if lv.get("available")]
    with_cash = [lv for lv in available if lv["slope_now"]["level_per_10k"] is not None]
    return {"by_pct": [lv["lever"] for lv in sorted(available, key=lambda lv: _sort_key(lv, "level_per_pct"))],
            "by_cash": [lv["lever"] for lv in sorted(with_cash, key=lambda lv: _sort_key(lv, "level_per_10k"))]}


def structural_note(sub_row, config):
    """§6.2.7: si `level_operations < tramo_bounds[0]`, el margen arrastra el nivel y no es palanca de tesorería."""
    operations, margin = _get(sub_row, "level_operations"), _get(sub_row, "op_margin_w")
    if math.isnan(operations) or not operations < config.tramo_bounds[0]:
        return None
    margin_text = "n/d" if math.isnan(margin) else f"{margin:.2f}".replace(".", ",")
    return (f"El margen 6m ({margin_text}) es el componente que arrastra el nivel; recortar salidas o subir entradas "
            "son decisiones de negocio, no de tesoreria.")


# ---------------------------------------------------------------- documento por empresa


def _lever_block(sub_row, signal_row, lever, reference_state, config, evidence):
    spec = _spec(lever)
    available, reason = lever_available(sub_row, signal_row, lever, reference_state)
    head = {"lever": lever, "type": spec.type, "component": spec.component, "available": available}
    if not available:
        return {**head, "reason": reason}
    unit = _text(sub_row["currency"]) if spec.unit_kind == "money" else "days"
    return {**head, "quantity": spec.quantity, "unit": unit, "current": quantity_now(signal_row, lever, config.horizon_months),
            "direction": spec.direction,
            "slope_now": slope_now(sub_row, signal_row, lever, reference_state, config),
            "grid": grid(sub_row, signal_row, lever, reference_state, config),
            "to_next_tramo": to_next_tramo(sub_row, signal_row, lever, reference_state, config),
            "feasibility": feasibility(sub_row, lever, config),
            "assumptions": list(LEVER_ASSUMPTIONS),
            "evidence": [eid for eid, item in evidence.items() if item["field"] in spec.evidence_fields]}


def _baseline(sub_row, signal_row, level, config):
    return {"level": level, "score": _get(sub_row, "score"), "momentum_adjustment": _get(sub_row, "momentum_adjustment"),
            "tramo": tramo_of(None if math.isnan(level) else level, config.tramo_bounds),
            "components": {c: _get(sub_row, f"level_{c}") for c in cf.COMPONENTS},
            "signals": {"op_margin_w": signal_row["op_margin_w"], "debt_service_w": signal_row["debt_service_w"],
                        "ar_delay_w": signal_row["ar_delay_w"], "ap_delay_w": signal_row["ap_delay_w"],
                        "level_inflow_sum": signal_row["level_inflow_sum"], "window_outflow_sum": signal_row["window_outflow_sum"],
                        "monthly_debt_service": _get(sub_row, "monthly_debt_service")},
            "liquidity": liquidity(sub_row, config),
            "ap": {"overdue_amount": _get(sub_row, "inv_ap_overdue_amount"), "due_30": _get(sub_row, "inv_ap_due_30_amount"),
                   "due_60": _get(sub_row, "inv_ap_due_60_amount")}}


def company_sensitivity(state: GroupState, company_id, config=None):
    """JSON (dict de tipos nativos) de la sensibilidad de `company_id` en `state` con el esquema de la spec §8.2.

    `status="not_scored"` (sin palancas ni ranking) si la empresa no tiene nivel. `group_context` queda vacío
    (`has_group_plan=None`): lo rellena el pipeline con el papel de la empresa en el plan de su grupo.
    """
    config = config or AdvisorConfig()
    if company_id not in state.subsidiaries.index:
        raise KeyError(f"{company_id} no pertenece al estado de {state.group_id}")
    sub_row = state.subsidiaries.loc[company_id]
    signal_row = state.signal_row(company_id)
    level = _get(sub_row, "level")
    scored = not math.isnan(level)
    evidence = {eid: dict(item) for eid, item in state.evidence.items() if item["company_id"] == company_id}
    levers = ([_lever_block(sub_row, signal_row, lever, state.reference_state, config, evidence) for lever in SENSITIVITY_LEVERS]
              if scored else [])
    doc = {"schema_version": SCHEMA_VERSION, "method": METHOD, "company_id": str(company_id), "group_id": _text(sub_row["group_id"]),
           "currency": _text(sub_row["currency"]), "month": str(pd.Timestamp(state.month).date()),
           "status": "sensitivity" if scored else "not_scored", "score_reason": _text(sub_row["score_reason"]),
           "baseline": _baseline(sub_row, signal_row, level, config),
           "group_context": {"has_group_plan": None, "role": None, "steps": []},
           "next_tramo_target": next_tramo_target(level, config), "levers": levers, "ranking": ranking(levers),
           "structural_note": structural_note(sub_row, config) if scored else None,
           "assumptions": list(ASSUMPTIONS), "limitations": list(LIMITATIONS), "evidence": evidence,
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "inputs_sha256": dict(state.inputs_sha256)}
    return _clean(doc)


def iter_company_sensitivities(inputs, month=None, config=None):
    """Genera `(company_id, sensibilidad)` para todas las empresas con fila en `month`, ordenado por `company_id`."""
    config = config or AdvisorConfig()
    states = list(iter_group_states(inputs, month, config))
    pairs = sorted((str(company_id), state) for state in states for company_id in state.subsidiaries.index)
    for company_id, state in pairs:
        yield company_id, company_sensitivity(state, company_id, config)


def sensitivity_to_json(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False)
