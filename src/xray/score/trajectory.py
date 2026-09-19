import numpy as np
import pandas as pd


DIRECTION_THRESHOLD = 10.0
CONFIRMATION_MONTHS = 2
STABILITY_WINDOW = 3
SIGNALS = (
    ("tx_operating_margin_delta3", 1.0, 0.10, 0.25,
     "Operating cash margin t minus t-3; higher improves; scale 0.10 (10 percentage points)."),
    ("debt_service_to_inflow_ratio_delta3", -1.0, 0.10, 0.25,
     "Debt service / operating inflow t minus t-3; lower improves; scale 0.10 (10 percentage points)."),
    ("inv_ar_delay_median_delta3", -1.0, 10.0, 0.125,
     "Realized AR median payment delay t minus t-3, four observed months; lower improves; scale 10 days."),
    ("inv_ap_delay_median_delta3", -1.0, 10.0, 0.125,
     "Realized AP median payment delay t minus t-3, four observed months; lower improves; scale 10 days."),
    ("tx_lfl_inflow_growth_ma3", 1.0, 0.05, 0.25,
     "Mean of three monthly inflow growth rates on common accounts; higher improves; scale 0.05 (5 percent)."),
)
EXPLANATION_COLUMNS = (
    "input_index", "input_position", "feature", "value", "feature_score",
    "effective_weight", "contribution", "direction", "definition",
)


def _empty_result(index):
    size = len(index)
    return pd.DataFrame({
        "momentum": np.full(size, np.nan),
        "momentum_coverage": np.zeros(size),
        "trajectory": pd.Series("insufficient_history", index=index, dtype=str),
        "direction": pd.Series("unknown", index=index, dtype=str),
        "momentum_strength": np.full(size, np.nan),
        "trend_months": np.zeros(size, dtype=np.int64),
        "stability": np.full(size, np.nan),
        "has_momentum": np.zeros(size, dtype=bool),
        "momentum_signal_count": np.zeros(size, dtype=np.int64),
        "momentum_conflict": np.zeros(size, dtype=bool),
        "momentum_sources_changed": np.zeros(size, dtype=bool),
        "momentum_confirmed": np.zeros(size, dtype=bool),
    }, index=index)


