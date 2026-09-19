"""«Por qué ha cambiado el Pulse»: deltas de contribución entre meses naturales consecutivos.

Entrada: `*_monthly_scores.parquet` y `*_score_explanations.parquet` de `xray.score_v2`.
Para cada entidad-moneda-mes con score y con score en el mes natural anterior, se compara
término a término (`layer`, `feature`) la contribución exacta al score final y se separa:

    delta_contribution = value_effect + weight_effect

- `value_effect`  : cambio del valor financiero (y de su transformación) con el peso del mes anterior.
- `weight_effect` : cambio de peso efectivo / disponibilidad (aparición o desaparición de una señal).

Para la capa `level`, `final_contribution = feature_score × effective_weight`, así que la
descomposición es exacta. Para `momentum` y `boundary` el término no factoriza de esa forma:
si existe en ambos meses todo el delta es `value_effect`; si aparece o desaparece, `weight_effect`.
La suma de deltas de todos los términos reproduce `delta_vs_prev` del score (validado).

`reference_changed` marca que la referencia estadística de nivel cambió entre los dos meses:
parte del `value_effect` de nivel puede venir de la referencia y no del valor financiero.
No se intenta aislar ese tercer efecto en esta versión.
"""
import numpy as np
import pandas as pd

TERM_KEYS = ["layer", "feature"]
LABELS = {
    "op_margin_w": "Generación operativa (margen 6m)",
    "debt_service_w": "Servicio de deuda / entradas (6m)",
    "debt_without_inflow_w": "Deuda servida sin entradas operativas",
    "ar_delay_w": "Retraso de cobro a clientes (6m)",
    "ap_delay_w": "Retraso de pago a proveedores (6m)",
    "op_margin_qoq": "Tendencia del margen (trimestre vs anterior)",
    "inflow_growth_q": "Crecimiento de entradas (3m)",
    "debt_service_qoq": "Tendencia del servicio de deuda",
    "ar_delay_qoq": "Tendencia del retraso de cobro",
    "ap_delay_qoq": "Tendencia del retraso de pago",
    "score_clipping": "Recorte a [0, 100]",
}
FORMATS = {
    "op_margin_w": lambda v: f"{v:+.2f}",
    "debt_service_w": lambda v: f"{v:.1%}",
    "debt_without_inflow_w": lambda v: "sí" if v else "no",
    "ar_delay_w": lambda v: f"{v:.0f} d",
    "ap_delay_w": lambda v: f"{v:.0f} d",
    "op_margin_qoq": lambda v: f"{v:+.2f}",
    "inflow_growth_q": lambda v: f"{v:+.2f}",
    "debt_service_qoq": lambda v: f"{v:+.1%}",
    "ar_delay_qoq": lambda v: f"{v:+.0f} d",
    "ap_delay_qoq": lambda v: f"{v:+.0f} d",
    "score_clipping": lambda v: f"{v:+.1f}",
}
OUTPUT_COLUMNS = ["month", "prev_month", "layer", "feature", "component", "label", "rank",
                  "delta_contribution", "value_effect", "weight_effect", "status",
                  "value_prev", "value_now", "feature_score_prev", "feature_score_now",
                  "weight_prev", "weight_now", "reference_changed", "sentence"]


def _fmt(feature, value):
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "—"
    return FORMATS.get(feature, lambda v: f"{v:.3g}")(value)


def _sentence(row):
    label = row.label
    points = f"{row.delta_contribution:+.1f} pts"
    if row.status == "appeared":
        return f"{label}: señal disponible desde este mes ({_fmt(row.feature, row.value_now)}) · {points}"
    if row.status == "disappeared":
        return f"{label}: señal ya no disponible (antes {_fmt(row.feature, row.value_prev)}) · {points}"
    text = f"{label}: {_fmt(row.feature, row.value_prev)} → {_fmt(row.feature, row.value_now)} · {points}"
    if row.layer == "level" and abs(row.weight_effect) > 0.05:
        text += f" (de los que {row.weight_effect:+.1f} por cambio de peso)"
    return text


