"""Monitor de alertas: el sistema levanta la mano sin que nadie pregunte (bonus del enunciado).

Publica, para el último cierre, la lista de empresas en alerta **ordenada por severidad**, con el motivo, la
evidencia numérica y la antelación que cabe esperar según lo medido (D41–D43). No inventa nada: cada alerta
es una regla observable y su rendimiento está medido con reserva de grupos.

Tipos de alerta (independientes, una empresa puede tener las dos):

- `presion_deuda` (D43): el servicio de deuda se come más de 5 puntos porcentuales de las entradas frente a
  la mediana propia de seis meses. Medido en la reserva: detecta el 44 % de los episodios de estrés propio,
  9 % de meses en alarma, ×1,8 sobre la tasa base, 3,5 meses de antelación mediana.
- `deterioro_confirmado` (V2): etiqueta `deteriorating` del score, es decir, dos meses seguidos de caída
  confirmada por el mes actual. Medido: ~43 % de detección con 14 % de meses en alarma y ×1,1.

`severity` ordena la lista: para la presión de deuda, los puntos porcentuales de subida; para el deterioro,
la magnitud del cambio de score. `streak_months` dice cuántos meses seguidos lleva encendida.
"""
import numpy as np
import pandas as pd

from xray.evaluation.early_warning import DEBT_PRESSURE_PP, debt_pressure_alarms

ALERT_STATS = {
    "presion_deuda": {"recall": 0.44, "alarm_rate": 0.09, "lift": 1.8, "median_lead_months": 3.5,
                      "source": "D43, medido en la reserva de grupos"},
    "deterioro_confirmado": {"recall": 0.43, "alarm_rate": 0.14, "lift": 1.1, "median_lead_months": 3.0,
                             "source": "D41/D42, alarma vigente del score"},
}
COLUMNS = ["company_id", "group_id", "month", "alert", "severity", "streak_months", "evidence", "score", "trajectory"]


def _streak(flag):
    """Meses consecutivos encendidos hasta cada fila (por empresa, sin mirar el futuro)."""
    out, run = np.zeros(len(flag), dtype=int), 0
    for i, on in enumerate(flag):
        run = run + 1 if on else 0
        out[i] = run
    return out


def debt_pressure_alerts(features, month):
    f = features.sort_values(["company_id", "month"]).copy()
    alarms = debt_pressure_alarms(f)
    f = f.merge(alarms, on=["company_id", "month"], how="left")
    inflow = pd.to_numeric(f.tx_inflow, errors="coerce")
    service = pd.to_numeric(f.debt_principal_paid, errors="coerce") + pd.to_numeric(f.debt_interest_paid, errors="coerce")
    f["burden"] = (service / inflow.where(inflow.gt(0))).replace([np.inf, -np.inf], np.nan)
    f["prior"] = f.groupby("company_id").burden.transform(lambda x: x.shift(1).rolling(6, min_periods=3).median())
    # Para mostrar, la carga se acota al 500 %: una empresa con entradas casi nulas daría cifras absurdas.
    # La alarma (debt_pressure_alarms) usa el valor sin acotar; el recorte solo afecta a severidad y evidencia.
    f["rise"] = f.burden.clip(upper=5) - f.prior.clip(upper=5)
    f["streak_months"] = np.concatenate([_streak(g.alarm.fillna(False).to_numpy()) for _, g in f.groupby("company_id", sort=False)])
    out = f.loc[f.month.eq(month) & f.alarm.fillna(False)].copy()
    out["alert"] = "presion_deuda"
    out["severity"] = out.rise
    out["evidence"] = [{"burden_now": None if pd.isna(b) else round(float(b), 4),
                        "burden_prior_median_6m": None if pd.isna(p) else round(float(p), 4),
                        "rise_pp": None if pd.isna(r) else round(float(r) * 100, 1),
                        "threshold_pp": DEBT_PRESSURE_PP * 100}
                       for b, p, r in zip(out.burden, out.prior, out.rise)]
    return out


def score_alerts(scores, month):
    s = scores.sort_values(["company_id", "month"]).copy()
    s["on"] = s.trajectory.eq("deteriorating")
    s["streak_months"] = np.concatenate([_streak(g.on.to_numpy()) for _, g in s.groupby("company_id", sort=False)])
    out = s.loc[s.month.eq(month) & s.on].copy()
    out["alert"] = "deterioro_confirmado"
    out["severity"] = -pd.to_numeric(out.get("delta_vs_prev"), errors="coerce").fillna(0)
    out["evidence"] = [{"score": None if pd.isna(v) else round(float(v), 1),
                        "delta_vs_prev": None if pd.isna(d) else round(float(d), 1),
                        "episode": None if pd.isna(e) else str(e)}
                       for v, d, e in zip(out.score, out.get("delta_vs_prev", pd.Series(index=out.index, dtype=float)), out.get("episode", pd.Series(index=out.index, dtype=object)))]
    return out


def build_monitor(features, scores, month=None):
    """Alertas del último cierre, ordenadas por tipo y severidad."""
    month = pd.Timestamp(month) if month is not None else features.month.max()
    context = scores.loc[scores.month.eq(month), ["company_id", "score", "trajectory"]]
    parts = []
    for frame in (debt_pressure_alerts(features, month), score_alerts(scores, month)):
        if frame.empty:
            continue
        frame = frame.drop(columns=[c for c in ("score", "trajectory") if c in frame], errors="ignore")
        parts.append(frame.merge(context, on="company_id", how="left"))
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    alerts = pd.concat(parts, ignore_index=True)
    alerts["month"] = month
    alerts = alerts.sort_values(["alert", "severity"], ascending=[True, False])
    return alerts.reindex(columns=COLUMNS).reset_index(drop=True)


def monitor_report(alerts, month):
    counts = alerts.alert.value_counts().to_dict() if len(alerts) else {}
    return {"method": "monitor_v1 (D44)", "month": str(pd.Timestamp(month).date()),
            "alerts": int(len(alerts)), "companies": int(alerts.company_id.nunique()) if len(alerts) else 0,
            "by_alert": {k: {"companies": int(v), **ALERT_STATS.get(k, {})} for k, v in counts.items()},
            "caveats": ["Cada alerta es una regla observable, no una predicción calibrada.",
                        "Rendimiento medido con reserva de grupos (D41–D43); dataset sintético.",
                        "Dos de cada tres alarmas no acaban en evento: es una lista de revisión, no un veredicto."]}
