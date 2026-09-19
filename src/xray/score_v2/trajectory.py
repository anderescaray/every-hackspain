"""Momentum y trayectoria de `financial_smoothed_v2`.

Cada señal de momentum es un cambio trimestre reciente − trimestre anterior (o crecimiento
compuesto de entradas) dividido por la variabilidad mensual propia de la empresa
(`*_change_z`, ver `signals.py`), orientado (positivo = mejora) y recortado a ±`z_clip`.

Agregación: Z ponderado de Stouffer, `z̄ = Σwᵢzᵢ / √Σwᵢ²` sobre las señales disponibles.
Bajo ruido independiente N(0,1) el agregado también es N(0,1), con cualquier subconjunto de
señales disponibles: el umbral de dirección `|z̄| ≥ direction_z` (1,5 por defecto, ≈13% de
falsos positivos mensuales bajo ruido puro) no depende de cuántas fuentes tenga la empresa.
`momentum = 50 + 50·tanh(z̄ / z_scale)`; 50 es neutral, 1,5 desviaciones ≈ 50 ± 31,7.

Pesos: margen 0,35 · crecimiento 0,25 · servicio de deuda 0,20 · retraso AR 0,10 · retraso
AP 0,10 (‖w‖ ≈ 0,495 con las cinco). Con esos pesos, una ruptura clara solo del margen
(z ≈ 2,1) o del crecimiento (z ≈ 3,0) basta para marcar dirección; dos señales moderadas
concordantes también. Retrasos AR/AP por sí solos no pueden marcar dirección.

Regla bache/tendencia: una dirección solo se **confirma** cuando (a) el momentum mantiene
el mismo signo dos meses seguidos y (b) el mes actual sigue del mismo lado de su propio
nivel de seis meses (`*_deviation_z`). Un mes atípico aislado mueve el trimestre reciente
pero, cuando la empresa vuelve a su nivel, la condición (b) impide confirmar la tendencia y
el caso queda etiquetado como `one_off`.
"""
import numpy as np
import pandas as pd


CONFIRMATION_MONTHS = 2
STABILITY_WINDOW = 3
SIGNALS = (
    ("op_margin_qoq", "op_margin_change_z", 0.35, "op_margin_deviation_z", 1.0,
     "Margen operativo del trimestre reciente menos el del trimestre anterior; mayor mejora."),
    ("debt_service_qoq", "debt_service_change_z", 0.20, "debt_service_deviation_z", -1.0,
     "Servicio de deuda / entradas del trimestre reciente menos el anterior; menor mejora."),
    ("ar_delay_qoq", "ar_delay_change_z", 0.10, "ar_delay_deviation_z", -1.0,
     "Retraso AR ponderado del trimestre reciente menos el anterior; menor mejora."),
    ("ap_delay_qoq", "ap_delay_change_z", 0.10, "ap_delay_deviation_z", -1.0,
     "Retraso AP ponderado del trimestre reciente menos el anterior; menor mejora."),
    ("inflow_growth_q", "inflow_growth_change_z", 0.25, "inflow_growth_deviation_z", 1.0,
     "Crecimiento compuesto de entradas en cuentas comunes en tres meses (suma de log(1+g)); mayor mejora."),
)
LABELS = ("improving", "deteriorating", "emerging_improvement", "emerging_deterioration",
          "mixed_signals", "stable", "insufficient_history")
EXPLANATION_COLUMNS = ("input_index", "feature", "value", "standardized_value", "feature_score",
                       "effective_weight", "contribution", "direction", "definition")


def _empty_result(index):
    n = len(index)
    return pd.DataFrame({
        "momentum": np.full(n, np.nan), "momentum_coverage": np.zeros(n),
        "trajectory": pd.Series("insufficient_history", index=index, dtype="str"),
        "direction": pd.Series("unknown", index=index, dtype="str"),
        "episode": pd.Series("none", index=index, dtype="str"),
        "momentum_strength": np.full(n, np.nan), "trend_months": np.zeros(n, dtype=np.int64),
        "stability": np.full(n, np.nan), "has_momentum": np.zeros(n, dtype=bool),
        "momentum_signal_count": np.zeros(n, dtype=np.int64), "momentum_conflict": np.zeros(n, dtype=bool),
        "momentum_sources_changed": np.zeros(n, dtype=bool), "momentum_confirmed": np.zeros(n, dtype=bool),
        "momentum_z": np.full(n, np.nan),
        "current_month_support_z": np.full(n, np.nan), "current_month_supports_direction": np.zeros(n, dtype=bool),
        "direction_held": np.zeros(n, dtype=bool),
    }, index=index)


def _oriented_z(frame, columns, orientations, clip):
    return (frame[list(columns)].astype(float) * orientations).clip(-clip, clip)


