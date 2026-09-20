"""Comparación de alertas tempranas con el protocolo de D41 (decisiones D42).

Mismo evento, misma ventana y mismas reglas de censura que `lead_time.py`; lo único que cambia es **qué
dispara la alarma**. Así se puede comparar sin trucar:

- `score_z<=X`: el agregado de momentum de V2 (`momentum_z`) por debajo de −X. X = 1,5 es el umbral vigente
  de la etiqueta `emerging_deterioration`, así que la curva incluye el punto que ya usamos.
- `runway<Xm`: meses de caja (`cash_runway_months_retrospective` = caja reconstruida / salidas medias de 3
  meses) por debajo de X. Solo cuenta donde la reconstrucción de caja es completa (D38).
- `cash<0`: caja reconstruida negativa.
- `presion_deuda>5%` (D43): el servicio de deuda se come 5 puntos más de las entradas que su mediana propia de
  seis meses. Es la mejor alerta encontrada: se eligió iterando **solo en los grupos de desarrollo** y se midió
  una vez en la reserva (44 % de detección, 9 % de meses en alarma, ×1,8 sobre la tasa base, 3,5 meses).
- `score_z<=X o runway<Ym` y `score_z<=X y runway<Ym`: unión e intersección de las dos familias.

Cada definición se evalúa sobre **sus propios meses disponibles**: una empresa sin caja fiable no cuenta como
fallo de la alerta de caja, igual que una sin score no cuenta como fallo del score. Por eso se publica, junto
a la detección, cuántos eventos y cuántas empresas puede ver cada alerta (cobertura): una alerta que detecta
mucho sobre pocos eventos no es mejor. Además se repite todo sobre el **subconjunto común** de eventos que
todas las alertas pueden ver, que es la única comparación limpia entre ellas.

Dos cifras evitan engañarse con una alerta trivial: `alarm_rate` (proporción de meses-empresa en alarma) y el
`lift` sobre la tasa base. Una alerta encendida el 80 % del tiempo detecta casi todo sin aportar nada.

Ninguna de estas curvas calibra el score: son diagnóstico. La elección de un punto de trabajo es una decisión
de producto (cuántas revisiones falsas se aceptan por cada aviso bueno) y debe documentarse aparte.
"""
import numpy as np
import pandas as pd

from xray.evaluation.lead_time import _quantiles, own_stress_months, stress_onsets

SCORE_THRESHOLDS = (0.5, 1.0, 1.5, 2.0)
RUNWAY_THRESHOLDS = (0.5, 1.0, 2.0)
DEBT_PRESSURE_PP = 0.05        # D43: puntos porcentuales sobre la mediana propia de 6 meses
DEBT_PRESSURE_WINDOW = 6
DEBT_PRESSURE_MIN_MONTHS = 3
HOLDOUT_SEED = 20260920
HOLDOUT_SHARE = 0.3


def _index(month):
    return month.dt.year * 12 + month.dt.month


def alarm_frame(company_id, month, alarm, available):
    return pd.DataFrame({"company_id": company_id, "month": month,
                         "alarm": np.asarray(alarm, dtype=bool) & np.asarray(available, dtype=bool),
                         "available": np.asarray(available, dtype=bool)})


def score_alarms(scores, threshold):
    z = pd.to_numeric(scores.momentum_z, errors="coerce")
    return alarm_frame(scores.company_id, scores.month, z.le(-threshold).fillna(False), z.notna())


def runway_alarms(liquidity, threshold):
    r = pd.to_numeric(liquidity.cash_runway_months_retrospective, errors="coerce")
    return alarm_frame(liquidity.company_id, liquidity.month, r.lt(threshold).fillna(False), r.notna())


def negative_cash_alarms(liquidity):
    c = pd.to_numeric(liquidity.reconstructed_cash, errors="coerce")
    return alarm_frame(liquidity.company_id, liquidity.month, c.lt(0).fillna(False), c.notna())


