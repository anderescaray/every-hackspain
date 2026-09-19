"""Fixed, explicitly versioned Operating and Extended Health composition."""
from pathlib import Path

import pandas as pd
import pytest

from xray.pulse import load_config, score_company
from xray.pulse.debt import UNCERTAINTY_COLUMNS


def facts(*, principal=2., interest=1., uncertain=0., outflows=100.):
    frame = pd.DataFrame({"month": pd.date_range("2026-03-01", periods=6, freq="MS")})
    for key, value in {"company_id": "COMP_1084", "currency": "EUR", "history_observed": True,
                       "operating_inflows": 110., "operating_outflows": outflows,
                       "operating_net_cash": 110. - outflows, "debt_principal_paid": principal,
                       "debt_interest_paid": interest, "verified_financing_fees": 0.,
                       "debt_service_paid": principal + interest, "uncertain_outflows": uncertain,
                       "uncertain_inflows": 0., "uncertain_amount": uncertain, "classified_amount": 220.,
                       "excluded_outflows": 0., "unknown_currency_count": 0, "ambiguous_currency_count": 0,
                       "facts_version": "monthly-facts-v2", "debt_uncertainty_version": "debt-uncertainty-v1"}.items():
        frame[key] = value
    for col in UNCERTAINTY_COLUMNS:
        frame[col] = uncertain if col in ("debt_unresolved_uncertain_outflows",
                                      "potentially_financial_uncertain_outflows") else 0.
    frame["active_product_ids"] = [["P"] for _ in range(6)]
    return frame


def score(frame=None, **kwargs):
    return score_company(facts() if frame is None else frame, company_id="COMP_1084", currency="EUR",
                         as_of="2026-08-31", **kwargs)


def test_operating_only_when_debt_is_not_identified():
    result = score(facts(principal=0., interest=0.))
    assert result.score_version == "PulseFourPillars-v1.2"
    assert result.cleaning_version == "cleaning-v2"
    assert result.composition_version == "operating-extended-health-v1"
    assert result.operating_health is not None
    assert result.extended_health is result.health is None
    assert result.health_level == "operating_only"
    assert result.missing_modules == ["debt_obligations", "extended_health"]
    assert "operating_health" in result.insights_available
    assert "extended_health" not in result.insights_available
    assert result.operating_health == sum(result.operating_contributions.values())
    assert result.operating_contributions == {
        name: result.operating_weights[name] * result.pillars[name]["score"]
        for name in ("generation", "momentum", "resilience")}


def test_verified_and_bounded_debt_identify_extended_health_without_reweighting():
    for uncertain, expected_level in ((0., "extended_verified"), (.1, "extended_bounded")):
        result = score(facts(uncertain=uncertain))
        assert result.health_level == expected_level
        assert result.operating_health is not None
        assert result.extended_health == result.health == sum(result.contributions.values())
        assert result.operating_health == sum(result.operating_contributions.values())
        assert result.missing_modules == []
        assert result.operating_weights == {"generation": .5, "momentum": .1875, "resilience": .3125}
        assert result.pillars["debt_obligations"]["score"] is not None
        if uncertain:
            assert result.health_evidence == "bounded"
            assert result.identified_range["min"] <= result.extended_health <= result.identified_range["max"]


def test_missing_operating_pillar_invalidates_both_healths():
    result = score(facts(outflows=0.))
    assert result.operating_health is result.extended_health is result.health is None
    assert result.health_level is None
    assert "operating_health" in result.missing_modules
    assert "extended_health" in result.missing_modules


def test_new_debt_evidence_is_not_an_economic_health_delta():
    before = score(facts(uncertain=30.)).to_dict()
    after = score(facts(uncertain=0.), previous=before)
    assert before["economic_facts"] == after.economic_facts
    assert before["operating_health"] == after.operating_health
    assert before["extended_health"] is None and after.extended_health is not None
    assert after.change["interpretation"] == "evidence_change"
    assert not after.change["comparable_to_previous"]
    assert after.change["economic_health_delta"] is None
    assert after.change["operating_health_delta"] == 0.
    assert after.change["extended_health_delta"] is None
    assert after.change["health_level_transition"] == {"before": "operating_only", "after": "extended_verified"}
    assert after.change["attribution"]["economic"]["identified_as_economic"] is False


def test_historical_v101_replay_omits_new_composition_fields_and_preserves_pillars():
    old_config = load_config(Path(__file__).parents[1] / "src/xray/pulse/configs/pulse_four_pillars_v1_0_1.json")
    old_facts = facts()
    old_facts["facts_version"] = "monthly-facts-v1.1"
    old = score(old_facts, config=old_config)
    new = score()
    assert old.score_version == "PulseFourPillars-v1.0.1"
    assert "operating_health" not in old.to_dict()
    assert "extended_health" not in old.to_dict()
    assert old.pillars == new.pillars
    assert old.health == new.extended_health


def test_v11_composition_config_remains_registered_for_historical_results():
    previous_config = load_config(Path(__file__).parents[1] / "src/xray/pulse/configs/pulse_four_pillars_v1_1.json")
    old_facts = facts()
    old_facts["facts_version"] = "monthly-facts-v1.1"
    previous = score(old_facts, config=previous_config)
    current = score()
    assert previous.score_version == "PulseFourPillars-v1.1"
    assert previous.config_version == "pulse-config-v1.1"
    assert previous.cleaning_version == "cleaning-v1"
    assert previous.operating_health == current.operating_health
    assert previous.extended_health == current.extended_health
    assert previous.pillars == current.pillars


def test_direct_scoring_rejects_mislabelling_v2_facts_as_historical_v11():
    previous_config = load_config(Path(__file__).parents[1] / "src/xray/pulse/configs/pulse_four_pillars_v1_1.json")
    with pytest.raises(ValueError, match="facts version is incompatible"):
        score(facts(), config=previous_config)