def compute_changes(scores, explanations, unit="company_id"):
    """Devuelve un DataFrame con un término por fila para cada entidad-moneda-mes comparable.

    Solo se comparan meses naturales consecutivos con score en ambos. `rank` ordena los términos
    por |delta_contribution| dentro de cada mes (1 = el que más movió el score).
    """
    keys = [unit, "currency"]
    s = scores.loc[scores.score.notna(), keys + ["month", "score", "reference_effective_from"]].copy()
    s["month"] = pd.to_datetime(s.month)
    prev = s.rename(columns={"score": "score_prev", "reference_effective_from": "reference_prev"})
    prev["month"] = prev.month + pd.offsets.MonthBegin(1)
    pairs = s.merge(prev, on=keys + ["month"], how="inner", validate="one_to_one")
    if pairs.empty:
        return pd.DataFrame(columns=keys + OUTPUT_COLUMNS)
    pairs["prev_month"] = pairs.month - pd.offsets.MonthBegin(1)
    pairs["reference_changed"] = pairs.reference_effective_from.ne(pairs.reference_prev)

    term_cols = ["value", "feature_score", "effective_weight", "final_contribution", "component"]
    e = explanations[keys + ["month"] + TERM_KEYS + term_cols].copy()
    e["month"] = pd.to_datetime(e.month)
    now = e.merge(pairs[keys + ["month"]], on=keys + ["month"], validate="many_to_one")
    before = e.merge(pairs[keys + ["prev_month"]].rename(columns={"prev_month": "month"}), on=keys + ["month"], validate="many_to_one")
    before["month"] = before.month + pd.offsets.MonthBegin(1)
    merged = now.merge(before, on=keys + ["month"] + TERM_KEYS, how="outer", suffixes=("_now", "_prev"), validate="one_to_one")

    c_now = merged.final_contribution_now.fillna(0.0)
    c_prev = merged.final_contribution_prev.fillna(0.0)
    merged["delta_contribution"] = c_now - c_prev
    both = merged.final_contribution_now.notna() & merged.final_contribution_prev.notna()
    level = merged.layer.eq("level")
    value_effect = np.where(both & level,
                            (merged.feature_score_now - merged.feature_score_prev) * merged.effective_weight_prev,
                            np.where(both, merged.delta_contribution, 0.0))
    merged["value_effect"] = pd.Series(value_effect, index=merged.index).fillna(0.0)
    merged["weight_effect"] = merged.delta_contribution - merged.value_effect
    for col in ("delta_contribution", "value_effect", "weight_effect"):
        merged[col] = merged[col].round(10)  # elimina ruido flotante (±1e-15) sin afectar a la validación
    merged["status"] = np.select([both, merged.final_contribution_now.notna()], ["present", "appeared"], "disappeared")
    merged["component"] = merged.component_now.fillna(merged.component_prev)
    merged["label"] = merged.feature.map(LABELS).fillna(merged.feature)
    merged = merged.merge(pairs[keys + ["month", "prev_month", "reference_changed"]], on=keys + ["month"], validate="many_to_one")
    merged["rank"] = merged.delta_contribution.abs().groupby([merged[k] for k in keys + ["month"]]).rank(method="first", ascending=False).astype(int)
    merged = merged.rename(columns={"effective_weight_now": "weight_now", "effective_weight_prev": "weight_prev"})
    merged["sentence"] = merged.apply(_sentence, axis=1)
    out = merged[keys + OUTPUT_COLUMNS].sort_values(keys + ["month", "rank"]).reset_index(drop=True)
    validate_changes(out, scores, unit)
    return out


def validate_changes(changes, scores, unit="company_id", tol=1e-6):
    """La suma de deltas por mes debe reproducir `delta_vs_prev` del score."""
    if changes.empty:
        return
    keys = [unit, "currency", "month"]
    total = changes.groupby(keys).delta_contribution.sum().rename("total").reset_index()
    s = scores[keys + ["delta_vs_prev"]].copy()
    s["month"] = pd.to_datetime(s.month)
    check = total.merge(s, on=keys, validate="one_to_one")
    gap = (check.total - check.delta_vs_prev).abs()
    if not (gap < tol).all():
        worst = check.loc[gap.idxmax()]
        raise ValueError(f"Los deltas de contribución no suman delta_vs_prev: {worst.to_dict()}")


def top_changes(changes, k=3, unit="company_id"):
    """Top-k términos por mes más una fila `other` con el resto agregado (para la ficha)."""
    keys = [unit, "currency", "month"]
    head = changes[changes["rank"] <= k]
    rest = changes[changes["rank"] > k].groupby(keys, as_index=False).agg(
        delta_contribution=("delta_contribution", "sum"), value_effect=("value_effect", "sum"),
        weight_effect=("weight_effect", "sum"), prev_month=("prev_month", "first"),
        reference_changed=("reference_changed", "first"))
    if not rest.empty:
        rest = rest.assign(layer="other", feature="other", component="other", label="Resto de señales", rank=k + 1,
                           status="present", sentence=lambda d: "Resto de señales · " + d.delta_contribution.map(lambda v: f"{v:+.1f} pts"))
    return pd.concat([head, rest], ignore_index=True).sort_values(keys + ["rank"]).reset_index(drop=True)
