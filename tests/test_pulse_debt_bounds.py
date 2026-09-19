"""Patch Debt identification mechanics, not statistical calibration."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from xray.pulse import load_config, score_company
from xray.pulse.critical import recalculate, without_transaction
from xray.pulse.debt import UNCERTAINTY_COLUMNS
from xray.pulse.features import extract_features

OLD_CONFIG = Path(__file__).parents[1] / "src/xray/pulse/configs/pulse_four_pillars_v1.json"


def facts(*, uncertain=0., principal=2., interest=1., fees=0., inflows=110., outflows=100.):
    frame = pd.DataFrame({"month": pd.date_range("2026-03-01", periods=6, freq="MS")})
    for key, value in {"company_id": "COMP_1084", "currency": "EUR", "history_observed": True,
                       "operating_inflows": inflows, "operating_outflows": outflows,
                       "operating_net_cash": inflows - outflows, "debt_principal_paid": principal,
                       "debt_interest_paid": interest, "verified_financing_fees": fees,
                       "debt_service_paid": principal + interest + fees, "uncertain_outflows": uncertain,
                       "uncertain_inflows": 0., "uncertain_amount": uncertain, "classified_amount": 220.,
                       "excluded_outflows": 0., "unknown_currency_count": 0, "ambiguous_currency_count": 0,
                       "facts_version": "monthly-facts-v1.1", "debt_uncertainty_version": "debt-uncertainty-v1"}.items():
        frame[key] = value
    for col in UNCERTAINTY_COLUMNS:
        frame[col] = uncertain if col in ("debt_unresolved_uncertain_outflows", "potentially_financial_uncertain_outflows") else 0.
    frame["active_product_ids"] = [["P"] for _ in range(6)]
    return frame


def score(frame=None, **kwargs):
    return score_company(facts() if frame is None else frame, company_id="COMP_1084", currency="EUR",
                         as_of="2026-08-31", **kwargs)


def test_small_uncertainty_bounded_midpoint_and_exact_health():
    result = score(facts(uncertain=.1))
    debt = result.pillars["debt_obligations"]
    assert result.status == "complete_bounded" and result.health_evidence == "bounded"
    assert debt["evidence_status"] == "bounded" and debt["score_estimation"] == "bounded_midpoint"
    assert debt["score"] == (debt["score_range"]["min"] + debt["score_range"]["max"]) / 2
    assert debt["identified_score"] == debt["score_range"]["max"]
    assert debt["score"] < debt["identified_score"]
    assert debt["features"]["observed_debt_service_burden"]["raw"] == 18 / 660
    assert result.health == sum(result.contributions.values())
    assert result.health_min == result.identified_range["min"] <= result.health <= result.identified_range["max"] == result.health_max
    assert result.config_version == "pulse-config-v1.0.1" and result.facts_version == "monthly-facts-v1.1"
    assert "not_confidence_interval" in result.identified_range["kind"]


def test_material_uncertainty_keeps_range_but_not_point():
    result = score(facts(uncertain=30.))
    debt = result.pillars["debt_obligations"]
    assert debt["score_range_width"] > 5 and debt["score"] is None
    assert debt["evidence_status"] == "partial" and result.health is None
    assert result.status == "partial" and result.known_weight == .8
    assert result.health_max == result.health_min + 20
    assert result.identified_range is not None
    assert result.identified_range["min"] <= result.identified_range["max"]


def test_five_point_policy_boundary_and_past_cutoff():
    f = facts(uncertain=2., principal=10., interest=0., inflows=100.)
    exact = score(f)
    debt = exact.pillars["debt_obligations"]
    assert debt["score_range_width"] == 5. and debt["evidence_status"] == "bounded"
    assert score(facts(uncertain=2.0001, principal=10., interest=0., inflows=100.)).pillars["debt_obligations"]["score"] is None
    future = f.iloc[:1].copy()
    future["month"] = pd.Timestamp("2026-09-01")
    future["operating_inflows"] = 99999.
    future["operating_net_cash"] = future.operating_inflows - future.operating_outflows
    assert score(pd.concat([f, future])).to_dict() == exact.to_dict()


@pytest.mark.parametrize("component", ["principal", "interest", "fees"])
def test_higher_service_never_improves_identified_range_or_midpoint(component):
    results = [score(facts(uncertain=.1, **{component: value})).pillars["debt_obligations"]
               for value in (1., 2., 5., 10., 40.)]
    for metric in ("score", "identified_score"):
        values = [v[metric] for v in results]
        assert values == sorted(values, reverse=True)
    for endpoint in ("min", "max"):
        values = [v["score_range"][endpoint] for v in results]
        assert values == sorted(values, reverse=True)


def test_uncertainty_only_widens_safe_range_and_cannot_improve_point():
    results = [score(facts(uncertain=value)).pillars["debt_obligations"] for value in (0, .1, .2, .5, 1.)]
    points = [r["score"] for r in results]
    assert points == sorted(points, reverse=True)
    assert all(r["score_range"]["max"] == results[0]["score_range"]["max"] for r in results)
    widths = [r["score_range_width"] for r in results]
    assert widths == sorted(widths)


def test_absence_stays_unknown_even_with_zero_uncertainty():
    debt = score(facts(principal=0, interest=0)).pillars["debt_obligations"]
    assert debt["score"] is debt["identified_score"] is None
    assert debt["evidence_status"] == "unknown" and debt["service_absence_verified"] is False
    assert debt["score_range"] == {"min": None, "max": None}


def test_partial_history_preserves_available_components_without_scoring():
    result = score(facts(principal=2, interest=3, fees=1).drop(index=5))
    debt = result.pillars["debt_obligations"]
    assert result.status == "insufficient_evidence" and result.health_evidence == "unknown"
    assert debt["evidence_status"] == "partial" and debt["score"] is None
    assert debt["identified_service"] == {"debt_principal_paid": 10., "debt_interest_paid": 15.,
                                          "verified_financing_fees": 5., "debt_service_paid": 30.,
                                          "observed_months": 5, "required_months": 6, "history_complete": False}
    assert debt["score_range"] == {"min": None, "max": None}
    empty = score(facts().iloc[:0]).pillars["debt_obligations"]
    assert empty["identified_service"]["debt_service_paid"] is None and empty["evidence_status"] == "unknown"


@pytest.mark.parametrize("field,reason", [("excluded_outflows", "excluded_outflows_unbounded"),
                                           ("unknown_currency_count", "currency_evidence_unbounded"),
                                           ("ambiguous_currency_count", "currency_evidence_unbounded")])
def test_unbounded_quality_exclusions_never_get_finite_full_range(field, reason):
    f = facts(uncertain=.1)
    f.loc[0, field] = 1
    debt = score(f).pillars["debt_obligations"]
    assert debt["score"] is None and debt["score_range"] == {"min": None, "max": None}
    assert debt["reason"] == reason and debt["service_bounds"]["max"] is None


def test_zero_denominators_and_invalid_assessment_fail_closed():
    result = score(facts(inflows=0))
    assert result.pillars["debt_obligations"]["reason"] == "zero_operating_inflows"
    assert result.pillars["debt_obligations"]["score_range"]["min"] is None
    result = score(facts(outflows=0))
    assert all(result.pillars[p]["score"] is None for p in ("generation", "momentum", "resilience"))
    with pytest.raises(ValueError, match="assessment facts missing"):
        score(facts().drop(columns=UNCERTAINTY_COLUMNS[0]))
    f = facts(uncertain=1.)
    f.loc[0, "potentially_financial_uncertain_outflows"] = 0
    with pytest.raises(ValueError, match="partition"):
        score(f)
    f = facts()
    f.loc[0, "debt_possible_uncertain_outflows"] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        score(f)


def test_legacy_replay_remains_strict_and_gmr_is_bit_exact():
    f = facts(uncertain=.1)
    old = score(f, config=load_config(OLD_CONFIG))
    new = score(f, previous=old)
    assert old.status == "partial" and old.pillars["debt_obligations"]["score"] is None
    assert old.facts_version == "monthly-facts-v1.1"  # Actual additive facts, not a fabricated old provenance.
    assert old.config_version == "pulse-config-v1"
    assert "health_evidence" not in old.to_dict()
    for name in ("generation", "momentum", "resilience"):
        assert old.pillars[name] == new.pillars[name]
    assert new.change["interpretation"] == "methodology_change" and not new.change["comparable_to_previous"]


def test_zero_width_range_contains_point_exactly():
    for f in (facts(), facts(principal=100., uncertain=50.)):
        result = score(f)
        assert result.health == sum(result.contributions.values())
        assert result.identified_range["min"] == result.health == result.identified_range["max"]


def test_uncertain_leave_one_out_updates_partition_and_does_not_certify_zero_service():
    frame = facts(uncertain=.1)
    before = score(frame)
    row = {"date": "2026-03-01", "amount": -.1, "eligible": True, "is_uncertain": True,
           "debt_uncertainty_status": "debt_unresolved"}
    changed = without_transaction(frame, row)
    assert changed.loc[0, "potentially_financial_uncertain_outflows"] == 0
    assert changed.loc[0, "debt_unresolved_uncertain_outflows"] == 0
    assert recalculate(changed, before, load_config()).pillars["debt_obligations"]["score"] >= before.pillars["debt_obligations"]["score"]


def test_incomplete_invalid_debt_keeps_generation_independent():
    f = facts()
    f.loc[0, "debt_service_paid"] = np.nan
    result = score(f)
    assert result.pillars["generation"]["score"] is not None
    assert result.pillars["debt_obligations"]["identified_service"]["debt_service_paid"] == 15.
    assert result.pillars["debt_obligations"]["score"] is None
    assert extract_features(f, company_id="COMP_1084", currency="EUR", as_of="2026-08-31").debt_status == "partial"


def test_bounded_economic_service_change_is_not_new_evidence_but_history_change_is():
    before = score(facts(uncertain=.1)).to_dict()
    before["as_of"] = "2026-07-31"
    changed = score(facts(uncertain=.1, principal=3.), previous=before)
    assert before["confidence"]["debt_evidence"]["status"] == changed.confidence["debt_evidence"]["status"] == "bounded"
    assert changed.change["comparable_to_previous"]
    assert changed.change["interpretation"] == "economic_deterioration"
    assert not changed.change["attribution"]["evidence"]
    assert changed.change["attribution"]["economic"]["facts"]["debt_service_paid"]["observed_fact_delta"] == 6.
    missing_history = score(facts(uncertain=.1).drop(index=0), previous=before)
    assert not missing_history.change["comparable_to_previous"]
    assert missing_history.change["interpretation"] == "evidence_change"
    assert "history_coverage" in missing_history.change["attribution"]["evidence"]
