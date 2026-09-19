from copy import deepcopy

import numpy as np
import pandas as pd


COMPONENT_WEIGHTS = {
    "operations": 0.45,
    "debt": 0.25,
    "collections": 0.15,
    "payments": 0.15,
}
FEATURE_SPECS = {
    "tx_operating_margin": {
        "component": "operations",
        "sources": ["tx_operating_margin_ma3", "tx_operating_margin"],
        "direction": "higher_is_better",
        "definition": "Margen de flujos operativos: (entradas - salidas) / (entradas + salidas); no margen contable.",
        "transform": "clip_to_anchor_domain",
        "valid_min": -1.0,
        "valid_max": 1.0,
        "anchors": [[-1.0, 0.0], [-0.25, 20.0], [0.0, 55.0], [0.1, 75.0],
                    [0.25, 90.0], [0.5, 100.0], [1.0, 100.0]],
    },
    "debt_service_to_inflow_ratio": {
        "component": "debt",
        "sources": ["debt_service_to_inflow_ratio_ma3", "debt_service_to_inflow_ratio"],
        "zero_inflow_indicator": {
            "feature": "debt_service_without_inflow",
            "value": 1.0,
            "score": 0.0,
            "definition": "Indicador: tx_inflow == 0 y debt_principal_paid + debt_interest_paid > 0, ambos pagos observados y finitos. Servicio de deuda sin entradas operativas actuales; no es un ratio ni implica impago. Score de deuda 0 con peso incluido; prevalece sobre la media de 3 meses.",
        },
        "direction": "lower_is_better",
        "definition": "Servicio de deuda observado: (principal pagado + intereses pagados) / entradas operativas; cero no implica ausencia de deuda.",
        "transform": "clip_to_anchor_domain",
        "valid_min": 0.0,
        "valid_max": None,
        "anchors": [[0.0, 100.0], [0.05, 90.0], [0.15, 70.0], [0.3, 40.0],
                    [0.5, 15.0], [1.0, 0.0]],
    },
    "inv_ar_delay_median": {
        "component": "collections",
        "sources": ["inv_ar_delay_median_ma3", "inv_ar_delay_median"],
        "current_source": "inv_ar_delay_median",
        "current_count_source": "inv_ar_delay_count",
        "current_min_count": 5,
        "direction": "lower_is_better",
        "definition": "Mediana de dias entre pago y vencimiento de facturas AR pagadas; no plazo desde emision ni stock vencido. Anticipado y puntual equivalen.",
        "transform": "clip_to_anchor_domain",
        "valid_min": -60.0,
        "valid_max": 365.0,
        "anchors": [[0.0, 100.0], [7.0, 85.0], [15.0, 65.0], [30.0, 40.0],
                    [60.0, 15.0], [90.0, 0.0]],
    },
    "inv_ap_delay_median": {
        "component": "payments",
        "sources": ["inv_ap_delay_median_ma3", "inv_ap_delay_median"],
        "current_source": "inv_ap_delay_median",
        "current_count_source": "inv_ap_delay_count",
        "current_min_count": 5,
        "direction": "lower_is_better",
        "definition": "Mediana de dias entre pago y vencimiento de facturas AP pagadas; no plazo desde emision ni stock vencido. Anticipado y puntual equivalen.",
        "transform": "clip_to_anchor_domain",
        "valid_min": -60.0,
        "valid_max": 365.0,
        "anchors": [[0.0, 100.0], [7.0, 85.0], [15.0, 65.0], [30.0, 40.0],
                    [60.0, 15.0], [90.0, 0.0]],
    },
}
_EXPLANATION_COLUMNS = [
    "input_index", "feature", "component", "value", "feature_score", "effective_weight",
    "contribution", "direction", "definition",
]


def _numeric_column(panel, column):
    if column not in panel.columns:
        return np.full(len(panel), np.nan)
    return pd.to_numeric(panel[column], errors="coerce").to_numpy(dtype=float, na_value=np.nan)


def _has_uncovered_debt_service(panel):
    principal = _numeric_column(panel, "debt_principal_paid")
    interest = _numeric_column(panel, "debt_interest_paid")
    return ((_numeric_column(panel, "tx_inflow") == 0.0)
            & np.isfinite(principal) & np.isfinite(interest) & (principal > -interest))


