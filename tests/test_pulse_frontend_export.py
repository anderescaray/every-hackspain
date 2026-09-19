"""Pulse web contract regressions. Written for later execution; no validation fit.

These tests deliberately remain separate from explicit legacy-export tests.
"""
import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from xray.artifacts import recursive_hashes, sha256
from xray.product.frontend_export import (
    WebEnvelope,
    company_detail,
    group_detail,
    portfolio_export,
    run,
)
from xray.pulse import score_company
from xray.pulse.config import load_config


def _source(debt=3.0, observed=True, *, patch=False, composition=False, uncertainty=0.0):
    rows = []
    for month in pd.date_range("2026-03-01", periods=6, freq="MS"):
        rows.append({"company_id": "COMP_1084", "currency": "EUR", "month": month,
                     "operating_inflows": 110.12345, "operating_outflows": 100.0,
                     "operating_net_cash": 10.12345, "debt_principal_paid": debt,
                     "debt_interest_paid": 0.0, "verified_financing_fees": 0.0,
                     "debt_service_paid": debt, "history_observed": observed,
                     "debt_uncertainty_version": "debt-uncertainty-v1",
                     "debt_possible_uncertain_outflows": 0., "debt_impossible_uncertain_outflows": 0.,
                     "debt_unresolved_uncertain_outflows": uncertainty,
                     "potentially_financial_uncertain_outflows": uncertainty,
                     "ambiguous_currency_count": 0, "unknown_currency_count": 0,
                     "uncertain_inflows": 0.0, "uncertain_outflows": uncertainty, "excluded_inflows": 0.0,
                     "excluded_outflows": 0.0, "classified_amount": 210.12345 + debt,
                     "uncertain_amount": uncertainty, "active_product_ids": ["P1"], "flags": []})
    score = score_company(pd.DataFrame(rows), company_id="COMP_1084", currency="EUR",
                          as_of="2026-08-31", run_id="pulse-contract-fixture",
                          config=load_config(Path(__file__).parents[1] / "src/xray/pulse/configs" /
                                             ("pulse_four_pillars_v1_1.json" if composition else
                                              "pulse_four_pillars_v1_0_1.json" if patch else
                                              "pulse_four_pillars_v1.json"))).to_dict()
    cash = {"schema_version": "1.0", "company_id": "COMP_1084", "currency": "EUR", "as_of": score["as_of"],
            "classification_version": score["classification_version"], "facts_version": score["facts_version"],
            "summary": {"net_operating_cash": 60.7407, "eligible_net_cash": 60.7407 - 6 * debt},
            "classes": [{"economic_class": "operating", "amount_abs": 1260.7407},
                        {"economic_class": "debt_service", "amount_abs": 6 * debt}],
            "evidence": {"window_start": "2026-03-01", "window_end": "2026-08-31"},
            "coverage": {"transaction_count": 18}, "flags": [], "critical_movements": []}
    envelope = WebEnvelope(run_id=score["run_id"], snapshot_id="web-" + "1" * 64,
                           **{key: score[key] for key in ("score_version", "classification_version", "cleaning_version",
                                                         "facts_version", "config_version", "as_of", "currency")})
    return score, cash, envelope


def test_complete_health_and_contributions_are_copied_without_rounding():
    score, cash, envelope = _source()
    before = copy.deepcopy(score)
    detail = company_detail(score, cash, "GROUP_0001", envelope)
    assert score == before and detail["pulse"] == before
    assert detail["health_score"] == score["health"]
    assert detail["dimensions"]["cash_generation"] == score["pillars"]["generation"]["score"]
    assert detail["pulse"]["contributions"] == score["contributions"]
    assert detail["health_score"] != round(detail["health_score"])
    assert detail["canonical_cash_truth"] == cash
    assert detail["health_score_model"]["version"] == "PulseFourPillars-v1.0"


def test_comp1084_unknown_debt_preserves_partial_company_and_portfolio():
    score, cash, envelope = _source(debt=0.0)
    detail = company_detail(score, cash, None, envelope)
    assert detail["status"] == "partial"
    assert detail["health_score"] is None and detail["dimensions"]["debt"] is None
    assert detail["dimensions"]["cash_generation"] is not None
    assert detail["pulse"]["pillars"]["debt_obligations"]["evidence_status"] == "unknown"
    portfolio = portfolio_export({"COMP_1084": detail}, envelope)
    assert len(portfolio["items"]) == 1 and portfolio["items"][0]["has_detail"]
    assert portfolio["items"][0]["health_score"] is None
    assert portfolio["items"][0]["missing_components"] == ["debt_obligations"]
    assert detail["history"] == [{"month": score["as_of"], "health_score": None}]


