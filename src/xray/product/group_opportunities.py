"""Oportunidades de tesorería dentro del grupo: hechos medidos, no escenarios (decisiones D47).

A diferencia del advisor (`xray.group_advisor`), aquí **no se simula el score**: se cuenta lo que ya pasó y
cuánto habría cambiado con prácticas de tesorería corporativa estándar. Todo es comprobable en los datos:

- **Cash pooling** (barrido de saldos): una filial en negativo mientras otra del mismo grupo tenía caja ese
  mismo mes. Es para lo que existe el *zero balancing*: que ninguna filial pague descubierto teniendo el
  grupo el dinero al lado. Se publica también la coincidencia con descubiertos observados (`event_type`) y
  su coste bancario real.
- **Netting intragrupo**: volumen bruto de transferencias entre filiales frente al neto que quedaría tras
  compensar posiciones. La diferencia es transferencia que sobra: comisiones, divisa y trabajo administrativo.
- **Crédito del grupo sin usar**: disponible en productos rotativos de unas filiales mientras otra está en
  negativo. El descubierto es el crédito más caro que existe; el crédito del grupo ya contratado suele ser
  una alternativa a revisar.

Límites que se publican con los números: la caja es **reconstruida** (solo cuentas corrientes con historia
fiable, D38/D46) y es retrospectiva; el disponible de póliza es la **foto a extracción** (D36), no una serie;
y el barrido real depende de fiscalidad, precio del préstamo intragrupo y restricciones legales que no están
en los datos. Son oportunidades a revisar, no instrucciones.
"""
import numpy as np
import pandas as pd

OVERDRAFT_EVENT = "descubierto"


def _month(values):
    return pd.to_datetime(values).dt.to_period("M").dt.to_timestamp()


def _group_cash(liquidity, companies):
    cash = liquidity.loc[liquidity.reconstruction_coverage.eq(1) & liquidity.reconstructed_cash.notna(),
                         ["company_id", "month", "reconstructed_cash"]]
    return cash.merge(companies[["company_id", "group_id"]], on="company_id", how="inner")


def pooling_opportunities(liquidity, companies, transactions=None):
    """Meses en que una filial estuvo en negativo teniendo el grupo caja en otra."""
    cash = _group_cash(liquidity, companies)
    observed = (cash.groupby(["group_id", "month"]).company_id.nunique()
                .rename("reliable_group_companies"))
    positive = (cash.loc[cash.reconstructed_cash.gt(0)].groupby(["group_id", "month"]).reconstructed_cash.sum()
                .rename("sibling_cash"))
    negative = (cash.loc[cash.reconstructed_cash.lt(0)]
                .merge(observed, on=["group_id", "month"], how="left")
                .merge(positive, on=["group_id", "month"], how="left"))
    negative["reliable_siblings"] = negative.reliable_group_companies.sub(1).clip(lower=0).astype(int)
    negative["sibling_cash_observed"] = negative.reliable_siblings.gt(0)
    negative["sibling_cash"] = negative.sibling_cash.fillna(0.0)
    negative["deficit"] = -negative.reconstructed_cash
    negative["coverable"] = negative.sibling_cash.ge(negative.deficit).astype("boolean")
    negative.loc[~negative.sibling_cash_observed, "coverable"] = pd.NA
    negative["covered_amount"] = np.minimum(negative.deficit, negative.sibling_cash).where(negative.sibling_cash_observed)
    negative["overdraft_observed"] = False
    if transactions is not None and "event_type" in transactions:
        od = transactions.loc[transactions.event_type.eq(OVERDRAFT_EVENT), ["company_id", "date"]].copy()
        od["month"] = _month(od.date)
        keys = set(zip(od.company_id, od.month))
        negative["overdraft_observed"] = [(c, m) in keys for c, m in zip(negative.company_id, negative.month)]
    columns = ["group_id", "company_id", "month", "reconstructed_cash", "deficit", "reliable_siblings",
               "sibling_cash_observed", "sibling_cash", "coverable", "covered_amount", "overdraft_observed"]
    return negative[columns].sort_values(["group_id", "month", "deficit"], ascending=[True, True, False]).reset_index(drop=True)


