"""Anticipación medida del score V2 frente a eventos de estrés propio (bonus del enunciado).

Reglas fijadas antes de mirar resultados (docs/decisiones.md D41). Nada se ajusta a los datos:

- Evento (`t_evidente`): primer mes con un evento de estrés **propio** de `event_type` (D30/D41) tras al menos
  `clean_months` meses observados sin ninguno. Estrés propio = cuota impagada, embargo a la propia empresa,
  aplazamiento, descubierto, recargo de apremio e intereses de demora. Quedan fuera los embargos a terceros,
  los impagos de clientes, los recibos devueltos y las reclamaciones: no son estrés de la empresa.
- Señal (`t_señal`): primer mes del intervalo [t_evidente − horizonte, t_evidente − 1] con etiqueta V2
  `emerging_deterioration` o `deteriorating` (umbral fijo de V2: |z̄| ≥ 1,5). Antelación = t_evidente − t_señal.
- Evaluable: el evento tiene score V2 en al menos `min_scored` de esos meses previos. Los demás son censurados
  (sin historia de score suficiente para haber podido avisar).
- Falsas alarmas: inicio de cada racha de alarma con `horizon` meses observados por delante; es falsa si no llega
  ningún evento de estrés propio en esos meses. Se compara con la tasa base: proporción de meses-empresa
  evaluables seguidos de un evento en el mismo horizonte.

Es un dataset sintético: la antelación medida aquí no es evidencia de rendimiento en producción.
"""
import numpy as np
import pandas as pd

OWN_STRESS = ("cuota_impagada", "embargo", "aplazamiento", "descubierto", "recargo_apremio", "demora")
NOT_OWN = ("embargo_tercero", "impagado_cliente", "recibo_devuelto", "reclamacion")
ALARM_LABELS = ("emerging_deterioration", "deteriorating")


def _month(values):
    return pd.to_datetime(values).dt.to_period("M").dt.to_timestamp()


def _index(month):
    return month.dt.year * 12 + month.dt.month


def own_stress_months(transactions):
    """Una fila por empresa-mes con al menos un evento de estrés propio (booked, sin duplicados de sincronización)."""
    t = transactions.loc[transactions.event_type.isin(OWN_STRESS) & transactions.status.eq("booked")]
    if "is_sync_duplicate" in t:
        t = t.loc[~t.is_sync_duplicate.fillna(False).astype(bool)]
    out = t.assign(month=_month(t.date)).groupby(["company_id", "month"]).event_type.agg(
        lambda s: s.value_counts().index[0]).rename("event_type").reset_index()
    return out


def stress_onsets(events, observed, clean_months=6):
    """Primer mes con estrés propio precedido de `clean_months` meses observados sin estrés."""
    obs = observed[["company_id", "month"]].drop_duplicates().copy()
    obs = obs.merge(events.assign(stress=True), on=["company_id", "month"], how="left")
    obs["stress"] = obs.stress.fillna(False).astype(bool)
    obs = obs.sort_values(["company_id", "month"]).reset_index(drop=True)
    rows = []
    for company, g in obs.groupby("company_id", sort=False):
        idx = _index(g.month).to_numpy()
        stress = g.stress.to_numpy()
        for i in np.flatnonzero(stress):
            prior = (idx >= idx[i] - clean_months) & (idx < idx[i])
            if prior.sum() == clean_months and not stress[prior].any():
                rows.append({"company_id": company, "onset": g.month.iloc[i], "event_type": g.event_type.iloc[i]})
    return pd.DataFrame(rows, columns=["company_id", "onset", "event_type"])


def lead_times(onsets, scores, horizon=6, min_scored=3):
    s = scores[["company_id", "month", "trajectory", "score"]].copy()
    s["alarm"] = s.trajectory.isin(ALARM_LABELS)
    by_company = {c: g.set_index("month") for c, g in s.groupby("company_id")}
    rows = []
    for row in onsets.itertuples():
        window = pd.date_range(row.onset - pd.DateOffset(months=horizon), row.onset - pd.DateOffset(months=1), freq="MS")
        g = by_company.get(row.company_id)
        g = g.reindex(window) if g is not None else pd.DataFrame(index=window, columns=["score", "alarm"])
        scored = int(g.score.notna().sum())
        alarms = g.index[g.alarm.fillna(False).astype(bool)]
        first = alarms.min() if len(alarms) else None
        lead = (row.onset.year * 12 + row.onset.month) - (first.year * 12 + first.month) if first is not None else None
        rows.append({"company_id": row.company_id, "onset": row.onset, "event_type": row.event_type,
                     "scored_months_before": scored, "evaluable": scored >= min_scored,
                     "detected": first is not None, "signal_month": first, "lead_months": lead})
    return pd.DataFrame(rows)


