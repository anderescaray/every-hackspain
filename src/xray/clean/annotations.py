"""Anotaciones semánticas de transactions (D25–D30).

Marcan, sin borrar ni recategorizar, bloques de texto y estructura que la exploración
(docs/hallazgos-datos.md) identificó como necesarios para no confundir cobertura con
comportamiento financiero. Cada feature decide qué hacer con ellos.
"""
import numpy as np
import pandas as pd

from xray.clean.log import CleaningLog

TABLE = "transactions"

# D26–D28 · Bloques sin categoría de banco pero identificables por plantilla de texto.
SCF_ADJUSTMENT = r"^SCF-AJUS\.SALDO"           # ajustes de confirming / supply chain finance
REPO_PAIR = r"^(?:PR|VT)\.A\b"                 # compra / venta con pacto de recompra (tesorería)
CASH_DISPOSAL = r"^DISP\.ENTREG\.EFECT"        # disposición de efectivo

# D29 · Pasarela de pago: '[fecha] tipo'. Antes de 2025-01 el banco etiquetaba parte como interest_charge.
GATEWAY = r"^\[[^\]]*\]\s*(charge|payment|payout|refund|stripe_fee|network_cost|adjustment|transfer)\s*$"
GATEWAY_COSTS = {"stripe_fee", "network_cost"}

# D30 · Eventos de estrés en el concepto bancario, por orden de prioridad (gana el primero que casa).
REFUND_CATEGORIES = {"collection_refund", "payment_refund"}
EVENT_PATTERNS = (
    ("cuota_impagada", r"CUOTA\s+IMPAGAD"),
    # Embargo a un tercero (no es estrés de la empresa): ingresa en Hacienda lo retenido a un empleado o proveedor
    # embargado, o transfiere al juzgado la parte embargada de una nómina.
    ("embargo_tercero", r"INGRESOS\s+ASOCIADOS\s+EMBARG|EMBARG\w*\s+(?:\S+\s+)?(?:Y\s+)?(?:SALARIO|NOMINA)"
                        r"|(?:SALARIO|NOMINA)\w*\W.*EMBARG|JUZGADO.*EMBARG|EMBARG.*JUZGADO|EMBARG\w*\s+\[PERSON\]"),
    ("embargo", r"\bEMBARG"),
    ("recargo_apremio", r"\bRECARGO\b|\bAPREMIO\b"),   # sin SANCION: 'SANCIONES Y MULTAS' son multas de tráfico en tarjeta
    ("aplazamiento", r"\bAPLAZA"),
    ("descubierto", r"\bDESCUBIERTO\b|\bEXCEDID"),
    ("demora", r"\bDEMORA\b"),
    ("reclamacion", r"\bRECLAMAC"),
    ("impagado_cliente", r"\bIMPAGAD"),
)


def annotate_products(t: pd.DataFrame, products: pd.DataFrame, log: CleaningLog) -> None:
    """D25 · Tipo de producto de la cuenta: separa cuentas corrientes de pólizas de crédito operativas."""
    index = products.set_index("product_id")
    t["product_kind"] = t.product_id.map(index["kind"]) if "kind" in index else pd.Series(pd.NA, index=t.index, dtype="string")
    t["product_type"] = t.product_id.map(index["type"]) if "type" in index else pd.Series(pd.NA, index=t.index, dtype="string")
    t["product_kind"] = t.product_kind.astype("string")
    t["product_type"] = t.product_type.astype("string")
    on_debt = t.product_kind.eq("debt").fillna(False).sum()
    log.add(TABLE, "D25", "annotate", on_debt, "product_kind/product_type: movimientos sobre productos de deuda (pólizas operativas)")


def annotate_text(t: pd.DataFrame, log: CleaningLog) -> None:
    text = t.description.fillna("").astype(str)
    upper = text.str.upper()

    _flag(t, log, "D26", "is_scf_adjustment", upper.str.contains(SCF_ADJUSTMENT, regex=True),
          "ajuste de saldo de confirming (SCF): financiación, no flujo operativo")
    _flag(t, log, "D27", "is_repo_pair", upper.str.contains(REPO_PAIR, regex=True),
          "PR.A / VT.A: compra-venta con pacto de recompra; pares espejo de tesorería")
    _flag(t, log, "D28", "is_cash_disposal", upper.str.contains(CASH_DISPOSAL, regex=True),
          "disposición de efectivo sin categoría")

    kind = text.str.extract(GATEWAY, flags=2)[0].str.lower()  # flags=2 -> re.IGNORECASE
    t["gateway_kind"] = kind.astype("string")
    log.add(TABLE, "D29", "annotate", kind.notna().sum(), "gateway_kind: movimientos de pasarela de pago '[fecha] tipo'")
    _flag(t, log, "D29", "is_gateway_cost", kind.isin(GATEWAY_COSTS),
          "coste de pasarela (stripe_fee / network_cost); antes de 2025-01 venía como interest_charge")

    event = pd.Series(pd.NA, index=t.index, dtype="string")
    for name, pattern in EVENT_PATTERNS:
        hit = upper.str.contains(pattern, regex=True) & event.isna()
        if name == "cuota_impagada":
            hit |= upper.str.contains(r"\bIMPAGAD", regex=True) & t.category.eq("debt_repayment") & event.isna()
        event = event.mask(hit, name)
    returned = t.amount.lt(0) & t.category.isin(REFUND_CATEGORIES) & event.isna()
    event = event.mask(returned, "recibo_devuelto")
    t["event_type"] = event
    log.add(TABLE, "D30", "annotate", event.notna().sum(),
            "event_type: " + ", ".join(dict(EVENT_PATTERNS)) + ", recibo_devuelto (refund negativo por signo)")


def _flag(t: pd.DataFrame, log: CleaningLog, rule: str, column: str, mask: pd.Series, detail: str) -> None:
    t[column] = np.asarray(mask.fillna(False), dtype=bool)
    log.add(TABLE, rule, "flag", int(t[column].sum()), f"{column}: {detail}")
