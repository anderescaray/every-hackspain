"""Motor contrafactual del advisor: primitivas sobre la fila de señales de ventana y nivel V2 resultante.

Una `SignalRow` es un `dict` con las cinco señales base de la ventana de nivel (`H` meses con calidad)
y las tres derivadas que consume `xray.score_v2.level.score_level`:

    level_inflow_sum (I)          Σ entradas operativas
    window_outflow_sum (O)        Σ salidas operativas
    window_debt_service_sum (S)   Σ principal + intereses pagados
    ar_delay_w (a), ap_delay_w (p)   retraso AR/AP ponderado por pagos
    op_margin_w = (I−O)/(I+O)     debt_service_w = S/I     debt_without_inflow_w = (I == 0 y S > 0)

Cada primitiva describe un cambio sostenido de los flujos mensuales; tras `k` meses (`1 ≤ k ≤ H`) la
ventana mezcla `H−k` meses antiguos y `k` nuevos (spec `docs/group-optimization.md` §4). Las primitivas
son puras: devuelven una copia ya derivada y nunca mutan la entrada. Una señal base NaN se queda NaN:
el motor no inventa magnitudes que la ventana no observó. El nivel de cualquier escenario es la función
exacta de V2 (`score_level`) con la referencia congelada del mes; aquí no se aproxima nada.
"""
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from xray.score.level import COMPONENT_WEIGHTS
from xray.score_v2.level import score_level


SignalRow = dict

SIGNAL_BASE = ("level_inflow_sum", "window_outflow_sum", "window_debt_service_sum", "ar_delay_w", "ap_delay_w")
SIGNAL_DERIVED = ("op_margin_w", "debt_service_w", "debt_without_inflow_w")
LEVEL_INPUT_COLUMNS = ("op_margin_w", "debt_service_w", "debt_without_inflow_w", "ar_delay_w", "ap_delay_w")
LEVEL_RESULT_COLUMNS = ("level", "level_operations", "level_debt", "level_collections", "level_payments",
                        "level_coverage", "level_components_available", "has_uncovered_debt_service")
COMPONENTS = tuple(COMPONENT_WEIGHTS)
LEVERS = ("D1", "P")
_ADD_TOLERANCE = 1e-9


# ---------------------------------------------------------------- fila de señales


def _num(value):
    """Escalar float; None, NaN e infinitos se tratan como NaN."""
    if value is None:
        return math.nan
    try:
        value = float(value)
    except (TypeError, ValueError):
        return math.nan
    return value if math.isfinite(value) else math.nan


