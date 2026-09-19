"""Raw-to-JSON integration, reproducibility and immutable-publication tests."""
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from xray.artifacts import publish_immutable_run, recursive_hashes, sha256, verify_run
from xray.pulse.pipeline import _source_code, run


def raw_fixture(path: Path, *, currencies=("EUR",), future=False) -> Path:
    """Synthetic COMP_1084 fixture, not a replacement for the real-data demo."""
    path.mkdir(parents=True)
    company_id = "COMP_1084"
    tables = {
        "groups": pd.DataFrame([{"group_id": "GROUP_1"}]),
        "companies": pd.DataFrame([{"company_id": company_id, "group_id": "GROUP_1", "currency": "EUR",
                                     "country": "ES", "created_at": "2026-09-01"}]),
        "banking_products": pd.DataFrame([{"product_id": f"BANK_{currency}", "company_id": company_id,
                                           "currency": currency, "type": "checking", "label": "account",
                                           "service": "bank", "created_at": "2026-09-01"} for currency in currencies]),
        "debt_products": pd.DataFrame(columns=["product_id", "company_id", "currency", "type", "label", "service", "created_at"]),
        "debt_schedule_config": pd.DataFrame(columns=["product_id", "company_id", "amortization_type", "next_payment_date", "last_payment_date"]),
        "balances": pd.DataFrame(columns=["product_id", "company_id", "date", "balance", "available"]),
        "invoices": pd.DataFrame(columns=["operation_id", "company_id", "document_type", "issuance_date", "due_date", "payment_date",
                                           "amount", "pending_amount", "currency", "accounting_currency", "exchange_rate", "status", "concept", "counterparty_id"]),
    }
    transactions = []
    for currency in currencies:
        for month in range(1, 8):
            for kind, amount in (("collection", 1200 + month * 10), ("payment", -1000), ("debt_repayment", -25), ("interest_charge", -5)):
                tx_date = f"2026-{month:02}-10"
                transactions.append({"transaction_id": f"{currency}_{month}_{kind}", "company_id": company_id,
                                     "product_id": f"BANK_{currency}", "date": tx_date, "value_date": tx_date,
                                     "amount": float(amount), "exchange_rate": 1., "status": "booked", "category": kind,
                                     "description": f"{kind} {month}", "accounting_status": None, "counterparty_id": None})
        # A future booked twin MUST NOT erase this pending row in an old ledger.
        transactions.append({"transaction_id": f"{currency}_pending", "company_id": company_id,
                             "product_id": f"BANK_{currency}", "date": "2026-07-30", "value_date": "2026-07-30",
                             "amount": 17., "exchange_rate": 1., "status": "pending", "category": "collection",
                             "description": "future twin", "accounting_status": None, "counterparty_id": None})
        if future:
            transactions.append({**transactions[-1], "transaction_id": f"{currency}_future", "date": "2026-08-02",
                                 "value_date": "2026-08-02", "status": "booked"})
    tables["transactions"] = pd.DataFrame(transactions)
    for name, frame in tables.items():
        frame.to_csv(path / f"{name}.csv", index=False)
    return path


def _run(raw: Path, out: Path, **kwargs):
    return run(raw, out, as_of="2026-07-31", data_vintage="2026-09-01", verbose=False, **kwargs)


def _score(out: Path, manifest: dict, currency="EUR") -> dict:
    return json.loads((out / "runs" / manifest["run_id"] / "companies" / "COMP_1084" / currency / "score.json").read_text())


