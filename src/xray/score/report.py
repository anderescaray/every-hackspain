import numpy as np
import pandas as pd


def distribution(values):
    values = values.dropna()
    if values.empty:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None}
    return {"count": len(values), "min": float(values.min()), "p25": float(values.quantile(.25)),
            "median": float(values.median()), "p75": float(values.quantile(.75)), "max": float(values.max())}


def summarize(scores):
    valid = scores.score.notna()
    return {"rows": len(scores), "scored_rows": int(valid.sum()), "coverage": float(valid.mean()) if len(scores) else None,
            "score": distribution(scores.score), "level": distribution(scores.level),
            "momentum": distribution(scores.momentum), "status": scores.score_status.value_counts().to_dict(),
            "reason": scores.score_reason.value_counts().to_dict(),
            "trajectory": scores.loc[valid].trajectory.value_counts().to_dict(),
            "absolute_monthly_delta": distribution(scores.delta_vs_prev.abs()),
            "saturated_scores": int((valid & (scores.score.le(1) | scores.score.ge(99))).sum()),
            "partial_currency_scored": int((valid & scores.has_partial_currency_coverage).sum())}


def score_report(scores, reference):
    unit = "company_id" if "company_id" in scores else "group_id"
    latest = latest_scores(scores, unit)
    monthly = []
    for month, frame in scores.groupby("month", sort=True):
        monthly.append({"month": str(month.date()), **summarize(frame)})
    cohorts = {str(name): summarize(frame) for name, frame in scores.groupby("reference_partition")}
    return {
        "method": reference["method"], "evaluation_kind": "mechanical_transfer_and_diagnostics_without_labels",
        "official_score_agreement": None, "predictive_accuracy": None, "lead_time": None,
        "is_probability": False, "weights_validated_against_labels": False,
        "reference_group_count": len(reference["reference_groups"]),
        "holdout_group_count": len(reference["holdout_groups"]),
        "holdout_group_fraction": len(reference["holdout_groups"]) / max(1, len(reference["reference_groups"]) + len(reference["holdout_groups"])),
        "all_months": summarize(scores), "latest_month": str(scores.month.max().date()),
        "latest": summarize(latest), "cohorts": cohorts, "by_month": monthly,
        "by_currency": {str(name): summarize(frame) for name, frame in scores.groupby("currency")},
        "reference_calendar": [{key: value for key, value in item.items() if key != "state"} for item in reference["references"]],
        "limitations": ["Sin score oficial ni etiquetas: no se ha medido acierto ni anticipación.",
                        "Holdout por grupo comprueba transferencia mecánica, no calidad crediticia.",
                        "Score de flujos observados, no rating contable ni probabilidad de impago.",
                        "Facturas opcionales, hipótesis de continuidad ERP y moneda incompleta afectan cobertura.",
                        "Las decisiones de limpieza provienen de snapshots sin histórico de ingestión."]}


def latest_scores(scores, unit):
    last_month = scores.month.max()
    current = scores.loc[scores.month.eq(last_month)].copy()
    keys = [unit, "currency"]
    metadata = list(dict.fromkeys(keys + ["group_id", "reference_partition", "method"]))
    universe = scores[metadata].drop_duplicates(keys)
    latest = universe.merge(current.drop(columns=[col for col in metadata if col not in keys]),
                            on=keys, how="left", validate="one_to_one")
    latest["current_month_present"] = latest.month.notna()
    absent = ~latest.current_month_present
    latest.loc[absent, "month"] = last_month
    latest.loc[absent, "score_status"] = "not_scored"
    latest.loc[absent, "score_reason"] = "missing_current_month"
    latest.loc[absent, "trajectory"] = "insufficient_history"
    latest.loc[absent, "direction"] = "unknown"
    historical = scores.loc[scores.score.notna()].groupby(keys).month.max().rename("last_scored_month")
    latest = latest.merge(historical.reset_index(), on=keys, how="left", validate="one_to_one")
    latest["is_stale"] = latest.last_scored_month.notna() & latest.last_scored_month.lt(latest.month)
    latest["staleness_status"] = np.select([latest.last_scored_month.isna(), latest.is_stale],
                                          ["never_scored", "stale"], default="current")
    return latest.sort_values(keys).reset_index(drop=True)


def example_cases(scores, explanations, unit):
    latest = scores.loc[scores.month.eq(scores.month.max()) & scores.score.notna() & scores.reference_partition.eq("holdout")]
    cases = []
    for trajectory in ("improving", "deteriorating", "stable", "watch"):
        selected = latest.loc[latest.trajectory.eq(trajectory)].sort_values(["momentum_strength", unit], ascending=[False, True]).head(2)
        for _, row in selected.iterrows():
            history = scores.loc[scores[unit].eq(row[unit]) & scores.currency.eq(row.currency)]
            drivers = explanations.loc[explanations[unit].eq(row[unit]) & explanations.currency.eq(row.currency)
                                       & explanations.month.eq(row.month)]
            driver_cols = ["layer", "feature", "value", "feature_score", "effective_weight", "final_contribution", "definition"]
            cases.append({"entity": str(row[unit]), "currency": str(row.currency), "selection": "illustrative_holdout_example_not_accuracy",
                          "trajectory": trajectory, "month": str(row.month.date()), "score": float(row.score),
                          "level": float(row.level), "momentum": float(row.momentum) if pd.notna(row.momentum) else None,
                          "status": row.score_status, "reason": row.score_reason,
                          "history": history[["month", "score", "level", "momentum", "trajectory", "score_status"]].to_dict("records"),
                          "drivers": drivers[driver_cols].to_dict("records")})
    return cases


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.generic):
        return value.item()
    return value
