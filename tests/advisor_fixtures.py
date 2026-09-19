"""Fixtures sintéticas del advisor: estados de grupo construidos a mano (WP1; los usan WP2, WP3 y WP7).

`make_group_state(rows)` recibe una lista de dicts con al menos `company_id`; el resto de
columnas del contrato se rellena con NaN. Las derivadas `op_margin_w`, `debt_service_w` y
`debt_without_inflow_w` se calculan desde `level_inflow_sum` / `window_outflow_sum` /
`window_debt_service_sum` si no se pasan; si no se pasa `level`, el nivel y sus componentes
se calculan con `xray.score_v2.level.score_level` sobre las señales y la referencia (por
defecto anclas puras), aplicando la regla de V2 de nivel nulo sin componente de operaciones
o con cobertura < 0,4. `cash_reliable` por defecto es verdadero cuando se pasa una caja.
"""
import math

import numpy as np
import pandas as pd

from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.state import NUMERIC_BASE_COLUMNS, assemble_group_state
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.level import fit_reference, score_level

LEVEL_COMPONENTS = ("level", "level_operations", "level_debt", "level_collections", "level_payments", "level_coverage")
SIGNAL_INPUTS = ("op_margin_w", "debt_service_w", "debt_without_inflow_w", "ar_delay_w", "ap_delay_w")


def anchor_reference_state():
    """Referencia de nivel con anclas puras (sin componente empírico): `fit_reference` sobre un DataFrame vacío."""
    return fit_reference(pd.DataFrame())


def _finite(value):
    return value is not None and isinstance(value, (int, float, np.floating, np.integer)) and math.isfinite(float(value))


def derive_signals(inflow, outflow, service):
    """Derivadas de la spec §4 desde las sumas de ventana: margen, servicio de deuda e indicador."""
    margin = (inflow - outflow) / (inflow + outflow) if _finite(inflow) and _finite(outflow) and inflow + outflow > 0 else np.nan
    debt = service / inflow if _finite(inflow) and _finite(service) and inflow > 0 else np.nan
    indicator = bool(_finite(inflow) and _finite(service) and inflow == 0 and service > 0)
    return margin, debt, indicator


def make_group_state(rows, month="2026-08-01", reference_state=None, config=None, group_id="GROUP_TEST", consolidated_scores=None):
    config = config or AdvisorConfig()
    reference_state = anchor_reference_state() if reference_state is None else reference_state
    records, explicit_level = [], set()
    for row in rows:
        if "company_id" not in row:
            raise ValueError("Cada fila necesita company_id")
        record = {column: np.nan for column in NUMERIC_BASE_COLUMNS}
        record.update(currency="EUR", group_id=group_id, score_status=None, score_reason=None)
        record.update(row)
        margin, debt, indicator = derive_signals(record["level_inflow_sum"], record["window_outflow_sum"], record["window_debt_service_sum"])
        defaults = {"op_margin_w": margin, "debt_service_w": debt, "debt_without_inflow_w": indicator,
                    "cash_reliable": _finite(record["reconstructed_cash"])}
        record.update({key: value for key, value in defaults.items() if key not in row})
        if "level" in row:
            explicit_level.add(str(row["company_id"]))
        records.append(record)
    frame = pd.DataFrame.from_records(records).set_index("company_id")
    frame.index = frame.index.astype(str)
    frame = frame.sort_index()
    frame["debt_without_inflow_w"] = frame.debt_without_inflow_w.eq(True)
    computed = ~frame.index.isin(sorted(explicit_level))
    if computed.any():
        level, _ = score_level(frame.loc[computed, list(SIGNAL_INPUTS)], reference_state)
        unusable = level.level_operations.isna() | level.level_coverage.lt(ScoreV2Config().min_level_coverage)
        level.loc[unusable, "level"] = np.nan
        for column in LEVEL_COMPONENTS:
            frame.loc[computed, column] = level[column].to_numpy()
    frame["momentum_adjustment"] = pd.to_numeric(frame.momentum_adjustment, errors="coerce").fillna(0.).where(frame.level.notna())
    frame["score"] = pd.to_numeric(frame.score, errors="coerce").fillna((frame.level + frame.momentum_adjustment).clip(0, 100))
    scored = frame.level.notna()
    frame["score_status"] = frame.score_status.where(frame.score_status.notna(), np.where(scored, "scored", "not_scored"))
    frame["score_reason"] = frame.score_reason.where(frame.score_reason.notna(), np.where(scored, "ok", "insufficient_components"))
    return assemble_group_state(group_id, month, frame, reference_state, consolidated_scores or {}, {}, config)
