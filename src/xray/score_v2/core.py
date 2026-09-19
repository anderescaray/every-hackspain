"""Integración de `financial_smoothed_v2`: contrato, referencia congelada, score y explicación aditiva.

`score = clip(level + momentum_weight · (momentum − 50), 0, 100)`; las explicaciones suman
exactamente el score. La referencia se ajusta solo con grupos de referencia y meses
anteriores a t (ventana `reference_months`, por defecto 24 = expansiva en este dataset).
"""
from dataclasses import asdict

import numpy as np
import pandas as pd

from xray.score.core import partition_groups
from xray.score_v2.config import ScoreV2Config
from xray.score_v2.level import fit_reference, score_level
from xray.score_v2.signals import (CORE_FEATURES, OPTIONAL_FEATURES, QUALITY_FIELDS, apply_seasonal_adjustment,
                                   build_signals, month_quality, seasonal_growth_factors)
from xray.score_v2.trajectory import score_trajectory


METHOD = "financial_smoothed_v2"
SCHEMA_VERSION = 2


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
        if f"inv_{side}_delay_median" in p and f"inv_{side}_delay_count" not in p:
            raise ValueError(f"inv_{side}_delay_median requiere inv_{side}_delay_count para acreditar su soporte")
    return p


def entry_reasons(p, signals, config):
    """Motivos por los que el mes no puede puntuarse (vacío = puntuable)."""
    reason = pd.Series("", index=p.index, dtype="string")
    checks = [
        (p.tx_usable_count.fillna(0).le(0), "no_usable_transactions"),
        (~p.tx_company_coverage.eq(1), "incomplete_group_coverage"),
        (signals.level_months.fillna(0).lt(config.level_min_months), "insufficient_window_history"),
    ]
    for mask, label in checks:
        reason.loc[mask.to_numpy(dtype=bool) & reason.eq("")] = label
    return reason


def _signals_with_ids(p, signals, config):
    ids = [c for c in ("group_id", "company_id") if c in p]
    return pd.concat([p[ids], signals], axis=1)


def fit_reference_bundle(panel, config=None):
    config = config or ScoreV2Config()
    p = prepare_panel(panel, config)
    if p.empty:
        raise ValueError("No se puede fijar un calendario de referencia con un panel vacío")
    signals = build_signals(p, config)
    reference_groups, holdout_groups = partition_groups(p.group_id.tolist(), config)
    eligible = entry_reasons(p, signals, config).eq("")
    source = _signals_with_ids(p, signals, config).loc[p.group_id.isin(reference_groups) & eligible]
    source_months = p.month.loc[source.index]
    references = []
    for month in pd.date_range(p.month.min(), p.month.max() + pd.offsets.MonthBegin(1), freq="MS"):
        start = month - pd.DateOffset(months=config.reference_months)
        prior = source.loc[source_months.ge(start) & source_months.lt(month)]
        references.append({
            "effective_from": str(month.date()), "window_start": str(start.date()),
            "max_observed_month": str(source_months.loc[prior.index].max().date()) if len(prior) else None,
            "rows": len(prior), "groups": int(prior.group_id.nunique()) if "group_id" in prior else 0,
            "state": fit_reference(prior),
            "seasonal_growth": seasonal_growth_factors(prior, source_months.loc[prior.index], config.seasonal_min_rows),
        })
    return {"schema_version": SCHEMA_VERSION, "method": METHOD, "config": asdict(config),
            "reference_groups": reference_groups, "holdout_groups": holdout_groups,
            "anchor_reference": fit_reference(source.iloc[:0]), "references": references,
            "anchor_seasonal_growth": seasonal_growth_factors(source.iloc[:0], source_months.iloc[:0], config.seasonal_min_rows),
            "input_contract": {"required_features": QUALITY_FIELDS + CORE_FEATURES,
                               "optional_invoice_features": OPTIONAL_FEATURES,
                               "keys": list(dict.fromkeys([config.unit, "group_id", "currency", "month"]))},
            "supervised": False, "official_labels_available": False,
            "holdout_note": "Mismo split que V1 (semilla 20260918); el holdout ya fue inspeccionado en la auditoría de V1."}