def debt_pressure_alarms(features, threshold=DEBT_PRESSURE_PP):
    """D43 · El servicio de deuda pasa a comerse `threshold` puntos más de lo que ingresa la empresa.

    `carga = (principal + intereses) / entradas operativas` del mes; la alarma salta cuando supera en más de
    `threshold` a la **mediana de la propia empresa** en los `DEBT_PRESSURE_WINDOW` meses anteriores (mínimo
    `DEBT_PRESSURE_MIN_MONTHS` observados). Solo mira el pasado: la mediana se calcula con `shift(1)`.

    Es la señal que mejor anticipa el estrés propio en el protocolo de D41: ni la cuota sola (×0,73) ni la
    caída de ingresos sola (×0,92) sirven; lo que avisa es el cociente.
    """
    f = features.sort_values(["company_id", "month"]).copy()
    inflow = pd.to_numeric(f.tx_inflow, errors="coerce")
    service = pd.to_numeric(f.debt_principal_paid, errors="coerce") + pd.to_numeric(f.debt_interest_paid, errors="coerce")
    f["burden"] = (service / inflow.where(inflow.gt(0))).replace([np.inf, -np.inf], np.nan)
    prior = f.groupby("company_id").burden.transform(
        lambda x: x.shift(1).rolling(DEBT_PRESSURE_WINDOW, min_periods=DEBT_PRESSURE_MIN_MONTHS).median())
    rise = f.burden - prior
    return alarm_frame(f.company_id, f.month, rise.gt(threshold), rise.notna())


def split_groups(companies, seed=HOLDOUT_SEED, holdout_share=HOLDOUT_SHARE):
    """Grupos de desarrollo y de reserva. La reserva solo se mide una vez, con la regla ya fijada."""
    groups = np.sort(pd.Series(companies.group_id).dropna().unique())
    rng = np.random.default_rng(seed)
    dev = set(rng.choice(groups, size=int(round((1 - holdout_share) * len(groups))), replace=False))
    return dev, set(groups) - dev


def combine(a, b, how):
    """Une dos alertas. `available` = donde las dos son evaluables, para no mezclar coberturas."""
    m = a.merge(b, on=["company_id", "month"], how="outer", suffixes=("_a", "_b")).fillna(
        {"alarm_a": False, "alarm_b": False, "available_a": False, "available_b": False})
    available = m.available_a & m.available_b
    alarm = (m.alarm_a | m.alarm_b) if how == "or" else (m.alarm_a & m.alarm_b)
    return alarm_frame(m.company_id, m.month, alarm, available)