def _stouffer(z, weights):
    """Z ponderado de Stouffer sobre las señales disponibles: N(0,1) bajo ruido independiente."""
    available = z.notna()
    w = available.mul(weights)
    norm = np.sqrt(w.pow(2).sum(axis=1))
    return (z * w).sum(axis=1, min_count=1).div(norm.where(norm.gt(0))), w.div(norm.where(norm.gt(0)), axis=0)


def _saturation(aggregate, z_scale):
    """k(z̄) = 50·tanh(z̄/s)/z̄, factor común que reparte momentum−50 entre señales de forma exacta."""
    with np.errstate(divide="ignore", invalid="ignore"):
        k = 50 * np.tanh(aggregate / z_scale) / aggregate
    return k.where(aggregate.ne(0), 50 / z_scale)


def score_calendar(signals, config):
    """Momentum, trayectoria y episodio para el calendario completo de una entidad-moneda.

    momentum = 50 + 50·tanh(z̄ / z_scale), con z̄ el Z ponderado de Stouffer de los cambios
    estandarizados disponibles. Se publica solo cuando las señales disponibles suman al menos
    `config.min_momentum_coverage` del peso nominal; con menos evidencia queda NaN y la
    trayectoria es `insufficient_history`. La contribución de cada señal es
    k(z̄)·wᵢzᵢ/‖w‖ y suma exactamente momentum − 50.
    """
    z_cols = [s[1] for s in SIGNALS]
    weights = np.array([s[2] for s in SIGNALS])
    dev_cols = [s[3] for s in SIGNALS]
    orientations = np.array([s[4] for s in SIGNALS])
    for column in z_cols + dev_cols + ["is_atypical_month", "op_margin_deviation_z"]:
        if column not in signals:
            raise ValueError(f"Falta la señal {column}")
    z = _oriented_z(signals, z_cols, orientations, config.z_clip)
    coverage = z.notna().mul(weights).sum(axis=1)
    aggregate, effective = _stouffer(z, weights)
    aggregate = aggregate.where(coverage.ge(config.min_momentum_coverage))
    published = aggregate.notna()
    momentum = (50 + 50 * np.tanh(aggregate / config.z_scale)).clip(0, 100)
    z, effective = z.where(published, axis=0), effective.where(published, axis=0)
    available = z.notna()
    feature_scores = 50 + 50 * np.tanh(z / config.z_scale)
    contributions = (z * effective).mul(_saturation(aggregate, config.z_scale), axis=0)
    deviation_z = _oriented_z(signals, dev_cols, orientations, config.z_clip)
    deviation_z.columns = z_cols
    support, _ = _stouffer(deviation_z, weights)
    feature_dir = np.where(z.to_numpy() >= config.direction_z, 1, np.where(z.to_numpy() <= -config.direction_z, -1, 0))
    aggregate_dir = np.where(aggregate.to_numpy() >= config.direction_z, 1, np.where(aggregate.to_numpy() <= -config.direction_z, -1, 0))
    result = _empty_result(signals.index)
    result["momentum"] = momentum
    result["momentum_z"] = aggregate
    result["momentum_coverage"] = coverage
    result["momentum_strength"] = (momentum - 50).abs() * 2
    result["has_momentum"] = published
    result["momentum_signal_count"] = available.sum(axis=1).astype(np.int64)
    result["momentum_conflict"] = (feature_dir > 0).any(axis=1) & (feature_dir < 0).any(axis=1)
    result["momentum_sources_changed"] = available.ne(available.shift(1, fill_value=False)).any(axis=1)
    result["current_month_support_z"] = support
    dispersion = aggregate.rolling(STABILITY_WINDOW, min_periods=STABILITY_WINDOW).std(ddof=0)
    result["stability"] = (100 / (1 + dispersion)).where(published).clip(0, 100)
    observed = published.to_numpy()
    support_values = support.to_numpy()
    atypical = signals.is_atypical_month.fillna(False).to_numpy(dtype=bool)
    deviation = signals.op_margin_deviation_z.to_numpy(dtype=float)
    conflict = result.momentum_conflict.to_numpy()
    runs = np.zeros(len(signals), dtype=np.int64)
    labels = np.full(len(signals), "insufficient_history", dtype=object)
    directions = np.full(len(signals), "unknown", dtype=object)
    episodes = np.full(len(signals), "none", dtype=object)
    confirmed = np.zeros(len(signals), dtype=bool)
    supports = np.zeros(len(signals), dtype=bool)
    held = np.zeros(len(signals), dtype=bool)
    signs = np.zeros(len(signals), dtype=np.int64)
    aggregate_values = aggregate.to_numpy()
    hold_level = config.direction_z * config.hysteresis
    for i in range(len(signals)):
        if not observed[i]:
            continue
        sign = aggregate_dir[i]
        if sign == 0 and i > 0 and confirmed[i - 1] and aggregate_values[i] * signs[i - 1] >= hold_level:
            sign, held[i] = signs[i - 1], True  # histéresis: una dirección confirmada no se abandona por una oscilación leve
        signs[i] = sign
        directions[i] = {1: "up", -1: "down", 0: "flat"}[sign]
        if sign:
            continues = i > 0 and observed[i - 1] and signs[i - 1] == sign
            runs[i] = runs[i - 1] + sign if continues else sign
            supports[i] = bool(np.isfinite(support_values[i]) and support_values[i] * sign > 0)
            confirmed[i] = abs(runs[i]) >= CONFIRMATION_MONTHS and supports[i]
            if confirmed[i]:
                labels[i] = "improving" if sign > 0 else "deteriorating"
            else:
                labels[i] = "emerging_improvement" if sign > 0 else "emerging_deterioration"
        else:
            labels[i] = "mixed_signals" if conflict[i] else "stable"
        if confirmed[i]:
            episodes[i] = "trend_improvement" if sign > 0 else "trend_deterioration"
        elif atypical[i] and np.isfinite(deviation[i]):
            episodes[i] = "one_off_dip" if deviation[i] < 0 else "one_off_spike"
        elif sign and abs(runs[i]) >= CONFIRMATION_MONTHS and not supports[i]:
            episodes[i] = "not_sustained_by_current_month"  # el trimestre arrastra un mes atípico; el mes actual ya no lo sostiene
    result["trajectory"] = labels
    result["direction"] = directions
    result["episode"] = episodes
    result["trend_months"] = runs
    result["momentum_confirmed"] = confirmed
    result["current_month_supports_direction"] = supports
    result["direction_held"] = held
    return result, feature_scores, effective, contributions


