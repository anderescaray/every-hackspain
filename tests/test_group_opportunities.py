"""D47 · Oportunidades de tesorería intragrupo: pooling, netting y crédito sin usar."""
import pandas as pd

from xray.product.group_opportunities import (netting_opportunities, opportunities_report, overdraft_coincidence,
                                              pooling_opportunities, unused_credit_opportunities)

MONTH = pd.Timestamp("2026-08-01")
COMPANIES = pd.DataFrame({"company_id": ["A", "B", "C"], "group_id": ["G1", "G1", "G2"]})


def liquidity(rows, coverage=1.0):
    return pd.DataFrame([{"company_id": c, "month": MONTH, "reconstructed_cash": v,
                          "reconstruction_coverage": coverage} for c, v in rows.items()])


def tx(rows):
    return pd.DataFrame([{"company_id": c, "date": pd.Timestamp(d), "status": "booked", "amount": a,
                          "amount_eur": a, "is_intragroup": ig, "event_type": ev}
                         for c, d, a, ig, ev in rows])


def test_pooling_only_counts_siblings_of_the_same_group():
    liq = liquidity({"A": -5000.0, "B": 20000.0, "C": 50000.0})
    out = pooling_opportunities(liq, COMPANIES)
    assert out.company_id.tolist() == ["A"]                        # solo A está en negativo
    assert out.sibling_cash.iloc[0] == 20000.0                     # la caja de C (otro grupo) no cuenta
    assert bool(out.coverable.iloc[0]) and out.covered_amount.iloc[0] == 5000.0


def test_pooling_ignores_cash_that_is_not_reliable():
    out = pooling_opportunities(liquidity({"A": -5000.0, "B": 20000.0}, coverage=0.5), COMPANIES)
    assert out.empty                                                # sin reconstrucción completa no se afirma nada


def test_overdraft_is_measured_apart_from_month_end_balance():
    # Descubierto en un mes que acaba en positivo: el bloque de caja negativa no lo vería.
    t = tx([("A", "2026-08-12", -120.0, False, "descubierto")])
    liq = liquidity({"A": 1000.0, "B": 8000.0})
    out = overdraft_coincidence(t, liq, COMPANIES)
    assert len(out) == 1 and out.sibling_cash.iloc[0] == 9000.0 and out.cost.iloc[0] == 120.0
    assert pooling_opportunities(liq, COMPANIES).empty


def test_netting_compensates_positions_and_ignores_external_flows():
    t = tx([("A", "2026-08-05", -1000.0, True, None), ("B", "2026-08-05", 1000.0, True, None),
            ("A", "2026-08-06", 600.0, True, None), ("B", "2026-08-06", -600.0, True, None),
            ("A", "2026-08-07", -5000.0, False, None)])          # pago externo: fuera
    out = netting_opportunities(t, COMPANIES)
    assert out.movements.iloc[0] == 4 and out.gross_amount.iloc[0] == 3200.0
    assert out.net_amount.iloc[0] == 400.0                        # solo queda la posición neta de B
    assert round(float(out.reduction_share.iloc[0]), 3) == 0.875


def test_unused_credit_compares_against_siblings_not_own_line():
    debt = pd.DataFrame({"company_id": ["A", "B"], "type": ["lineofcredit"] * 2, "is_revolving": [True, True],
                         "liquidity": [1000.0, 50000.0]})
    out = unused_credit_opportunities(debt, liquidity({"A": -8000.0, "B": 5000.0}), COMPANIES)
    assert out.company_id.tolist() == ["A"]
    assert out.own_available_credit.iloc[0] == 1000.0 and out.sibling_available_credit.iloc[0] == 50000.0
    assert bool(out.covered_by_sibling_credit.iloc[0])


def test_report_carries_limits_and_headline_numbers():
    liq = liquidity({"A": -5000.0, "B": 20000.0})
    r = opportunities_report(pooling_opportunities(liq, COMPANIES), netting_opportunities(tx([]), COMPANIES),
                             unused_credit_opportunities(pd.DataFrame(columns=["company_id", "is_revolving", "liquidity"]), liq, COMPANIES))
    assert r["cash_pooling"]["coverable_by_sibling_cash"] == 1
    assert any("no instrucciones ejecutables" in c for c in r["caveats"])
