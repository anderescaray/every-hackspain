import pandas as pd

from xray.features.temporal import divide
from xray.fx import REPORTING_CURRENCY
from xray.ledger.classify import FIXED, QUALITY_FLAGS, classify_transactions

FLAGS = list(QUALITY_FLAGS)
AMOUNTS = ["tx_cash_inflow", "tx_cash_outflow", "tx_inflow", "tx_outflow", "tx_fixed_cost",
           "tx_fees_paid", "debt_principal_paid", "debt_interest_paid", "tx_uncategorized_amount",
           "tx_internal_amount", "tx_intragroup_amount", "tx_ai_categorized_amount", "tx_ai_nonoperating_amount"]
# D33: columnas bancarias que dependen de tener el mes completo; se anulan en el primer mes parcial.
PARTIAL_MONTH_COLUMNS = AMOUNTS + ["tx_counterparty_hhi", "tx_counterparty_known_share",
                                   "tx_operating_amount_share", "tx_lfl_inflow_growth"]


def prepare_transactions(tables, config):
    # Compatibility projection only: no independent economic category map.
    t = classify_transactions(tables["transactions"], as_of=config.stop - pd.Timedelta(days=1),
        ai_categories_path=config.ai_categories_path, ai_min_confidence=config.ai_min_confidence)
    t["group_id"] = t.company_id.map(tables["companies"].set_index("company_id").group_id)
    eligible = t.eligible
    t["usable"] = eligible
    t["tx_cash_inflow"] = t.amount.clip(lower=0).where(eligible, 0.)
    t["tx_cash_outflow"] = (-t.amount).clip(lower=0).where(eligible, 0.)
    t["tx_inflow"] = t.amount.clip(lower=0).where(t.included_in_operating_inflows, 0.)
    t["tx_outflow"] = (-t.amount).clip(lower=0).where(t.included_in_operating_outflows, 0.)
    t["tx_fixed_cost"] = t.tx_outflow.where(t.economic_subclass.isin(FIXED), 0.)
    t["tx_fees_paid"] = (-t.amount).clip(lower=0).where(
        eligible & t.economic_subclass.isin(["financial_fee", "payment_processing_fee"]), 0.)
    for name, subclass in (("debt_principal_paid", "debt_principal"), ("debt_interest_paid", "debt_interest")):
        t[name] = (-t.amount).clip(lower=0).where(t.included_in_debt_service & t.economic_subclass.eq(subclass), 0.)
    for name, cls in (("tx_uncategorized_amount", "uncertain"),
                      ("tx_internal_amount", "own_account_circulation"),
                      ("tx_intragroup_amount", "group_or_internal")):
        t[name] = t.amount.abs().where(eligible & t.economic_class.eq(cls), 0.)
    # Diagnostic compatibility columns; shared ledger enrichment preserves D31.
    t["tx_ai_categorized_amount"] = t.amount.abs().where(eligible & t.category_source.eq("ai"), 0.)
    t["tx_ai_nonoperating_amount"] = t.amount.abs().where(eligible & t.category.eq("ai_nonoperating"), 0.)
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
    """`companies` con su moneda declarada; el panel sale en moneda de reporte (D32)."""
    grid = (companies[["company_id"]].assign(currency=REPORTING_CURRENCY)
            .merge(pd.DataFrame({"month": months}), how="cross"))
    keys = ["company_id", "month"]
    data = t.copy()
    declared = data.company_id.map(companies.set_index("company_id").currency)
    data["primary_currency_row"] = data.source_currency.eq(declared)
    data["unknown_currency_row"] = data.source_currency.isna()
    agg = data.groupby(keys).agg(tx_all_currency_count=("amount", "size"),
                                 tx_primary_currency_count=("primary_currency_row", "sum"),
                                 tx_unknown_currency_count=("unknown_currency_row", "sum"))
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
