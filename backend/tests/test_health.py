import json

from app.store import MISSING_HINT  # noqa: F401  (documenta el mensaje esperado)
from tests.conftest import write_product


def test_health_reads_manifest(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["latest_month"] == "2026-08-01T00:00:00"
    assert body["git_commit"] == "abc123" and body["n_companies"] == 3 and body["method"] == "financial_smoothed_v2"
    assert r.headers["X-Xray-Manifest"] == body["manifest_sha256"]


def test_manifest_header_changes_after_reload_with_new_manifest(client, settings):
    before = client.get("/portfolio").headers["X-Xray-Manifest"]
    manifest = settings.product_dir / "_product_manifest.json"
    data = json.loads(manifest.read_text())
    data["created_at"] = "2026-09-20T00:00:00+00:00"
    manifest.write_text(json.dumps(data))
    assert client.post("/reload", headers={"X-Admin-Token": "bad"}).status_code == 401
    r = client.post("/reload", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200 and r.json()["reloaded"] and r.json()["manifest_sha256"] != before
    assert client.get("/portfolio").headers["X-Xray-Manifest"] == r.json()["manifest_sha256"]


def test_auto_refresh_when_manifest_hash_changes(client, settings):
    before = client.get("/health").json()["git_commit"]
    product = settings.product_dir
    for p in product.rglob("*"):
        if p.is_file():
            p.unlink()
    for d in ("companies", "groups"):
        (product / d).rmdir()
    write_product(product, git_commit="newcommit")
    assert before == "abc123" and client.get("/health").json()["git_commit"] == "newcommit"


def test_missing_artifacts_give_503_with_hint(tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        assert c.get("/health").json()["status"] == "degraded"
        r = c.get("/portfolio")
        assert r.status_code == 503 and "08_build_product.py" in r.json()["detail"]