def _select_feature(panel, spec):
    values = np.full(len(panel), np.nan)
    sources = np.full(len(panel), "", dtype=object)
    zero_inflow = (_numeric_column(panel, "tx_inflow") == 0.0
                   if spec["component"] == "debt" else np.zeros(len(panel), dtype=bool))
    for source in spec["sources"]:
        if source not in panel.columns:
            continue
        candidate = _numeric_column(panel, source)
        valid = np.isfinite(candidate) & ~zero_inflow
        if spec["valid_min"] is not None:
            valid &= candidate >= spec["valid_min"]
        if spec["valid_max"] is not None:
            valid &= candidate <= spec["valid_max"]
        if source == spec.get("current_source") and spec["current_count_source"] in panel.columns:
            count = _numeric_column(panel, spec["current_count_source"])
            valid &= np.isfinite(count) & (count >= spec["current_min_count"])
        use = np.isnan(values) & valid
        values[use] = candidate[use]
        sources[use] = source
    return values, sources


def _transform(values, spec):
    return np.clip(values, spec["anchors"][0][0], spec["anchors"][-1][0])


def _balanced_weights(panel, present):
    selected = panel.iloc[np.flatnonzero(present)]
    weights = pd.DataFrame(index=pd.RangeIndex(len(selected)))
    weights["group"] = pd.factorize(selected["group_id"], sort=False)[0] if "group_id" in panel else 0
    weights["company"] = pd.factorize(selected["company_id"], sort=False)[0] if "company_id" in panel else 0
    keys = ["group", "company"]
    observations = weights.groupby(keys, sort=False)["company"].transform("size")
    companies = weights.groupby("group", sort=False)["company"].transform("nunique")
    balanced = 1.0 / (observations.to_numpy(dtype=float) * companies.to_numpy(dtype=float))
    known_groups = int(selected["group_id"].nunique()) if "group_id" in selected else 0
    return balanced, known_groups, int(weights[keys].drop_duplicates().shape[0])


def _weighted_quantiles(values, weights, quantiles):
    support = pd.DataFrame({"value": values, "weight": weights}).groupby("value", sort=True).weight.sum()
    mass = support.to_numpy(dtype=float)
    cumulative = np.cumsum(mass) / mass.sum()
    positions = np.searchsorted(cumulative, quantiles, side="left")
    return support.index.to_numpy(dtype=float)[positions].tolist()


def fit_reference(panel: pd.DataFrame) -> dict:
    reference = {
        "version": 1,
        "anchor_weight": 0.7,
        "empirical_weight": 0.3,
        "empirical_quantiles": [0.1, 0.9],
        "quantile_method": "inverse_weighted_ecdf",
        "empirical_min_spread": 1e-12,
        "empirical_min_rows": 100,
        "empirical_min_groups": 20,
        "balance": "equal_groups_equal_companies_within_group_equal_observations_within_company",
        "missing_id_policy": "missing IDs share a balancing bucket but do not count toward the group minimum; absent group_id balances companies; absent both balances rows",
        "component_weights": deepcopy(COMPONENT_WEIGHTS),
        "features": deepcopy(FEATURE_SPECS),
    }
    for spec in reference["features"].values():
        values, _ = _select_feature(panel, spec)
        present = np.isfinite(values)
        spec["reference_low"] = None
        spec["reference_high"] = None
        spec["reference_rows"] = int(present.sum())
        spec["reference_groups"] = 0
        spec["reference_companies"] = 0
        spec["empirical_active"] = False
        if not present.any():
            continue
        weights, groups, companies = _balanced_weights(panel, present)
        low, high = _weighted_quantiles(_transform(values[present], spec), weights,
                                        reference["empirical_quantiles"])
        spec["reference_low"] = float(low)
        spec["reference_high"] = float(high)
        spec["reference_groups"] = groups
        spec["reference_companies"] = companies
        spec["empirical_active"] = bool(
            spec["reference_rows"] >= reference["empirical_min_rows"]
            and groups >= reference["empirical_min_groups"]
            and high - low > reference["empirical_min_spread"]
        )
    return reference