def evaluate(onsets, alarms, events, observed, horizon=6, min_available=3):
    """Detección, antelación y falsas alarmas de una definición de alarma (protocolo de D41)."""
    by_company = {c: g.set_index("month") for c, g in alarms.groupby("company_id")}
    rows = []
    for row in onsets.itertuples():
        window = pd.date_range(row.onset - pd.DateOffset(months=horizon), row.onset - pd.DateOffset(months=1), freq="MS")
        g = by_company.get(row.company_id)
        g = g.reindex(window) if g is not None else pd.DataFrame(index=window, columns=["alarm", "available"])
        available = int(g.available.fillna(False).sum())
        hits = g.index[g.alarm.fillna(False).astype(bool)]
        first = hits.min() if len(hits) else None
        rows.append({"company_id": row.company_id, "onset": row.onset, "event_type": row.event_type,
                     "evaluable": available >= min_available, "detected": first is not None,
                     "lead_months": None if first is None else
                     (row.onset.year * 12 + row.onset.month) - (first.year * 12 + first.month)})
    leads = pd.DataFrame(rows, columns=["company_id", "onset", "event_type", "evaluable", "detected", "lead_months"])
    ev = leads.loc[leads.evaluable] if len(leads) else leads

    a = alarms.sort_values(["company_id", "month"]).copy()
    a["start"] = a.alarm & ~a.groupby("company_id").alarm.shift(1, fill_value=False)
    last_obs = observed.groupby("company_id").month.max()
    a["i"] = _index(a.month)
    a["judgeable"] = (_index(a.company_id.map(last_obs)) >= a.i + horizon).fillna(False)
    ev_idx = {c: _index(g.month).to_numpy() for c, g in events.groupby("company_id")}

    def followed(frame):
        return np.array([(lambda e: e is not None and bool(((e > i) & (e <= i + horizon)).any()))(ev_idx.get(c))
                         for c, i in zip(frame.company_id, frame.i)], dtype=bool)

    starts = a.loc[a.start & a.judgeable]
    base = a.loc[a.judgeable & a.available]
    precision = float(followed(starts).mean()) if len(starts) else None
    base_rate = float(followed(base).mean()) if len(base) else None
    available_rows = a.available.sum()
    return {"evaluable_onsets": int(len(ev)), "detected": int(ev.detected.sum()) if len(ev) else 0,
            "alarm_rate": float(a.loc[a.available, "alarm"].mean()) if available_rows else None,
            "recall": float(ev.detected.mean()) if len(ev) else None,
            "lead_months": _quantiles(ev.loc[ev.detected, "lead_months"] if len(ev) else []),
            "alarm_starts_judgeable": int(len(starts)),
            "false_alarm_share": None if precision is None else 1 - precision,
            "event_rate_after_alarm": precision, "base_event_rate": base_rate,
            "lift": None if not precision or not base_rate else precision / base_rate,
            "companies_covered": int(alarms.loc[alarms.available, "company_id"].nunique())}, leads


def holdout_check(transactions, features, scores, liquidity, horizon=6, clean_months=6):
    """Mide la regla elegida (D43) y la alarma vigente del score en desarrollo y en la reserva.

    La reserva son grupos completos que no se tocaron al elegir la regla; se mide una sola vez. Se espera algo
    de encogimiento: si la diferencia fuera grande, la regla estaria ajustada a los datos de desarrollo.
    """
    dev, hold = split_groups(features[["group_id"]].drop_duplicates())
    out = {}
    for label, groups in (("dev", dev), ("holdout", hold)):
        f = features.loc[features.group_id.isin(groups)]
        companies = set(f.company_id)
        tx = transactions.loc[transactions.company_id.isin(companies)]
        observed = f.loc[f.tx_count.gt(0), ["company_id", "month"]]
        events = own_stress_months(tx)
        onsets = stress_onsets(events, observed, clean_months)
        rules = {"presion_deuda>5%": debt_pressure_alarms(f),
                 "score_z<=-1.5": score_alarms(scores.loc[scores.company_id.isin(companies)], 1.5)}
        out[label] = {"groups": len(groups), "onsets": int(len(onsets)),
                      **{name: evaluate(onsets, frame, events, observed, horizon)[0] for name, frame in rules.items()}}
    return out


