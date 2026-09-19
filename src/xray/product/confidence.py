"""Confidence 0–100: cuánta evidencia sostiene el diagnóstico de un mes.

NO es una probabilidad de acierto. Es una media ponderada de sub-puntuaciones de cobertura que ya
calcula `xray.score_v2` (historia, componentes disponibles, calidad del mes, tendencia) más, si se
aporta el panel de features, la certeza de caja (parte del movimiento bancario sin categoría).
Cada sub-puntuación es 0–100; si una fuente no está disponible su peso se reparte entre las demás.
"""
import numpy as np
import pandas as pd

WEIGHTS = {"history": 25, "coverage": 25, "month_quality": 15, "trend": 15, "cash_certainty": 20}
LABELS = {
    "history": "Historia disponible",
    "coverage": "Componentes del score disponibles",
    "month_quality": "Calidad del mes actual",
    "trend": "Tendencia calculable",
    "cash_certainty": "Movimientos bancarios identificados",
}
PARTIAL_CURRENCY_CAP = 70.0
BANDS = [(70, "high"), (40, "medium"), (0, "low")]
OUTPUT_COLUMNS = ["month", "confidence", "confidence_band", "limiting_factor", "limiting_factor_label",
                  *[f"sub_{k}" for k in WEIGHTS], "has_partial_currency_coverage", "score_status"]


def cash_certainty(features, unit="company_id", window=6):
    """1 − (importe sin categoría / importe bancario total) en los últimos `window` meses, por entidad-moneda.

    Usa solo meses <= t (rolling hacia atrás). NaN si no hay movimiento en la ventana.
    """
    keys = [unit, "currency"]
    f = features[keys + ["month", "tx_uncategorized_amount", "tx_cash_inflow", "tx_cash_outflow"]].copy()
    f["month"] = pd.to_datetime(f.month)
    f = f.sort_values(keys + ["month"])
    f["total"] = f.tx_cash_inflow.fillna(0) + f.tx_cash_outflow.fillna(0)
    f["uncat"] = f.tx_uncategorized_amount.fillna(0)
    g = f.groupby(keys, sort=False)
    total = g.total.transform(lambda s: s.rolling(window, min_periods=1).sum())
    uncat = g.uncat.transform(lambda s: s.rolling(window, min_periods=1).sum())
    f["cash_certainty"] = np.where(total > 0, 1 - uncat / total.where(total > 0), np.nan)
    return f[keys + ["month", "cash_certainty"]]


def compute_confidence(scores, features=None, unit="company_id", level_window=6):
    keys = [unit, "currency"]
    s = scores.copy()
    s["month"] = pd.to_datetime(s.month)
    sub = pd.DataFrame(index=s.index)
    sub["history"] = (s.level_months.fillna(0).clip(upper=level_window) / level_window * 100)
    sub["coverage"] = s.level_coverage.fillna(0).clip(0, 1) * 100
    usable = s.tx_usable_row_share.fillna(0).clip(0, 1)
    sub["month_quality"] = np.where(s.month_quality_ok.fillna(False).astype(bool), 100.0, 40.0) * usable
    has_momentum = s.has_momentum.fillna(False).astype(bool)
    sub["trend"] = np.where(has_momentum, s.momentum_coverage.fillna(0).clip(0, 1) * 100, 0.0)
    if features is not None:
        cc = cash_certainty(features, unit)
        merged = s[keys + ["month"]].merge(cc, on=keys + ["month"], how="left", validate="one_to_one")
        sub["cash_certainty"] = merged.cash_certainty.to_numpy() * 100
    else:
        sub["cash_certainty"] = np.nan

    weights = pd.DataFrame({k: np.where(sub[k].notna(), v, 0.0) for k, v in WEIGHTS.items()}, index=s.index)
    total_w = weights.sum(axis=1)
    confidence = (sub.fillna(0) * weights).sum(axis=1) / total_w.where(total_w > 0)
    partial = s.has_partial_currency_coverage.fillna(False).astype(bool)
    confidence = confidence.where(~partial, confidence.clip(upper=PARTIAL_CURRENCY_CAP))
    confidence = confidence.where(s.tx_count.fillna(0) > 0, 0.0)  # sin movimientos, sin evidencia

    out = s[keys + ["month"]].copy()
    out["confidence"] = confidence.round(1)
    out["confidence_band"] = pd.cut(out.confidence, [-np.inf, 40, 70, np.inf], right=False, labels=["low", "medium", "high"]).astype(str)
    weighted_gap = (100 - sub).mul(weights).where(weights > 0)
    out["limiting_factor"] = weighted_gap.idxmax(axis=1).where(weighted_gap.notna().any(axis=1))
    out["limiting_factor_label"] = out.limiting_factor.map(LABELS)
    for k in WEIGHTS:
        out[f"sub_{k}"] = sub[k].round(1)
    out["has_partial_currency_coverage"] = partial
    out["score_status"] = s.score_status
    validate_confidence(out)
    return out[keys + OUTPUT_COLUMNS]


def validate_confidence(out):
    if not out.confidence.dropna().between(0, 100).all():
        raise ValueError("confidence fuera de [0,100]")
    if (out.loc[out.has_partial_currency_coverage, "confidence"] > PARTIAL_CURRENCY_CAP + 1e-9).any():
        raise ValueError("cobertura parcial de moneda debe topar la confianza")