def overdraft_coincidence(transactions, liquidity, companies):
    """Meses con descubierto observado y cuánta caja tenían las hermanas ese mismo mes.

    Se mide aparte del bloque de caja negativa: un descubierto puede durar unos días y no dejar el saldo de
    fin de mes en negativo, así que mirar solo los cierres negativos lo infravalora.
    """
    od = transactions.loc[transactions.event_type.eq(OVERDRAFT_EVENT), ["company_id", "date"]].copy()
    if od.empty:
        return pd.DataFrame(columns=["group_id", "company_id", "month", "sibling_cash", "cost"])
    od["month"] = _month(od.date)
    cost = transactions.loc[transactions.event_type.eq(OVERDRAFT_EVENT)].copy()
    cost["month"] = _month(cost.date)
    cost["eur"] = pd.to_numeric(cost.get("amount_eur"), errors="coerce")
    per_month = cost.loc[cost.eur.lt(0)].groupby(["company_id", "month"]).eur.sum().mul(-1).rename("cost")
    cash = _group_cash(liquidity, companies)
    observed = (cash.groupby(["group_id", "month"]).company_id.nunique()
                .rename("reliable_group_companies"))
    own_observed = cash.set_index(["group_id", "company_id", "month"]).reconstructed_cash.notna().rename("own_cash_observed")
    positive = cash.loc[cash.reconstructed_cash.gt(0), ["group_id", "company_id", "month", "reconstructed_cash"]]
    group_positive = positive.groupby(["group_id", "month"]).reconstructed_cash.sum().rename("group_positive_cash")
    own_positive = positive.set_index(["group_id", "company_id", "month"]).reconstructed_cash.rename("own_positive_cash")
    out = (od[["company_id", "month"]].drop_duplicates()
           .merge(companies[["company_id", "group_id"]], on="company_id", how="left")
           .merge(observed, on=["group_id", "month"], how="left")
           .merge(own_observed, on=["group_id", "company_id", "month"], how="left")
           .merge(group_positive, on=["group_id", "month"], how="left")
           .merge(own_positive, on=["group_id", "company_id", "month"], how="left")
           .merge(per_month, on=["company_id", "month"], how="left"))
    out["reliable_siblings"] = (out.reliable_group_companies.fillna(0)
                                - out.own_cash_observed.fillna(False).astype(int)).clip(lower=0).astype(int)
    out["sibling_cash_observed"] = out.reliable_siblings.gt(0)
    out["sibling_cash"] = out.group_positive_cash.fillna(0.0) - out.own_positive_cash.fillna(0.0)
    out = out.drop(columns=["reliable_group_companies", "own_cash_observed", "group_positive_cash", "own_positive_cash"])
    return out.sort_values(["group_id", "month"]).reset_index(drop=True)


def netting_opportunities(transactions, companies, amount_column="amount_eur"):
    """Volumen intragrupo bruto frente al neto tras compensar posiciones, por grupo y mes."""
    if transactions.empty or "is_intragroup" not in transactions:
        return pd.DataFrame(columns=["group_id", "month", "ledger_entries", "movements", "gross_amount",
                                     "net_amount", "reduction_share"])
    t = transactions.loc[transactions.is_intragroup.fillna(False).astype(bool) & transactions.status.eq("booked")].copy()
    if t.empty:
        return pd.DataFrame(columns=["group_id", "month", "ledger_entries", "movements", "gross_amount",
                                     "net_amount", "reduction_share"])
    t["month"] = _month(t.date)
    t["amount"] = pd.to_numeric(t[amount_column], errors="coerce")
    t = t.merge(companies[["company_id", "group_id"]], on="company_id", how="inner").dropna(subset=["amount"])
    # D05 marca las dos patas espejo. El volumen transferido se cuenta una vez, por la pata pagadora;
    # sumar |amount| de ambas duplica tanto el número de transferencias como el bruto.
    per = (t.groupby(["group_id", "month"]).amount
           .agg(ledger_entries="size", movements=lambda s: int(s.lt(0).sum()),
                gross_amount=lambda s: float(-s.loc[s.lt(0)].sum())))
    positions = t.groupby(["group_id", "month", "company_id"]).amount.sum()
    net = positions.clip(lower=0).groupby(level=[0, 1]).sum().rename("net_amount")
    out = per.join(net).reset_index()
    out["reduction_share"] = np.where(out.gross_amount > 0, 1 - out.net_amount / out.gross_amount, np.nan)
    return out.sort_values(["group_id", "month"]).reset_index(drop=True)