def test_raw_to_immutable_run_reconciles_and_repeats(tmp_path):
    raw = raw_fixture(tmp_path / "raw")
    source_hashes = recursive_hashes(raw)
    out = tmp_path / "out"
    first = _run(raw, out)
    run_dir = out / "runs" / first["run_id"]
    assert verify_run(run_dir) == first
    hashes = recursive_hashes(run_dir)
    assert "companies/COMP_1084/EUR/score.json" in first["outputs_sha256"]
    assert "companies/COMP_1084/EUR/cash_truth.json" in first["outputs_sha256"]
    assert "source_snapshot/transactions.parquet" in first["outputs_sha256"]
    score = _score(out, first)
    assert score["status"] == "complete"
    assert score["health"] == sum(p["health_contribution"] for p in score["pillars"].values())
    assert score["lineage"]["history_mode"] == "retrospective_restatement"
    assert score["lineage"]["knowledge_cutoff"] == "2026-09-01"
    assert score["change"]["previous_health"] is not None
    assert first["versions"]["facts_version"]
    assert first["versions"]["config_version"]
    assert _run(raw, out) == first
    assert hashes == recursive_hashes(run_dir)
    other = tmp_path / "other_destination"
    assert _run(raw, other) == first
    assert hashes == recursive_hashes(other / "runs" / first["run_id"])
    assert source_hashes == recursive_hashes(raw)
    pointer = json.loads((out / "latest.json").read_text())
    assert pointer["manifest_sha256"] == sha256(run_dir / "manifest.json")


def test_future_raw_twin_does_not_change_past_facts_or_pillars(tmp_path):
    raw_a = raw_fixture(tmp_path / "raw_a", future=False)
    raw_b = raw_fixture(tmp_path / "raw_b", future=True)
    out_a, out_b = tmp_path / "out_a", tmp_path / "out_b"
    first, future = _run(raw_a, out_a), _run(raw_b, out_b)
    score_a, score_b = _score(out_a, first), _score(out_b, future)
    assert score_a["pillars"] == score_b["pillars"]
    assert score_a["health"] == score_b["health"]
    assert first["lineage"]["input_hash"] == future["lineage"]["input_hash"]
    assert first["lineage"]["ledger_hash"] == future["lineage"]["ledger_hash"]
    assert first["lineage"]["facts_hash"] == future["lineage"]["facts_hash"]
    ledger = pd.read_parquet(out_b / "runs" / future["run_id"] / "ledger.parquet")
    assert "EUR_pending" in set(ledger.transaction_id)
    assert "EUR_future" not in set(ledger.transaction_id)


def test_currency_runs_do_not_overwrite_or_mix(tmp_path):
    raw = raw_fixture(tmp_path / "raw", currencies=("EUR", "USD"))
    out = tmp_path / "out"
    manifest = _run(raw, out)
    eur, usd = _score(out, manifest, "EUR"), _score(out, manifest, "USD")
    assert eur["currency"] == "EUR" and usd["currency"] == "USD"
    assert eur["health"] == usd["health"]
    portfolio = json.loads((out / "runs" / manifest["run_id"] / "portfolio.json").read_text())
    assert {r["currency"] for r in portfolio["companies"]} == {"EUR", "USD"}
    assert len(portfolio["companies"]) == 2
    assert all("evidence" not in row for row in portfolio["companies"])


def test_tampered_run_rejected_before_previous_comparison(tmp_path):
    raw = raw_fixture(tmp_path / "raw")
    out = tmp_path / "out"
    manifest = _run(raw, out)
    run_dir = out / "runs" / manifest["run_id"]
    (run_dir / "companies" / "COMP_1084" / "EUR" / "score.json").write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        _run(raw, out, previous_run=run_dir)


def _staged(path: Path, run_id: str, value="ok") -> Path:
    path.mkdir()
    (path / "nested").mkdir()
    (path / "nested" / "result.json").write_text(value)
    manifest = {"run_id": run_id, "outputs_sha256": recursive_hashes(path)}
    (path / "manifest.json").write_text(json.dumps(manifest))
    return path


