"""Nivel 0–100 de `financial_smoothed_v2`.

Misma estructura que V1 (anclas financieras + referencia empírica acotada, pesos
renormalizados entre componentes disponibles), pero las entradas son los agregados de
ventana de `signals.py`, no el valor mensual ni una media de tres ratios mensuales.
Reutiliza los helpers de V1 para cuantiles ponderados y mezcla ancla/empírica.
"""
from copy import deepcopy

import numpy as np
import pandas as pd

from xray.score.level import (COMPONENT_WEIGHTS, FEATURE_SPECS as V1_SPECS, _balanced_weights,
                              _feature_score, _transform, _weighted_quantiles)


FEATURE_SPECS = {
    "op_margin_w": {
        "component": "operations",
        "direction": "higher_is_better",
        "definition": ("Margen de flujos operativos de la ventana: (sum entradas - sum salidas) / (sum entradas + sum salidas) "
                       "sobre los meses con calidad de los ultimos 6; no margen contable."),
        "valid_min": -1.0, "valid_max": 1.0,
        "anchors": V1_SPECS["tx_operating_margin"]["anchors"],
    },
    "debt_service_w": {
        "component": "debt",
        "direction": "lower_is_better",
        "definition": ("Servicio de deuda de la ventana: (sum principal + sum intereses) / sum entradas operativas "
                       "de los ultimos 6 meses con calidad; cero no implica ausencia de deuda."),
        "valid_min": 0.0, "valid_max": None,
        "anchors": V1_SPECS["debt_service_to_inflow_ratio"]["anchors"],
        "zero_inflow_indicator": {
            "feature": "debt_without_inflow_w", "value": 1.0, "score": 0.0,
            "definition": ("Indicador: entradas operativas de la ventana = 0 con principal + intereses pagados > 0. "
                           "Servicio de deuda sin entradas en 6 meses; nota de deuda 0 con su peso, no un ratio inventado."),
        },
    },
    "ar_delay_w": {
        "component": "collections",
        "direction": "lower_is_better",
        "definition": ("Retraso de cobro AR de la ventana: media de las medianas mensuales (pago - vencimiento) ponderada "
                       "por numero de pagos con vencimiento valido, minimo 5 pagos en 6 meses."),
        "valid_min": -60.0, "valid_max": 365.0,
        "anchors": V1_SPECS["inv_ar_delay_median"]["anchors"],
    },
    "ap_delay_w": {
        "component": "payments",
        "direction": "lower_is_better",
        "definition": ("Retraso de pago AP de la ventana: media de las medianas mensuales (pago - vencimiento) ponderada "
                       "por numero de pagos con vencimiento valido, minimo 5 pagos en 6 meses."),
        "valid_min": -60.0, "valid_max": 365.0,
        "anchors": V1_SPECS["inv_ap_delay_median"]["anchors"],
    },
}
EXPLANATION_COLUMNS = ["input_index", "feature", "component", "value", "feature_score", "effective_weight",
                       "contribution", "direction", "definition"]


