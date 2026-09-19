"""Legacy product views over the canonical Cash Truth ledger.

The six historical UI buckets are a projection, NEVER another economic
classifier. Pulse consumes independent monthly facts from xray.ledger instead
of this legacy rolling support-dependency view.
"""
import numpy as np
import pandas as pd

from xray.ledger.classify import classify_transactions
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
EVIDENCE_COLUMNS = ["company_id", "currency", "month", "bucket", "transaction_id", "date", "amount", "category", "description"]


def classify(transactions, stop=EXTRACTION_DATE, *, ai_categories_path=None, ai_min_confidence=0.7):
    """Eligible movements with compatibility buckets derived from canonical classes."""
    t = classify_transactions(transactions, as_of=pd.Timestamp(stop) - pd.Timedelta(days=1),
                              ai_categories_path=ai_categories_path, ai_min_confidence=ai_min_confidence)
    t = t.loc[t.eligible].copy()
    mapping = {"own_account_circulation": "own_circulation", "group_or_internal": "group_support",
               "external_financing": "financing_investment", "debt_service": "financing_investment",
               "investment": "financing_investment", "operating": "operations", "uncertain": "uncertain"}
    t["bucket"] = t.economic_class.map(mapping)
    t.loc[t.economic_subclass.eq("unpaired_transfer"), "bucket"] = "unpaired_transfer"
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


def compute_cash_truth(transactions, stop=EXTRACTION_DATE, window=6, *, ai_categories_path=None, ai_min_confidence=0.7):
    classified = classify(transactions, stop, ai_categories_path=ai_categories_path, ai_min_confidence=ai_min_confidence)
    monthly = monthly_buckets(classified)
    summary = dependency_summary(monthly, window=window, last_month=(stop - pd.offsets.MonthBegin(1)).normalize())
    validate_cash_truth(monthly, summary)
    return classified, monthly, summary