def score_trajectory(signals, panel, unit, config):
    """Aplica `score_calendar` por entidad-moneda. `signals` y `panel` comparten índice; `panel` aporta claves."""
    keys = [unit, "currency", "month"]
    empty = _empty_result(panel.index)
    pieces, explanations = [], []
    for _, group in panel[keys].groupby([unit, "currency"], sort=False, observed=True):
        ordered = group.sort_values("month")
        calendar = pd.date_range(ordered.month.min(), ordered.month.max(), freq="MS", name="month")
        expanded = signals.loc[ordered.index].set_index(ordered.month.to_numpy()).reindex(calendar)
        scored, feature_scores, effective, contributions = score_calendar(expanded, config)
        present = calendar.isin(ordered.month)
        idx = ordered.index.to_numpy()
        pieces.append(scored.loc[present].set_index(idx))
        position_map = pd.Series(idx, index=ordered.month.to_numpy())
        for number, (feature, z_col, _, _, orientation, definition) in enumerate(SIGNALS):
            valid = feature_scores[z_col].notna() & present
            if not valid.any():
                continue
            values = expanded.loc[valid, feature].to_numpy(dtype=float)
            explanations.append(pd.DataFrame({
                "input_index": position_map.loc[calendar[valid]].to_numpy(),
                "feature": feature, "value": values,
                "standardized_value": np.clip(expanded.loc[valid, z_col].to_numpy(dtype=float) * orientation, -config.z_clip, config.z_clip),
                "feature_score": feature_scores.loc[valid, z_col].to_numpy(),
                "effective_weight": effective.loc[valid, z_col].to_numpy(),
                "contribution": contributions.loc[valid, z_col].to_numpy(),
                "direction": np.where(values * orientation > 0, "up", np.where(values * orientation < 0, "down", "flat")),
                "definition": (definition + f" z = {orientation:g} * cambio / (sigma propia ajustada a la ventana), recortado a +-{config.z_clip:g}; "
                               f"nota individual = 50 + 50*tanh(z/{config.z_scale:g}); momentum = 50 + 50*tanh(z_agregado/{config.z_scale:g}) "
                               "con z_agregado = sum(w*z)/sqrt(sum(w^2)) sobre señales observadas; la contribucion reparte momentum-50 "
                               "en proporcion a w*z con un factor de saturacion comun."),
                "_order": number,
            }))
    result = pd.concat(pieces).reindex(panel.index) if pieces else empty
    for column in empty:
        result[column] = result[column].where(result[column].notna(), empty[column]).astype(empty[column].dtype)
    if explanations:
        explain = pd.concat(explanations, ignore_index=True)
        order = pd.Series(np.arange(len(panel)), index=panel.index)
        explain["_pos"] = order.loc[explain.input_index].to_numpy()
        explain = explain.sort_values(["_pos", "_order"]).drop(columns=["_pos", "_order"]).reset_index(drop=True)
    else:
        explain = pd.DataFrame({c: pd.Series(dtype=object if c in {"input_index", "feature", "direction", "definition"} else float)
                                for c in EXPLANATION_COLUMNS})
    return result, explain
