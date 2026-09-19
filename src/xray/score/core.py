import hashlib
from dataclasses import asdict

import numpy as np
import pandas as pd

from xray.score.config import ScoreConfig


METHOD = "financial_baseline_v1"
QUALITY_FIELDS = ["tx_count", "tx_usable_count", "tx_usable_row_share", "tx_operating_amount_share", "tx_company_coverage"]
CORE_FEATURES = ["tx_operating_margin", "tx_operating_margin_ma3", "tx_operating_margin_delta3",
                 "debt_service_to_inflow_ratio", "debt_service_to_inflow_ratio_ma3",
                 "debt_service_to_inflow_ratio_delta3", "tx_lfl_inflow_growth", "tx_inflow",
                 "debt_principal_paid", "debt_interest_paid", "has_sufficient_history"]
OPTIONAL_FEATURES = [f"inv_{side}_{metric}" for side in ("ar", "ap") for metric in ("delay_median", "delay_count")]


def prepare_panel(panel, config):
    required = {config.unit, "group_id", "month", "currency", *QUALITY_FIELDS, *CORE_FEATURES}
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"Faltan columnas del contrato de features: {sorted(missing)}")
    p = panel.copy().reset_index(drop=True)
    p["month"] = pd.to_datetime(p.month)
    keys = [config.unit, "currency", "month"]
    if p[keys + ["group_id"]].isna().any().any():
        raise ValueError("Las claves del panel no pueden tener nulos")
    if p.duplicated(keys).any():
        raise ValueError("El panel contiene claves duplicadas")
    if not p.month.eq(p.month.dt.to_period("M").dt.to_timestamp()).all():
        raise ValueError("month debe ser el primer día del mes")
    for side in ("ar", "ap"):
        count = p.get(f"inv_{side}_delay_count", pd.Series(np.nan, index=p.index))
        if f"inv_{side}_delay_median" in p:
            p.loc[count.isna() | count.lt(5), f"inv_{side}_delay_median"] = np.nan
        if f"inv_{side}_delay_median_ma3" in p:
            p[f"inv_{side}_delay_median_ma3"] = np.nan
    supported = quality_reasons(p, config).eq("")
    previous = p[keys].assign(usable=supported)
    for lag in (1, 2):
        shifted = previous.copy()
        shifted["month"] += pd.offsets.MonthBegin(lag)
        support = p[keys].merge(shifted, on=keys, how="left", validate="one_to_one").usable
        supported &= support.fillna(False).to_numpy(dtype=bool)
    columns = [col for col in ("tx_operating_margin_ma3", "debt_service_to_inflow_ratio_ma3") if col in p]
    p.loc[~supported, columns] = np.nan
    return p


def quality_reasons(p, config):
    reason = pd.Series("", index=p.index, dtype="string")
    checks = [
        (p.tx_usable_count.fillna(0).le(0), "no_usable_transactions"),
        (p.tx_usable_count.lt(config.min_transactions), "insufficient_current_activity"),
        (p.tx_usable_row_share.fillna(0).lt(config.min_usable_share), "insufficient_usable_coverage"),
        (p.tx_operating_amount_share.fillna(0).lt(config.min_operating_share), "insufficient_operating_coverage"),
        (~p.tx_company_coverage.eq(1), "incomplete_group_coverage"),
    ]
    for mask, label in checks:
        reason.loc[mask & reason.eq("")] = label
    return reason


def partition_groups(groups, config):
    ordered = sorted(set(groups), key=lambda group: hashlib.sha256(f"{config.split_seed}:{group}".encode()).hexdigest())
    count = min(int(len(ordered) * config.holdout_fraction), max(0, len(ordered) - 1))
    return sorted(ordered[count:]), sorted(ordered[:count])


