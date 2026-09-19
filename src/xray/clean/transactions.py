"""Limpieza de transactions.

Solo se QUITA lo obvio (T*). Lo dudoso se MARCA con columnas booleanas `is_*` (D*) para que
cada feature decida qué hacer. Los IDs corresponden a docs/decisiones.md.
"""
import numpy as np
import pandas as pd

from xray.clean.annotations import annotate_products, annotate_text
from xray.clean.log import CleaningLog

TABLE = "transactions"
SYNC_DUP_SHARE = 0.5          # D03: empresa-mes con ≥ 50% de filas duplicadas
SYNC_DUP_MIN_ROWS = 20        # D03: solo en meses con actividad suficiente
PENDING_TWIN_DAYS = 5         # T02


def clean_transactions(tx: pd.DataFrame, products: pd.DataFrame, company_group: pd.Series,
                       log: CleaningLog) -> pd.DataFrame:
    """`products`: product_id + company_id (+ type, kind) de banking y debt. `company_group`: company_id -> group_id."""
    t = tx.copy()
    t["amount"] = pd.to_numeric(t.amount)
    t["exchange_rate"] = pd.to_numeric(t.exchange_rate)
    t["product_currency"] = t.product_id.map(products.set_index("product_id").currency)

    # T01 · Importe cero: no es un movimiento de dinero.
    mask = t.amount == 0
    log.add(TABLE, "T01", "drop_rows", mask.sum(), "amount == 0")
    t = t[~mask]

    # T02 · Un `pending` que ya aparece asentado como `booked` es el mismo movimiento dos veces.
    mask = pending_with_booked_twin(t)
    log.add(TABLE, "T02", "drop_rows", mask.sum(), f"pending con gemelo booked (±{PENDING_TWIN_DAYS} días)")
    t = t[~mask]

    # T03 · value_date: contiene basura (2099-12-31) y `date` es la fecha contable de referencia.
    t = t.drop(columns="value_date")
    log.add(TABLE, "T03", "drop_column", 0, "value_date")

    # T04 · Categoría sin asignar: '-' y nulos pasan a un único valor explícito.
    mask = t.category.isna() | (t.category == "-")
    t["category"] = t.category.where(~mask, "uncategorized")
    log.add(TABLE, "T04", "normalize", mask.sum(), "category '-' / nulo -> 'uncategorized'")

    # --- Marcas para decisiones pendientes ---
    # D32: ningún movimiento se marca ni se excluye por su tamaño, ni absoluto (D01) ni relativo (D02).
    _flag(t, log, "D03", "is_sync_duplicate", sync_duplicates(t),
          f"repetición en empresa-mes con ≥ {SYNC_DUP_SHARE:.0%} de filas duplicadas")
    candidates = t.loc[(t.status == "booked") & ~t.is_sync_duplicate]
    internal = mirror_pairs(candidates, candidates.company_id).reindex(t.index, fill_value=False)
    _flag(t, log, "D04", "is_internal_transfer", internal, "espejo +X/−X mismo día y moneda entre cuentas propias; booked")
    residual = candidates.loc[~internal.reindex(candidates.index)]
    intragroup = mirror_pairs(residual, residual.company_id.map(company_group), different_company=True)
    _flag(t, log, "D05", "is_intragroup", intragroup.reindex(t.index, fill_value=False),
          "espejo +X/−X mismo día y moneda entre empresas del grupo, sin reutilizar traspasos")
    known = products.set_index("product_id").company_id
    _flag(t, log, "D06", "is_unknown_product", ~t.product_id.isin(known.index),
          "product_id no está en banking_products ni en debt_products")
    _flag(t, log, "D23", "has_invalid_exchange_rate", ~np.isfinite(t.exchange_rate) | t.exchange_rate.le(0),
          "exchange_rate no finito o no positivo; informativo, la conversión usa xray.fx (D32)")
    annotate_products(t, products, log)
    annotate_text(t, log)
    return t.reset_index(drop=True)


def pending_with_booked_twin(t: pd.DataFrame) -> pd.Series:
    """True para los `pending` con un `booked` del mismo importe, cuenta y concepto a ±N días."""
    keys = ["company_id", "product_id", "amount", "description"]
    pending = t.loc[t.status == "pending", keys + ["date"]].reset_index()
    booked = t.loc[t.status == "booked", keys + ["date"]]
    pairs = pending.merge(booked, on=keys, suffixes=("", "_booked"))
    close = (pairs.date_booked - pairs.date).dt.days.abs() <= PENDING_TWIN_DAYS
    return pd.Series(t.index.isin(pairs.loc[close, "index"]), index=t.index)


def sync_duplicates(t: pd.DataFrame) -> pd.Series:
    """Repeticiones (todas menos la primera) dentro de empresa-mes cargados dos o más veces.

    Los duplicados sueltos se consideran legítimos (la anonimización hace idénticos pagos distintos);
    solo se marcan los meses donde la proporción de filas duplicadas es anómala.
    """
    keys = ["company_id", "product_id", "date", "amount", "description"]
    month = t.date.dt.to_period("M")
    in_dup = t.duplicated(keys, keep=False)
    share = in_dup.groupby([t.company_id, month]).transform("mean")
    rows = in_dup.groupby([t.company_id, month]).transform("size")
    return t.duplicated(keys, keep="first") & (share >= SYNC_DUP_SHARE) & (rows >= SYNC_DUP_MIN_ROWS)


def mirror_pairs(t: pd.DataFrame, unit: pd.Series, different_company: bool = False) -> pd.Series:
    """True para los movimientos +X / −X del mismo día dentro de `unit` en cuentas distintas.

    Empareja 1 a 1 (el k-ésimo +X con el k-ésimo −X), así un importe repetido no se reutiliza.
    """
    d = pd.DataFrame({"unit": unit, "product_id": t.product_id, "amount": t.amount,
                      "company_id": t.company_id, "currency": t.product_currency,
                      "day": t.date.dt.normalize(), "abs": t.amount.abs()}, index=t.index)
    d = d[d.unit.notna() & d.currency.notna() & (d.amount != 0)]
    d["k"] = d.groupby(["unit", "currency", "day", "abs", np.sign(d.amount)]).cumcount()
    keys = ["unit", "currency", "day", "abs", "k"]
    pairs = (d[d.amount > 0].reset_index()
             .merge(d[d.amount < 0].reset_index(), on=keys, suffixes=("_in", "_out")))
    pairs = pairs[pairs.product_id_in != pairs.product_id_out]
    if different_company:
        pairs = pairs[pairs.company_id_in != pairs.company_id_out]
    ids = pd.concat([pairs["index_in"], pairs["index_out"]])
    return pd.Series(t.index.isin(ids), index=t.index)


def _flag(t: pd.DataFrame, log: CleaningLog, rule: str, column: str, mask: pd.Series, detail: str) -> None:
    t[column] = mask.to_numpy(dtype=bool)
    log.add(TABLE, rule, "flag", t[column].sum(), f"{column}: {detail}")