def false_alarms(scores, events, observed, horizon=6):
    s = scores[["company_id", "month", "trajectory"]].sort_values(["company_id", "month"]).copy()
    s["alarm"] = s.trajectory.isin(ALARM_LABELS)
    s["start"] = s.alarm & ~s.groupby("company_id").alarm.shift(1, fill_value=False)
    last_obs = observed.groupby("company_id").month.max()
    ev = events.assign(i=_index(events.month))
    ev_idx = {c: g.i.to_numpy() for c, g in ev.groupby("company_id")}
    s["i"] = _index(s.month)
    s["judgeable"] = (s.company_id.map(last_obs).pipe(lambda m: _index(m)) >= s.i + horizon).fillna(False)

    def followed(frame):
        out = np.zeros(len(frame), dtype=bool)
        for n, (c, i) in enumerate(zip(frame.company_id, frame.i)):
            e = ev_idx.get(c)
            out[n] = e is not None and bool(((e > i) & (e <= i + horizon)).any())
        return out

    starts = s.loc[s.start & s.judgeable].copy()
    starts["followed"] = followed(starts)
    base = s.loc[s.judgeable & s.trajectory.notna() & ~s.trajectory.eq("insufficient_history")].copy()
    base["followed"] = followed(base)
    precision = float(starts.followed.mean()) if len(starts) else None
    base_rate = float(base.followed.mean()) if len(base) else None
    return {"alarm_starts_judgeable": int(len(starts)),
            "false_alarm_share": None if precision is None else 1 - precision,
            "event_rate_after_alarm": precision, "base_event_rate": base_rate,
            "lift": None if not precision or not base_rate else precision / base_rate,
            "alarm_starts_not_judgeable": int((s.start & ~s.judgeable).sum())}


def _quantiles(values):
    v = pd.Series(values, dtype=float).dropna()
    if v.empty:
        return {"median": None, "p25": None, "p75": None}
    return {"median": float(v.median()), "p25": float(v.quantile(.25)), "p75": float(v.quantile(.75))}


def lead_time_report(transactions, features, scores, horizon=6, clean_months=6, min_scored=3):
    observed = features.loc[features.tx_count.gt(0), ["company_id", "month"]]
    events = own_stress_months(transactions)
    onsets = stress_onsets(events, observed, clean_months)
    leads = lead_times(onsets, scores, horizon, min_scored)
    ev = leads.loc[leads.evaluable]
    report = {
        "method": "lead_time_v1 (D41)", "horizon_months": horizon, "clean_months": clean_months,
        "min_scored_months": min_scored, "alarm_labels": list(ALARM_LABELS), "own_stress": list(OWN_STRESS),
        "excluded_event_types": list(NOT_OWN),
        "events": {"companies_with_own_stress": int(events.company_id.nunique()), "onsets": int(len(onsets)),
                   "evaluable_onsets": int(len(ev)), "censored_onsets": int((~leads.evaluable).sum()) if len(leads) else 0,
                   "companies_never_with_own_stress": int(features.company_id.nunique() - events.company_id.nunique())},
        "detection": {"detected": int(ev.detected.sum()), "recall": float(ev.detected.mean()) if len(ev) else None,
                      "lead_months": _quantiles(ev.loc[ev.detected, "lead_months"])},
        "by_event_type": {k: {"evaluable": int(len(g)), "recall": float(g.detected.mean()),
                              "lead_months_median": _quantiles(g.loc[g.detected, "lead_months"])["median"]}
                          for k, g in ev.groupby("event_type")},
        "false_alarms": false_alarms(scores, events, observed, horizon),
        "caveats": ["Dataset sintético: no es evidencia de rendimiento en producción.",
                    "Reglas fijadas antes de ver resultados; umbral de alarma = el de V2, sin calibrar con eventos.",
                    "La primera aparición observada de un evento puede no ser la primera real (historia truncada)."],
    }
    return report, leads


def render_markdown(r):
    d, f, e = r["detection"], r["false_alarms"], r["events"]
    pct = lambda x: "—" if x is None else f"{100 * x:.0f}%"
    num = lambda x: "—" if x is None else f"{x:.1f}"
    lines = [
        "# Anticipación medida (V2 frente a estrés propio)", "",
        f"Método `{r['method']}`: evento = primer estrés propio tras {r['clean_months']} meses observados sin estrés; "
        f"señal = primera etiqueta {', '.join(r['alarm_labels'])} en los {r['horizon_months']} meses previos.", "",
        "| Medida | Valor |", "|---|---|",
        f"| Eventos de estrés propio (inicios) | {e['onsets']} ({e['evaluable_onsets']} evaluables, {e['censored_onsets']} censurados) |",
        f"| Detectados con antelación | {d['detected']} de {e['evaluable_onsets']} ({pct(d['recall'])}) |",
        f"| Antelación (meses): mediana · p25–p75 | {num(d['lead_months']['median'])} · {num(d['lead_months']['p25'])}–{num(d['lead_months']['p75'])} |",
        f"| Alarmas evaluables | {f['alarm_starts_judgeable']} |",
        f"| Falsas alarmas (sin evento en {r['horizon_months']} meses) | {pct(f['false_alarm_share'])} |",
        f"| Evento tras alarma frente a tasa base | {pct(f['event_rate_after_alarm'])} frente a {pct(f['base_event_rate'])} (×{num(f['lift'])}) |",
        f"| Empresas que nunca tienen estrés propio | {e['companies_never_with_own_stress']} |", "",
        "Por tipo de evento:", "", "| Tipo | Evaluables | Detectados | Antelación mediana |", "|---|---|---|---|",
    ]
    for k, v in sorted(r["by_event_type"].items(), key=lambda kv: -kv[1]["evaluable"]):
        lines.append(f"| {k} | {v['evaluable']} | {pct(v['recall'])} | {num(v['lead_months_median'])} |")
    lines += ["", "Límites:"] + [f"- {c}" for c in r["caveats"]]
    return "\n".join(lines) + "\n"
