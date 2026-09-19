import time

from app.jobs import RAW_FILES


def upload_files():
    return [("files", (name, b"a,b\n1,2\n", "text/csv")) for name in RAW_FILES]


def wait_done(client, job_id, timeout=5):
    for _ in range(int(timeout * 20)):
        job = client.get(f"/import/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job no terminó")


def test_import_job_runs_pipeline_with_isolated_data_dir(client, settings, fake_runner):
    r = client.post("/import", files=upload_files())
    assert r.status_code == 202 and r.json()["status"] in ("queued", "running", "done")
    job = wait_done(client, r.json()["job_id"])
    assert job["status"] == "done" and job["artifacts_dir"].endswith("processed/product") and "simulado" in job["log_tail"]
    call = fake_runner.calls[0]
    assert call["env"]["XRAY_DATA_DIR"] == str(settings.uploads_dir / job["job_id"])
    scripts = [" ".join(c) for c in call["commands"]]
    assert "00_clean_data.py" in scripts[0] and "predict" in scripts[2] and "_company_score_reference.json" in scripts[2]
    assert "fit" not in scripts[2] and "08_build_product.py" in scripts[3]
    assert (settings.uploads_dir / job["job_id"] / "raw" / "transactions.csv").exists()
    # el dataset del job se consulta con ?dataset=, sin tocar el principal
    r = client.get(f"/portfolio?dataset={job['job_id']}")
    assert r.status_code == 200 and r.headers["X-Xray-Dataset"] == job["job_id"]
    assert client.get(f"/health?dataset={job['job_id']}").json()["git_commit"] == "jobcommit"
    assert client.get("/health").json()["git_commit"] == "abc123"


def test_import_validates_files_and_unknown_job(client):
    r = client.post("/import", files=upload_files()[:2])
    assert r.status_code == 400 and "Faltan" in r.json()["detail"]
    assert client.get("/import/nope").status_code == 404
    assert client.get("/portfolio?dataset=nope").status_code == 404
