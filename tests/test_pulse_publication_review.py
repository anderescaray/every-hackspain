"""Independent checks of immutable publication and exported traceability."""
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from test_pulse_engine import score
from test_pulse_pipeline import _run, _staged, raw_fixture

from xray.artifacts import publish_immutable_run, recursive_hashes, verify_run
from xray.pulse.pipeline import _features_flat, _source_code


def test_failed_directory_publication_keeps_old_pointer_and_releases_lock(tmp_path, monkeypatch):
    output = tmp_path / "out"
    publish_immutable_run(_staged(tmp_path / "first", "run-first"), output, "run-first")
    before = (output / "latest.json").read_bytes()
    actual_rename = os.rename

    def fail_run(source, destination):
        if Path(destination).name == "run-second":
            raise OSError("simulated directory publication failure")
        return actual_rename(source, destination)

    monkeypatch.setattr(os, "rename", fail_run)
    with pytest.raises(OSError, match="publication failure"):
        publish_immutable_run(_staged(tmp_path / "second", "run-second"), output, "run-second")
    assert (output / "latest.json").read_bytes() == before
    assert verify_run(output / "runs" / "run-first")
    assert not (output / "runs" / "run-second").exists()
    monkeypatch.setattr(os, "rename", actual_rename)
    # The failed publisher cannot retain the advisory lock.
    publish_immutable_run(tmp_path / "second", output, "run-second")
    assert json.loads((output / "latest.json").read_text())["run_id"] == "run-second"


def test_nested_symlink_is_rejected_without_touching_external_target(tmp_path):
    external = tmp_path / "external"
    external.write_text("unchanged")
    staged = _staged(tmp_path / "stage", "run-test")
    (staged / "nested" / "external").symlink_to(external)
    with pytest.raises(ValueError, match="Symbolic links"):
        recursive_hashes(staged)
    assert external.read_text() == "unchanged"


def test_symlinked_runs_directory_cannot_redirect_publication(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    output = tmp_path / "out"
    output.mkdir()
    (output / "runs").symlink_to(outside, target_is_directory=True)
    staged = _staged(tmp_path / "stage", "run-test")
    with pytest.raises(ValueError, match="[Ss]ymbolic link"):
        publish_immutable_run(staged, output, "run-test")
    assert list(outside.iterdir()) == []
    assert not (output / "latest.json").exists()


def test_flat_feature_window_retains_exact_month_keys():
    payload = score().to_dict()
    rows = _features_flat(payload)
    assert len(rows) == 4
    for row in rows:
        window = json.loads(row["window_json"])
        assert window["count"] == 6 and window["observed_months"] == 6
        assert window["months"][0] == "2026-01-01"
        assert window["end"] == "2026-06-30"
        assert json.loads(row["feature_json"])["window6m"] == window


def test_code_fingerprint_includes_cached_classification_implementation():
    sources = _source_code()["source_sha256"]
    assert "ledger/enrichment.py" in sources
    assert "pulse/config.py" in sources
    assert "clean/transactions.py" in sources


@pytest.mark.parametrize("field,value", [
    ("company_id", "../../escaped-company"),
    ("company_id", "absolute"),
    ("currency", "../escaped-currency"),
    ("currency", ".."),
])
def test_dataset_path_components_cannot_escape_staging(tmp_path, field, value):
    raw = raw_fixture(tmp_path / "raw")
    escaped = tmp_path / "escaped-company"
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("untouched")
    if value == "absolute":
        value = str(escaped)
    for path in raw.glob("*.csv"):
        frame = pd.read_csv(path)
        if field in frame:
            frame[field] = value
            frame.to_csv(path, index=False)
    source_hashes = recursive_hashes(raw)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="Unsafe company/currency path segment"):
        _run(raw, out)
    assert not escaped.exists()
    assert not (out / "latest.json").exists()
    assert not list(out.glob(".pulse-stage-*"))
    assert sentinel.read_text() == "untouched"
    assert recursive_hashes(raw) == source_hashes
