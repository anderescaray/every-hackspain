"""Tests de las reglas de limpieza sobre datos mínimos construidos a mano."""
import pandas as pd
import pytest

from xray.clean.invoices import clean_invoices
from xray.clean.log import CleaningLog
from xray.clean.tables import clean_table
from xray.clean.transactions import clean_transactions, mirror_pairs, sync_duplicates
from xray.clean.validate import ValidationError, validate


def tx_frame(rows):
    cols = ["transaction_id", "company_id", "product_id", "date", "value_date", "amount",
            "exchange_rate", "status", "accounting_status", "category", "description", "counterparty_id"]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df.date)
    df["value_date"] = pd.to_datetime(df.value_date)
    return df


def row(i, company="C1", product="P1", date="2025-01-10", amount=100.0, status="booked",
        category="collection", description="X"):
    return [f"t{i}", company, product, date, date, amount, 1.0, status, None, category, description, None]


PRODUCTS = pd.DataFrame({"product_id": ["P1", "P2", "P3"], "company_id": ["C1", "C1", "C2"]})
GROUPS = pd.Series({"C1": "G1", "C2": "G1"})


def run_tx(rows):
    log = CleaningLog()
    return clean_transactions(tx_frame(rows), PRODUCTS, GROUPS, log), log.to_frame()


def test_drops_zero_amount_and_value_date():
    out, _ = run_tx([row(1), row(2, amount=0.0)])
    assert list(out.transaction_id) == ["t1"]
    assert "value_date" not in out


def test_drops_pending_with_booked_twin_only():
    out, _ = run_tx([
        row(1, status="pending", date="2025-01-10"),
        row(2, status="booked", date="2025-01-12"),              # gemelo a 2 días -> se quita t1
        row(3, status="pending", amount=55.0, date="2025-01-10"),  # sin gemelo -> se queda
    ])
    assert set(out.transaction_id) == {"t2", "t3"}


def test_uncategorized_is_normalized():
    out, _ = run_tx([row(1, category="-"), row(2, category=None)])
    assert (out.category == "uncategorized").all()


def test_internal_transfer_and_intragroup_mirrors():
    out, _ = run_tx([
        row(1, product="P1", amount=-500.0),
        row(2, product="P2", amount=500.0),                  # espejo de t1 en otra cuenta de C1
        row(3, company="C2", product="P3", amount=-70.0),
        row(4, company="C1", product="P1", amount=70.0),     # espejo entre empresas del grupo G1
        row(5, product="P1", amount=-900.0),
        row(6, product="P1", amount=900.0),                  # misma cuenta: no es traspaso
    ])
    flags = out.set_index("transaction_id")
    assert flags.loc[["t1", "t2"], "is_internal_transfer"].all()
    assert not flags.loc[["t3", "t4", "t5", "t6"], "is_internal_transfer"].any()
    assert flags.loc[["t3", "t4"], "is_intragroup"].all()


def test_mirror_pairs_one_to_one():
    t = tx_frame([row(1, product="P1", amount=-10.0), row(2, product="P2", amount=10.0),
                  row(3, product="P2", amount=10.0)])
    assert mirror_pairs(t, t.company_id).sum() == 2        # el segundo +10 no tiene pareja


def test_sync_duplicates_only_in_anomalous_months():
    doubled = [row(i, description=f"d{i % 15}") for i in range(30)]           # enero: todo repetido 2 veces
    normal = [row(100 + i, date="2025-02-10", description=f"n{i}") for i in range(20)]
    normal.append(row(200, date="2025-02-10", description="n0"))              # un duplicado suelto en febrero
    t = tx_frame(doubled + normal)
    flags = sync_duplicates(t)
    assert flags[t.date.dt.month == 1].sum() == 15
    assert flags[t.date.dt.month == 2].sum() == 0


def test_unknown_product_is_flagged_not_dropped():
    out, _ = run_tx([row(1, product="P9")])
    assert len(out) == 1 and out.is_unknown_product.all()


def inv_frame(rows):
    cols = ["operation_id", "company_id", "document_type", "issuance_date", "due_date", "payment_date",
            "amount", "pending_amount", "currency", "accounting_currency", "exchange_rate", "status",
            "concept", "counterparty_id"]
    df = pd.DataFrame(rows, columns=cols)
    for c in ["issuance_date", "due_date", "payment_date"]:
        df[c] = pd.to_datetime(df[c])
    return df


def inv(i, doc="invoice", issued="2025-01-01", due="2025-01-31", paid="2025-02-05", amount=100.0, status="paid"):
    return [f"o{i}", "C1", doc, issued, due, paid, amount, 0.0, "EUR", "EUR", 1.0, status, f"c{i}", "K1"]


def test_invoices_rules():
    log = CleaningLog()
    out = clean_invoices(inv_frame([
        inv(1),
        inv(2, amount=0.0),                                   # F01
        inv(3, status="cancel"),                              # F02
        inv(4, doc="deliveryNote"),                           # F03
        inv(5, status="overdue", paid="2025-01-31"),          # F04: payment_date de relleno
        inv(6, due="7025-07-31"),                             # F05
        inv(7, amount=-40.0, doc="paymentDocument"),          # D11
        inv(8, status="pending", paid="2025-01-31"),          # D14: vencida hace mucho
    ]), log).set_index("operation_id")
    assert set(out.index) == {"o1", "o5", "o6", "o7", "o8"}
    assert pd.isna(out.loc["o5", "payment_date"])
    assert pd.isna(out.loc["o6", "due_date"]) and out.loc["o6", "has_anomalous_term"]
    assert out.loc["o7", "direction"] == "AP" and out.loc["o7", "is_ambiguous_document"]
    assert out.loc["o8", "is_stale_pending"]
    assert not out.loc["o1", ["is_possible_duplicate", "has_anomalous_term", "is_future_payment"]].any()


def test_drop_columns_small_tables():
    out = clean_table("balances", pd.DataFrame({"product_id": ["P1"], "available": [None], "balance": [1.0]}), CleaningLog())
    assert list(out.columns) == ["product_id", "balance"]


def test_validate_detects_duplicate_keys():
    tables = {
        "groups": pd.DataFrame({"group_id": ["G1"]}),
        "companies": pd.DataFrame({"company_id": ["C1"], "group_id": ["G1"]}),
        "banking_products": pd.DataFrame({"product_id": ["P1"], "company_id": ["C1"]}),
        "debt_products": pd.DataFrame({"product_id": ["P2"], "company_id": ["C1"]}),
        "debt_schedule_config": pd.DataFrame({"product_id": ["P2"], "company_id": ["C1"]}),
        "balances": pd.DataFrame({"product_id": ["P1"], "company_id": ["C1"]}),
        "invoices": pd.DataFrame({"operation_id": ["o1", "o1"], "company_id": ["C1", "C1"]}),
        "transactions": pd.DataFrame({"transaction_id": ["t1"], "company_id": ["C1"]}),
    }
    with pytest.raises(ValidationError, match="invoices.operation_id no es único"):
        validate(tables)
