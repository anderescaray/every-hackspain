"""Objetivo del plan de grupo: utilidad cóncava por tramos y utilidad de grupo `G` (spec §5.3).

`U(L)` es lineal a tramos con las pendientes de `config.utility_knots` (por defecto 3 en [0,40),
2 en [40,70) y 1 en [70,100]; `U(100) = 210`). `G = Σ ω_i U(L_i) / (U(100)·Σ ω_i) · 100` vive en
0–100 y no es el consolidado grupo-moneda de V2. Las filiales sin nivel (NaN) no entran en `G`.
"""
import math

import numpy as np

from xray.group_advisor.config import TRAMO_LABELS, AdvisorConfig
from xray.group_advisor.state import tramo_of

LEVEL_MAX = 100.0


def _num(value):
    if value is None:
        return math.nan
    try:
        value = float(value)
    except (TypeError, ValueError):
        return math.nan
    return value if math.isfinite(value) else math.nan


def utility(level, config=None):
    """`U(L) = Σ_i pendiente_i · clip(L − inicio_i, 0, inicio_{i+1} − inicio_i)`, con el último tramo hasta 100; NaN si `L` es NaN."""
    config = config or AdvisorConfig()
    level = _num(level)
    if math.isnan(level):
        return math.nan
    level = min(max(level, 0.0), LEVEL_MAX)
    knots = [(float(start), float(slope)) for start, slope in config.utility_knots]
    total = 0.0
    for index, (start, slope) in enumerate(knots):
        end = knots[index + 1][0] if index + 1 < len(knots) else LEVEL_MAX
        total += slope * min(max(level - start, 0.0), end - start)
    return total


def utility_max(config=None):
    """`U(100)`: normalizador de `G` (210 con los nudos por defecto)."""
    return utility(LEVEL_MAX, config)


def group_utility(levels, weights=None, config=None):
    """`G` en 0–100 sobre las filiales con nivel finito; NaN si no hay ninguna o los pesos suman 0."""
    config = config or AdvisorConfig()
    levels = [_num(value) for value in levels]
    weights = [1.0] * len(levels) if weights is None else [_num(value) for value in weights]
    if len(weights) != len(levels):
        raise ValueError("levels y weights deben tener la misma longitud")
    numerator = denominator = 0.0
    for level, weight in zip(levels, weights):
        if math.isnan(level) or math.isnan(weight):
            continue
        numerator += weight * utility(level, config)
        denominator += weight
    if denominator <= 0:
        return math.nan
    return numerator / (utility_max(config) * denominator) * 100.0


def subsidiary_weights(state, config=None):
    """`ω_i` por `company_id`: 1.0 (`equal`) o `level_inflow_sum + window_outflow_sum` con NaN → 0 (`size`)."""
    config = config or AdvisorConfig()
    frame = state.subsidiaries
    if config.subsidiary_weighting == "size":
        inflow = frame.level_inflow_sum.to_numpy(dtype=float)
        outflow = frame.window_outflow_sum.to_numpy(dtype=float)
        size = np.nan_to_num(inflow, nan=0.0) + np.nan_to_num(outflow, nan=0.0)
        return {str(cid): float(value) for cid, value in zip(frame.index, size)}
    return {str(cid): 1.0 for cid in frame.index}


def tramo(level, config=None):
    """`red` / `amber` / `green` según `config.tramo_bounds`; `none` sin nivel."""
    config = config or AdvisorConfig()
    return tramo_of(_num(level), config.tramo_bounds)


def levels_by_tramo(levels, config=None):
    """Conteo `{"red": n, "amber": n, "green": n}` de los niveles finitos."""
    config = config or AdvisorConfig()
    counts = {label: 0 for label in TRAMO_LABELS}
    for level in levels:
        label = tramo(level, config)
        if label in counts:
            counts[label] += 1
    return counts
