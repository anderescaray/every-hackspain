import pandas as pd

from xray.features.temporal import divide


INFLOW = {"collection", "bulk_collection", "pos_settlement", "cash_settlement", "cash_settlements",
          "payment_refund", "tax_refund"}
OUTFLOW = {"payment", "bulk_payment", "utility", "salary", "social_security", "tax", "collection_refund"}
FIXED = {"salary", "social_security", "tax", "utility"}
FLAGS = ["is_extreme_amount", "is_relative_outlier", "is_sync_duplicate", "is_unknown_product"]
AMOUNTS = ["tx_cash_inflow", "tx_cash_outflow", "tx_inflow", "tx_outflow", "tx_fixed_cost",
           "tx_fees_paid", "debt_principal_paid", "debt_interest_paid", "tx_uncategorized_amount",
           "tx_internal_amount", "tx_intragroup_amount"]


def prepare_transactions(tables, config):
    t = tables["transactions"].copy()
    t["amount"] = t.amount.astype(float)
    t = t.loc[t.date.lt(config.stop)].rename(columns={"product_currency": "currency"})
    t["group_id"] = t.company_id.map(tables["companies"].set_index("company_id").group_id)
    t["month"] = t.date.dt.to_period("M").dt.to_timestamp()
    eligible = t.status.eq("booked") & t.exchange_rate.eq(1) & ~t[FLAGS].any(axis=1)
    operating = eligible & ~t.is_internal_transfer & ~t.is_intragroup
    t["usable"] = eligible
    t["tx_cash_inflow"] = t.amount.clip(lower=0).where(eligible, 0.)
    t["tx_cash_outflow"] = (-t.amount).clip(lower=0).where(eligible, 0.)
    t["tx_inflow"] = t.amount.clip(lower=0).where(operating & t.category.isin(INFLOW), 0.)
    t["tx_outflow"] = (-t.amount).clip(lower=0).where(operating & t.category.isin(OUTFLOW), 0.)
    for name, categories in (("tx_fixed_cost", FIXED), ("tx_fees_paid", {"fee"}),
                             ("debt_principal_paid", {"debt_repayment"}), ("debt_interest_paid", {"interest_charge"})):
        scope = eligible & ~t.is_intragroup if name.startswith("debt_") else operating
        t[name] = (-t.amount).clip(lower=0).where(scope & t.category.isin(categories), 0.)
    for name, mask in (("tx_uncategorized_amount", t.category.eq("uncategorized")),
                       ("tx_internal_amount", t.is_internal_transfer), ("tx_intragroup_amount", t.is_intragroup)):
        t[name] = t.amount.abs().where(eligible & mask, 0.)
    tokens = t.description.fillna("").str.findall(r"\bCOUNTERPARTY_\d+\b")
    extracted = tokens.str[0].where(tokens.str.len().eq(1))
    t["counterparty"] = t.counterparty_id.fillna(extracted)
    t["counterparty"] = t.company_id.astype("string") + ":" + t.counterparty.astype("string")
    products = pd.concat([tables["banking_products"], tables["debt_products"]], ignore_index=True)
    connected = pd.to_datetime(products.set_index("product_id").created_at)
    t["connected_at"] = connected.reindex(t.product_id).to_numpy()
    t["predates_connection"] = t.date.lt(t.connected_at)
    return t