def test_atomic_pointer_failure_keeps_previous_run(tmp_path, monkeypatch):
    out = tmp_path / "out"
    publish_immutable_run(_staged(tmp_path / "stage1", "run-1"), out, "run-1")
    before = (out / "latest.json").read_bytes()
    original_replace = os.replace

    def fail_pointer(source, target):
        if Path(target).name == "latest.json":
            raise OSError("simulated pointer failure")
        return original_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_pointer)
    with pytest.raises(OSError, match="simulated"):
        publish_immutable_run(_staged(tmp_path / "stage2", "run-2"), out, "run-2")
    assert (out / "latest.json").read_bytes() == before
    assert verify_run(out / "runs" / "run-1")
    assert verify_run(out / "runs" / "run-2")  # complete, merely unreferenced


def test_conflicting_immutable_run_and_unlisted_file_are_rejected(tmp_path):
    out = tmp_path / "out"
    publish_immutable_run(_staged(tmp_path / "stage1", "run-1"), out, "run-1")
    with pytest.raises(ValueError, match="conflict"):
        publish_immutable_run(_staged(tmp_path / "stage2", "run-1", "different"), out, "run-1")
    (out / "runs" / "run-1" / "unlisted.txt").write_text("unexpected")
    with pytest.raises(ValueError, match="integrity"):
        verify_run(out / "runs" / "run-1")


def test_code_identity_has_no_git_or_docs_dependency():
    source = _source_code()
    assert "git_commit" not in source
    assert all(not name.endswith(".md") for name in source["source_sha256"])
    assert "pulse/scorer.py" in source["source_sha256"]
    assert "ledger/classify.py" in source["source_sha256"]


def test_source_vintage_required_and_invalid_dates_fail(tmp_path):
    raw = raw_fixture(tmp_path / "raw")
    with pytest.raises(ValueError, match="predate"):
        run(raw, tmp_path / "out", as_of="2026-07-31", data_vintage="2026-01-01")
    frame = pd.read_csv(raw / "transactions.csv")
    frame.loc[0, "date"] = "not-a-date"
    frame.to_csv(raw / "transactions.csv", index=False)
    with pytest.raises(ValueError, match="invalid required dates"):
        _run(raw, tmp_path / "out")


def test_cached_classification_evidence_is_explicit_and_snapshotted(tmp_path):
    raw = raw_fixture(tmp_path / "raw")
    cache = tmp_path / "categories.parquet"
    pd.DataFrame([{"tpl": "NO MATCH", "sign": 1, "jev_block": "operating_inflow",
                   "jev_confidence": 0.9, "sign_conflict": False}]).to_parquet(cache, index=False)
    out = tmp_path / "out"
    manifest = _run(raw, out, ai_categories_path=cache)
    stored = out / "runs" / manifest["run_id"] / "classification_evidence" / "template_categories.parquet"
    assert sha256(stored) == sha256(cache)
    assert manifest["classification_evidence_hash"] == sha256(cache)
    assert _score(out, manifest)["classification_version"].startswith("cash-truth-v1+jev-")
    assert "classification_evidence/template_categories.parquet" in manifest["outputs_sha256"]


def test_company_without_observed_months_has_missing_not_zero_health(tmp_path):
    raw = raw_fixture(tmp_path / "raw")
    transactions = pd.read_csv(raw / "transactions.csv").iloc[:0]
    transactions.to_csv(raw / "transactions.csv", index=False)
    out = tmp_path / "out"
    manifest = _run(raw, out)
    score = _score(out, manifest)
    assert score["health"] is None
    assert score["status"] == "partial"
    assert score["known_weight"] == 0
    assert score["health_min"] == 0 and score["health_max"] == 100
    assert len(score["missing_components"]) == 4


