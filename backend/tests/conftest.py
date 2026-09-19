import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

MONTH = "2026-08-01T00:00:00"


def row(company_id, group_id, score, trajectory="stable", status="scored", confidence=90.0, band="high", **extra):
    return {"company_id": company_id, "group_id": group_id, "currency": "EUR", "currencies": ["EUR"], "month": MONTH,
            "score": score, "level": score, "momentum": 50.0, "stability": None, "trajectory": trajectory, "episode": "none",
            "score_status": status, "score_reason": "ok" if status == "scored" else "short_history", "delta_vs_prev": None,
            "confidence": confidence, "confidence_band": band, "main_signal": None, "main_signal_delta": None, **extra}


def write_product(product_dir: Path, created_at="2026-09-19T00:00:00+00:00", git_commit="abc123"):
    companies = [row("C1", "G1", 80.0, "improving", delta_vs_prev=4.0), row("C2", "G1", 40.0, "deteriorating", delta_vs_prev=-6.0),
                 row("C3", "G2", None, "insufficient_history", status="not_scored", confidence=10.0, band="low")]
    (product_dir / "companies").mkdir(parents=True)
    (product_dir / "groups").mkdir()
    (product_dir / "portfolio.json").write_text(json.dumps({"latest_month": MONTH, "companies": companies}))
    for c in companies:
        timeline = [{"month": "2026-07-01T00:00:00", "score": None if c["score"] is None else c["score"] - 1, "confidence": 80.0},
                    {"month": MONTH, "score": c["score"], "confidence": c["confidence"]}]
        payload = {"company_id": c["company_id"], "group_id": c["group_id"], "latest_month": MONTH,
                   "currencies": {"EUR": {"timeline": timeline,
                                          "why_changed": {"month": MONTH, "terms": [{"feature": "op_margin_w", "rank": 1, "sentence": "x"}]},
                                          "confidence": {"confidence": c["confidence"]}}}}
        (product_dir / "companies" / f"{c['company_id']}.json").write_text(json.dumps(payload))
    for g in ("G1", "G2"):
        members = [c for c in companies if c["group_id"] == g]
        (product_dir / "groups" / f"{g}.json").write_text(json.dumps({"group_id": g, "n_companies": len(members), "companies": members}))
    (product_dir / "_product_manifest.json").write_text(json.dumps(
        {"created_at": created_at, "latest_month": MONTH, "inputs_sha256": {}, "code": {"git_commit": git_commit}}))


@pytest.fixture
def data_dir(tmp_path):
    write_product(tmp_path / "processed" / "product")
    scores = tmp_path / "processed" / "scores_v2"
    scores.mkdir(parents=True)
    (scores / "company_latest_scores.csv").write_text("company_id,score\nC1,80\n")
    (scores / "_company_score_reference.json").write_text("{}")
    return tmp_path


@pytest.fixture
def settings(data_dir):
    return Settings(data_dir=data_dir, cors_origins=("http://localhost:3000",), admin_token="secret")


@pytest.fixture
def fake_runner():
    calls = []

    def runner(commands, env, log_path: Path):
        calls.append({"commands": commands, "env": env})
        log_path.write_text("simulado\n")
        product = Path(env["XRAY_DATA_DIR"]) / "processed" / "product"
        write_product(product, git_commit="jobcommit")
    runner.calls = calls
    return runner


@pytest.fixture
def client(settings, fake_runner):
    with TestClient(create_app(settings, job_runner=fake_runner)) as c:
        yield c
