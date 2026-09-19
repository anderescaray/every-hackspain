def test_company_detail_is_file_plus_meta(client):
    r = client.get("/companies/C3")
    assert r.status_code == 200
    body = r.json()
    assert body["company_id"] == "C3" and body["meta"]["method"] == "financial_smoothed_v2" and body["meta"]["dataset"] == "main"
    assert body["currencies"]["EUR"]["timeline"][-1]["score"] is None
    assert client.get("/companies/NOPE").status_code == 404
    assert client.get("/companies/..%2F..%2Fportfolio").status_code == 404


def test_timeline_and_why_by_currency(client):
    r = client.get("/companies/C1/timeline")
    assert r.status_code == 200 and [p["score"] for p in r.json()] == [79.0, 80.0]
    assert client.get("/companies/C1/timeline?currency=USD").status_code == 400
    r = client.get("/companies/C1/why?currency=EUR")
    assert r.status_code == 200 and r.json()["terms"][0]["feature"] == "op_margin_w" and r.json()["currency"] == "EUR"


def test_group(client):
    r = client.get("/groups/G1")
    assert r.status_code == 200 and r.json()["n_companies"] == 2
    assert client.get("/groups/G9").status_code == 404