def unused_credit_opportunities(debt_snapshot, liquidity, companies, month=None):
    """Filiales en negativo mientras otras tienen crédito rotativo disponible (foto a extracción)."""
    revolving = debt_snapshot.loc[debt_snapshot.get("is_revolving", pd.Series(False, index=debt_snapshot.index)).fillna(False)]
    available = (revolving.assign(available=pd.to_numeric(revolving.liquidity, errors="coerce").clip(lower=0))
                 .groupby("company_id").available.sum().rename("available_credit").reset_index())
    available = available.merge(companies[["company_id", "group_id"]], on="company_id", how="inner")
    by_group = available.groupby("group_id").available_credit.sum().rename("group_available_credit")
    cash = _group_cash(liquidity, companies)
    month = pd.Timestamp(month) if month is not None else cash.month.max()
    short = cash.loc[cash.month.eq(month) & cash.reconstructed_cash.lt(0)].copy()
    short["own_available_credit"] = short.company_id.map(available.set_index("company_id").available_credit).fillna(0.0)
    short["group_available_credit"] = short.group_id.map(by_group).fillna(0.0)
    short["sibling_available_credit"] = (short.group_available_credit - short.own_available_credit).clip(lower=0)
    short["covered_by_sibling_credit"] = short.sibling_available_credit.ge(-short.reconstructed_cash)
    columns = ["group_id", "company_id", "month", "reconstructed_cash", "own_available_credit",
               "sibling_available_credit", "covered_by_sibling_credit"]
    return short[columns].sort_values("reconstructed_cash").reset_index(drop=True)


def opportunities_report(pooling, netting, credit, overdrafts=None, overdraft_cost=None):
    def money(x):
        return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), 2)

    od = overdrafts if overdrafts is not None else pooling.loc[pooling.overdraft_observed] if len(pooling) else pooling
    pool_observed = pooling.loc[pooling.sibling_cash_observed] if len(pooling) and "sibling_cash_observed" in pooling else pooling
    od_observed = od.loc[od.sibling_cash_observed] if len(od) and "sibling_cash_observed" in od else od
    return {
        "method": "group_opportunities_v1 (D47)",
        "cash_pooling": {
            "negative_company_months": int(len(pooling)),
            "companies": int(pooling.company_id.nunique()) if len(pooling) else 0,
            "groups": int(pooling.group_id.nunique()) if len(pooling) else 0,
            "assessable_company_months": int(len(pool_observed)),
            "unassessable_company_months": int(len(pooling) - len(pool_observed)),
            "coverable_by_sibling_cash": int(pool_observed.coverable.sum()) if len(pool_observed) else 0,
            "coverable_share": float(pool_observed.coverable.mean()) if len(pool_observed) else None,
            "median_deficit": money(pooling.loc[pooling.coverable, "deficit"].median()) if len(pooling) else None,
            "overdraft_months": int(len(od)),
            "overdraft_companies": int(od.company_id.nunique()) if len(od) else 0,
            "overdraft_months_assessable": int(len(od_observed)),
            "overdraft_months_unassessable": int(len(od) - len(od_observed)),
            "overdraft_months_with_sibling_cash": int(od.sibling_cash.gt(0).sum()) if len(od) else 0,
            "overdraft_share_with_sibling_cash": float(od.sibling_cash.gt(0).mean()) if len(od) else None,
            "overdraft_share_with_sibling_cash_assessable": float(od_observed.sibling_cash.gt(0).mean()) if len(od_observed) else None,
            "observed_overdraft_cost": money(overdraft_cost),
        },
        "netting": {
            "group_months": int(len(netting)),
            "groups": int(netting.group_id.nunique()) if len(netting) else 0,
            "ledger_entries": int(netting.ledger_entries.sum()) if len(netting) else 0,
            "movements": int(netting.movements.sum()) if len(netting) else 0,
            "gross_amount": money(netting.gross_amount.sum()) if len(netting) else None,
            "net_amount": money(netting.net_amount.sum()) if len(netting) else None,
            "reduction_share": float(1 - netting.net_amount.sum() / netting.gross_amount.sum()) if len(netting) and netting.gross_amount.sum() else None,
        },
        "unused_credit": {
            "companies_in_negative_cash": int(len(credit)),
            "with_sibling_credit_available": int(credit.covered_by_sibling_credit.sum()) if len(credit) else 0,
            "sibling_credit_median": money(credit.loc[credit.covered_by_sibling_credit, "sibling_available_credit"].median()) if len(credit) else None,
        },
        "caveats": ["Caja reconstruida (solo cuentas corrientes con historia fiable) y retrospectiva.",
                    "El crédito rotativo disponible es la foto a extracción, no una serie mensual.",
                    "Un barrido real depende de fiscalidad, precio del préstamo intragrupo y restricciones legales.",
                    "Son oportunidades a revisar con el cliente, no instrucciones ejecutables."],
    }