def fit_reference_bundle(panel, config=None):
    from xray.score.level import fit_reference

    config = config or ScoreConfig()
    p = prepare_panel(panel, config)
    if p.empty:
        raise ValueError("No se puede fijar un calendario de referencia con un panel vacío")
    reference_groups, holdout_groups = partition_groups(p.group_id.tolist(), config)
    usable = quality_reasons(p, config).eq("")
    source = p.loc[p.group_id.isin(reference_groups) & usable]
    references = []
    months = pd.date_range(p.month.min(), p.month.max() + pd.offsets.MonthBegin(1), freq="MS")
    for month in months:
        start = month - pd.DateOffset(months=config.reference_months)
        prior = source.loc[source.month.ge(start) & source.month.lt(month)]
        references.append({
            "effective_from": str(month.date()), "window_start": str(start.date()),
            "max_observed_month": str(prior.month.max().date()) if len(prior) else None,
            "rows": len(prior), "groups": int(prior.group_id.nunique()),
            "state": fit_reference(prior),
        })
    return {"schema_version": 1, "method": METHOD, "config": asdict(config),
            "reference_groups": reference_groups, "holdout_groups": holdout_groups,
            "anchor_reference": fit_reference(p.iloc[:0]), "references": references,
            "input_contract": {"required_features": QUALITY_FIELDS + CORE_FEATURES,
                               "optional_invoice_features": OPTIONAL_FEATURES,
                               "keys": list(dict.fromkeys([config.unit, "group_id", "currency", "month"]))},
            "supervised": False, "official_labels_available": False}


