import numpy as np
import pandas as pd
import pytest

from xray.product.cash_truth import (
    BUCKETS,
    classify,
    compute_cash_truth,
    dependency_summary,
    monthly_buckets,
)


def tx(i, company, date, amount, category="collection", internal=False, intragroup=False, status="booked", fx=1.0, **flags):
    row = {"transaction_id": f"T{i}", "company_id": company, "product_id": "P1", "date": pd.Timestamp(date), "amount": float(amount),
               "exchange_rate": fx, "status": status, "category": category, "description": "", "product_currency": "EUR",
               "is_internal_transfer": internal, "is_intragroup": intragroup, "is_extreme_amount": False, "is_relative_outlier": False,
               "is_sync_duplicate": False, "is_unknown_product": False}
    row.update(flags)
    return row


def test_buckets_priority_and_eligibility():
    rows = [tx(1, "A", "2026-01-05", 100),                                   # operations
            tx(2, "A", "2026-01-05", -100, category="transfer", internal=True),  # own_circulation gana a transfer
            tx(3, "A", "2026-01-06", 500, category="collection", intragroup=True),  # group_support gana a operations
            tx(4, "A", "2026-01-07", -20, category="fee"),                    # unverified fee remains uncertain
            tx(5, "A", "2026-01-08", -30, category="transfer"),               # unpaired_transfer
            tx(6, "A", "2026-01-09", 40, category="uncategorized"),           # uncertain
            tx(7, "A", "2026-01-10", 999, status="pending"),                  # fuera: no booked
            tx(8, "A", "2026-01-11", 999, fx=1.1),                            # fuera: FX
            tx(9, "A", "2026-01-12", 999, is_extreme_amount=True),            # fuera: flag
            tx(10, "A", "2026-09-02", 999)]                                   # fuera: posterior a la extracción
    c = classify(pd.DataFrame(rows), stop=pd.Timestamp("2026-09-01"))
    assert dict(zip(c.transaction_id, c.bucket)) == {"T1": "operations", "T2": "own_circulation", "T3": "group_support",
                                                     "T4": "uncertain", "T5": "unpaired_transfer", "T6": "uncertain"}
    m = monthly_buckets(c)
    assert m.share_abs.sum() == pytest.approx(1.0) and set(m.bucket) <= set(BUCKETS)
    assert m.set_index("bucket").loc["group_support", "amount_in"] == 500


def test_intragroup_pair_nets_to_zero_across_the_group_and_roles_are_assigned():
    rows = []
    for k, month in enumerate(("2026-01-01", "2026-02-01", "2026-03-01")):
        rows += [tx(10 + k, "A", month, 1000, intragroup=True), tx(20 + k, "B", month, -1000, intragroup=True),
                 tx(30 + k, "A", month, 500), tx(40 + k, "B", month, 3000)]
    _, monthly, summary = compute_cash_truth(pd.DataFrame(rows), stop=pd.Timestamp("2026-04-01"))
    support = monthly[monthly.bucket == "group_support"]
    assert (support.amount_in.sum() - support.amount_out.sum()) == pytest.approx(0.0)
    last = summary[summary.month == "2026-03-01"].set_index("company_id")
    assert last.loc["A", "support_dependency_ratio"] == pytest.approx(3000 / (1500 + 3000))
    assert last.loc["A", "support_role"] == "net_receiver" and last.loc["B", "support_role"] == "net_provider"
    assert last.loc["B", "support_dependency_ratio"] == 0.0  # B no recibe apoyo


def test_dependency_uses_only_past_months_and_needs_support():
    rows = [tx(1, "A", "2026-01-01", 100), tx(2, "A", "2026-02-01", 100), tx(3, "A", "2026-03-01", 100),
            tx(4, "A", "2026-04-01", 100, intragroup=True), tx(5, "A", "2026-05-01", 100), tx(6, "A", "2026-06-01", 100),
            tx(7, "A", "2026-07-01", 100), tx(8, "A", "2026-08-01", 100)]
    _, _monthly, summary = compute_cash_truth(pd.DataFrame(rows), stop=pd.Timestamp("2026-09-01"))
    s = summary.set_index("month")
    assert np.isnan(s.loc["2026-01-01", "support_dependency_ratio"]) and np.isnan(s.loc["2026-02-01", "support_dependency_ratio"])
    assert s.loc["2026-03-01", "support_dependency_ratio"] == 0.0            # 3 meses de soporte, sin apoyo
    assert s.loc["2026-04-01", "support_dependency_ratio"] == pytest.approx(100 / 400)
    assert s.loc["2026-08-01", "support_dependency_ratio"] == pytest.approx(100 / 600)  # ventana mar-ago incluye abril
    # prefijo: recalcular con datos hasta mayo reproduce exactamente los meses anteriores
    _, _, prefix = compute_cash_truth(pd.DataFrame(rows[:5]), stop=pd.Timestamp("2026-06-01"))
    p = prefix.set_index("month").support_dependency_ratio
    pd.testing.assert_series_equal(p.loc[:"2026-05-01"], s.support_dependency_ratio.loc[:"2026-05-01"], check_names=False)


def test_months_without_movement_count_as_zero_inside_the_window():
    rows = [tx(1, "A", "2026-01-01", 100), tx(2, "A", "2026-01-15", 100, intragroup=True), tx(3, "A", "2026-06-01", 100)]
    monthly = monthly_buckets(classify(pd.DataFrame(rows), stop=pd.Timestamp("2026-07-01")))
    summary = dependency_summary(monthly, last_month=pd.Timestamp("2026-06-01"))
    s = summary.set_index("month")
    assert list(s.index) == list(pd.date_range("2026-01-01", "2026-06-01", freq="MS"))
    assert s.loc["2026-06-01", "months_active_6m"] == 2 and np.isnan(s.loc["2026-06-01", "support_dependency_ratio"])