def render_markdown(r):
    p, n, c = r["cash_pooling"], r["netting"], r["unused_credit"]
    pct = lambda x: "—" if x is None else f"{100 * x:.0f}%"
    eur = lambda x: "—" if x is None else f"{x:,.0f} €".replace(",", ".")
    lines = [f"# Oportunidades de tesorería en el grupo ({r['method']})", "",
             "## Cash pooling: caja parada mientras otra filial está en negativo", "",
             "| Medida | Valor |", "|---|---|",
             f"| Meses-empresa con caja negativa | {p['negative_company_months']} ({p['companies']} empresas, {p['groups']} grupos) |",
             f"| Evaluables (≥1 hermana con caja fiable observada) | {p['assessable_company_months']} "
             f"({p['unassessable_company_months']} sin cobertura suficiente) |",
             f"| Cubribles entre los evaluables | {p['coverable_by_sibling_cash']} ({pct(p['coverable_share'])}) |",
             f"| Déficit mediano cubrible | {eur(p['median_deficit'])} |",
             f"| Meses con descubierto observado | {p['overdraft_months']} en {p['overdraft_companies']} empresas |",
             f"| Evaluables por caja de hermanas | {p['overdraft_months_assessable']} "
             f"({p['overdraft_months_unassessable']} sin cobertura suficiente) |",
             f"| Con una hermana con caja | {p['overdraft_months_with_sibling_cash']} "
             f"({pct(p['overdraft_share_with_sibling_cash'])} del total; "
             f"{pct(p['overdraft_share_with_sibling_cash_assessable'])} de los evaluables) |",
             f"| Coste bancario observado de descubiertos | {eur(p['observed_overdraft_cost'])} |", "",
             "## Netting: transferencias intragrupo que sobran", "",
             "| Medida | Valor |", "|---|---|",
             f"| Grupos con flujo intragrupo | {n['groups']} ({n['group_months']} grupo-mes) |",
             f"| Transferencias (apuntes contables) | {n['movements']:,} ({n['ledger_entries']:,})".replace(",", ".") + " |",
             f"| Volumen bruto → neto tras compensar | {eur(n['gross_amount'])} → {eur(n['net_amount'])} ({pct(n['reduction_share'])} menos) |", "",
             "## Crédito rotativo del grupo sin usar", "",
             "| Medida | Valor |", "|---|---|",
             f"| Filiales en caja negativa (último cierre) | {c['companies_in_negative_cash']} |",
             f"| Con crédito rotativo suficiente en hermanas | {c['with_sibling_credit_available']} |",
             f"| Disponible mediano de las hermanas | {eur(c['sibling_credit_median'])} |", "",
             "Límites:"] + [f"- {x}" for x in r["caveats"]]
    return "\n".join(lines) + "\n"
