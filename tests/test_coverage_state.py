"""FE10 · coverage_state: cuentas dormidas, onboarding, cambio de cuentas y desconexión."""
import pandas as pd
import pytest

from test_clean import row
from test_features import build, company, fixture_tables
from xray.features import FeatureConfig, build_features


def active_month(start, month, product="P1", n=6, amount=500.0):
    return [row(start + i, product=product, date=f"2025-{month:02d}-{10 + i:02d}", amount=amount) for i in range(n)]


def fee_only(start, month, product="P1"):
    return [row(start, product=product, date=f"2025-{month:02d}-28", amount=-12.0, category="fee")]


def test_states_over_a_typical_onboarding_and_disconnection():
    rows = (fee_only(1, 1) + fee_only(2, 2)                 # ene-feb: solo comisión -> pre_activity
            + active_month(10, 3) + active_month(20, 4)     # mar-abr: primera actividad real -> onboarding
            + active_month(30, 5)                           # may: comparable -> ok
            + fee_only(40, 6))                              # jun: vuelve a solo comisión -> dormant
    panel = company(build(fixture_tables(rows)))
    assert panel.coverage_state.tolist() == ["pre_activity", "pre_activity", "onboarding", "onboarding", "ok", "dormant"]
    assert panel.tx_dormant_accounts.tolist() == [1, 1, 0, 0, 0, 1]
    assert panel.months_since_first_activity.tolist()[2:] == [0, 1, 2, 3]
    assert panel.is_coverage_comparable.tolist() == [False, False, False, False, True, False]
    # C2 no tiene movimientos: todo no_data y nunca se etiqueta como dormida
    assert (company(build(fixture_tables(rows)), "C2").coverage_state == "no_data").all()


def test_new_account_and_dropped_account_are_account_change():
    rows = (active_month(1, 1) + active_month(10, 2) + active_month(20, 3)          # P1 ene-mar
            + active_month(30, 4) + active_month(40, 4, product="P2")               # abr: aparece P2
            + active_month(50, 5) + active_month(60, 5, product="P2")               # may: las dos -> ok
            + active_month(70, 6))                                                  # jun: desaparece P2
    panel = company(build(fixture_tables(rows)))
    assert panel.coverage_state.tolist() == ["onboarding", "onboarding", "ok", "account_change", "ok", "account_change"]
    assert panel.tx_new_active_accounts.tolist() == [1, 0, 0, 1, 0, 0]
    assert panel.tx_dropped_active_accounts.tolist() == [0, 0, 0, 0, 0, 1]


def test_immaterial_secondary_account_does_not_break_comparability():
    rows = active_month(1, 1) + active_month(10, 2) + active_month(20, 3) + active_month(30, 4)   # P1: 3.000/mes
    rows += [row(40 + i, product="P2", date=f"2025-04-{10 + i:02d}", amount=-20.0, category="payment") for i in range(4)]  # P2: 80 (2,6 %)
    panel = company(build(fixture_tables(rows)))
    assert panel.coverage_state.loc["2025-04-01"] == "ok"
    assert panel.tx_new_active_accounts.loc["2025-04-01"] == 1
    assert panel.tx_account_change_share.loc["2025-04-01"] == pytest.approx(80 / 3080)
    strict = build_features(fixture_tables(rows), FeatureConfig(start_month="2025-01-01", end_month="2025-06-01",
                                                                account_change_min_share=0.0))
    assert company(strict).coverage_state.loc["2025-04-01"] == "account_change"


def test_dormant_threshold_uses_both_count_and_amount():
    rows = active_month(1, 1) + active_month(10, 2) + active_month(20, 3)
    rows += [row(30, date="2025-04-05", amount=50000.0)]            # 1 movimiento pero importe grande: no dormida
    rows += [row(40 + i, date=f"2025-05-0{i + 1}", amount=10.0) for i in range(3)]  # 3 movimientos pequeños: dormida
    panel = company(build(fixture_tables(rows)))
    assert panel.coverage_state.loc["2025-04-01"] == "ok"
    assert panel.coverage_state.loc["2025-05-01"] == "dormant"
    relaxed = build_features(fixture_tables(rows), FeatureConfig(start_month="2025-01-01", end_month="2025-06-01",
                                                                 dormant_max_transactions=0))
    assert company(relaxed).coverage_state.loc["2025-05-01"] == "ok"


def test_gap_month_is_no_data_and_revival_is_account_change():
    rows = active_month(1, 1) + active_month(10, 2) + active_month(20, 3) + active_month(40, 5)   # abril sin filas
    panel = company(build(fixture_tables(rows)))
    assert panel.coverage_state.loc["2025-04-01"] == "no_data"
    assert panel.coverage_state.loc["2025-05-01"] == "account_change"   # la cuenta reaparece: no comparable con abril


def test_prefix_invariance_of_coverage_state():
    rows = active_month(1, 1) + active_month(10, 2) + active_month(20, 3) + fee_only(30, 4)
    short = company(build(fixture_tables(rows), end="2025-04-01"))
    long = company(build(fixture_tables(rows + active_month(40, 6)), end="2025-06-01"))
    assert short.coverage_state.tolist() == long.coverage_state.tolist()[:4]
    assert long.coverage_state.loc["2025-04-01"] == "dormant"          # no se reetiqueta como 'bache' al ver la vuelta


def test_group_panel_tracks_accounts_across_subsidiaries():
    rows = (active_month(1, 1) + active_month(10, 2) + active_month(20, 3) + active_month(30, 4)
            + [row(40 + i, company="C2", product="P3", date=f"2025-04-{10 + i:02d}", amount=300.0) for i in range(6)])
    group = build(fixture_tables(rows))["group_currency_monthly_features"].set_index("month")
    assert group.coverage_state.loc["2025-04-01"] == "account_change"
    assert group.tx_new_active_accounts.loc["2025-04-01"] == 1


def test_config_rejects_invalid_thresholds():
    with pytest.raises(ValueError):
        FeatureConfig(dormant_max_amount=0)