def transaction_features(t, skeleton, unit):
    keys = [unit, "currency", "month"]
    grouped = t.groupby(keys, observed=True)
    q = grouped.agg(tx_count=("amount", "size"), tx_usable_count=("usable", "sum"),
                    tx_reporting_companies=("company_id", "nunique"),
                    tx_preconnection_row_share=("predates_connection", "mean"))
    amounts = grouped[AMOUNTS].sum().where(q.tx_usable_count.gt(0), axis=0)
    q = q.join(amounts)
    active = t.loc[t.usable].groupby(keys).product_id.nunique().rename("tx_active_accounts")
    q = q.join(active)
    q["tx_usable_companies"] = t.loc[t.usable].groupby(keys).company_id.nunique()
    cp = t.loc[t.tx_inflow.gt(0) & t.counterparty.notna()].groupby(keys + ["counterparty"]).tx_inflow.sum()
    known = cp.groupby(level=[0, 1, 2]).sum()
    shares = cp / cp.groupby(level=[0, 1, 2]).transform("sum")
    q["tx_counterparty_hhi"] = shares.pow(2).groupby(level=[0, 1, 2]).sum()
    q["tx_counterparty_known_share"] = divide(known.reindex(q.index), q.tx_inflow)
    q["tx_operating_amount_share"] = divide(q.tx_inflow + q.tx_outflow, q.tx_cash_inflow + q.tx_cash_outflow)
    q["tx_usable_row_share"] = divide(q.tx_usable_count, q.tx_count)
    account = t.loc[t.usable].groupby(keys + ["product_id"]).tx_inflow.sum().reset_index()
    previous = account.rename(columns={"tx_inflow": "previous_inflow"})
    previous["month"] = previous.month + pd.offsets.MonthBegin(1)
    matched = account.merge(previous, on=keys + ["product_id"], how="inner")
    matched = matched.groupby(keys)[["tx_inflow", "previous_inflow"]].sum()
    q["tx_lfl_inflow_growth"] = divide(matched.tx_inflow - matched.previous_inflow, matched.previous_inflow)
    first = t.loc[t.usable].groupby([unit, "currency", "product_id"]).month.min().reset_index()
    new = first.groupby(keys).size().rename("tx_new_accounts")
    q = q.join(new)
    p = skeleton.merge(q.reset_index(), on=keys, how="left", validate="one_to_one")
    counts = ["tx_count", "tx_usable_count", "tx_reporting_companies", "tx_usable_companies", "tx_active_accounts", "tx_new_accounts"]
    p[counts] = p[counts].fillna(0).astype(int)
    first_company = t.groupby([unit, "currency", "company_id"] if unit != "company_id" else ["company_id", "currency"]).month.min().reset_index()
    expected = []
    for month in sorted(p.month.unique()):
        seen = first_company.loc[first_company.month <= month].groupby([unit, "currency"]).size()
        current = p.loc[p.month == month, [unit, "currency"]]
        expected.append(pd.Series(seen.reindex(pd.MultiIndex.from_frame(current)).fillna(0).to_numpy(), index=current.index))
    p["tx_expected_companies"] = pd.concat(expected).reindex(p.index).astype(int)
    p["tx_company_coverage"] = divide(p.tx_usable_companies, p.tx_expected_companies)
    return p


def coverage_by_company(t, companies, months):
    grid = companies[["company_id", "currency"]].merge(pd.DataFrame({"month": months}), how="cross")
    keys = ["company_id", "month"]
    data = t.copy()
    primary = data.company_id.map(companies.set_index("company_id").currency)
    data["primary_currency_row"] = data.currency.eq(primary)
    data["unknown_currency_row"] = data.currency.isna()
    data["ambiguous_fx_row"] = ~data.exchange_rate.eq(1)
    agg = data.groupby(keys).agg(tx_all_currency_count=("amount", "size"),
                                 tx_primary_currency_count=("primary_currency_row", "sum"),
                                 tx_unknown_currency_count=("unknown_currency_row", "sum"),
                                 tx_ambiguous_fx_count=("ambiguous_fx_row", "sum"))
    p = grid.merge(agg.reset_index(), on=keys, how="left")
    columns = list(agg.columns)
    p[columns] = p[columns].fillna(0).astype(int)
    p["tx_primary_currency_row_share"] = divide(p.tx_primary_currency_count, p.tx_all_currency_count)
    return p


def stress_events(t, companies, months):
    p = companies[["company_id", "group_id"]].merge(pd.DataFrame({"month": months}), how="cross")
    subset = t.loc[t.status.eq("booked") & ~t.is_sync_duplicate].copy()
    text = subset.description.fillna("").str.upper()
    patterns = {"embargo": r"\bEMBARG\w*", "unpaid": r"\bIMPAGAD\w*",
                "deferral": r"\bAPLAZAMIENTO\b", "overdraft": r"\b(?:DESCUBIERTO|EXCEDIDO)\b",
                "late_interest": r"\bDEMORA\b"}
    cols = []
    for name, pattern in patterns.items():
        col = f"stress_{name}_count"
        subset[col] = text.str.contains(pattern, regex=True).astype(int)
        cols.append(col)
    agg = subset.groupby(["company_id", "month"])[cols].sum().reset_index()
    p = p.merge(agg, on=["company_id", "month"], how="left")
    return p
