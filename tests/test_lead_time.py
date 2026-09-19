"""D41 · Anticipación medida: eventos de estrés propio, antelación, censura y falsas alarmas."""
import pandas as pd

from xray.evaluation.lead_time import lead_time_report, stress_onsets, own_stress_months

MONTHS = pd.date_range("2025-01-01", "2025-12-01", freq="MS")


def features(companies):
    return pd.DataFrame([{"company_id": c, "month": m, "tx_count": 10} for c in companies for m in MONTHS])


def scores(labels):
    """labels: {company: {month_str: trajectory}}; resto 'stable' con score."""
    rows = []
    for c, marks in labels.items():
        for m in MONTHS:
            rows.append({"company_id": c, "month": m, "score": 60.0, "trajectory": marks.get(str(m.date())[:7], "stable")})
    return pd.DataFrame(rows)


def tx(rows):
    return pd.DataFrame([{"company_id": c, "date": pd.Timestamp(d), "status": "booked", "event_type": e,
                          "is_sync_duplicate": False} for c, d, e in rows])


def test_detected_event_reports_lead_from_first_alarm():
    t = tx([("A", "2025-09-15", "cuota_impagada")])
    s = scores({"A": {"2025-06": "emerging_deterioration", "2025-07": "deteriorating"}, "B": {}})
    r, leads = lead_time_report(t, features(["A", "B"]), s)
    assert r["events"]["onsets"] == 1 and r["events"]["evaluable_onsets"] == 1
    assert r["detection"]["detected"] == 1 and r["detection"]["lead_months"]["median"] == 3   # sept − junio


def test_third_party_garnishment_and_client_defaults_are_not_events():
    t = tx([("A", "2025-09-15", "embargo_tercero"), ("A", "2025-10-15", "impagado_cliente")])
    assert own_stress_months(t).empty


def test_event_without_clean_history_is_not_an_onset():
    t = tx([("A", "2025-03-10", "descubierto")])                      # solo 2 meses observados antes
    onsets = stress_onsets(own_stress_months(t), features(["A"]), clean_months=6)
    assert onsets.empty


def test_event_without_scored_history_is_censored_not_missed():
    t = tx([("A", "2025-09-15", "aplazamiento")])
    s = scores({"A": {}})
    s.loc[s.month.lt("2025-09-01"), ["score", "trajectory"]] = [None, None]
    r, _ = lead_time_report(t, features(["A"]), s)
    assert r["events"]["censored_onsets"] == 1 and r["events"]["evaluable_onsets"] == 0


def test_false_alarm_counts_only_judgeable_alarm_starts():
    t = tx([("A", "2025-09-15", "cuota_impagada")])
    s = scores({"A": {"2025-06": "deteriorating"},                    # seguida de evento: acierto
                "B": {"2025-02": "emerging_deterioration"},           # nada en 6 meses: falsa alarma
                "C": {"2025-10": "deteriorating"}})                   # sin 6 meses por delante: no evaluable
    r, _ = lead_time_report(t, features(["A", "B", "C"]), s)
    fa = r["false_alarms"]
    assert fa["alarm_starts_judgeable"] == 2 and fa["false_alarm_share"] == 0.5
    assert fa["alarm_starts_not_judgeable"] == 1


def test_recovery_is_six_clean_months_after_stress_and_is_flagged_by_improvement_labels():
    from xray.evaluation.lead_time import recoveries
    t = tx([("A", "2025-02-15", "cuota_impagada"), ("A", "2025-03-15", "descubierto")])
    f = features(["A"])
    events = own_stress_months(t)
    ups = recoveries(events, f[["company_id", "month"]])
    assert ups.onset.tolist() == [pd.Timestamp("2025-04-01")]          # abril-septiembre sin estrés
    s = scores({"A": {"2025-02": "emerging_improvement"}})
    r, _ = lead_time_report(t, f, s)
    up = r["improvement"]
    assert up["recoveries"] == 1 and up["detected"] == 1 and up["lead_months"]["median"] == 2


def test_company_block_counts_companies_not_events():
    t = tx([("A", "2025-09-15", "cuota_impagada"), ("B", "2025-09-15", "embargo")])
    s = scores({"A": {"2025-07": "deteriorating"}, "B": {}, "C": {"2025-03": "emerging_deterioration"}})
    r, _ = lead_time_report(t, features(["A", "B", "C"]), s)
    c = r["companies"]
    assert c["companies"] == 3 and c["with_own_stress"] == 2
    assert c["warned_before_event"] == 1                                # solo A tenía alarma antes
    assert c["alarmed_without_event"] == 1                              # C se avisó y no tuvo estrés