def score_panel(panel, reference):
    from xray.score.level import score_level
    from xray.score.trajectory import score_trajectory

    if reference.get("method") != METHOD or reference.get("schema_version") != 1:
        raise ValueError("Versión de referencia no compatible")
    config = ScoreConfig(**reference["config"])
    p = prepare_panel(panel, config)
    if p.empty:
        raise ValueError("El panel de inferencia está vacío")
    dates = [pd.Timestamp(item["effective_from"]) for item in reference["references"]]
    if dates != sorted(set(dates)):
        raise ValueError("El calendario de referencia no está ordenado o tiene duplicados")
    levels, explanations = [], []
    reference_date = pd.Series(pd.NaT, index=p.index, dtype="datetime64[ns]")
    reference_rows = pd.Series(0, index=p.index, dtype=int)
    for month, subset in p.groupby("month", sort=True):
        selected = np.searchsorted(np.array(dates, dtype="datetime64[ns]"), np.datetime64(month), side="right") - 1
        state = reference["anchor_reference"]
        if selected >= 0:
            entry = reference["references"][selected]
            if entry["max_observed_month"] is not None and pd.Timestamp(entry["max_observed_month"]) >= month:
                raise ValueError("La referencia contiene datos del mes puntuado o del futuro")
            state = entry["state"]
            reference_date.loc[subset.index] = dates[selected]
            reference_rows.loc[subset.index] = entry["rows"]
        level, explanation = score_level(subset, state)
        levels.append(level)
        explanation["layer"] = "level"
        explanations.append(explanation)
    level = pd.concat(levels).reindex(p.index)
    reason = quality_reasons(p, config)
    unavailable = level.level.isna() | level.level_operations.isna() | level.level_coverage.lt(config.min_level_coverage)
    reason.loc[reason.eq("") & unavailable] = "insufficient_components"
    usable = reason.eq("")
    trend_input = p.copy()
    trend_input["score_input_usable"] = usable
    protected = set(QUALITY_FIELDS + ["history_observed_months", "month_of_year"])
    numeric = [col for col in trend_input.select_dtypes("number") if col not in protected]
    trend_input.loc[~usable, numeric] = np.nan
    trajectory, trend_explanations = score_trajectory(trend_input, unit=config.unit)
    trajectory = trajectory.reindex(p.index)
    keys = list(dict.fromkeys([config.unit, "group_id", "currency", "month"]))
    result = pd.concat([p[keys], level, trajectory], axis=1)
    result["reference_partition"] = np.select(
        [p.group_id.isin(reference["reference_groups"]), p.group_id.isin(reference["holdout_groups"])],
        ["reference", "holdout"], default="unseen")
    result["reference_effective_from"] = reference_date
    result["reference_rows"] = reference_rows
    result["method"] = METHOD
    result["momentum_adjustment"] = config.momentum_weight * (result.momentum - 50)
    result["momentum_adjustment"] = result.momentum_adjustment.fillna(0).where(usable)
    result.loc[~usable, ["level", "momentum", "stability", "momentum_strength"]] = np.nan
    result.loc[~usable, "trajectory"] = "insufficient_history"
    result.loc[~usable, "direction"] = "unknown"
    result.loc[~usable, "trend_months"] = 0
    result.loc[~usable, ["has_momentum", "momentum_confirmed"]] = False
    raw = result.level + result.momentum_adjustment
    result["score"] = raw.clip(0, 100)
    result["clipping_adjustment"] = result.score - raw
    history = p.get("has_sufficient_history", pd.Series(False, index=p.index)).fillna(False).astype(bool)
    partial_currency = p.get("has_partial_currency_coverage", pd.Series(False, index=p.index)).fillna(False).astype(bool)
    result["has_partial_currency_coverage"] = partial_currency
    result["has_sufficient_history"] = history
    for col in QUALITY_FIELDS:
        result[col] = p[col]
    result["score_status"] = np.where(usable, "scored", "not_scored")
    provisional = usable & (~history | result.momentum.isna() | level.level_coverage.lt(.999) | partial_currency)
    result.loc[provisional, "score_status"] = "provisional"
    reason.loc[usable & ~history] = "short_history"
    reason.loc[usable & history & result.momentum.isna()] = "trend_unavailable"
    reason.loc[usable & history & result.momentum.notna() & level.level_coverage.lt(.999)] = "optional_components_missing"
    reason.loc[usable & reason.eq("") & partial_currency] = "partial_currency"
    result["score_reason"] = reason.replace("", "ok")
    component_columns = [f"level_{name}" for name in ("operations", "debt", "collections", "payments")]
    result["component_mask"] = result[component_columns].notna().astype(int).astype(str).agg("".join, axis=1)
    previous = result[keys + ["score", "component_mask"]].copy()
    previous["month"] += pd.offsets.MonthBegin(1)
    previous = result[keys].merge(previous, on=keys, how="left", validate="one_to_one")
    result["delta_vs_prev"] = result.score - previous.score.to_numpy()
    result["component_set_changed"] = (previous.component_mask.notna().to_numpy()
                                         & result.component_mask.ne(previous.component_mask.to_numpy()))
    result["delta_requires_review"] = result.delta_vs_prev.notna() & (
        result.component_set_changed | partial_currency | p.get("tx_new_accounts", pd.Series(0, index=p.index)).gt(0))
    terms = pd.concat(explanations, ignore_index=True)
    terms["final_contribution"] = terms.contribution
    trend_explanations = trend_explanations.copy()
    trend_explanations["layer"] = "momentum"
    trend_explanations["final_contribution"] = config.momentum_weight * (
        trend_explanations.contribution - 50 * trend_explanations.effective_weight)
    terms = pd.concat([terms, trend_explanations], ignore_index=True)
    clipping = result.loc[result.clipping_adjustment.ne(0) & result.score.notna()]
    if len(clipping):
        extra = pd.DataFrame({"input_index": clipping.index, "feature": "score_clipping", "component": "boundary",
                              "value": clipping.clipping_adjustment, "feature_score": np.nan, "effective_weight": 0.,
                              "contribution": clipping.clipping_adjustment, "direction": "bounded",
                              "definition": "Ajuste para mantener score en [0,100]", "layer": "boundary",
                              "final_contribution": clipping.clipping_adjustment})
        terms = pd.concat([terms, extra], ignore_index=True)
    terms = terms.loc[terms.input_index.isin(result.index[result.score.notna()])]
    terms = terms.merge(p[keys].rename_axis("input_index").reset_index(), on="input_index", validate="many_to_one")
    terms = terms.drop(columns=["input_index", "input_position"], errors="ignore")
    validate_scores(result, terms, config)
    return result, terms


def validate_scores(scores, explanations, config):
    for col in ("score", "level", "momentum", "stability"):
        if not scores[col].dropna().between(0, 100).all():
            raise ValueError(f"{col} fuera de [0,100]")
    if np.isinf(scores.select_dtypes("number").to_numpy(dtype=float)).any():
        raise ValueError("Score con valores infinitos")
    keys = [config.unit, "currency", "month"]
    sums = explanations.groupby(keys).final_contribution.sum()
    expected = scores.set_index(keys).score.dropna()
    if not np.allclose(sums.reindex(expected.index), expected, atol=1e-8):
        raise ValueError("Las explicaciones no suman el score")