def _values(signals, spec, feature):
    values = pd.to_numeric(signals[feature], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    valid = np.isfinite(values)
    if spec["valid_min"] is not None:
        valid &= values >= spec["valid_min"]
    if spec["valid_max"] is not None:
        valid &= values <= spec["valid_max"]
    return np.where(valid, values, np.nan)


def fit_reference(signals):
    reference = {
        "version": 2, "anchor_weight": 0.7, "empirical_weight": 0.3, "empirical_quantiles": [0.1, 0.9],
        "quantile_method": "inverse_weighted_ecdf", "empirical_min_spread": 1e-12,
        "empirical_min_rows": 100, "empirical_min_groups": 20,
        "balance": "equal_groups_equal_companies_within_group_equal_observations_within_company",
        "component_weights": deepcopy(COMPONENT_WEIGHTS), "features": deepcopy(FEATURE_SPECS),
    }
    for feature, spec in reference["features"].items():
        values = _values(signals, spec, feature) if feature in signals else np.full(len(signals), np.nan)
        present = np.isfinite(values)
        spec.update(reference_low=None, reference_high=None, reference_rows=int(present.sum()),
                    reference_groups=0, reference_companies=0, empirical_active=False)
        if not present.any():
            continue
        weights, groups, companies = _balanced_weights(signals, present)
        low, high = _weighted_quantiles(_transform(values[present], spec), weights, reference["empirical_quantiles"])
        spec.update(reference_low=float(low), reference_high=float(high), reference_groups=groups,
                    reference_companies=companies,
                    empirical_active=bool(spec["reference_rows"] >= reference["empirical_min_rows"]
                                          and groups >= reference["empirical_min_groups"]
                                          and high - low > reference["empirical_min_spread"]))
    return reference


def score_level(signals, reference):
    if not signals.index.is_unique:
        raise ValueError("El índice de entrada debe ser único para explicar cada fila")
    if reference.get("version") != 2:
        raise ValueError("Versión de referencia de nivel no compatible con V2")
    weights = reference["component_weights"]
    result = pd.DataFrame(np.nan, index=signals.index,
                          columns=["level", *[f"level_{c}" for c in COMPONENT_WEIGHTS], "level_coverage"])
    coverage = np.zeros(len(signals))
    counts = np.zeros(len(signals), dtype=np.int64)
    pieces, selected = [], []
    for feature, spec in reference["features"].items():
        values = _values(signals, spec, feature) if feature in signals else np.full(len(signals), np.nan)
        present = np.isfinite(values)
        scores = np.full(len(signals), np.nan)
        scores[present] = _feature_score(values[present], spec, reference)
        names = np.full(len(signals), feature, dtype=object)
        indicator = spec.get("zero_inflow_indicator")
        if indicator and indicator["feature"] in signals:
            flagged = signals[indicator["feature"]].fillna(False).to_numpy(dtype=bool) & ~present
            values[flagged], scores[flagged], names[flagged] = indicator["value"], indicator["score"], indicator["feature"]
            present |= flagged
        component = spec["component"]
        result[f"level_{component}"] = scores
        coverage[present] += weights[component]
        counts[present] += 1
        selected.append((spec, values, names, present, scores))
    result["level_coverage"] = coverage
    result["level_components_available"] = counts
    result["has_uncovered_debt_service"] = signals.get("debt_without_inflow_w", pd.Series(False, index=signals.index)).fillna(False).astype(bool)
    original = signals.index.to_numpy()
    for spec, values, names, present, scores in selected:
        positions = np.flatnonzero(present)
        if not len(positions):
            continue
        indicator = spec.get("zero_inflow_indicator", {})
        definitions = np.where(names[present] == indicator.get("feature"), indicator.get("definition", ""), spec["definition"])
        pieces.append(pd.DataFrame({
            "input_index": original[present], "feature": names[present], "component": spec["component"],
            "value": values[present], "feature_score": scores[present],
            "effective_weight": weights[spec["component"]] / coverage[present],
            "contribution": scores[present] * weights[spec["component"]] / coverage[present],
            "direction": spec["direction"], "definition": definitions, "_position": positions,
        }))
    if not pieces:
        return result, pd.DataFrame({c: pd.Series(dtype=float if c in {"value", "feature_score", "effective_weight", "contribution"} else object)
                                     for c in EXPLANATION_COLUMNS})
    explanations = pd.concat(pieces, ignore_index=True).sort_values("_position", kind="stable").reset_index(drop=True)
    totals = explanations.groupby("_position", sort=False).contribution.sum()
    level = np.full(len(signals), np.nan)
    level[totals.index.to_numpy()] = totals.to_numpy(dtype=float)
    result["level"] = level
    return result, explanations[EXPLANATION_COLUMNS]
