"""Approved mechanical invariants, not financial calibration or outcome validation."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from xray.pulse import load_config, score_company
from xray.pulse.config import PulseConfig
from xray.pulse.contracts import canonical_json
from xray.pulse.features import complete_months, theil_sen
from xray.pulse.scorer import feature_records


def facts(nets=None, outflow=100., principal=2., interest=1., fees=0.):
    nets = [10.] * 6 if nets is None else nets
    rows = []
    for month, net in zip(pd.date_range("2026-01-01", periods=len(nets), freq="MS"), nets):
        rows.append({"company_id": "COMP_1084", "currency": "EUR", "month": month,
                     "operating_inflows": outflow + net, "operating_outflows": outflow,
                     "operating_net_cash": net, "debt_principal_paid": principal,
                     "debt_interest_paid": interest, "verified_financing_fees": fees,
                     "debt_service_paid": principal + interest + fees, "history_observed": True,
                     "uncertain_inflows": 0., "uncertain_outflows": 0., "excluded_inflows": 0.,
                     "excluded_outflows": 0., "classified_amount": 2 * outflow + net + principal + interest + fees,
                     "uncertain_amount": 0., "active_product_ids": ["P1"], "flags": []})
    return pd.DataFrame(rows)


def score(frame=None, **kwargs):
    # These regression cases freeze the original strict V1 methodology.
    kwargs.setdefault("config", load_config(Path(__file__).parents[1] / "src/xray/pulse/configs/pulse_four_pillars_v1.json"))
    return score_company(facts() if frame is None else frame, company_id="COMP_1084", currency="EUR",
                         as_of="2026-06-30", **kwargs)


def pillar(result, name):
    return result.pillars[name]["score"]


def test_four_exact_formulas_and_json_contributions():
    result = score(facts([-10, 0, 10, 20, 30, 40]))
    assert pillar(result, "generation") == pytest.approx(80.)
    assert pillar(result, "momentum") == 100.
    assert pillar(result, "resilience") == pytest.approx(100 - 400 * 10 / 600)
    assert pillar(result, "debt_obligations") == pytest.approx(100 - 500 * 18 / 690)
    payload = json.loads(canonical_json(result.to_dict()))
    # JSON key order is independent of the financial canonical summation order.
    ordered = ("generation", "momentum", "resilience", "debt_obligations")
    assert sum(payload["pillars"][p]["health_contribution"] for p in ordered) == payload["health"]
    assert len(feature_records(result)) == 4
    for block in result.pillars.values():
        item = next(iter(block["features"].values()))
        assert {"raw", "score", "numerator", "denominator", "anchors", "window6m", "formula_id"} <= item.keys()


@pytest.mark.parametrize("nets,sign", [([0, 2, 4, 6, 8, 10], 1), ([10, 8, 6, 4, 2, 0], -1), ([2] * 6, 0)])
def test_momentum_direction(nets, sign):
    assert np.sign(pillar(score(facts(nets)), "momentum") - 50) == sign
    assert theil_sen(nets) == pytest.approx((nets[-1] - nets[0]) / 5)


def test_generation_monotonic_and_monetary_scale_invariant():
    results = [score(facts([x] * 6)) for x in (-20, -10, 0, 10, 20)]
    assert [pillar(r, "generation") for r in results] == sorted(pillar(r, "generation") for r in results)
    base = facts([-10, 5, 15, -2, 20, 9])
    scaled = base.copy(deep=True)
    for col in scaled.select_dtypes(include="number"):
        scaled[col] *= 1234.5
    a, b = score(base), score(scaled)
    for name in a.pillars:
        assert pillar(a, name) == pytest.approx(pillar(b, name))


def test_downside_monotonic_micro_deficits_no_frequency_penalty():
    a = score(facts([-1., 0, 0, 0, 0, 0]))
    b = score(facts([-2., 0, 0, 0, 0, 0]))
    assert pillar(b, "resilience") < pillar(a, "resilience")
    one = score(facts([-6e-9, 0, 0, 0, 0, 0]))
    six = score(facts([-1e-9] * 6))
    assert pillar(one, "resilience") == pillar(six, "resilience")
    assert one.pillars["resilience"]["diagnostics"]["negative_months"] == 1
    assert six.pillars["resilience"]["diagnostics"]["negative_months"] == 6


@pytest.mark.parametrize("component", ["principal", "interest", "fees"])
def test_more_observed_service_never_improves_debt(component):
    values = [pillar(score(facts(**{component: x})), "debt_obligations") for x in (1., 5., 10., 20.)]
    assert values == sorted(values, reverse=True)


def test_piecewise_debt_anchors_and_continuity():
    for burden, expected in [(0.1, 50.), (.2, 25.), (.3, 0.), (.5, 0.)]:
        assert pillar(score(facts([0.] * 6, principal=100 * burden, interest=0)), "debt_obligations") == pytest.approx(expected)
    left = pillar(score(facts([0.] * 6, principal=10 - 1e-8, interest=0)), "debt_obligations")
    right = pillar(score(facts([0.] * 6, principal=10 + 1e-8, interest=0)), "debt_obligations")
    assert abs(left - right) < 1e-5


def test_absent_service_unknown_not_100_and_non_debt_pillars_survive():
    result = score(facts(principal=0, interest=0))
    assert result.health is None and result.missing_components == ["debt_obligations"]
    assert pillar(result, "debt_obligations") is None
    assert result.known_weight == .8
    assert result.health_max == pytest.approx(result.health_min + 20)
    for name in ("generation", "momentum", "resilience"):
        assert result.pillars[name]["weight"] == load_config().weights[name]
    unavailable = facts()
    unavailable.loc[:, "debt_service_paid"] = np.nan
    assert pillar(score(unavailable), "generation") is not None


def test_months_with_no_service_do_not_invalidate_verified_observed_window():
    f = facts(principal=0, interest=0)
    f.loc[5, "debt_principal_paid"] = f.loc[5, "debt_service_paid"] = 10.
    assert score(f).pillars["debt_obligations"]["evidence_status"] == "verified"


@pytest.mark.parametrize("column", ["uncertain_outflows", "excluded_outflows"])
def test_ambiguous_or_excluded_outflows_make_service_partial(column):
    f = facts()
    f.loc[2, column] = 1.
    result = score(f)
    assert pillar(result, "debt_obligations") is None
    assert result.pillars["debt_obligations"]["evidence_status"] == "partial"


def test_zero_denominators_remain_missing_without_epsilon():
    no_out = score(facts([10.] * 6, outflow=0.))
    assert all(pillar(no_out, p) is None for p in ("generation", "momentum", "resilience"))
    no_in = score(facts([-100.] * 6))
    feature = no_in.pillars["debt_obligations"]["features"]["observed_debt_service_burden"]
    assert feature["missing_reason"] == "zero_operating_inflows"
    assert pillar(no_in, "debt_obligations") is None and no_in.health is None


def test_missing_calendar_month_not_zero_or_compressed():
    result = score(facts().drop(index=3))
    assert result.health is None and len(result.missing_components) == 4
    assert result.health_min == 0. and result.health_max == 100. and result.known_weight == 0.
    assert result.confidence["history_coverage"] == 5 / 6
    assert complete_months("2026-07-01")[-1] == pd.Timestamp("2026-06-01")
    assert complete_months("2026-06-29")[-1] == pd.Timestamp("2026-05-01")


def test_future_and_order_do_not_change_past():
    f = facts()
    future = facts([100000.] * 8)
    combined = pd.concat([f, future.iloc[6:]], ignore_index=True)
    assert canonical_json(score(f).to_dict()) == canonical_json(score(combined.sample(frac=1, random_state=42)).to_dict())


def test_contract_rejects_duplicate_keys_nonreconciliation_and_negative_magnitudes():
    with pytest.raises(ValueError, match="duplicate"):
        score(pd.concat([facts(), facts().iloc[:1]]))
    f = facts()
    f.loc[0, "debt_service_paid"] += 10
    with pytest.raises(ValueError, match="double counting"):
        score(f)
    f = facts()
    f.loc[0, "operating_outflows"] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        score(f)


@pytest.mark.parametrize("mutation", ["weight", "anchor", "formula", "critical", "robustness"])
def test_version_rejects_changed_configuration_under_same_score_version(mutation):
    cfg = load_config().to_dict()
    if mutation == "weight":
        cfg["weights"]["generation"] = .3
    elif mutation == "anchor":
        cfg["anchors"]["generation"][1][1] = 51
    elif mutation == "formula":
        cfg["formulas"]["momentum"] = "some-other-formula"
    elif mutation == "critical":
        cfg["critical"]["max_candidates"] = 100
    else:
        cfg["robustness"]["max_stable_health_range"] = 10
    with pytest.raises(ValueError, match="registered score_version"):
        PulseConfig(json.dumps(cfg))


def test_evidence_and_methodology_changes_are_not_economic_deterioration():
    before = score().to_dict()
    cfg_before = copy.deepcopy(before)
    cfg_before["score_version"] = "older"
    newer = score(previous=cfg_before)
    assert not newer.change["comparable_to_previous"]
    assert newer.change["interpretation"] == "methodology_change"
    f = facts()
    f.loc[5, "active_product_ids"] = ["new_account"]
    changed = score(f, previous=before)
    assert changed.health == before["health"]
    assert not changed.change["comparable_to_previous"]
    assert changed.change["interpretation"] == "evidence_change"
    absent = score(facts(principal=0, interest=0)).to_dict()
    identified = score(previous=absent)
    assert not identified.change["comparable_to_previous"]
    assert identified.change["economic_health_delta"] is None


def test_restatement_same_cutoff_is_evidence_even_when_confidence_is_unchanged():
    before = score(lineage={"input_hash": "original"}).to_dict()
    revised = score(facts([0.] * 6), lineage={"input_hash": "revised"}, previous=before)
    assert revised.confidence == before["confidence"]
    assert revised.health < before["health"]
    assert not revised.change["comparable_to_previous"]
    assert revised.change["economic_health_delta"] is None
    assert revised.change["interpretation"] == "evidence_change"
    assert "input_restatement" in revised.change["attribution"]["evidence"]


def test_vintage_change_is_evidence_but_new_month_input_alone_is_not():
    before = score(lineage={"input_hash": "old", "data_vintage": "2026-07-01"}).to_dict()
    vintage = score(lineage={"input_hash": "old", "data_vintage": "2026-08-01"}, previous=before)
    assert vintage.change["interpretation"] == "evidence_change"
    assert "data_vintage" in vintage.change["attribution"]["evidence"]
    before["as_of"] = "2026-05-31"
    later = score(lineage={"input_hash": "new", "data_vintage": "2026-07-01"}, previous=before)
    assert later.change["comparable_to_previous"]
    assert "input_restatement" not in later.change["attribution"]["evidence"]


def test_confidence_is_structured_not_a_health_multiplier():
    f = facts()
    a = score(f)
    f["uncertain_amount"] = 100.
    b = score(f)
    assert a.health == b.health
    assert b.confidence["classification_coverage"] < a.confidence["classification_coverage"]


def critical_fixture(last_service_only=False):
    from xray.ledger import build_monthly_facts
    rows = []
    for index, month in enumerate(pd.date_range("2026-01-01", periods=6, freq="MS")):
        flows = [("base", 90., "operating", "customer_collection", True, False, False),
                 ("small_sign_changer", 30., "operating", "customer_collection", True, False, False),
                 ("cost", -100., "operating", "supplier_payment", False, True, False)]
        if not last_service_only or index == 5:
            flows.append(("principal", -2., "debt_service", "debt_principal", False, False, True))
        flows.append(("large_irrelevant", 1e6, "own_account_circulation", "own_transfer", False, False, False))
        for name, amount, cls, sub, inflow, outflow, service in flows:
            rows.append({"transaction_id": f"COMP1084-{index}-{name}", "company_id": "COMP_1084", "product_id": "P1",
                         "date": month, "month": month, "currency": "EUR", "amount": amount, "eligible": True, "exchange_rate": 1.,
                         "economic_class": cls, "economic_subclass": sub, "classification_version": "cash-truth-v1",
                         "included_in_operating_inflows": inflow, "included_in_operating_outflows": outflow,
                         "included_in_debt_service": service, "is_uncertain": False, "status": "booked",
                         "flags": [], "source_lineage": {"transaction_id": f"COMP1084-{index}-{name}"}})
    ledger = pd.DataFrame(rows)
    monthly = build_monthly_facts(ledger, as_of="2026-06-30")
    return ledger, monthly


def test_comp1084_criticality_is_not_size_ranking_and_reconciles_loo():
    ledger, monthly = critical_fixture()
    before = ledger.copy(deep=True)
    result = score(monthly, ledger=ledger)
    assert result.critical_movements
    assert not any("large_irrelevant" in row["transaction_id"] for row in result.critical_movements)
    small = next(row for row in result.critical_movements if "small_sign_changer" in row["transaction_id"])
    assert small["reason"] == "changes_month_from_positive_to_deficit"
    assert small["impact"]["monthly_net_without"] == -10.
    assert small["impact"]["monthly_net_before"] == 20.
    assert small["impact"]["generation_delta"] < 0
    pd.testing.assert_frame_equal(before, ledger)
    robustness = result.robustness
    assert robustness["tested_range"]["min"] <= result.health <= robustness["tested_range"]["max"]
    assert "not_confidence_interval" in robustness["range_kind"]
    assert all(row["version"] == robustness["version"] for row in robustness["tested_assumptions"])


def test_loo_last_service_becomes_unknown_not_health_improvement():
    ledger, monthly = critical_fixture(last_service_only=True)
    result = score(monthly, ledger=ledger)
    debt = next(row for row in result.critical_movements if "principal" in row["transaction_id"])
    assert debt["impact"]["health_delta"] is None
    assert "debt_obligations" in debt["missing_components_without"]
    assert result.robustness["level"] == "indeterminate"
    assert result.robustness["diagnosis_stable"] is None


def test_unknown_currency_does_not_disappear_from_evidence_or_debt():
    f = facts()
    f["unknown_currency_count"] = [0, 0, 1, 0, 0, 0]
    f["ambiguous_currency_count"] = [0, 0, 1, 0, 0, 0]
    result = score(f)
    assert result.confidence["currency_consistency"]["status"] == "partial"
    assert result.confidence["currency_consistency"]["unknown_currency_count"] == 1
    assert pillar(result, "debt_obligations") is None
    assert "currency_evidence_incomplete" in result.flags


def test_cached_evidence_change_is_not_attributed_to_economy():
    before = score(lineage={"classification_evidence_hash": "old"}).to_dict()
    after = score(lineage={"classification_evidence_hash": "new"}, previous=before)
    assert after.change["interpretation"] == "evidence_change"
    assert not after.change["comparable_to_previous"]


def test_actual_classification_version_is_not_hardcoded_score_configuration():
    f = facts()
    f["classification_version"] = "cash-truth-v1+cached-policy"
    assert score(f).classification_version == "cash-truth-v1+cached-policy"


def test_partial_robustness_does_not_invent_health_or_certify_uncertainty():
    f = facts()
    f["uncertain_amount"] = 20.
    f["uncertain_outflows"] = 20.
    result = score(f)
    assert result.health is None and result.robustness["level"] == "indeterminate"
    assert result.robustness["tested_range"] == {"min": None, "max": None}
    scenario = result.robustness["tested_assumptions"][0]
    assert not scenario["evaluable"] and "debt_obligations" in scenario["missing_components"]
    assert scenario["assumptions"]["evidence_unchanged"]