def test_company_selection_preserves_group_counterlegs_before_cleaning(tmp_path):
    raw = raw_fixture(tmp_path / "raw")
    companies = pd.read_csv(raw / "companies.csv")
    companies = pd.concat([companies, companies.assign(company_id="PEER")], ignore_index=True)
    companies.to_csv(raw / "companies.csv", index=False)
    products = pd.read_csv(raw / "banking_products.csv")
    products = pd.concat([products, products.assign(company_id="PEER", product_id="PEER_BANK")], ignore_index=True)
    products.to_csv(raw / "banking_products.csv", index=False)
    tx = pd.read_csv(raw / "transactions.csv")
    receipt = {**tx.iloc[0].to_dict(), "transaction_id": "GROUP_RECEIPT", "date": "2026-07-21", "value_date": "2026-07-21", "amount": 777.}
    counterleg = {**receipt, "transaction_id": "GROUP_PAYMENT", "company_id": "PEER", "product_id": "PEER_BANK", "amount": -777., "category": "payment"}
    pd.concat([tx, pd.DataFrame([receipt, counterleg])], ignore_index=True).to_csv(raw / "transactions.csv", index=False)
    selected_out, all_out = tmp_path / "selected", tmp_path / "all"
    selected = _run(raw, selected_out, company_ids=["COMP_1084"])
    complete = _run(raw, all_out)
    ledger = pd.read_parquet(selected_out / "runs" / selected["run_id"] / "ledger.parquet").set_index("transaction_id")
    assert ledger.loc["GROUP_RECEIPT", "economic_class"] == "group_or_internal"
    assert "GROUP_PAYMENT" in ledger.index
    assert _score(selected_out, selected)["pillars"] == _score(all_out, complete)["pillars"]
    assert selected["rows"]["scores"] == 1


def test_product_replays_feature_manifest_classification_and_rejects_cache_mutation(tmp_path):
    from xray.artifacts import cash_classification_manifest
    from xray.product.bundle import cash_truth_classification_config

    cache = tmp_path / "cache.parquet"
    cache.write_bytes(b"frozen evidence")
    output = tmp_path / "features.parquet"
    output.write_bytes(b"frozen features")
    manifest = {"config": {"ai_categories_path": str(cache), "ai_min_confidence": .8,
                            "end_month": "2026-07-01"}, "ai_categories_sha256": sha256(cache),
                "classification": cash_classification_manifest(cache, .8),
                "outputs_sha256": {"features.parquet": sha256(output)}}
    (tmp_path / "_feature_manifest.json").write_text(json.dumps(manifest))
    kwargs, inputs = cash_truth_classification_config(tmp_path)
    assert kwargs["ai_categories_path"] == cache
    assert kwargs["ai_min_confidence"] == .8
    assert kwargs["stop"] == pd.Timestamp("2026-08-01")
    assert inputs["ai_categories"] == cache
    cache.write_bytes(b"new evidence")
    with pytest.raises(ValueError, match="differs"):
        cash_truth_classification_config(tmp_path)


def test_product_rejects_precanonical_and_mismatched_feature_sources(tmp_path):
    from xray.artifacts import cash_classification_manifest
    from xray.product.bundle import cash_truth_classification_config

    feature_dir, cleaned_dir = tmp_path / "features", tmp_path / "cleaned"
    feature_dir.mkdir()
    cleaned_dir.mkdir()
    feature, cleaned = feature_dir / "features.parquet", cleaned_dir / "transactions.parquet"
    feature.write_bytes(b"features")
    cleaned.write_bytes(b"cleaned")
    manifest = {"config": {"end_month": "2026-07-01"}, "classification": cash_classification_manifest(),
                "outputs_sha256": {feature.name: sha256(feature)}, "inputs_sha256": {cleaned.name: sha256(cleaned)}}
    manifest_path = feature_dir / "_feature_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    cash_truth_classification_config(feature_dir, cleaned_dir=cleaned_dir)
    cleaned.write_bytes(b"changed snapshot")
    with pytest.raises(ValueError, match="Cleaned input"):
        cash_truth_classification_config(feature_dir, cleaned_dir=cleaned_dir)
    cleaned.write_bytes(b"cleaned")
    feature.write_bytes(b"changed feature")
    with pytest.raises(ValueError, match="Feature artifact"):
        cash_truth_classification_config(feature_dir, cleaned_dir=cleaned_dir)
    manifest.pop("classification")
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Pre-canonical"):
        cash_truth_classification_config(feature_dir, cleaned_dir=cleaned_dir)