def test_all_missing_is_insufficient_without_changing_original_engine_status():
    score, cash, envelope = _source(observed=False)
    detail = company_detail(score, cash, None, envelope)
    assert detail["status"] == "insufficient_evidence"
    assert detail["pulse"]["status"] == "partial"
    assert all(value is None for value in detail["dimensions"].values())


def test_zero_is_not_missing_and_group_health_is_never_average():
    score, cash, envelope = _source()
    score["pillars"]["generation"]["score"] = 0.0
    score["pillars"]["generation"]["health_contribution"] = 0.0
    score["contributions"]["generation"] = 0.0
    score["health"] = sum(score["contributions"].values())
    detail = company_detail(score, cash, "GROUP_0001", envelope)
    assert detail["dimensions"]["cash_generation"] == 0.0
    group = group_detail("GROUP_0001", [detail], envelope)
    assert group["health_score"] is None and group["status"] == "insufficient_evidence"
    assert group["members"][0]["health_score"] == score["health"]


@pytest.mark.parametrize("key,value", [("run_id", "different-run"), ("score_version", "financial_smoothed_v2"),
                                       ("as_of", "2026-07-31"), ("classification_version", "legacy")])
def test_legacy_or_mixed_source_fails_closed(key, value):
    score, cash, envelope = _source()
    score[key] = value
    with pytest.raises(ValueError):
        company_detail(score, cash, None, envelope)


def test_tampered_contributions_rejected_not_recomputed():
    score, cash, envelope = _source()
    score["contributions"]["generation"] += 1
    with pytest.raises(ValueError, match="contribution"):
        company_detail(score, cash, None, envelope)


def _write_run(root: Path) -> Path:
    score, cash, envelope = _source(debt=0.0)
    folder = root / "runs" / score["run_id"]
    (folder / "companies" / "COMP_1084" / "EUR").mkdir(parents=True)
    (folder / "cleaned").mkdir()
    pd.DataFrame([{"company_id": "COMP_1084", "group_id": "GROUP_0001"}]).to_parquet(folder / "cleaned/companies.parquet")
    for name, value in (("score", score), ("cash_truth", cash)):
        (folder / "companies/COMP_1084/EUR" / f"{name}.json").write_text(json.dumps(value))
    manifest = {"run_id": score["run_id"], "as_of": score["as_of"], "companies": ["COMP_1084"],
                "versions": {key: value for key, value in envelope.to_dict().items() if key.endswith("_version")},
                "outputs_sha256": recursive_hashes(folder)}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


def test_atomic_snapshot_replay_and_recursive_integrity(tmp_path):
    source = _write_run(tmp_path / "input")
    output = tmp_path / "generated"
    manifest = run(source, output, verbose=False)
    pointer = json.loads((output / "current.json").read_text())
    target = output / "snapshots" / pointer["snapshot_id"]
    assert pointer["run_id"] == manifest["run_id"]
    assert pointer["manifest_sha256"] == sha256(target / "manifest.json")
    assert recursive_hashes(target, exclude=("manifest.json",)) == manifest["outputs_sha256"]
    before = recursive_hashes(target)
    assert run(source, output, verbose=False) == manifest
    assert recursive_hashes(target) == before
    old_pointer = (output / "current.json").read_bytes()
    (target / "companies/COMP_1084.json").write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        run(source, output, verbose=False)
    assert (output / "current.json").read_bytes() == old_pointer


def test_symlink_snapshot_destination_cannot_escape(tmp_path):
    source = _write_run(tmp_path / "input")
    output, outside = tmp_path / "generated", tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    (output / "snapshots").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Symbolic"):
        run(source, output, verbose=False)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("uncertainty,status", [(0.0, "complete_verified"), (0.5, "complete_bounded"), (30.0, "partial")])
def test_patch_exports_original_identification_without_recalculating(uncertainty, status):
    score, cash, envelope = _source(patch=True, uncertainty=uncertainty)
    before = copy.deepcopy(score)
    detail = company_detail(score, cash, "GROUP_0001", envelope)
    debt = score["pillars"]["debt_obligations"]
    assert detail["status"] == status
    assert detail["pulse"] == before == score
    assert detail["health_score"] == score["health"]
    assert detail["dimensions"]["debt"] == debt["score"]
    for projection in (portfolio_export({"COMP_1084": detail}, envelope)["items"][0],
                       group_detail("GROUP_0001", [detail], envelope)["members"][0]):
        assert projection["identified_range"] == score["identified_range"]
        assert projection["health_evidence"] == score["health_evidence"]
        assert projection["score_status"] == status
    if status == "complete_bounded":
        assert debt["score"] != debt["identified_score"]
        assert "acotada" in detail["assessment"]
        assert detail["health_score_model"]["provisional"]
    elif status == "partial":
        assert debt["score"] is None and debt["score_range"]["min"] is not None
        assert detail["health_score"] is None