def compare_alarms(transactions, features, scores, liquidity, horizon=6, clean_months=6):
    observed = features.loc[features.tx_count.gt(0), ["company_id", "month"]]
    events = own_stress_months(transactions)
    onsets = stress_onsets(events, observed, clean_months)
    definitions = {}
    for x in SCORE_THRESHOLDS:
        definitions[f"score_z<=-{x:g}"] = score_alarms(scores, x)
    for y in RUNWAY_THRESHOLDS:
        definitions[f"runway<{y:g}m"] = runway_alarms(liquidity, y)
    definitions["cash<0"] = negative_cash_alarms(liquidity)
    definitions[f"presion_deuda>{DEBT_PRESSURE_PP:.0%}"] = debt_pressure_alarms(features)
    definitions["score_z<=-1.5 o runway<1m"] = combine(definitions["score_z<=-1.5"], definitions["runway<1m"], "or")
    definitions["score_z<=-1.5 y runway<1m"] = combine(definitions["score_z<=-1.5"], definitions["runway<1m"], "and")
    rows, evaluable = {}, []
    for name, frame in definitions.items():
        rows[name], leads = evaluate(onsets, frame, events, observed, horizon)
        evaluable.append(set(zip(leads.loc[leads.evaluable, "company_id"], leads.loc[leads.evaluable, "onset"])))
    common = set.intersection(*evaluable) if evaluable else set()
    shared = onsets[[(c, o) in common for c, o in zip(onsets.company_id, onsets.onset)]]
    rows_common = {name: evaluate(shared, frame, events, observed, horizon, min_available=0)[0]
                   for name, frame in definitions.items()}
    return {"method": "early_warning_v1 (D42)", "horizon_months": horizon, "clean_months": clean_months,
            "onsets": int(len(onsets)), "common_onsets": int(len(shared)), "alarms": rows, "alarms_common": rows_common,
            "holdout": holdout_check(transactions, features, scores, liquidity, horizon, clean_months),
            "caveats": ["Mismo evento y censura que D41; solo cambia el disparador.",
                        "Cada alerta se evalúa donde su señal existe: comparar también la cobertura.",
                        "Diagnóstico, no calibración: elegir un punto de trabajo es decisión de producto.",
                        "Dataset sintético."]}


def render_markdown(r):
    pct = lambda x: "—" if x is None else f"{100 * x:.0f}%"
    num = lambda x: "—" if x is None else f"{x:.1f}"
    lines = [f"# Alertas tempranas comparadas ({r['method']})", "",
             f"Evento: primer estrés propio tras {r['clean_months']} meses sin estrés ({r['onsets']} inicios). "
             f"Horizonte {r['horizon_months']} meses.", "",
             "| Alarma | Eventos evaluables | Detectados | Antelación mediana (p25–p75) | Meses en alarma | Falsas alarmas | Evento tras alarma vs base | Empresas cubiertas |",
             "|---|---|---|---|---|---|---|---|"]
    for name, v in r["alarms"].items():
        lead = v["lead_months"]
        lines.append(f"| `{name}` | {v['evaluable_onsets']} | {v['detected']} ({pct(v['recall'])}) | "
                     f"{num(lead['median'])} ({num(lead['p25'])}–{num(lead['p75'])}) | {pct(v['alarm_rate'])} | {pct(v['false_alarm_share'])} | "
                     f"{pct(v['event_rate_after_alarm'])} vs {pct(v['base_event_rate'])} (×{num(v['lift'])}) | {v['companies_covered']} |")
    lines += ["", f"Mismos {r['common_onsets']} eventos para todas las alertas (única comparación limpia):", "",
              "| Alarma | Detectados | Antelación mediana | Meses en alarma |", "|---|---|---|---|"]
    for name, v in r["alarms_common"].items():
        lines.append(f"| `{name}` | {v['detected']} ({pct(v['recall'])}) | {num(v['lead_months']['median'])} | {pct(v['alarm_rate'])} |")
    for label, block in r.get("holdout", {}).items():
        if label == "dev":
            lines += ["", "Regla elegida (D43) en desarrollo frente a la reserva de grupos, no tocada al elegirla:", "",
                      "| Conjunto | Grupos | Eventos | Alarma | Detecta | Meses en alarma | Antelación | Lift |",
                      "|---|---|---|---|---|---|---|---|"]
        for name in ("presion_deuda>5%", "score_z<=-1.5"):
            v = block[name]
            lines.append(f"| {label} | {block['groups']} | {v['evaluable_onsets']} | `{name}` | {pct(v['recall'])} | "
                         f"{pct(v['alarm_rate'])} | {num(v['lead_months']['median'])} | ×{num(v['lift'])} |")
    lines += ["", "Límites:"] + [f"- {c}" for c in r["caveats"]]
    return "\n".join(lines) + "\n"