def score_panel(panel, reference):
    if reference.get("method") != METHOD or reference.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Versión de referencia no compatible")
    config = ScoreV2Config(**reference["config"])
    p = prepare_panel(panel, config)
    if p.empty:
        raise ValueError("El panel de inferencia está vacío")
    signals = build_signals(p, config)
    dates = [pd.Timestamp(item["effective_from"]) for item in reference["references"]]
    if dates != sorted(set(dates)):
        raise ValueError("El calendario de referencia no está ordenado o tiene duplicados")
    levels, explanations = [], []
    reference_date = pd.Series(pd.NaT, index=p.index, dtype="datetime64[ns]")
    reference_rows = pd.Series(0, index=p.index, dtype=int)
    entries = {}
    for month, subset in p.groupby("month", sort=True):
        selected = np.searchsorted(np.array(dates, dtype="datetime64[ns]"), np.datetime64(month), side="right") - 1
        entry = None
        if selected >= 0:
            entry = reference["references"][selected]
            if entry["max_observed_month"] is not None and pd.Timestamp(entry["max_observed_month"]) >= month:
                raise ValueError("La referencia contiene datos del mes puntuado o del futuro")
            reference_date.loc[subset.index] = dates[selected]
            reference_rows.loc[subset.index] = entry["rows"]
        entries[month] = entry
    if config.seasonal_adjustment:
        anchor = reference.get("anchor_seasonal_growth", {"factors": {}})["factors"]
        table = pd.DataFrame(0.0, index=p.index, columns=[str(m) for m in range(1, 13)])
        for month, subset in p.groupby("month", sort=True):
            factors = (entries[month] or {}).get("seasonal_growth", {"factors": anchor})["factors"]
            table.loc[subset.index, list(factors)] = [factors[k] for k in factors]
        signals = apply_seasonal_adjustment(signals, p.month, table, config)
    for month, subset in p.groupby("month", sort=True):
        state = entries[month]["state"] if entries[month] else reference["anchor_reference"]
        level, explanation = score_level(signals.loc[subset.index], state)
        levels.append(level)
        explanation["layer"] = "level"
        explanations.append(explanation)
    level = pd.concat(levels).reindex(p.index)
    reason = entry_reasons(p, signals, config)
    unavailable = level.level.isna() | level.level_operations.isna() | level.level_coverage.lt(config.min_level_coverage)
    reason.loc[reason.eq("") & unavailable] = "insufficient_components"
    usable = reason.eq("").to_numpy(dtype=bool)
    trajectory, trend_terms = score_trajectory(signals, p, config.unit, config)
    keys = list(dict.fromkeys([config.unit, "group_id", "currency", "month"]))
    result = pd.concat([p[keys], level, trajectory], axis=1)
    diagnostics = ["month_quality_ok", "level_months", "op_margin_w", "op_margin_m1", "op_margin_sigma",
                   "op_margin_deviation", "op_margin_deviation_z", "is_atypical_month", "atypical_months_in_window",
                   "op_margin_q_recent", "op_margin_q_prior", "op_margin_qoq", "op_margin_change_z",
                   "inflow_growth_q", "inflow_growth_change_z", "coverage_state",
                   "inflow_growth_q_raw", "inflow_growth_seasonal_factor"]
    for column in diagnostics:
        result[column] = signals[column] if column in signals else np.nan
    result["reference_partition"] = np.select(
        [p.group_id.isin(reference["reference_groups"]), p.group_id.isin(reference["holdout_groups"])],
        ["reference", "holdout"], default="unseen")
    result["reference_effective_from"] = reference_date
    result["reference_rows"] = reference_rows
    result["method"] = METHOD
    result["momentum_adjustment"] = (config.momentum_weight * (result.momentum - 50)).fillna(0).where(usable)
    result.loc[~usable, ["level", "momentum", "momentum_z", "stability", "momentum_strength", "current_month_support_z"]] = np.nan
    result.loc[~usable, "trajectory"] = "insufficient_history"
    result.loc[~usable, "direction"] = "unknown"
    result.loc[~usable, "episode"] = "none"
    result.loc[~usable, "trend_months"] = 0
    result.loc[~usable, ["has_momentum", "momentum_confirmed", "current_month_supports_direction", "direction_held"]] = False
    raw = result.level + result.momentum_adjustment
    result["score"] = raw.clip(0, 100)
    result["clipping_adjustment"] = result.score - raw
    history = p.has_sufficient_history.fillna(False).astype(bool)
    partial = p.get("has_partial_currency_coverage", pd.Series(False, index=p.index)).fillna(False).astype(bool)
    quality_ok = signals.month_quality_ok.fillna(False).astype(bool)
    result["has_partial_currency_coverage"] = partial
    result["has_sufficient_history"] = history
    for col in QUALITY_FIELDS:
        result[col] = p[col]
    result["score_status"] = np.where(usable, "scored", "not_scored")
    provisional = usable & (~quality_ok | ~history | result.momentum.isna() | level.level_coverage.lt(.999) | partial)
    result.loc[provisional, "score_status"] = "provisional"
    reason.loc[usable & ~quality_ok] = "thin_current_month"
    reason.loc[usable & quality_ok & ~history] = "short_history"
    reason.loc[usable & quality_ok & history & result.momentum.isna()] = "trend_unavailable"
    reason.loc[usable & quality_ok & history & result.momentum.notna() & level.level_coverage.lt(.999)] = "optional_components_missing"
    reason.loc[usable & reason.eq("") & partial] = "partial_currency"
    coverage = signals.coverage_state.astype("string").fillna("ok")
    for state in ("onboarding", "account_change"):   # FE10: mes no comparable con el anterior; nivel válido, trayectoria a revisar
        flagged = usable & reason.eq("") & coverage.eq(state).to_numpy(dtype=bool)
        result.loc[flagged, "score_status"] = "provisional"
        reason.loc[flagged] = f"coverage_{state}"
    result["score_reason"] = reason.replace("", "ok")
    components = [f"level_{name}" for name in ("operations", "debt", "collections", "payments")]
    result["component_mask"] = result[components].notna().astype(int).astype(str).agg("".join, axis=1)
    previous = result[keys + ["score", "component_mask"]].copy()
    previous["month"] += pd.offsets.MonthBegin(1)
    previous = result[keys].merge(previous, on=keys, how="left", validate="one_to_one")
    result["delta_vs_prev"] = result.score - previous.score.to_numpy()
    result["component_set_changed"] = previous.component_mask.notna().to_numpy() & result.component_mask.ne(previous.component_mask.to_numpy())
    result["delta_requires_review"] = result.delta_vs_prev.notna() & (
        result.component_set_changed | partial | p.get("tx_new_accounts", pd.Series(0, index=p.index)).fillna(0).gt(0))
    terms = pd.concat(explanations, ignore_index=True)
    terms["standardized_value"] = np.nan
    terms["final_contribution"] = terms.contribution
    trend_terms = trend_terms.copy()
    trend_terms["layer"] = "momentum"
    trend_terms["component"] = "momentum"
    trend_terms["final_contribution"] = config.momentum_weight * trend_terms.contribution
    terms = pd.concat([terms, trend_terms], ignore_index=True)
    clipping = result.loc[result.clipping_adjustment.ne(0) & result.score.notna()]
    if len(clipping):
        terms = pd.concat([terms, pd.DataFrame({
            "input_index": clipping.index, "feature": "score_clipping", "component": "boundary",
            "value": clipping.clipping_adjustment, "standardized_value": np.nan, "feature_score": np.nan, "effective_weight": 0.,
            "contribution": clipping.clipping_adjustment, "direction": "bounded",
            "definition": "Ajuste para mantener score en [0,100]", "layer": "boundary",
            "final_contribution": clipping.clipping_adjustment})], ignore_index=True)
    terms = terms.loc[terms.input_index.isin(result.index[result.score.notna()])]
    terms = terms.merge(p[keys].rename_axis("input_index").reset_index(), on="input_index", validate="many_to_one")
    terms = terms.drop(columns=["input_index"])
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