def _numeric(frame, column):
    if column not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    try:
        values = pd.to_numeric(frame[column], errors="raise").astype(float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Feature {column} must be numeric") from exc
    return values.where(np.isfinite(values))


def _complete(valid, months=4):
    return valid.astype(int).rolling(months, min_periods=months).sum().eq(months)


def _signals(frame, present):
    usable = present.copy()
    if "score_input_usable" in frame:
        usable &= _numeric(frame, "score_input_usable").eq(1)
    bank_valid = usable.copy()
    if "tx_usable_count" in frame:
        bank_valid &= _numeric(frame, "tx_usable_count").ge(5)
    values = pd.DataFrame(index=frame.index)
    for base in ("tx_operating_margin", "debt_service_to_inflow_ratio"):
        valid = bank_valid.copy()
        if base in frame:
            valid &= _numeric(frame, base).notna()
        name = f"{base}_delta3"
        values[name] = _numeric(frame, name).where(_complete(valid))
    for side in ("ar", "ap"):
        delay = _numeric(frame, f"inv_{side}_delay_median")
        valid = usable & delay.notna()
        if "inv_source_seen" in frame:
            valid &= _numeric(frame, "inv_source_seen").gt(0)
        delay_count = f"inv_{side}_delay_count"
        paid_count = f"inv_{side}_paid_count"
        if delay_count in frame:
            valid &= _numeric(frame, delay_count).ge(5)
        elif paid_count in frame:
            valid &= _numeric(frame, paid_count).gt(0)
        values[f"inv_{side}_delay_median_delta3"] = delay.diff(3).where(_complete(valid))
    growth = _numeric(frame, "tx_lfl_inflow_growth").where(bank_valid & bank_valid.shift(1, fill_value=False))
    values["tx_lfl_inflow_growth_ma3"] = growth.rolling(3, min_periods=3).mean()
    return values.replace([np.inf, -np.inf], np.nan)


def _directions(scores):
    return np.where(scores >= 50 + DIRECTION_THRESHOLD, 1,
                    np.where(scores <= 50 - DIRECTION_THRESHOLD, -1, 0))


def _score_calendar(frame, present):
    values = _signals(frame, present)
    orientations = np.array([signal[1] for signal in SIGNALS])
    scales = np.array([signal[2] for signal in SIGNALS])
    weights = np.array([signal[3] for signal in SIGNALS])
    with np.errstate(over="ignore", invalid="ignore"):
        standardized = (values * orientations / scales).clip(-1e6, 1e6)
    feature_scores = 50 + 50 * np.tanh(standardized)
    available = feature_scores.notna()
    coverage = available.mul(weights).sum(axis=1)
    effective_weights = available.mul(weights).div(coverage.where(coverage.gt(0)), axis=0)
    contributions = feature_scores * effective_weights
    momentum = contributions.sum(axis=1, min_count=1).clip(0, 100)
    feature_directions = _directions(feature_scores.to_numpy())
    aggregate_directions = _directions(momentum.to_numpy())
    result = _empty_result(frame.index)
    result["momentum"] = momentum
    result["momentum_coverage"] = coverage
    result["momentum_strength"] = (momentum - 50).abs() * 2
    result["has_momentum"] = momentum.notna()
    result["momentum_signal_count"] = available.sum(axis=1).astype(np.int64)
    result["momentum_conflict"] = ((feature_directions > 0).any(axis=1)
                                   & (feature_directions < 0).any(axis=1))
    result["momentum_sources_changed"] = available.ne(available.shift(1, fill_value=False)).any(axis=1)
    dispersion = standardized.rolling(STABILITY_WINDOW, min_periods=STABILITY_WINDOW).std(ddof=0)
    diagnostic_weights = dispersion.notna().mul(weights)
    diagnostic_coverage = diagnostic_weights.sum(axis=1)
    diagnostic = (dispersion * diagnostic_weights).sum(axis=1, min_count=1)
    result["stability"] = 100 / (1 + diagnostic.div(diagnostic_coverage.where(diagnostic_coverage.gt(0))))
    result["stability"] = result.stability.where(result.has_momentum).clip(0, 100)
    runs = np.zeros(len(frame), dtype=np.int64)
    labels = np.full(len(frame), "insufficient_history", dtype=object)
    directions = np.full(len(frame), "unknown", dtype=object)
    confirmed = np.zeros(len(frame), dtype=bool)
    seen = available.to_numpy()
    observed = momentum.notna().to_numpy()
    for i in range(len(frame)):
        if not observed[i]:
            continue
        sign = aggregate_directions[i]
        directions[i] = {1: "up", -1: "down", 0: "flat"}[sign]
        labels[i] = "watch"
        shared = seen[i] & seen[i - 1] if i else np.zeros(len(SIGNALS), dtype=bool)
        if sign:
            supported = i > 0 and np.any(shared & (feature_directions[i] == sign)
                                        & (feature_directions[i - 1] == sign))
            continues = supported and observed[i - 1] and aggregate_directions[i - 1] == sign
            runs[i] = runs[i - 1] + sign if continues else sign
            if abs(runs[i]) >= CONFIRMATION_MONTHS:
                labels[i] = "improving" if sign > 0 else "deteriorating"
                confirmed[i] = True
        elif i and observed[i - 1] and aggregate_directions[i - 1] == 0:
            quiet = not feature_directions[i].any() and not feature_directions[i - 1].any()
            if quiet and shared.any():
                labels[i] = "stable"
                confirmed[i] = True
    result["trajectory"] = labels
    result["direction"] = directions
    result["trend_months"] = runs
    result["momentum_confirmed"] = confirmed
    return result, values, feature_scores, effective_weights, contributions


def score_trajectory(panel: pd.DataFrame, unit: str = "company_id") -> tuple[pd.DataFrame, pd.DataFrame]:
    if not isinstance(panel, pd.DataFrame):
        raise TypeError("panel must be a pandas DataFrame")
    if not panel.columns.is_unique:
        raise ValueError("panel columns must be unique")
    if not isinstance(unit, str) or not unit or unit in {"currency", "month"}:
        raise ValueError("unit must identify entities separately from currency and month")
    keys = [unit, "currency", "month"]
    for column in keys:
        if column not in panel:
            raise ValueError(f"Missing required key: {column}")
        if panel[column].isna().any():
            raise ValueError(f"Null key: {column}")
    if pd.api.types.is_numeric_dtype(panel.month.dtype) and not panel.empty:
        raise ValueError("month must contain dates, not numbers")
    try:
        months = pd.to_datetime(panel.month, errors="raise", format="mixed")
        if months.dt.tz is not None:
            raise ValueError("month must be timezone-naive")
        months = months.dt.to_period("M").dt.to_timestamp()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("month must contain valid timezone-naive dates") from exc
    if months.isna().any():
        raise ValueError("month must contain non-null dates")
    frame = panel.copy().reset_index(drop=True)
    frame["month"] = months.to_numpy()
    if frame.duplicated(keys).any():
        raise ValueError(f"Duplicate monthly keys: {', '.join(keys)}")
    result = _empty_result(panel.index.copy())
    explanations = []
    frame["_input_position"] = np.arange(len(frame), dtype=np.int64)
    for _, group in frame.groupby([unit, "currency"], sort=False, observed=True):
        group = group.sort_values("month").set_index("month")
        calendar = pd.date_range(group.index.min(), group.index.max(), freq="MS", name="month")
        expanded = group.reindex(calendar)
        present = pd.Series(calendar.isin(group.index), index=calendar)
        scored, values, feature_scores, effective_weights, contributions = _score_calendar(expanded, present)
        positions = group._input_position.to_numpy(dtype=np.int64)
        for column in result:
            result.iloc[positions, result.columns.get_loc(column)] = scored.loc[group.index, column].to_numpy()
        for feature_number, (feature, orientation, scale, _, definition) in enumerate(SIGNALS):
            valid = feature_scores[feature].notna()
            positions = expanded.loc[valid, "_input_position"].to_numpy(dtype=np.int64)
            if not len(positions):
                continue
            feature_values = values.loc[valid, feature].to_numpy()
            explanations.append(pd.DataFrame({
                "input_index": pd.Series(panel.index.take(positions).to_numpy(), dtype=object),
                "input_position": positions,
                "feature": feature,
                "value": feature_values,
                "feature_score": feature_scores.loc[valid, feature].to_numpy(),
                "effective_weight": effective_weights.loc[valid, feature].to_numpy(),
                "contribution": contributions.loc[valid, feature].to_numpy(),
                "direction": np.where(feature_values * orientation > 0, "up",
                                      np.where(feature_values * orientation < 0, "down", "flat")),
                "definition": definition + f" score = 50 + 50*tanh({orientation:g}*value/{scale:g}); fixed weights renormalized over observed signals.",
                "_feature_order": feature_number,
            }))
    if explanations:
        explain = pd.concat(explanations, ignore_index=True)
        explain = explain.sort_values(["input_position", "_feature_order"]).drop(columns="_feature_order").reset_index(drop=True)
    else:
        text = {"feature", "direction", "definition"}
        dtypes = {"input_index": object, "input_position": np.int64}
        explain = pd.DataFrame({column: pd.Series(dtype=dtypes.get(column, str if column in text else float))
                                for column in EXPLANATION_COLUMNS})
    return result, explain