def _feature_score(values, spec, reference):
    transformed = _transform(values, spec)
    anchors = np.asarray(spec["anchors"], dtype=float)
    anchored = np.interp(transformed, anchors[:, 0], anchors[:, 1])
    low, high = spec["reference_low"], spec["reference_high"]
    if (not spec.get("empirical_active", False) or low is None or high is None
            or high - low <= reference["empirical_min_spread"]):
        return anchored
    empirical = np.interp(transformed, [low, high], [0.0, 100.0])
    if spec["direction"] == "lower_is_better":
        empirical = 100.0 - empirical
    return np.clip(reference["anchor_weight"] * anchored + reference["empirical_weight"] * empirical, 0.0, 100.0)


def _source_definition(source, spec):
    indicator = spec.get("zero_inflow_indicator", {})
    if source == indicator.get("feature"):
        return indicator["definition"]
    window = ("Media de 3 meses completos, incluido el actual."
              if source.endswith("_ma3") else "Valor actual; fallback cuando no hay media de 3 meses valida.")
    if "current_count_source" in spec:
        if source.endswith("_ma3"):
            window += " El conteo actual no valida el soporte de toda esta ventana."
        else:
            window += (f" Si existe {spec['current_count_source']}, se exige >= {spec['current_min_count']}"
                       " retrasos validos; sin ese campo se conserva compatibilidad sin validar el soporte.")
    return spec["definition"] + " " + window


def _empty_explanations():
    return pd.DataFrame({
        column: pd.Series(dtype="float64" if column in {
            "value", "feature_score", "effective_weight", "contribution"
        } else "object") for column in _EXPLANATION_COLUMNS
    })


def score_level(panel: pd.DataFrame, reference: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not panel.index.is_unique:
        raise ValueError("El indice (input index) debe ser unico para explicar cada fila.")
    if reference.get("version") != 1:
        raise ValueError("Version de referencia no compatible; usar fit_reference(panel).")
    component_weights = reference["component_weights"]
    result = pd.DataFrame(np.nan, index=panel.index, columns=[
        "level", *[f"level_{component}" for component in COMPONENT_WEIGHTS], "level_coverage",
    ])
    coverage = np.zeros(len(panel), dtype=float)
    counts = np.zeros(len(panel), dtype=np.int64)
    selected_features = []
    uncovered_debt = _has_uncovered_debt_service(panel)
    for feature in FEATURE_SPECS:
        spec = reference["features"][feature]
        values, sources = _select_feature(panel, spec)
        present = np.isfinite(values)
        scores = np.full(len(panel), np.nan)
        scores[present] = _feature_score(values[present], spec, reference)
        component = spec["component"]
        if component == "debt" and uncovered_debt.any():
            indicator = spec["zero_inflow_indicator"]
            values[uncovered_debt] = indicator["value"]
            sources[uncovered_debt] = indicator["feature"]
            scores[uncovered_debt] = indicator["score"]
            present |= uncovered_debt
        result[f"level_{component}"] = scores
        coverage[present] += component_weights[component]
        counts[present] += 1
        selected_features.append((spec, values, sources, present, scores))
    result["level_coverage"] = coverage
    result["level_components_available"] = counts
    result["has_uncovered_debt_service"] = uncovered_debt
    pieces = []
    original_index = panel.index.to_numpy()
    for spec, values, sources, present, scores in selected_features:
        positions = np.flatnonzero(present)
        if len(positions) == 0:
            continue
        component = spec["component"]
        effective = component_weights[component] / coverage[present]
        definitions = {source: _source_definition(source, spec) for source in np.unique(sources[present])}
        pieces.append(pd.DataFrame({
            "input_index": original_index[present],
            "feature": sources[present],
            "component": component,
            "value": values[present],
            "feature_score": scores[present],
            "effective_weight": effective,
            "contribution": scores[present] * effective,
            "direction": spec["direction"],
            "definition": [definitions[source] for source in sources[present]],
            "_position": positions,
        }))
    if not pieces:
        return result, _empty_explanations()
    explanations = pd.concat(pieces, ignore_index=True).sort_values("_position", kind="stable").reset_index(drop=True)
    totals = explanations.groupby("_position", sort=False).contribution.sum()
    level = np.full(len(panel), np.nan)
    level[totals.index.to_numpy()] = totals.to_numpy(dtype=float)
    result["level"] = level
    return result, explanations[_EXPLANATION_COLUMNS]
