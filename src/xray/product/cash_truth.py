"""Cash Truth: ¿esta caja se genera, circula o viene de apoyo?

Clasifica cada movimiento bancario elegible (booked, FX=1, sin flags de calidad; mismo criterio que
`xray.features.transactions`) en un único bucket, por prioridad:

    own_circulation        espejo +X/−X mismo día entre cuentas propias (D04 `is_internal_transfer`)
    group_support          espejo entre empresas del mismo grupo (D05 `is_intragroup`)
    financing_investment   deuda, intereses, inversión y comisiones bancarias
    operations             categorías operativas de entrada/salida del score (INFLOW ∪ OUTFLOW)
    unpaired_transfer      `transfer` y retiradas de efectivo sin espejo identificado
    uncertain              sin categoría o categoría no interpretable

No se inventa clasificación: lo que no se identifica queda en `uncertain` y se enseña como tal.

Agregados por entidad-moneda-mes y, sobre una ventana hacia atrás de `window` meses (solo meses
<= t), el ratio de dependencia de apoyo del grupo:

    support_dependency_ratio = apoyo_recibido_6m / (entradas_operativas_6m + apoyo_recibido_6m)

y su tendencia (trimestre reciente − trimestre anterior). NaN si no hay soporte suficiente.
"""
import numpy as np
import pandas as pd

from xray.features.transactions import FLAGS, INFLOW, OUTFLOW
from xray.paths import EXTRACTION_DATE

BUCKETS = ["own_circulation", "group_support", "financing_investment", "operations", "unpaired_transfer", "uncertain"]
BUCKET_LABELS = {
    "own_circulation": "Circulación entre cuentas propias",
    "group_support": "Apoyo / flujos intragrupo",
    "financing_investment": "Financiación, inversión y comisiones",
    "operations": "Operación identificada",
    "unpaired_transfer": "Traspasos sin emparejar",
    "uncertain": "No identificable con suficiente confianza",
}
FINANCING = {"debt_repayment", "interest_charge", "investment_deployment", "investment_return", "fee"}
UNPAIRED = {"transfer", "cash_withdrawal", "pos_withdrawal"}
EVIDENCE_COLUMNS = ["company_id", "currency", "month", "bucket", "transaction_id", "date", "amount", "category", "description"]


def classify(transactions, stop=EXTRACTION_DATE):
    """Devuelve los movimientos elegibles con columnas `month`, `bucket` y `currency`."""
    t = transactions.loc[transactions.date.lt(stop)].copy()
    if "currency" not in t and "product_currency" in t:
        t = t.rename(columns={"product_currency": "currency"})
    flags = [f for f in FLAGS if f in t]
    eligible = t.status.eq("booked") & t.exchange_rate.eq(1) & ~t[flags].any(axis=1) if flags else t.status.eq("booked") & t.exchange_rate.eq(1)
    t = t.loc[eligible].copy()
    t["amount"] = t.amount.astype(float)
    t["month"] = t.date.dt.to_period("M").dt.to_timestamp()
    t["bucket"] = np.select(
        [t.is_internal_transfer.fillna(False).astype(bool), t.is_intragroup.fillna(False).astype(bool),
         t.category.isin(FINANCING), t.category.isin(INFLOW | OUTFLOW), t.category.isin(UNPAIRED)],
        BUCKETS[:5], default="uncertain")
    return t


def monthly_buckets(classified):
    """Una fila por entidad-moneda-mes-bucket con entradas, salidas, importe absoluto, nº y cuota."""
    keys = ["company_id", "currency", "month"]
    c = classified
    g = c.assign(amount_in=c.amount.clip(lower=0), amount_out=(-c.amount).clip(lower=0), amount_abs=c.amount.abs())
    m = g.groupby(keys + ["bucket"], observed=True).agg(amount_in=("amount_in", "sum"), amount_out=("amount_out", "sum"),
                                                      amount_abs=("amount_abs", "sum"), n_tx=("amount", "size")).reset_index()
    total = m.groupby(keys).amount_abs.transform("sum")
    m["share_abs"] = np.where(total > 0, m.amount_abs / total.where(total > 0), np.nan)
    m["label"] = m.bucket.map(BUCKET_LABELS)
    return m.sort_values(keys + ["bucket"]).reset_index(drop=True)


