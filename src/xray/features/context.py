import numpy as np
import pandas as pd

from xray.features.temporal import divide
from xray.fx import REPORTING_CURRENCY, to_eur


def reconstruct_liquidity(tables, config):
    bank = tables["banking_products"]
    accounts = bank.loc[bank.type.eq("checking"), ["product_id", "company_id", "currency", "created_at"]]
    snap = tables["balances"].reindex(columns=["product_id", "date", "balance", "is_sentinel_balance"])
    snap["is_sentinel_balance"] = snap.is_sentinel_balance.fillna(False).astype(bool)
    balances = accounts.merge(snap, on="product_id", how="left", validate="one_to_one")
    balances["is_sentinel_balance"] = balances.is_sentinel_balance.fillna(False).astype(bool)
    # D32: saldo y movimientos en EUR con el mismo tipo fijo, así la identidad hacia atrás se mantiene.
    balances["balance"] = to_eur(balances.balance.astype(float), balances.currency)
    balances["currency"] = REPORTING_CURRENCY
    tx = tables["transactions"]
    tx = tx.loc[tx.product_id.isin(balances.product_id)].copy()
    tx["amount"] = to_eur(tx.amount.astype(float), tx.product_currency)
    tx = tx.merge(balances[["product_id", "date"]].rename(columns={"date": "snapshot_date"}), on="product_id", validate="many_to_one")
    tx = tx.loc[tx.date.lt(tx.snapshot_date.dt.normalize() + pd.Timedelta(days=1))]
    technical = tx.is_technical_placeholder if "is_technical_placeholder" in tx else pd.Series(False, index=tx.index)
    # D38: un ajuste técnico posterior al cierre invalida la caja reconstruida de ese cierre (no se borra).
    tx["unsafe"] = ~tx.status.eq("booked") | tx.amount.isna() | tx.is_sync_duplicate | technical.fillna(False)
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
                                              | a.is_sentinel_balance | a.date.isna() | a.balance.isna()
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


# D36: solo en productos rotativos el uso (dispuesto / concedido) indica tensión; en préstamos,
# leasing, hipotecas o avales es amortización pendiente.
REVOLVING_DEBT = frozenset({"lineofcredit", "confirming", "factoring"})


# D38/B3: foto de liquidez disponible a extracción, por empresa (contexto; no es predictor histórico).
CASH_ACCOUNT_TYPES = frozenset({"checking", "saving", "wallet", "tpv", "expensesPlatform"})


def liquidity_snapshot(tables, config):
    """Caja en cuentas + inversión + disponible de pólizas, en EUR, sin saldos centinela (D38).

    Las tarjetas no cuentan (su saldo es deuda de tarjeta). El disponible de póliza sale de
    `balances.liquidity` y, si falta, de `debt_products.liquidity`; solo cuenta si es positivo.
    """
    bank = tables["banking_products"][["product_id", "company_id", "type", "currency"]]
    debt = tables["debt_products"][["product_id", "company_id", "type", "currency", "liquidity"]]
    snap = tables["balances"].reindex(columns=["product_id", "balance", "liquidity", "is_sentinel_balance"])
    snap["is_sentinel_balance"] = snap.is_sentinel_balance.fillna(False).astype(bool)
    accounts = bank.merge(snap, on="product_id", how="inner", validate="one_to_one")
    accounts["eur"] = to_eur(pd.to_numeric(accounts.balance), accounts.currency)
    usable = ~accounts.is_sentinel_balance
    cash = accounts.loc[usable & accounts.type.isin(CASH_ACCOUNT_TYPES)].groupby("company_id").eur.sum(min_count=1)
    invest = accounts.loc[usable & accounts.type.eq("investment")].groupby("company_id").eur.sum(min_count=1)
    lines = debt.loc[debt.type.eq("lineofcredit")].merge(snap[["product_id", "liquidity"]].rename(columns={"liquidity": "snap_liq"}),
                                                        on="product_id", how="left")
    lines["available"] = to_eur(pd.to_numeric(lines.snap_liq).fillna(pd.to_numeric(lines.liquidity)), lines.currency).clip(lower=0)
    credit = lines.groupby("company_id").available.sum(min_count=1)
    out = tables["companies"][["company_id"]].copy()
    out["currency"] = REPORTING_CURRENCY
    out["snapshot_date"] = pd.Timestamp(config.extraction_date)
    out["cash_accounts_eur"] = out.company_id.map(cash)
    out["investment_eur"] = out.company_id.map(invest)
    out["credit_line_available_eur"] = out.company_id.map(credit)
    parts = out[["cash_accounts_eur", "investment_eur", "credit_line_available_eur"]]
    out["total_available_eur"] = parts.sum(axis=1, min_count=1)
    out["sentinel_balances_excluded"] = out.company_id.map(accounts.loc[~usable].groupby("company_id").size()).fillna(0).astype(int)
    return out


def debt_snapshot(tables, config):
    """Foto de deuda a extracción (contexto de producto, nunca predictor histórico; D21/D36).

    Fuente principal `balances` (fechada, misma foto que los saldos de cuentas); `debt_products` solo
    cuando falta. Las dos coinciden en ~71% de productos y difieren poco en el resto (desfase de fecha).
    """
    debt = tables["debt_products"].copy()
    snap = (tables["balances"].reindex(columns=["product_id", "balance", "granted", "liquidity"])
            .rename(columns={"balance": "snap_outstanding", "granted": "snap_granted", "liquidity": "snap_liquidity"}))
    debt = debt.merge(snap, on="product_id", how="left", validate="one_to_one")
    debt["snapshot_date"] = pd.Timestamp(config.extraction_date)
    debt["source_currency"] = debt.currency
    outstanding = pd.to_numeric(debt.snap_outstanding).fillna(pd.to_numeric(debt.outstanding))
    granted = pd.to_numeric(debt.snap_granted).fillna(pd.to_numeric(debt.granted))
    liquidity = pd.to_numeric(debt.snap_liquidity).fillna(pd.to_numeric(debt.liquidity))
    debt["outstanding_source"] = np.select([debt.snap_outstanding.notna(), debt.outstanding.notna()],
                                           ["balances", "debt_products"], default="missing")
    debt["debt_outstanding"] = -to_eur(outstanding, debt.source_currency)
    debt["debt_granted"] = -to_eur(granted, debt.source_currency)
    debt["liquidity"] = to_eur(liquidity, debt.source_currency)
    debt["currency"] = REPORTING_CURRENCY
    debt["is_revolving"] = debt.type.isin(REVOLVING_DEBT)
    debt["debt_utilization"] = divide(debt.debt_outstanding, debt.debt_granted).where(debt.is_revolving)
    debt["has_unexpected_sign"] = debt.debt_outstanding.lt(0) | debt.debt_granted.lt(0)
    return debt[["company_id", "product_id", "currency", "source_currency", "type", "is_revolving", "snapshot_date",
                 "outstanding_source", "debt_outstanding", "debt_granted", "liquidity", "debt_utilization",
                 "has_unexpected_sign"]]
