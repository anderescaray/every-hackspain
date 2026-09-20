"""D44 · Monitor de alertas: qué se enciende, con qué evidencia y en qué orden."""
import pandas as pd

from xray.product.monitor import build_monitor, monitor_report

MONTHS = pd.date_range("2025-01-01", "2025-08-01", freq="MS")
LAST = MONTHS[-1]


def features(rows):
    out = []
    for company, service in rows.items():
        for m, s in zip(MONTHS, service):
            out.append({"company_id": company, "group_id": f"G_{company}", "month": m, "tx_inflow": 1000.0,
                        "debt_principal_paid": s, "debt_interest_paid": 0.0})
    return pd.DataFrame(out)


def scores(labels):
    return pd.DataFrame([{"company_id": c, "month": m, "score": 60.0, "delta_vs_prev": -8.0,
                          "episode": "trend_deterioration", "trajectory": labels.get((c, str(m.date())[:7]), "stable")}
                         for c in labels_companies(labels) for m in MONTHS])


def labels_companies(labels):
    return sorted({c for c, _ in labels})


def test_debt_pressure_alert_carries_its_evidence():
    f = features({"A": [50.0] * 7 + [250.0], "B": [200.0] * 8})      # A salta de 5% a 25%; B estable al 20%
    s = scores({("A", "2025-08"): "stable", ("B", "2025-08"): "stable"})
    alerts = build_monitor(f, s)
    assert alerts.company_id.tolist() == ["A"] and alerts.alert.tolist() == ["presion_deuda"]
    evidence = alerts.evidence.iloc[0]
    assert evidence["rise_pp"] == 20.0 and evidence["threshold_pp"] == 5.0    # de 5% a 25% de las entradas
    assert alerts.streak_months.iloc[0] == 1


def test_confirmed_deterioration_alert_and_ordering_by_severity():
    f = features({"A": [50.0] * 8, "B": [50.0] * 8})
    s = scores({("A", "2025-08"): "deteriorating", ("B", "2025-08"): "deteriorating"})
    s.loc[s.company_id.eq("B") & s.month.eq(LAST), "delta_vs_prev"] = -20.0
    alerts = build_monitor(f, s)
    assert alerts.alert.unique().tolist() == ["deterioro_confirmado"]
    assert alerts.company_id.tolist() == ["B", "A"]                            # mayor caída primero


def test_report_states_measured_performance_and_limits():
    f = features({"A": [50.0] * 7 + [250.0]})
    s = scores({("A", "2025-08"): "stable"})
    alerts = build_monitor(f, s)
    r = monitor_report(alerts, LAST)
    assert r["by_alert"]["presion_deuda"]["median_lead_months"] == 3.5
    assert r["by_alert"]["presion_deuda"]["lift"] == 1.8
    assert any("no acaban en evento" in c for c in r["caveats"])