def _calendar(frame, keys, last_month):
    """Rellena con ceros los meses sin movimiento entre el primer mes de la entidad y `last_month`."""
    pieces = []
    for key, rows in frame.groupby(keys, sort=False):
        idx = pd.date_range(rows.month.min(), last_month, freq="MS")
        piece = rows.set_index("month").reindex(idx).fillna(0.0).rename_axis("month").reset_index()
        for k, v in zip(keys, key if isinstance(key, tuple) else (key,)):
            piece[k] = v
        pieces.append(piece)
    return pd.concat(pieces, ignore_index=True)


def dependency_summary(monthly, window=6, quarter=3, min_months=3, last_month=None):
    """Ratio de dependencia de apoyo, su tendencia y la cuota incierta, por entidad-moneda-mes."""
    keys = ["company_id", "currency"]
    wide = monthly.pivot_table(index=keys + ["month"], columns="bucket", values=["amount_in", "amount_out", "amount_abs"],
                               aggfunc="sum", fill_value=0.0)
    wide.columns = [f"{a}__{b}" for a, b in wide.columns]
    wide = wide.reset_index()
    for col in [f"{a}__{b}" for a in ("amount_in", "amount_out", "amount_abs") for b in BUCKETS]:
        if col not in wide:
            wide[col] = 0.0
    wide["total_abs"] = sum(wide[f"amount_abs__{b}"] for b in BUCKETS)
    wide["active"] = wide.total_abs.gt(0).astype(float)
    last_month = pd.Timestamp(last_month) if last_month is not None else wide.month.max()
    cal = _calendar(wide, keys, last_month).sort_values(keys + ["month"])
    g = cal.groupby(keys, sort=False)

    def roll(col, n):
        return g[col].transform(lambda s: s.rolling(n, min_periods=1).sum())

    def ratio(n):
        support = roll("amount_in__group_support", n)
        ops = roll("amount_in__operations", n)
        denom = ops + support
        return pd.Series(np.where(denom > 0, support / denom.where(denom > 0), np.nan), index=cal.index)

    months_active = roll("active", window)
    enough = months_active.ge(min_months)
    out = cal[keys + ["month"]].copy()
    out["support_in_6m"] = roll("amount_in__group_support", window)
    out["support_out_6m"] = roll("amount_out__group_support", window)
    out["support_net_6m"] = out.support_in_6m - out.support_out_6m
    out["operations_in_6m"] = roll("amount_in__operations", window)
    out["support_dependency_ratio"] = ratio(window).where(enough)
    recent = ratio(quarter)
    prior_support = g["amount_in__group_support"].transform(lambda s: s.shift(quarter).rolling(quarter, min_periods=1).sum())
    prior_ops = g["amount_in__operations"].transform(lambda s: s.shift(quarter).rolling(quarter, min_periods=1).sum())
    prior_denom = prior_ops + prior_support
    prior_ratio = pd.Series(np.where(prior_denom > 0, prior_support / prior_denom.where(prior_denom > 0), np.nan), index=cal.index)
    out["support_dependency_trend"] = (recent - prior_ratio).where(enough & months_active.ge(2 * quarter - 1))
    total_6m = roll("total_abs", window)
    out["uncertain_share_6m"] = (roll("amount_abs__uncertain", window) / total_6m.where(total_6m > 0)).where(enough)
    out["own_circulation_share_6m"] = (roll("amount_abs__own_circulation", window) / total_6m.where(total_6m > 0)).where(enough)
    out["months_active_6m"] = months_active.astype(int)
    out["support_role"] = np.select([out.support_dependency_ratio.isna(), out.support_net_6m.gt(0), out.support_net_6m.lt(0)],
                                    ["unknown", "net_receiver", "net_provider"], default="balanced")
    return out.reset_index(drop=True)


def evidence(classified):
    """Índice movimiento → bucket para el drill-down de la interfaz."""
    return classified[EVIDENCE_COLUMNS].sort_values(["company_id", "month", "bucket", "date"]).reset_index(drop=True)


def validate_cash_truth(monthly, summary):
    shares = monthly.groupby(["company_id", "currency", "month"]).share_abs.sum()
    if not np.allclose(shares.dropna(), 1.0):
        raise ValueError("Las cuotas por mes no suman 1")
    if not summary.support_dependency_ratio.dropna().between(0, 1).all():
        raise ValueError("support_dependency_ratio fuera de [0,1]")


def compute_cash_truth(transactions, stop=EXTRACTION_DATE, window=6):
    classified = classify(transactions, stop)
    monthly = monthly_buckets(classified)
    summary = dependency_summary(monthly, window=window, last_month=(stop - pd.offsets.MonthBegin(1)).normalize())
    validate_cash_truth(monthly, summary)
    return classified, monthly, summary
