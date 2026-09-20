"""Stress export preflight rejects mixed snapshots before any company JSON is written."""
import json

import pandas as pd
import pytest
from test_frontend_export import EVIDENCE, company

from xray.artifacts import recursive_hashes, sha256
from xray.product.frontend_export import _stress_snapshots, company_detail


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def snapshot(tmp_path):
    run = tmp_path / "runs" / "run-one"
    detail = {"as_of": "2026-08-31", "score_version": "financial_smoothed_v2", "baseline_health": 63.6,
              "exposures": {"company_id": "COMP_0001"}, "lineage": {"run_id": "run-one"}}
    _write(run / "companies" / "COMP_0001.json", detail)
    inputs = {"scores": "score-hash", "feature_manifest": "manifest-hash", "features": "feature-hash"}
    manifest = {"run_id": "run-one", "method": "v2_observed_window_stress_v1", "month": "2026-08-01",
                "company_count": 1, "inputs_sha256": inputs, "outputs_sha256": recursive_hashes(run)}
    _write(run / "manifest.json", manifest)
    _write(tmp_path / "latest.json", {"run_id": "run-one", "manifest_sha256": sha256(run / "manifest.json")})
    product = {"scores": "score-hash", "feature_manifest": "manifest-hash",
               "feature_artifact:company_monthly_features.parquet": "feature-hash"}
    return run, product


def test_export_preflights_immutable_stress_hashes_and_v2_sources(tmp_path):
    run, product = snapshot(tmp_path)
    found_run, manifest, docs = _stress_snapshots(tmp_path, pd.Timestamp("2026-08-01"), product)
    assert found_run == run and manifest["company_count"] == 1
    assert docs["COMP_0001"]["baseline_health"] == 63.6
    with pytest.raises(ValueError, match="different V2/features"):
        _stress_snapshots(tmp_path, pd.Timestamp("2026-08-01"), {**product, "scores": "wrong"})
    (run / "companies" / "COMP_0001.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity check"):
        _stress_snapshots(tmp_path, pd.Timestamp("2026-08-01"), product)


def test_export_requires_explicit_stress_run(tmp_path):
    with pytest.raises(FileNotFoundError, match="10b_build_stress"):
        _stress_snapshots(tmp_path, pd.Timestamp("2026-08-01"), {})


def test_company_detail_never_recomputes_stress_baseline():
    source = company([63.6])
    stress = {"as_of": "2026-01-31", "score_version": "financial_smoothed_v2", "baseline_health": 63.6,
              "exposures": {"company_id": "COMP_0001"}, "scenarios": []}
    detail = company_detail(source, None, EVIDENCE, stress=stress)
    assert detail["stress_test"]["baseline_health"] == 63.6
    assert detail["stress_test"]["scenarios"] == []
    with pytest.raises(ValueError, match="baseline mismatch"):
        company_detail(source, None, EVIDENCE, stress={**stress, "baseline_health": 60})
    with pytest.raises(ValueError, match="cutoff/method mismatch"):
        company_detail(source, None, EVIDENCE, stress={**stress, "as_of": "2026-02-28"})


def test_export_sanitizes_unavailable_scenarios_and_unit_shares():
    source = company([63.6])
    stress = {
        "as_of": "2026-01-31", "score_version": "financial_smoothed_v2", "baseline_health": 63.6,
        "exposures": {"company_id": "COMP_0001", "costs": {"category_gates": {"other_operating_payment": {
            "status": "unavailable", "reason": "x", "amount_6m": 1, "share_of_outflow": 1.0000000000000002,
            "score_runnable": False}}}},
        "scenarios": [{"id": "preset_severe", "status": "unavailable", "results": [{"observed_months": 1}],
                       "path": [{"observed_months": 1, "health": 50, "band": "amber"}],
                       "band_crossing_horizon": 3}],
    }
    detail = company_detail(source, None, EVIDENCE, stress=stress)["stress_test"]
    scenario = detail["scenarios"][0]
    assert scenario["results"] == [] and scenario["path"] == [] and scenario["band_crossing_horizon"] is None
    assert detail["exposures"]["costs"]["category_gates"]["other_operating_payment"]["share_of_outflow"] == 1.0