def _flag(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return bool(value)


def derive(row):
    """Copia de `row` con `op_margin_w`, `debt_service_w` y `debt_without_inflow_w` recalculadas desde las bases."""
    out = dict(row)
    inflow, outflow, service = (_num(out.get(c)) for c in SIGNAL_BASE[:3])
    total = inflow + outflow
    out["op_margin_w"] = (inflow - outflow) / total if total > 0 else math.nan
    out["debt_service_w"] = service / inflow if inflow > 0 and not math.isnan(service) else math.nan
    out["debt_without_inflow_w"] = bool(inflow == 0 and service > 0)
    return out


# ---------------------------------------------------------------- primitivas


def _check_step(k, horizon):
    if isinstance(horizon, bool) or not isinstance(horizon, (int, np.integer)) or horizon < 1:
        raise ValueError(f"horizon debe ser un entero ≥ 1, no {horizon!r}")
    if isinstance(k, bool) or not isinstance(k, (int, np.integer)) or not 1 <= k <= horizon:
        raise ValueError(f"k debe ser un entero en [1, {horizon}], no {k!r}")
    return k / horizon


def _check_param(name, value, low=None, high=None):
    value = _num(value)
    if math.isnan(value) or (low is not None and value < low) or (high is not None and value > high):
        bound = "" if low is None and high is None else (f" y en [{low}, {high}]" if high is not None else f" y ≥ {low}")
        raise ValueError(f"{name} debe ser finito{bound}, no {value!r}")
    return value


def _scaled(row, key, factor):
    out = dict(row)
    base = _num(out.get(key))
    out[key] = base * factor if not math.isnan(base) else math.nan
    return derive(out)


def inflow_scale(row, beta, k, horizon):
    """`I_k = I · (1 + kβ/H)`, β ≥ −1. Mueve margen y servicio de deuda a la vez."""
    step = _check_step(k, horizon)
    return _scaled(row, "level_inflow_sum", 1.0 + step * _check_param("beta", beta, -1.0))


def outflow_scale(row, alpha, k, horizon):
    """`O_k = O · (1 + kα/H)`, α ≥ −1. Solo mueve el margen operativo."""
    step = _check_step(k, horizon)
    return _scaled(row, "window_outflow_sum", 1.0 + step * _check_param("alpha", alpha, -1.0))


def debt_service_scale(row, phi, k, horizon):
    """`S_k = S · (1 + kφ/H)`, φ ≥ −1."""
    step = _check_step(k, horizon)
    return _scaled(row, "window_debt_service_sum", 1.0 + step * _check_param("phi", phi, -1.0))


def debt_service_add(row, delta, k, horizon):
    """`S_k = S + k·Δ` con Δ la cuota mensual asumida (o liberada si Δ < 0).

    Error si dejaría `S_k < 0`; un residuo negativo de redondeo (|S_k| ≤ 1e-9·max(1, |S|)) se toma como 0.
    Si `S` no está observado (NaN) se mantiene NaN.
    """
    _check_step(k, horizon)
    delta = _check_param("delta", delta)
    out = dict(row)
    base = _num(out.get("window_debt_service_sum"))
    if math.isnan(base):
        out["window_debt_service_sum"] = math.nan
        return derive(out)
    service = base + k * delta
    if service < 0:
        if abs(service) > _ADD_TOLERANCE * max(1.0, abs(base)):
            raise ValueError(f"debt_service_add dejaría el servicio de la ventana negativo ({service!r})")
        service = 0.0
    out["window_debt_service_sum"] = service
    return derive(out)


def ap_delay_scale(row, psi, k, horizon):
    """`p_k = p · (1 − kψ/H)`, 0 ≤ ψ ≤ 1."""
    step = _check_step(k, horizon)
    return _scaled(row, "ap_delay_w", 1.0 - step * _check_param("psi", psi, 0.0, 1.0))


def ar_delay_scale(row, theta, k, horizon):
    """`a_k = a · (1 − kθ/H)`, 0 ≤ θ ≤ 1."""
    step = _check_step(k, horizon)
    return _scaled(row, "ar_delay_w", 1.0 - step * _check_param("theta", theta, 0.0, 1.0))


PRIMITIVES = {f.__name__: f for f in (inflow_scale, outflow_scale, debt_service_scale, debt_service_add,
                                      ap_delay_scale, ar_delay_scale)}


# ---------------------------------------------------------------- nivel V2 de un escenario


def level_from_signals(rows, reference_state):
    """Nivel V2 (`score_level`) de cada fila; índice = ids en orden de inserción.

    Solo lee las cinco columnas que consume `score_level`; si a una fila le falta alguna derivada se
    recalcula con `derive` desde las bases. Las filas que ya vienen derivadas se usan tal cual.
    """
    ids = list(rows)
    prepared = [row if all(c in row for c in SIGNAL_DERIVED) else derive(row) for row in rows.values()]
    signals = pd.DataFrame(index=pd.Index(ids, dtype=object, name="company_id"))
    for column in LEVEL_INPUT_COLUMNS:
        if column == "debt_without_inflow_w":
            signals[column] = np.array([_flag(row.get(column)) for row in prepared], dtype=bool)
        else:
            signals[column] = np.array([_num(row.get(column)) for row in prepared], dtype=float)
    result, _ = score_level(signals, reference_state)
    return result[list(LEVEL_RESULT_COLUMNS)]


def component_scores(result_row):
    """Notas por componente `{operations, debt, collections, payments}` de una fila de `level_from_signals` (NaN → None)."""
    scores = {}
    for component in COMPONENTS:
        value = _num(result_row[f"level_{component}"])
        scores[component] = None if math.isnan(value) else value
    return scores


# ---------------------------------------------------------------- acciones de grupo


@dataclass(frozen=True)
class Action:
    lever: str                      # "D1" | "P"
    donor: str
    recipient: str
    donor_currency: str
    recipient_currency: str
    fraction: float
    amount_recipient_ccy: float     # D1: horizon·fraction·monthly_debt_service_b ; P: fraction·gap_b
    amount_donor_ccy: float         # convertido con la tabla FX (igual si misma moneda)
    fx_applied: float | None        # tipo aplicado c_b -> c_a, None si misma moneda
    psi: float | None               # solo P


@dataclass(frozen=True)
class ActionEffect:
    k: int
    donor_level_before: float
    donor_level_after: float
    recipient_level_before: float
    recipient_level_after: float
    donor_components_after: dict
    recipient_components_after: dict
    donor_signal_before: float          # la señal tocada
    donor_signal_after: float
    recipient_signal_before: float
    recipient_signal_after: float
    recipient_component_dropped: bool
    donor_hits_zero_inflow_indicator: bool


def apply_d1(row_a, row_b, phi, k, horizon, monthly_service_b_in_donor_ccy):
    """D1: la donante `a` asume la fracción φ del servicio de deuda de la receptora `b`.

    Receptora: `debt_service_scale(−φ)`. Donante: `debt_service_add(+φ·s_b)` con `s_b` la cuota mensual
    de `b` ya expresada en la moneda de `a`. El servicio externo del grupo no cambia: se redistribuye.
    Devuelve `(row_a', row_b')`.
    """
    phi = _check_param("phi", phi, 0.0, 1.0)
    monthly = _check_param("monthly_service_b_in_donor_ccy", monthly_service_b_in_donor_ccy, 0.0)
    return (debt_service_add(row_a, phi * monthly, k, horizon), debt_service_scale(row_b, -phi, k, horizon))


def apply_p(row_b, psi, k, horizon):
    """P: financiar el pago de proveedores a tiempo en `b`; `ap_delay_scale(ψ)`. El donante no cambia de señales."""
    return ap_delay_scale(row_b, psi, k, horizon)


def _level(result, company_id):
    return float(result.at[company_id, "level"])


def evaluate_action(rows, reference_state, action, k, horizon, monthly_service_b_in_donor_ccy=None):
    """Compone la acción sobre las filas de donante y receptora, recalcula sus niveles y describe el efecto.

    Solo se puntúan las dos filiales implicadas (`score_level` es fila a fila). `D1` exige
    `monthly_service_b_in_donor_ccy`; `P` exige `action.psi`.
    """
    if action.lever not in LEVERS:
        raise ValueError(f"Palanca desconocida: {action.lever!r}")
    if action.donor == action.recipient:
        raise ValueError("Donante y receptora deben ser filiales distintas")
    for company_id in (action.donor, action.recipient):
        if company_id not in rows:
            raise KeyError(f"No hay fila de señales para {company_id}")
    row_a, row_b = rows[action.donor], rows[action.recipient]
    before = level_from_signals({action.donor: row_a, action.recipient: row_b}, reference_state)
    if action.lever == "D1":
        if monthly_service_b_in_donor_ccy is None:
            raise ValueError("D1 requiere monthly_service_b_in_donor_ccy (cuota mensual de b en moneda de a)")
        row_a2, row_b2 = apply_d1(row_a, row_b, action.fraction, k, horizon, monthly_service_b_in_donor_ccy)
        signal = "debt_service_w"
    else:
        if action.psi is None:
            raise ValueError("P requiere action.psi")
        row_a2, row_b2 = dict(row_a), apply_p(row_b, action.psi, k, horizon)
        signal = "ap_delay_w"
    after = level_from_signals({action.donor: row_a2, action.recipient: row_b2}, reference_state)
    debt_before, debt_after = before.at[action.recipient, "level_debt"], after.at[action.recipient, "level_debt"]
    return ActionEffect(
        k=int(k),
        donor_level_before=_level(before, action.donor), donor_level_after=_level(after, action.donor),
        recipient_level_before=_level(before, action.recipient), recipient_level_after=_level(after, action.recipient),
        donor_components_after=component_scores(after.loc[action.donor]),
        recipient_components_after=component_scores(after.loc[action.recipient]),
        donor_signal_before=_num(row_a.get(signal)), donor_signal_after=_num(row_a2.get(signal)),
        recipient_signal_before=_num(row_b.get(signal)), recipient_signal_after=_num(row_b2.get(signal)),
        recipient_component_dropped=bool(action.lever == "D1" and pd.notna(debt_before) and pd.isna(debt_after)),
        donor_hits_zero_inflow_indicator=bool(_flag(row_a2.get("debt_without_inflow_w"))
                                              and not _flag(row_a.get("debt_without_inflow_w"))),
    )
