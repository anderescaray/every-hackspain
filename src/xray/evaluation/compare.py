"""Comparador reproducible de variantes de score (V1 control frente a V2 suavizado).

Protocolo fijado antes de mirar resultados; ver `docs/validation.md`.

Bloques:
1. Estabilidad y cobertura: cambio mensual absoluto, extremos, cambios de etiqueta, filas puntuadas.
2. Proxy de estrés futuro (texto bancario reservado), normalizado por exposición: AUC global,
   AUC dentro de terciles de actividad (control de tamaño), Spearman con la tasa de eventos por
   movimiento y bootstrap por grupo de la diferencia de AUC V2−V1 sobre las **mismas filas**.
3. Riesgo relativo por etiqueta de trayectoria: tasa de eventos a 6 meses de las empresas
   marcadas como deteriorándose / mejorando frente a estables.
4. Anticipación con regla independiente del modelo: inicio de episodio de estrés tras seis
   meses limpios; `lead = t_evidente − t_señal`; tasa de falsas alarmas con el mismo umbral.
5. Sensibilidad de las etiquetas V2 al umbral de dirección.

El proxy no es la nota del organizador: sirve para comparar variantes, no para afirmar acierto.
El holdout ya fue inspeccionado en la auditoría de V1; se reporta aparte y etiquetado.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from xray.artifacts import code_manifest, sha256
from xray.paths import PROCESSED_DIR
from xray.score.report import json_safe

KEYS = ["company_id", "currency", "month"]
HORIZONS = (3, 6)
BOOTSTRAP = 200
SEED = 20260919
V1_DETERIORATING = {"deteriorating"}
V1_IMPROVING = {"improving"}
V2_DETERIORATING = {"deteriorating"}
V2_IMPROVING = {"improving"}
V2_ANY_DOWN = {"deteriorating", "emerging_deterioration"}
V2_ANY_UP = {"improving", "emerging_improvement"}


# ---------------------------------------------------------------- utilidades


def _q(values, quantiles=(.5, .75, .95)):
    values = pd.Series(values).dropna()
    if values.empty:
        return {f"p{int(q * 100)}": None for q in quantiles}
    return {f"p{int(q * 100)}": float(values.quantile(q)) for q in quantiles}


def auc(y, risk):
    """AUC por rangos medios (equivalente a Mann-Whitney); None si falta una clase."""
    valid = pd.Series(y).notna() & pd.Series(risk).notna()
    y, risk = pd.Series(y)[valid].astype(int), pd.Series(risk)[valid]
    positives = int(y.sum())
    negatives = len(y) - positives
    if not positives or not negatives:
        return None
    ranks = risk.rank(method="average")
    return float((ranks[y.eq(1)].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def spearman(a, b):
    valid = pd.Series(a).notna() & pd.Series(b).notna()
    if valid.sum() < 3:
        return None
    ra, rb = pd.Series(a)[valid].rank(), pd.Series(b)[valid].rank()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def stratified_auc(frame, y, risk, strata):
    values = []
    for _, part in frame.groupby(strata, observed=True):
        value = auc(part[y], part[risk])
        if value is not None:
            values.append(value)
    return float(np.mean(values)) if values else None


def group_bootstrap_auc_difference(frame, y, risk_a, risk_b, groups, n=BOOTSTRAP, seed=SEED):
    """IC 95% por bootstrap de grupos completos para AUC(risk_b) − AUC(risk_a)."""
    rng = np.random.default_rng(seed)
    unique = frame[groups].unique()
    by_group = {g: part for g, part in frame.groupby(groups, observed=True)}
    diffs = []
    for _ in range(n):
        sample = pd.concat([by_group[g] for g in rng.choice(unique, len(unique), replace=True)], ignore_index=True)
        a, b = auc(sample[y], sample[risk_a]), auc(sample[y], sample[risk_b])
        if a is not None and b is not None:
            diffs.append(b - a)
    if not diffs:
        return None
    diffs = np.array(diffs)
    return {"mean": float(diffs.mean()), "ci95": [float(np.quantile(diffs, .025)), float(np.quantile(diffs, .975))],
            "share_positive": float((diffs > 0).mean()), "resamples": len(diffs), "groups": int(len(unique))}


# ---------------------------------------------------------------- bloque 1: estabilidad


def stability(scores, label_column="trajectory"):
    valid = scores.score.notna()
    ordered = scores.loc[valid].sort_values(["company_id", "currency", "month"])
    previous_label = ordered.groupby(["company_id", "currency"])[label_column].shift(1)
    pairs = previous_label.notna()
    latest = scores.loc[scores.month.eq(scores.month.max())]
    delta = scores.delta_vs_prev.abs()
    return {
        "rows": int(len(scores)), "scored_rows": int(valid.sum()),
        "abs_monthly_delta": _q(delta), "share_delta_over_10": float(delta.gt(10).mean()) if delta.notna().any() else None,
        "share_delta_over_20": float(delta.gt(20).mean()) if delta.notna().any() else None,
        "exact_extremes": int((scores.score.eq(0) | scores.score.eq(100)).sum()),
        "near_extremes": int((scores.score.le(1) | scores.score.ge(99)).sum()),
        "label_flip_rate": float((ordered[label_column].ne(previous_label) & pairs).sum() / pairs.sum()) if pairs.any() else None,
        "trajectory_counts": scores.loc[valid, label_column].value_counts().to_dict(),
        "latest_month": str(scores.month.max().date()), "latest_scored": int(latest.score.notna().sum()),
        "latest_entities": int(latest.company_id.nunique()),
        "latest_trajectory_counts": latest.loc[latest.score.notna(), label_column].value_counts().to_dict(),
        "latest_status": latest.score_status.value_counts().to_dict(),
    }


def common_rows_stability(v1, v2):
    merged = v1[KEYS + ["score"]].merge(v2[KEYS + ["score"]], on=KEYS, suffixes=("_v1", "_v2"))
    both = merged.dropna(subset=["score_v1", "score_v2"]).sort_values(KEYS)
    out = {"common_scored_rows": int(len(both)), "only_v1": int((merged.score_v1.notna() & merged.score_v2.isna()).sum()),
           "only_v2": int((merged.score_v2.notna() & merged.score_v1.isna()).sum())}
    if len(both) > 2:
        out["pearson"] = float(np.corrcoef(both.score_v1, both.score_v2)[0, 1])
        out["spearman"] = spearman(both.score_v1, both.score_v2)
        grouped = both.groupby(["company_id", "currency"])
        consecutive = grouped.month.diff().eq(pd.Timedelta(days=28)) | grouped.month.diff().dt.days.between(28, 31)
        for name in ("v1", "v2"):
            delta = grouped[f"score_{name}"].diff().abs().where(consecutive)
            out[f"abs_monthly_delta_{name}_common"] = _q(delta)
    return out


# ---------------------------------------------------------------- bloque 2: proxy de estrés futuro


def future_stress(events, features, horizon):
    """Eventos y exposición en t+1..t+h; censura si algún mes futuro no tiene registro observable."""
    e = events.copy()
    e["stress_total"] = e.filter(regex="^stress_").sum(axis=1, min_count=1)
    e = e.merge(features[["company_id", "month", "tx_all_currency_count"]], on=["company_id", "month"], how="left")
    e = e.sort_values(["company_id", "month"]).reset_index(drop=True)
    g = e.groupby("company_id")
    future_events = sum(g.stress_total.shift(-k) for k in range(1, horizon + 1))
    future_exposure = sum(g.tx_all_currency_count.shift(-k) for k in range(1, horizon + 1))
    observed = pd.concat([g.stress_total.shift(-k) for k in range(1, horizon + 1)], axis=1).notna().all(axis=1)
    out = e[["company_id", "month"]].copy()
    out[f"future_any_{horizon}"] = future_events.gt(0).astype(float).where(observed)
    out[f"future_rate_{horizon}"] = (future_events / future_exposure.where(future_exposure.gt(0))).where(observed)
    out[f"future_observed_{horizon}"] = observed
    return out


def future_liquidity_stress(liquidity, horizon):
    """Tensión de liquidez futura: caja reconstruida < 0 (descubierto) en algún mes de t+1..t+h, con los h meses observados.

    Independiente del score: la caja reconstruida no es una feature de V1 ni de V2. Se usa caja negativa
    y no runway < 1 porque en este dataset la mediana de runway es 0,9 meses (runway < 1 ocurre en el 51% de
    las filas y no discrimina); caja negativa ocurre en ≈7,5% de las filas con caja. Sigue siendo una
    reconstrucción retrospectiva (ver FE06), no un saldo observado en producción.
    """
    l = liquidity.sort_values(KEYS).reset_index(drop=True)
    g = l.groupby(["company_id", "currency"])
    ahead = pd.concat([g.reconstructed_cash.shift(-k) for k in range(1, horizon + 1)], axis=1)
    observed = ahead.notna().all(axis=1)
    out = l[KEYS].copy()
    out[f"future_liquidity_stress_{horizon}"] = ahead.lt(0).any(axis=1).astype(float).where(observed)
    return out


def liquidity_stress_onsets(liquidity, clean_months=6):
    """Primer mes con caja reconstruida < 0 tras `clean_months` meses observados consecutivos con caja ≥ 0."""
    l = liquidity.sort_values(KEYS).reset_index(drop=True)
    cash = l.reconstructed_cash
    healthy = cash.ge(0).astype(float).where(cash.notna())
    run = healthy.groupby([l.company_id, l.currency]).rolling(clean_months, min_periods=clean_months).sum().droplevel([0, 1]).reindex(l.index)
    previous = run.groupby([l.company_id, l.currency]).shift(1)
    onset = cash.lt(0) & previous.eq(clean_months)
    return l.loc[onset, ["company_id", "month"]].rename(columns={"month": "onset"})


def proxy_discrimination(frame, y, rate, risks, activity="activity"):
    frame = frame.copy()
    frame["_stratum"] = pd.qcut(frame[activity].rank(method="first"), 3, labels=["small", "mid", "large"])
    out = {"rows": int(len(frame)), "groups": int(frame.group_id.nunique()), "positives": int(frame[y].sum()),
           "positive_rate": float(frame[y].mean()), "risks": {}}
    for name, column in risks.items():
        out["risks"][name] = {"auc": auc(frame[y], frame[column]),
                              "auc_within_activity_terciles": stratified_auc(frame, y, column, "_stratum"),
                              "spearman_with_event_rate": spearman(frame[column], frame[rate]) if rate else None}
    return out


def proxy_block(features, events, v1, v2, liquidity):
    base = features[KEYS + ["group_id", "tx_all_currency_count"]].merge(
        v1[KEYS + ["score", "trajectory", "momentum", "reference_partition"]].rename(
            columns={"score": "score_v1", "trajectory": "trajectory_v1", "momentum": "momentum_v1"}), on=KEYS)
    base = base.merge(v2[KEYS + ["score", "level", "momentum", "trajectory", "episode"]].rename(
        columns={"score": "score_v2", "level": "level_v2", "momentum": "momentum_v2", "trajectory": "trajectory_v2"}), on=KEYS)
    base = base.merge(liquidity[KEYS + ["cash_runway_months_retrospective", "reconstructed_cash"]], on=KEYS, how="left")
    base["activity"] = np.log1p(base.tx_all_currency_count)
    results = {}
    for horizon in HORIZONS:
        future = future_stress(events, features, horizon)
        frame = base.merge(future, on=["company_id", "month"], how="left")
        y, rate = f"future_any_{horizon}", f"future_rate_{horizon}"
        frame["risk_v1"], frame["risk_v2"], frame["risk_level_v2"] = -frame.score_v1, -frame.score_v2, -frame.level_v2
        frame["risk_momentum_v2"] = -frame.momentum_v2
        frame["risk_cash"] = -frame.cash_runway_months_retrospective
        frame["risk_activity"] = -frame.activity
        per_partition = {}
        for partition in ("reference", "holdout"):
            part = frame.loc[frame.reference_partition.eq(partition) & frame[y].notna()]
            common = part.dropna(subset=["score_v1", "score_v2"])
            block = {"note": "development partition" if partition == "reference" else "holdout already inspected during V1 audit; not a pristine test",
                     "common_v1_v2": proxy_discrimination(common, y, rate, {
                         "v1_score": "risk_v1", "v2_score": "risk_v2", "v2_level": "risk_level_v2",
                         "v2_momentum": "risk_momentum_v2", "activity_baseline": "risk_activity"})}
            if len(common) and common[y].nunique() == 2:
                block["bootstrap_auc_v2_minus_v1"] = group_bootstrap_auc_difference(common, y, "risk_v1", "risk_v2", "group_id")
            with_cash = common.dropna(subset=["cash_runway_months_retrospective"])
            if len(with_cash):
                block["common_with_cash"] = proxy_discrimination(with_cash, y, rate, {
                    "v1_score": "risk_v1", "v2_score": "risk_v2", "cash_runway": "risk_cash", "activity_baseline": "risk_activity"})
            only_v2 = part.loc[part.score_v2.notna() & part.score_v1.isna()]
            block["rows_scored_only_by_v2"] = {"rows": int(len(only_v2)), "positive_rate": float(only_v2[y].mean()) if len(only_v2) else None,
                                               "auc_v2": auc(only_v2[y], only_v2.risk_v2) if len(only_v2) else None}
            per_partition[partition] = block
        results[f"horizon_{horizon}"] = per_partition
    return results, base


def liquidity_proxy_block(base, liquidity):
    """Discriminación frente a tensión de liquidez futura (caja reconstruida < 0), filas comunes V1/V2 con caja futura observada."""
    results = {}
    for horizon in HORIZONS:
        future = future_liquidity_stress(liquidity, horizon)
        y = f"future_liquidity_stress_{horizon}"
        frame = base.merge(future, on=KEYS, how="left")
        frame["risk_v1"], frame["risk_v2"], frame["risk_level_v2"] = -frame.score_v1, -frame.score_v2, -frame.level_v2
        frame["risk_momentum_v2"], frame["risk_activity"] = -frame.momentum_v2, -frame.activity
        frame["risk_current_runway"] = -frame.cash_runway_months_retrospective
        frame["risk_current_cash"] = -frame.reconstructed_cash
        per_partition = {}
        for partition in ("reference", "holdout"):
            common = frame.loc[frame.reference_partition.eq(partition) & frame[y].notna()].dropna(subset=["score_v1", "score_v2"])
            if common.empty or common[y].nunique() < 2:
                per_partition[partition] = {"rows": int(len(common)), "note": "sin ambas clases"}
                continue
            block = {"common_v1_v2": proxy_discrimination(common, y, None, {
                "v1_score": "risk_v1", "v2_score": "risk_v2", "v2_level": "risk_level_v2", "v2_momentum": "risk_momentum_v2",
                "activity_baseline": "risk_activity", "current_runway_persistence_baseline": "risk_current_runway",
                "current_cash_persistence_baseline": "risk_current_cash"}),
                "bootstrap_auc_v2_minus_v1": group_bootstrap_auc_difference(common, y, "risk_v1", "risk_v2", "group_id")}
            per_partition[partition] = block
        results[f"horizon_{horizon}"] = per_partition
    return results


def label_relative_risk(base, events, features, horizon=6):
    """Tasa de eventos futuros por etiqueta de trayectoria, frente a la etiqueta neutral de cada versión."""
    future = future_stress(events, features, horizon)
    frame = base.merge(future, on=["company_id", "month"], how="left")
    y = f"future_any_{horizon}"
    frame = frame.loc[frame[y].notna() & frame.reference_partition.eq("reference")]
    out = {"horizon": horizon, "partition": "reference"}
    for name, column, neutral in (("v1", "trajectory_v1", "watch"), ("v2", "trajectory_v2", "stable")):
        rates = frame.loc[frame[f"score_{name}"].notna()].groupby(column)[y].agg(["mean", "size"])
        neutral_rate = float(rates.loc[neutral, "mean"]) if neutral in rates.index else None
        out[name] = {label: {"event_rate": float(row["mean"]), "rows": int(row["size"]),
                             "relative_risk_vs_neutral": float(row["mean"] / neutral_rate) if neutral_rate else None}
                     for label, row in rates.iterrows()}
    v2 = frame.loc[frame.score_v2.notna()]
    episodes = v2.groupby("episode")[y].agg(["mean", "size"])
    out["v2_episode"] = {label: {"event_rate": float(row["mean"]), "rows": int(row["size"])} for label, row in episodes.iterrows()}
    return out


# ---------------------------------------------------------------- bloque 4: anticipación con regla independiente


def stress_onsets(events, clean_months=6):
    """Primer mes con evento tras `clean_months` meses observados consecutivos sin eventos."""
    e = events.copy()
    e["stress_total"] = e.filter(regex="^stress_").sum(axis=1, min_count=1)
    e = e.sort_values(["company_id", "month"])
    clean = e.stress_total.eq(0)
    run = clean.astype(int).groupby(e.company_id).rolling(clean_months, min_periods=clean_months).sum().droplevel(0).reindex(e.index)
    previous_clean = run.groupby(e.company_id).shift(1)
    onset = e.stress_total.gt(0) & previous_clean.eq(clean_months)
    return e.loc[onset, ["company_id", "month"]].rename(columns={"month": "onset"})


def stress_recoveries(events, clean_months=6):
    """Primer mes de una racha de `clean_months` meses sin eventos que sigue a un mes con evento."""
    e = events.copy()
    e["stress_total"] = e.filter(regex="^stress_").sum(axis=1, min_count=1)
    e = e.sort_values(["company_id", "month"]).reset_index(drop=True)
    g = e.groupby("company_id")
    ahead = pd.concat([g.stress_total.shift(-k) for k in range(clean_months)], axis=1)
    clean_run_starts = ahead.notna().all(axis=1) & ahead.eq(0).all(axis=1)
    previous_event = g.stress_total.shift(1).gt(0)
    return e.loc[clean_run_starts & previous_event, ["company_id", "month"]].rename(columns={"month": "recovery"})


def lead_time(scores, flags, anchors, anchor_column, lookback=6):
    """Para cada ancla (inicio o recuperación), primer mes marcado en [ancla−lookback, ancla−1]."""
    flagged = scores.loc[flags, ["company_id", "month"]]
    leads, detected = [], 0
    for _, row in anchors.iterrows():
        window = flagged.loc[flagged.company_id.eq(row.company_id)
                             & flagged.month.lt(row[anchor_column])
                             & flagged.month.ge(row[anchor_column] - pd.DateOffset(months=lookback))]
        if len(window):
            detected += 1
            leads.append((row[anchor_column].to_period("M") - window.month.min().to_period("M")).n)
    return {"anchors": int(len(anchors)), "detected_within_lookback": detected,
            "detection_share": float(detected / len(anchors)) if len(anchors) else None,
            "lead_months": {"median": float(np.median(leads)) if leads else None,
                            "p25": float(np.quantile(leads, .25)) if leads else None,
                            "p75": float(np.quantile(leads, .75)) if leads else None}}


def false_alarm_rate(scores, flags, events, features, horizon=6):
    future = future_stress(events, features, horizon)
    frame = scores.loc[flags, ["company_id", "month"]].merge(future, on=["company_id", "month"], how="left")
    y = f"future_any_{horizon}"
    evaluable = frame[y].notna()
    return {"flagged_rows": int(len(frame)), "evaluable_rows": int(evaluable.sum()),
            "false_alarm_share": float(1 - frame.loc[evaluable, y].mean()) if evaluable.any() else None}


def anticipation_block(v1, v2, events, features, liquidity):
    onsets = stress_onsets(events)
    recoveries = stress_recoveries(events)
    liquidity_onsets = liquidity_stress_onsets(liquidity)
    scored_companies = v2.loc[v2.score.notna(), "company_id"].unique()
    onsets = onsets.loc[onsets.company_id.isin(scored_companies)]
    recoveries = recoveries.loc[recoveries.company_id.isin(scored_companies)]
    liquidity_onsets = liquidity_onsets.loc[liquidity_onsets.company_id.isin(scored_companies)]
    base_rate = future_stress(events, features, 6)
    definitions = {
        "v1_confirmed_deteriorating": (v1, v1.trajectory.isin(V1_DETERIORATING)),
        "v1_momentum_below_40": (v1, v1.momentum.le(40)),
        "v2_confirmed_deteriorating": (v2, v2.trajectory.isin(V2_DETERIORATING)),
        "v2_emerging_or_confirmed_deterioration": (v2, v2.trajectory.isin(V2_ANY_DOWN)),
    }
    up_definitions = {
        "v1_confirmed_improving": (v1, v1.trajectory.isin(V1_IMPROVING)),
        "v2_confirmed_improving": (v2, v2.trajectory.isin(V2_IMPROVING)),
        "v2_emerging_or_confirmed_improvement": (v2, v2.trajectory.isin(V2_ANY_UP)),
    }
    out = {"rule": "t_evidente = primer mes con evento textual de estrés tras 6 meses observados sin eventos; "
                   "t_señal = primer mes marcado en los 6 meses anteriores; lead = t_evidente − t_señal. "
                   "Regla independiente del score; el texto es un proxy sintético, no un impago confirmado.",
           "base_event_rate_6m_all_scored_rows": float(base_rate.merge(v2.loc[v2.score.notna(), ["company_id", "month"]],
                                                                          on=["company_id", "month"]).future_any_6.mean()),
           "deterioration": {}, "improvement": {}}
    for name, (scores, flags) in definitions.items():
        out["deterioration"][name] = {**lead_time(scores, flags, onsets, "onset"),
                                      "false_alarms_6m": false_alarm_rate(scores, flags, events, features)}
    for name, (scores, flags) in up_definitions.items():
        out["improvement"][name] = {**lead_time(scores, flags, recoveries, "recovery"),
                                    "note": "recuperación = inicio de 6 meses limpios tras un evento; señal de mejora en los 6 meses previos"}
    out["liquidity_rule"] = "t_evidente = primer mes con caja reconstruida < 0 tras 6 meses observados con caja ≥ 0. La caja no es feature de V1 ni V2."
    out["liquidity_deterioration"] = {}
    future_liq = future_liquidity_stress(liquidity, 6)
    for name, (scores, flags) in definitions.items():
        flagged = scores.loc[flags, KEYS].merge(future_liq, on=KEYS, how="left")
        evaluable = flagged.future_liquidity_stress_6.notna()
        out["liquidity_deterioration"][name] = {
            **lead_time(scores, flags, liquidity_onsets, "onset"),
            "false_alarms_6m": {"flagged_rows": int(len(flagged)), "evaluable_rows": int(evaluable.sum()),
                                "false_alarm_share": float(1 - flagged.loc[evaluable, "future_liquidity_stress_6"].mean()) if evaluable.any() else None}}
    scored_rows = v2.loc[v2.score.notna(), KEYS].merge(future_liq, on=KEYS, how="left")
    out["base_liquidity_stress_rate_6m_all_scored_rows"] = float(scored_rows.future_liquidity_stress_6.mean()) if scored_rows.future_liquidity_stress_6.notna().any() else None
    return out


# ---------------------------------------------------------------- bloque 5: sensibilidad al umbral


def threshold_sensitivity(features, events, thresholds=(1.0, 1.5, 2.0)):
    from xray.score_v2.config import ScoreV2Config
    from xray.score_v2.core import prepare_panel
    from xray.score_v2.signals import build_signals
    from xray.score_v2.trajectory import score_trajectory

    config = ScoreV2Config()
    panel = prepare_panel(features, config)
    signals = build_signals(panel, config)
    future = future_stress(events, features, 6)
    out = {}
    for threshold in thresholds:
        variant = ScoreV2Config(direction_z=threshold)
        trajectory, _ = score_trajectory(signals, panel, config.unit, variant)
        frame = pd.concat([panel[["company_id", "month"]], trajectory[["trajectory", "momentum"]]], axis=1)
        frame = frame.loc[frame.momentum.notna()].merge(future, on=["company_id", "month"], how="left")
        counts = frame.trajectory.value_counts(normalize=True).round(4).to_dict()
        flagged = frame.loc[frame.trajectory.eq("deteriorating") & frame.future_any_6.notna()]
        out[str(threshold)] = {"label_shares": counts,
                               "confirmed_deteriorating_false_alarm_6m": float(1 - flagged.future_any_6.mean()) if len(flagged) else None,
                               "confirmed_deteriorating_rows": int(len(flagged))}
    return out


# ---------------------------------------------------------------- orquestación


def compare(features_dir=PROCESSED_DIR, v1_dir=None, v2_dir=None, out_dir=None, with_sensitivity=True):
    features_dir = Path(features_dir)
    v1_dir = Path(v1_dir) if v1_dir else features_dir / "scores"
    v2_dir = Path(v2_dir) if v2_dir else features_dir / "scores_v2"
    out_dir = Path(out_dir) if out_dir else features_dir / "evaluation"
    inputs = {"features": features_dir / "company_monthly_features.parquet",
              "events": features_dir / "stress_events_reserved.parquet",
              "liquidity": features_dir / "company_currency_liquidity_context.parquet",
              "v1": v1_dir / "company_monthly_scores.parquet", "v2": v2_dir / "company_monthly_scores.parquet"}
    features, events, liquidity = (pd.read_parquet(inputs[k]) for k in ("features", "events", "liquidity"))
    v1, v2 = pd.read_parquet(inputs["v1"]), pd.read_parquet(inputs["v2"])
    if v1.method.iloc[0] == v2.method.iloc[0]:
        raise ValueError("Las dos salidas comparadas tienen el mismo método")
    proxy, base = proxy_block(features, events, v1, v2, liquidity)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methods": {"v1": v1.method.iloc[0], "v2": v2.method.iloc[0]},
        "inputs_sha256": {k: sha256(p) for k, p in inputs.items()}, "code": code_manifest(),
        "protocol": {"horizons": list(HORIZONS), "bootstrap_resamples": BOOTSTRAP, "seed": SEED,
                     "development_partition": "reference", "holdout_status": "already inspected in V1 audit",
                     "proxy": "any reserved stress text event in t+1..t+h with all future months observed; "
                              "rate = events / tx_all_currency_count over the same months",
                     "official_labels_available": False},
        "stability": {"v1": stability(v1), "v2": stability(v2), "common_rows": common_rows_stability(v1, v2)},
        "proxy_discrimination": proxy,
        "liquidity_proxy_discrimination": liquidity_proxy_block(base, liquidity),
        "label_relative_risk_6m": label_relative_risk(base, events, features),
        "anticipation": anticipation_block(v1, v2, events, features, liquidity),
        "limitations": [
            "El proxy son menciones textuales sintéticas (EMBARGO, IMPAGADO, DESCUBIERTO...), no impagos confirmados ni la nota del organizador.",
            "Las ventanas de horizonte se solapan y las filas no son independientes; los IC son por bootstrap de grupos completos.",
            "El holdout se inspeccionó en la auditoría de V1: no es un test intacto.",
            "La cobertura de V2 difiere de V1 (ventana mínima de 3 meses; mes actual fino permitido): la discriminación se compara en filas comunes.",
            "Ninguna cifra demuestra acuerdo con el score oculto ni anticipación financiera real.",
        ],
    }
    if with_sensitivity:
        report["v2_direction_threshold_sensitivity"] = threshold_sensitivity(features, events)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "score_comparison.json").write_text(json.dumps(json_safe(report), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (out_dir / "score_comparison.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def _fmt(value, digits=3):
    return "—" if value is None else f"{value:.{digits}f}"


def render_markdown(report):
    s1, s2, common = report["stability"]["v1"], report["stability"]["v2"], report["stability"]["common_rows"]
    lines = [f"# Comparación de scores · {report['methods']['v1']} frente a {report['methods']['v2']}", "",
             f"Generado {report['created_at']}. Proxy: {report['protocol']['proxy']}. Sin etiquetas oficiales.", "",
             "## 1. Estabilidad y cobertura (toda la historia)", "",
             "| Métrica | V1 | V2 |", "|---|---:|---:|",
             f"| Filas puntuadas | {s1['scored_rows']} | {s2['scored_rows']} |",
             f"| Mediana / p75 / p95 de cambio mensual absoluto | {_fmt(s1['abs_monthly_delta']['p50'], 2)} / {_fmt(s1['abs_monthly_delta']['p75'], 2)} / {_fmt(s1['abs_monthly_delta']['p95'], 2)} | {_fmt(s2['abs_monthly_delta']['p50'], 2)} / {_fmt(s2['abs_monthly_delta']['p75'], 2)} / {_fmt(s2['abs_monthly_delta']['p95'], 2)} |",
             f"| Cambios > 10 puntos | {_fmt(s1['share_delta_over_10'])} | {_fmt(s2['share_delta_over_10'])} |",
             f"| Scores exactamente 0/100 | {s1['exact_extremes']} | {s2['exact_extremes']} |",
             f"| Tasa de cambio de etiqueta mes a mes | {_fmt(s1['label_flip_rate'])} | {_fmt(s2['label_flip_rate'])} |",
             f"| Puntuadas en {s1['latest_month']} | {s1['latest_scored']} | {s2['latest_scored']} |", "",
             f"Filas comunes puntuadas por ambas: {common['common_scored_rows']} (solo V1: {common['only_v1']}, solo V2: {common['only_v2']}); "
             f"Spearman entre scores {_fmt(common.get('spearman'))}. En esas filas, mediana de |Δ| V1 {_fmt(common.get('abs_monthly_delta_v1_common', {}).get('p50'), 2)} "
             f"frente a V2 {_fmt(common.get('abs_monthly_delta_v2_common', {}).get('p50'), 2)}.", "",
             f"Trayectorias V1: {s1['trajectory_counts']}", "", f"Trayectorias V2: {s2['trajectory_counts']}", "",
             "## 2. Proxy de estrés futuro (filas comunes, partición de desarrollo)", "",
             "| Horizonte | Filas / grupos | Positivos | AUC V1 | AUC V2 | AUC V2 nivel | AUC V2 momentum | AUC actividad | AUC V2 en terciles | AUC V1 en terciles | Δ AUC V2−V1 IC95 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for horizon in HORIZONS:
        block = report["proxy_discrimination"][f"horizon_{horizon}"]["reference"]
        c = block["common_v1_v2"]
        r = c["risks"]
        boot = block.get("bootstrap_auc_v2_minus_v1") or {}
        ci = boot.get("ci95")
        lines.append(f"| {horizon}m | {c['rows']} / {c['groups']} | {c['positives']} | {_fmt(r['v1_score']['auc'])} | {_fmt(r['v2_score']['auc'])} | "
                     f"{_fmt(r['v2_level']['auc'])} | {_fmt(r['v2_momentum']['auc'])} | {_fmt(r['activity_baseline']['auc'])} | "
                     f"{_fmt(r['v2_score']['auc_within_activity_terciles'])} | {_fmt(r['v1_score']['auc_within_activity_terciles'])} | "
                     f"{'—' if not ci else f'[{ci[0]:+.3f}, {ci[1]:+.3f}]'} |")
    lines += ["", "Spearman con la tasa de eventos por movimiento (6m, desarrollo): " + ", ".join(
        f"{k} {_fmt(v['spearman_with_event_rate'])}" for k, v in report["proxy_discrimination"]["horizon_6"]["reference"]["common_v1_v2"]["risks"].items()), ""]
    cash = report["proxy_discrimination"]["horizon_6"]["reference"].get("common_with_cash")
    if cash:
        lines += [f"Cohorte con caja reconstruida (6m, {cash['rows']} filas): " + ", ".join(f"{k} AUC {_fmt(v['auc'])}" for k, v in cash["risks"].items()), ""]
    hold = report["proxy_discrimination"]["horizon_6"]["holdout"]["common_v1_v2"]["risks"]
    lines += [f"Holdout (ya inspeccionado, 6m): AUC V1 {_fmt(hold['v1_score']['auc'])}, V2 {_fmt(hold['v2_score']['auc'])}, actividad {_fmt(hold['activity_baseline']['auc'])}.", "",
              "## 2b. Proxy de tensión de liquidez futura (caja reconstruida < 0; filas comunes con caja futura observada)", "",
              "| Horizonte | Partición | Filas / grupos | Positivos | AUC V1 | AUC V2 | AUC V2 nivel | AUC V2 momentum | AUC actividad | AUC caja actual | Δ AUC V2−V1 IC95 |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for horizon in HORIZONS:
        for partition in ("reference", "holdout"):
            block = report["liquidity_proxy_discrimination"][f"horizon_{horizon}"][partition]
            if "common_v1_v2" not in block:
                continue
            c, r = block["common_v1_v2"], block["common_v1_v2"]["risks"]
            ci = (block.get("bootstrap_auc_v2_minus_v1") or {}).get("ci95")
            lines.append(f"| {horizon}m | {partition} | {c['rows']} / {c['groups']} | {c['positives']} | {_fmt(r['v1_score']['auc'])} | {_fmt(r['v2_score']['auc'])} | "
                         f"{_fmt(r['v2_level']['auc'])} | {_fmt(r['v2_momentum']['auc'])} | {_fmt(r['activity_baseline']['auc'])} | "
                         f"{_fmt(r['current_cash_persistence_baseline']['auc'])} | {'—' if not ci else f'[{ci[0]:+.3f}, {ci[1]:+.3f}]'} |")
    lines += ["", "## 3. Riesgo relativo por etiqueta (eventos en los 6 meses siguientes, desarrollo)", "",
              "| Versión | Etiqueta | Filas | Tasa de eventos | Riesgo relativo frente a neutral |", "|---|---|---:|---:|---:|"]
    rr = report["label_relative_risk_6m"]
    for version in ("v1", "v2"):
        for label, row in sorted(rr[version].items()):
            lines.append(f"| {version} | {label} | {row['rows']} | {_fmt(row['event_rate'])} | {_fmt(row['relative_risk_vs_neutral'], 2)} |")
    for label, row in sorted(rr["v2_episode"].items()):
        lines.append(f"| v2 episodio | {label} | {row['rows']} | {_fmt(row['event_rate'])} | — |")
    ant = report["anticipation"]
    lines += ["", "## 4. Anticipación con regla independiente", "", ant["rule"], "",
              f"Tasa base de evento a 6 meses en filas puntuadas: {_fmt(ant['base_event_rate_6m_all_scored_rows'])}.", "",
              "| Señal | Inicios | Detectados | Cuota | Lead mediana (p25–p75) | Falsas alarmas 6m | Filas marcadas evaluables |", "|---|---:|---:|---:|---|---:|---:|"]
    for name, row in ant["deterioration"].items():
        lead = row["lead_months"]
        lines.append(f"| {name} | {row['anchors']} | {row['detected_within_lookback']} | {_fmt(row['detection_share'])} | "
                     f"{_fmt(lead['median'], 1)} ({_fmt(lead['p25'], 1)}–{_fmt(lead['p75'], 1)}) | {_fmt(row['false_alarms_6m']['false_alarm_share'])} | {row['false_alarms_6m']['evaluable_rows']} |")
    lines += ["", "| Señal de mejora | Recuperaciones | Detectadas | Cuota | Lead mediana (p25–p75) |", "|---|---:|---:|---:|---|"]
    for name, row in ant["improvement"].items():
        lead = row["lead_months"]
        lines.append(f"| {name} | {row['anchors']} | {row['detected_within_lookback']} | {_fmt(row['detection_share'])} | {_fmt(lead['median'], 1)} ({_fmt(lead['p25'], 1)}–{_fmt(lead['p75'], 1)}) |")
    lines += ["", f"**Regla de liquidez.** {ant['liquidity_rule']} Tasa base de tensión de liquidez a 6 meses en filas puntuadas con caja: "
              f"{_fmt(ant['base_liquidity_stress_rate_6m_all_scored_rows'])}.", "",
              "| Señal | Inicios de tensión de caja | Detectados | Cuota | Lead mediana (p25–p75) | Falsas alarmas 6m | Filas marcadas evaluables |", "|---|---:|---:|---:|---|---:|---:|"]
    for name, row in ant["liquidity_deterioration"].items():
        lead = row["lead_months"]
        lines.append(f"| {name} | {row['anchors']} | {row['detected_within_lookback']} | {_fmt(row['detection_share'])} | "
                     f"{_fmt(lead['median'], 1)} ({_fmt(lead['p25'], 1)}–{_fmt(lead['p75'], 1)}) | {_fmt(row['false_alarms_6m']['false_alarm_share'])} | {row['false_alarms_6m']['evaluable_rows']} |")
    if "v2_direction_threshold_sensitivity" in report:
        lines += ["", "## 5. Sensibilidad de V2 al umbral de dirección", "", "| direction_z | Cuotas de etiqueta | Falsas alarmas de `deteriorating` 6m | Filas |", "|---|---|---:|---:|"]
        for threshold, row in report["v2_direction_threshold_sensitivity"].items():
            lines.append(f"| {threshold} | {row['label_shares']} | {_fmt(row['confirmed_deteriorating_false_alarm_6m'])} | {row['confirmed_deteriorating_rows']} |")
    lines += ["", "## Límites", ""] + [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"