@pytest.mark.parametrize("change", ["missing_range", "wrong_method", "hide_bounded", "outside_range", "invent_absence"])
def test_patch_rejects_missing_or_misrepresented_bounds(change):
    score, cash, envelope = _source(patch=True, uncertainty=0.5)
    debt = score["pillars"]["debt_obligations"]
    if change == "missing_range":
        del debt["score_range"]
    elif change == "wrong_method":
        score["config_version"] = "pulse-config-v1"
    elif change == "hide_bounded":
        score["status"] = "complete_verified"
        score["health_evidence"] = "verified"
    elif change == "outside_range":
        score["identified_range"] = {"min": 0.0, "max": 1.0, "kind": "identification_bounds_not_confidence_interval"}
    else:
        debt["service_absence_verified"] = True
    with pytest.raises(ValueError):
        company_detail(score, cash, None, envelope)


def test_patch_no_service_and_missing_history_remain_null():
    for kwargs in ({"debt": 0.0}, {"observed": False}):
        score, cash, envelope = _source(patch=True, **kwargs)
        detail = company_detail(score, cash, None, envelope)
        assert detail["health_score"] is None
        assert detail["dimensions"]["debt"] is None
        assert detail["pulse"]["identified_range"] is None
        assert detail["pulse"]["pillars"]["debt_obligations"]["service_absence_verified"] is False


def test_historical_v101_export_does_not_invent_dual_health():
    score, cash, envelope = _source(patch=True)
    detail = company_detail(score, cash, None, envelope)
    item = portfolio_export({"COMP_1084": detail}, envelope)["items"][0]
    for projection in (detail, item):
        assert "operating_health" not in projection
        assert "extended_health" not in projection
        assert "health_level" not in projection
        assert projection["health_score"] == score["health"]


@pytest.mark.parametrize("debt,uncertainty,expected_level", [
    (0.0, 0.0, "operating_only"), (3.0, 0.0, "extended_verified"),
    (3.0, 0.5, "extended_bounded"),
])
def test_v11_projects_dual_health_without_recalculation(debt, uncertainty, expected_level):
    score, cash, envelope = _source(debt=debt, uncertainty=uncertainty, composition=True)
    detail = company_detail(score, cash, "GROUP_0001", envelope)
    item = portfolio_export({"COMP_1084": detail}, envelope)["items"][0]
    member = group_detail("GROUP_0001", [detail], envelope)["members"][0]
    for projection in (detail, item, member):
        for field in ("composition_version", "operating_health", "extended_health", "health_level",
                      "insights_available", "missing_modules"):
            assert projection[field] == score[field]
        assert projection["health_score"] == score["extended_health"]
        assert projection["dimensions"]["debt"] == score["pillars"]["debt_obligations"]["score"]
    assert detail["health_level"] == expected_level
    assert detail["operating_contributions"] == score["operating_contributions"]
    assert detail["operating_weights"] == score["operating_weights"]
    assert detail["debt_obligations"] == score["pillars"]["debt_obligations"]
    assert detail["pulse"] == score
    if expected_level == "operating_only":
        assert detail["operating_health"] is not None and detail["extended_health"] is None
        assert detail["history"][0]["health_score"] is None
        assert "extended_health" in item["missing_modules"]
    else:
        assert detail["operating_health"] is not None and detail["extended_health"] is not None
        assert score["health"] == score["extended_health"]
        if expected_level == "extended_bounded":
            assert item["identified_range"] == score["identified_range"]
            assert detail["debt_obligations"]["score_range"] == score["pillars"]["debt_obligations"]["score_range"]


def test_v11_missing_operating_pillar_keeps_both_healths_null():
    score, cash, envelope = _source(observed=False, composition=True)
    detail = company_detail(score, cash, None, envelope)
    assert detail["health_level"] is None
    assert detail["operating_health"] is None and detail["extended_health"] is None
    assert "operating_health" in detail["missing_modules"]
    assert "extended_health" in detail["missing_modules"]


@pytest.mark.parametrize("field", ["operating_health", "extended_health", "health_level", "missing_modules"])
def test_v11_rejects_tampered_composition_not_recomputed(field):
    score, cash, envelope = _source(composition=True)
    score[field] = ["debt_obligations"] if field == "missing_modules" else "tampered"
    with pytest.raises((ValueError, TypeError)):
        company_detail(score, cash, None, envelope)
