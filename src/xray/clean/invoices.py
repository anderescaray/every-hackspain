"""Limpieza de invoices.

Solo se QUITA lo obvio (F*). Lo dudoso se MARCA con columnas booleanas `is_*` / `has_*` (D*).
Los IDs corresponden a docs/decisiones.md.
"""
import pandas as pd

from xray.clean.log import CleaningLog
from xray.paths import EXTRACTION_DATE

TABLE = "invoices"
NOT_AN_OBLIGATION = ["deliveryNote", "purchaseOrder"]          # F03
AMBIGUOUS_DOCUMENTS = ["paymentDocument", "deposit", "other", "cheque"]  # D11
VALID_YEARS = (2020, 2030)                                     # F05
MAX_TERM_DAYS = 365                                            # D12
STALE_PENDING_DAYS = 30                                        # D14


def clean_invoices(inv: pd.DataFrame, log: CleaningLog, extraction_date: pd.Timestamp = EXTRACTION_DATE) -> pd.DataFrame:
    f = inv.copy()
    f["amount"] = pd.to_numeric(f.amount)
    f["exchange_rate"] = pd.to_numeric(f.exchange_rate)

    # F01 · Importe cero.
    mask = f.amount == 0
    log.add(TABLE, "F01", "drop_rows", mask.sum(), "amount == 0")
    f = f[~mask]

    # F02 · Factura anulada: no existe a efectos financieros.
    mask = f.status == "cancel"
    log.add(TABLE, "F02", "drop_rows", mask.sum(), "status == cancel")
    f = f[~mask]

    # F03 · Albaranes y pedidos: todavía no son una obligación de cobro/pago.
    mask = f.document_type.isin(NOT_AN_OBLIGATION)
    log.add(TABLE, "F03", "drop_rows", mask.sum(), f"document_type in {NOT_AN_OBLIGATION}")
    f = f[~mask]

    # F04 · En facturas no pagadas, payment_date es un relleno (= due_date): no es una fecha de pago.
    # F07 · Ese relleno es la fecha prevista de pago del ERP: se conserva aparte, nunca como pago realizado.
    mask = (f.status != "paid") & f.payment_date.notna()
    f["expected_payment_date"] = f.payment_date.where(mask)
    f["payment_date"] = f.payment_date.where(~mask)
    log.add(TABLE, "F04", "set_null", mask.sum(), "payment_date cuando status != paid (valor de relleno)")
    log.add(TABLE, "F07", "normalize", mask.sum(), "nueva columna expected_payment_date: fecha prevista en facturas no pagadas")

    # F05 · Fechas imposibles (años 2000, 6913, 7025...).
    lo, hi = VALID_YEARS
    for col in ["due_date", "payment_date"]:
        mask = f[col].notna() & ~f[col].dt.year.between(lo, hi)
        f[col] = f[col].where(~mask)
        log.add(TABLE, "F05", "set_null", mask.sum(), f"{col} fuera de {lo}-{hi}")

    # F06 · Dirección explícita a partir del signo.
    f["direction"] = f.amount.gt(0).map({True: "AR", False: "AP"})
    log.add(TABLE, "F06", "normalize", len(f), "nueva columna direction: AR (amount > 0, a cobrar) / AP (a pagar)")

    # --- Marcas para decisiones pendientes ---
    keys = ["company_id", "counterparty_id", "document_type", "issuance_date", "due_date", "amount", "currency", "concept"]
    _flag(f, log, "D10", "is_possible_duplicate", f.duplicated(keys),
          "repetición exacta (empresa, contraparte, tipo, fechas, importe, concepto)")
    _flag(f, log, "D11", "is_ambiguous_document", f.document_type.isin(AMBIGUOUS_DOCUMENTS),
          f"document_type in {AMBIGUOUS_DOCUMENTS}")
    term = (f.due_date - f.issuance_date).dt.days
    _flag(f, log, "D12", "has_anomalous_term", term.isna() | (term < 0) | (term > MAX_TERM_DAYS),
          f"plazo < 0, > {MAX_TERM_DAYS} días o sin vencimiento válido")
    _flag(f, log, "D13", "is_future_payment", (f.status == "paid") & (f.payment_date.dt.normalize() > extraction_date.normalize()),
          "paid con payment_date posterior al día de extracción")
    _flag(f, log, "D22", "is_payment_before_issuance", f.payment_date < f.issuance_date,
          "pago anterior a emisión: posible anticipo, no sirve para DSO/DPO")
    _flag(f, log, "D14", "is_stale_pending",
          (f.status == "pending") & (f.due_date < extraction_date - pd.Timedelta(days=STALE_PENDING_DAYS)),
          f"pending vencida hace > {STALE_PENDING_DAYS} días")
    _flag(f, log, "D23", "has_invalid_exchange_rate",
          f.exchange_rate.isna() | f.exchange_rate.le(0) | f.exchange_rate.abs().eq(float("inf")),
          "exchange_rate no finito o no positivo; informativo, la conversión usa xray.fx (D32)")
    return f.reset_index(drop=True)


def _flag(f: pd.DataFrame, log: CleaningLog, rule: str, column: str, mask: pd.Series, detail: str) -> None:
    f[column] = mask.to_numpy(dtype=bool)
    log.add(TABLE, rule, "flag", f[column].sum(), f"{column}: {detail}")
