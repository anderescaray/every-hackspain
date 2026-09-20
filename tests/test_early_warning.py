"""D42 · Comparación de alertas tempranas: cobertura propia, subconjunto común y alarma trivial."""
import pandas as pd

from xray.evaluation.early_warning import combine, compare_alarms, evaluate, runway_alarms, score_alarms
from xray.evaluation.lead_time import own_stress_months, stress_onsets

MONTHS = pd.date_range("2025-01-01", "2025-12-01", freq="MS")


def frames(companies):
    features = pd.DataFrame([{"company_id": c, "group_id": f"G_{c}", "month": m, "tx_count": 10, "tx_inflow": 1000.0,
                              "debt_principal_paid": 50.0, "debt_interest_paid": 0.0}
                             for c in companies for m in MONTHS])
    return features, features[["company_id", "month"]]


def tx(rows):
    return pd.DataFrame([{"company_id": c, "date": pd.Timestamp(d), "status": "booked", "event_type": e,
                          "is_sync_duplicate": False} for c, d, e in rows])


def panel(companies, z=None, runway=None):
    rows = []
    for c in companies:
        for m in MONTHS:
            rows.append({"company_id": c, "month": m, "momentum_z": (z or {}).get((c, str(m.date())[:7])),
                         "cash_runway_months_retrospective": (runway or {}).get((c, str(m.date())[:7])),
                         "reconstructed_cash": 1000.0})
    return pd.DataFrame(rows)


def test_alarm_rate_exposes_a_trivially_always_on_alarm():
    companies = ["A", "B"]
    features, observed = frames(companies)
    t = tx([("A", "2025-09-15", "cuota_impagada")])
    events = own_stress_months(t)
    onsets = stress_onsets(events, observed)
    always = runway_alarms(panel(companies, runway={(c, str(m.date())[:7]): 0.1 for c in companies for m in MONTHS}), 1.0)
    r, _ = evaluate(onsets, always, events, observed)
    assert r["recall"] == 1.0 and r["alarm_rate"] == 1.0          # detecta todo, pero está siempre encendida


def test_signal_only_counts_where_it_exists():
    companies = ["A"]
    features, observed = frames(companies)
    t = tx([("A", "2025-09-15", "descubierto")])
    events = own_stress_months(t)
    onsets = stress_onsets(events, observed)
    sin_caja = runway_alarms(panel(companies), 1.0)               # runway todo NaN
    r, leads = evaluate(onsets, sin_caja, events, observed)
    assert r["evaluable_onsets"] == 0 and not leads.evaluable.any()   # censurado, no "fallo" de la alerta


def test_combination_only_lives_where_both_signals_exist():
    companies = ["A"]
    keys = [(c, str(m.date())[:7]) for c in companies for m in MONTHS]
    z = {k: (-2.0 if k[1] == "2025-06" else 0.0) for k in keys}          # score disponible todos los meses
    runway = {k: (0.2 if k[1] in ("2025-06", "2025-07") else 5.0) for k in keys}
    p = panel(companies, z=z, runway=runway)
    a, b = score_alarms(p, 1.5), runway_alarms(p, 1.0)
    assert a.alarm.sum() == 1 and b.alarm.sum() == 2
    assert combine(a, b, "or").alarm.sum() == 2 and combine(a, b, "and").alarm.sum() == 1
    sin_caja = runway_alarms(panel(companies, z=z), 1.0)                  # sin caja no hay combinación evaluable
    assert not combine(a, sin_caja, "or").available.any()


def test_common_subset_uses_the_same_events_for_every_alarm():
    companies = ["A", "B"]
    features, observed = frames(companies)
    t = tx([("A", "2025-09-15", "cuota_impagada"), ("B", "2025-10-15", "aplazamiento")])
    keys = [(c, str(m.date())[:7]) for c in companies for m in MONTHS]
    z = {k: (-2.0 if (k[0], k[1]) in (("A", "2025-07"), ("B", "2025-08")) else 0.0) for k in keys}
    runway = {k: (0.2 if k[0] == "A" else None) for k in keys}            # B no tiene caja reconstruida
    p = panel(companies, z=z, runway=runway)
    r = compare_alarms(t, features, p, p)
    assert r["onsets"] == 2 and r["common_onsets"] == 1                   # B queda fuera del subconjunto común
    assert all(v["evaluable_onsets"] == 1 for v in r["alarms_common"].values())
    assert r["alarms"]["score_z<=-1.5"]["evaluable_onsets"] == 2          # el score sí ve los dos


def test_debt_pressure_needs_a_rise_over_its_own_history_not_a_high_level():
    from xray.evaluation.early_warning import debt_pressure_alarms
    months = pd.date_range("2025-01-01", "2025-08-01", freq="MS")
    # A: carga alta pero estable (20% siempre) -> no es alarma. B: salta de 5% a 20% en julio -> alarma.
    rows = []
    for m in months:
        rows.append({"company_id": "A", "month": m, "tx_inflow": 1000.0, "debt_principal_paid": 200.0, "debt_interest_paid": 0.0})
        salto = m >= pd.Timestamp("2025-07-01")
        rows.append({"company_id": "B", "month": m, "tx_inflow": 1000.0, "debt_principal_paid": 200.0 if salto else 50.0,
                     "debt_interest_paid": 0.0})
    a = debt_pressure_alarms(pd.DataFrame(rows)).set_index(["company_id", "month"])
    assert not a.loc["A", "alarm"].any()
    assert a.loc[("B", pd.Timestamp("2025-07-01")), "alarm"]
    assert not a.loc[("B", pd.Timestamp("2025-04-01")), "alarm"]          # antes del salto, nada
    assert not a.loc[("B", pd.Timestamp("2025-01-01")), "available"]      # sin historia previa no es evaluable


def test_debt_pressure_ignores_months_without_operating_inflow():
    from xray.evaluation.early_warning import debt_pressure_alarms
    months = pd.date_range("2025-01-01", "2025-06-01", freq="MS")
    rows = [{"company_id": "A", "month": m, "tx_inflow": 0.0 if m == months[-1] else 1000.0,
             "debt_principal_paid": 100.0, "debt_interest_paid": 0.0} for m in months]
    a = debt_pressure_alarms(pd.DataFrame(rows)).set_index("month")
    assert not a.loc[months[-1], "available"]                              # sin entradas no hay cociente


def test_holdout_split_is_by_group_and_deterministic():
    from xray.evaluation.early_warning import split_groups
    companies = pd.DataFrame({"group_id": [f"G{i:03d}" for i in range(100)]})
    dev, hold = split_groups(companies)
    assert len(dev) == 70 and len(hold) == 30 and not dev & hold
    assert (dev, hold) == split_groups(companies)                          # misma semilla, mismo reparto
