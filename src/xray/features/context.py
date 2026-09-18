import pandas as pd

from xray.features.temporal import divide


def reconstruct_liquidity(tables, config):
    bank = tables["banking_products"]
    accounts = bank.loc[bank.type.eq("checking"), ["product_id", "company_id", "currency", "created_at"]]
    balances = accounts.merge(tables["balances"][["product_id", "date", "balance"]], on="product_id", how="left", validate="one_to_one")
    tx = tables["transactions"]
    tx = tx.loc[tx.product_id.isin(balances.product_id)].copy()
    tx = tx.merge(balances[["product_id", "date"]].rename(columns={"date": "snapshot_date"}), on="product_id", validate="many_to_one")
    tx = tx.loc[tx.date.lt(tx.snapshot_date.dt.normalize() + pd.Timedelta(days=1))]
    tx["unsafe"] = (~tx.status.eq("booked") | ~tx.exchange_rate.eq(1) | tx.is_extreme_amount
                    | tx.is_relative_outlier | tx.is_sync_duplicate)
    first = tx.groupby("product_id").date.min()
    bank_flow = tx.loc[tx.status.eq("booked") & ~tx.is_sync_duplicate]
    frames = []
    for month in config.months:
        end = month + pd.offsets.MonthBegin(1)
        a = balances.copy()
        after = bank_flow.loc[bank_flow.date.ge(end)].groupby("product_id").amount.sum()
        unsafe = tx.loc[tx.date.ge(end)].groupby("product_id").unsafe.any()
        a["observed_from"] = first.reindex(a.product_id).to_numpy()
        a["reconstructed_balance"] = a.balance - a.product_id.map(after).fillna(0)
        a["account_seen_asof"] = a.created_at.lt(end) | a.observed_from.lt(end)
        a["is_reconstruction_unreliable"] = (a.product_id.map(unsafe).fillna(False).astype(bool)
                                              | a.date.isna() | a.balance.isna()
                                              | a.date.lt(end - pd.Timedelta(days=1))
                                              | a.observed_from.isna() | a.observed_from.ge(end))
        a["month"] = month
        a["snapshot_date"] = a.date
        a["reconstructed_balance"] = a.reconstructed_balance.where(~a.is_reconstruction_unreliable)
        frames.append(a[["company_id", "product_id", "currency", "month", "snapshot_date", "account_seen_asof",
                         "reconstructed_balance", "is_reconstruction_unreliable"]])
    return pd.concat(frames, ignore_index=True)


def liquidity_summary(accounts, panel):
    keys = ["company_id", "currency", "month"]
    seen = accounts.loc[accounts.account_seen_asof]
    grouped = seen.groupby(keys)
    summary = grouped.agg(checking_accounts=("product_id", "size"),
                           reliable_accounts=("reconstructed_balance", "count"),
                           reconstructed_cash=("reconstructed_balance", "sum"))
    summary["reconstruction_coverage"] = divide(summary.reliable_accounts, summary.checking_accounts)
    summary["reconstructed_cash"] = summary.reconstructed_cash.where(summary.reconstruction_coverage.eq(1))
    p = panel[keys + ["tx_outflow_ma3", "inv_ap_due_30_amount", "inv_ap_open_due_coverage"]].merge(
        summary.reset_index(), on=keys, how="left", validate="one_to_one")
    p["cash_runway_months_retrospective"] = divide(p.reconstructed_cash, p.tx_outflow_ma3)
    p["cash_to_ap_due_30_retrospective"] = divide(p.reconstructed_cash, p.inv_ap_due_30_amount).where(p.inv_ap_open_due_coverage.eq(1))
    return p


def debt_snapshot(tables, config):
    debt = tables["debt_products"].copy()
    debt["snapshot_date"] = pd.Timestamp(config.extraction_date)
    debt["debt_outstanding"] = -pd.to_numeric(debt.outstanding)
    debt["debt_granted"] = -pd.to_numeric(debt.granted)
    debt["debt_utilization"] = divide(debt.debt_outstanding, debt.debt_granted)
    debt["has_unexpected_sign"] = debt.debt_outstanding.lt(0) | debt.debt_granted.lt(0)
    return debt[["company_id", "product_id", "currency", "type", "snapshot_date", "debt_outstanding",
                 "debt_granted", "liquidity", "debt_utilization", "has_unexpected_sign"]]
