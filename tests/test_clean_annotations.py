"""Tests de las anotaciones semánticas D25–D30 y F07 sobre datos mínimos."""
import pandas as pd

from xray.clean.invoices import clean_invoices
from xray.clean.log import CleaningLog
from xray.clean.transactions import clean_transactions
from tests.test_clean import GROUPS, inv, inv_frame, row, tx_frame

PRODUCTS = pd.DataFrame({"product_id": ["P1", "P2", "L1"], "company_id": ["C1", "C1", "C1"],
                         "currency": ["EUR"] * 3, "type": ["checking", "card", "lineofcredit"],
                         "kind": ["banking", "banking", "debt"]})


def run_tx(rows, products=PRODUCTS):
    log = CleaningLog()
    out = clean_transactions(tx_frame(rows), products, GROUPS, log)
    return out.set_index("transaction_id"), log.to_frame()


def test_product_kind_marks_operating_credit_lines():
    out, log = run_tx([row(1, product="P1"), row(2, product="L1", category="salary", amount=-900.0), row(3, product="P9")])
    assert out.loc["t1", "product_kind"] == "banking" and out.loc["t1", "product_type"] == "checking"
    assert out.loc["t2", "product_kind"] == "debt" and out.loc["t2", "product_type"] == "lineofcredit"
    assert pd.isna(out.loc["t3", "product_kind"]) and out.loc["t3", "is_unknown_product"]
    assert log.loc[log.rule == "D25", "rows"].item() == 1


def test_product_kind_is_optional_for_legacy_product_tables():
    legacy = PRODUCTS[["product_id", "company_id", "currency"]]
    out, _ = run_tx([row(1)], products=legacy)
    assert out.product_kind.isna().all() and out.product_type.isna().all()


def test_text_blocks_without_category():
    out, _ = run_tx([
        row(1, category="-", description="SCF-AJUS.SALDO C., DC: 8631.[NUM]", amount=-5000.0),
        row(2, category="-", description="PR.A [NUM]-[NUM]", amount=-1e6),
        row(3, category="-", description="VT.A [NUM]-[NUM]", amount=1e6),
        row(4, category="-", description="DISP.ENTREG.EFECT.", amount=-300.0),
        row(5, category="collection", description="TRANSFERENCIA SCF-AJUS.SALDO"),  # no empieza por SCF: no casa
    ])
    assert out.is_scf_adjustment.tolist() == [True, False, False, False, False]
    assert out.is_repo_pair.tolist() == [False, True, True, False, False]
    assert out.is_cash_disposal.tolist() == [False, False, False, True, False]


def test_gateway_kind_and_cost():
    out, _ = run_tx([
        row(1, category="interest_charge", description="[2024-11-27] stripe_fee", amount=-3.2),
        row(2, category="-", description="[2025-02-01] NETWORK_COST", amount=-1.1),
        row(3, category="-", description="[2025-02-01] payout", amount=-800.0),
        row(4, category="-", description="[2025-02-01] charge", amount=120.0),
        row(5, category="-", description="[X] REFUND - [X] TRANSFERENCIAS", amount=-50.0),  # texto libre: no es pasarela
        row(6, category="interest_charge", description="LIQUIDACION DE INTERESES", amount=-90.0),
    ])
    assert out.gateway_kind.tolist()[:4] == ["stripe_fee", "network_cost", "payout", "charge"]
    assert out.gateway_kind.isna().tolist()[4:] == [True, True]
    assert out.is_gateway_cost.tolist() == [True, True, False, False, False, False]


def test_event_type_priority_and_sign_based_returns():
    out, _ = run_tx([
        row(1, category="debt_repayment", description="CUOTA IMPAGADA [COMPANY] 0049 1917 123 [NUM]", amount=-4734.9),
        row(2, category="debt_repayment", description="RECIBO IMPAGADO PTMO [NUM]", amount=-500.0),   # IMPAGAD + debt_repayment
        row(3, category="tax", description="EMBARGO AEAT [REF]", amount=-1200.0),
        row(4, category="-", description="RECARGO DE APREMIO [NUM]", amount=-80.0),
        row(5, category="social_security", description="APLAZAMIENTO TGSS CUOTA 3/12", amount=-2000.0),
        row(6, category="fee", description="COMISION DESCUBIERTO", amount=-30.0),
        row(7, category="fee", description="INTERESES DE DEMORA", amount=-12.0),
        row(8, category="fee", description="GASTOS RECLAMACION POSICIONES DEUDORAS", amount=-35.0),
        row(9, category="fee", description="RECOBRO DE COMISIONES IMPAGADAS", amount=-9.0),
        row(10, category="collection_refund", description="DEVOLUCION RECIBO [NAME]", amount=-280.0),
        row(11, category="payment_refund", description="DEVOLUCION", amount=-150.0),     # taxonomía pre-2025: signo manda
        row(12, category="payment_refund", description="DEVOLUCION COMPRA", amount=73.6),  # positivo: no es recibo devuelto
        row(13, category="bulk_collection", description="LIQUIDACION NOMINAL REMESAS DE COMERCIOS", amount=879.5),
        row(14, category="collection", description="[COMPANY]. - Renovación de lote (app)", amount=0.01),
        row(15, category="-", description="WEB AMENDE.[X] [NUM] FR TRAFFIC FINE 146 - 629098 SANCIONES Y MULTAS", amount=-90.0),
    ])
    expected = ["cuota_impagada", "cuota_impagada", "embargo", "recargo_apremio", "aplazamiento", "descubierto",
                "demora", "reclamacion", "impagado_cliente", "recibo_devuelto", "recibo_devuelto"]
    assert out.event_type.tolist()[:11] == expected
    assert out.event_type.isna().tolist()[11:] == [True, True, True, True]


def test_expected_payment_date_kept_apart_from_real_payment():
    out = clean_invoices(inv_frame([
        inv(1),                                             # paid: sin fecha prevista
        inv(2, status="overdue", paid="2025-01-31"),        # relleno = due_date -> prevista
        inv(3, status="pending", paid="2025-03-15"),
    ]), CleaningLog()).set_index("operation_id")
    assert pd.isna(out.loc["o1", "expected_payment_date"]) and out.loc["o1", "payment_date"] == pd.Timestamp("2025-02-05")
    assert pd.isna(out.loc["o2", "payment_date"]) and out.loc["o2", "expected_payment_date"] == pd.Timestamp("2025-01-31")
    assert out.loc["o3", "expected_payment_date"] == pd.Timestamp("2025-03-15")
