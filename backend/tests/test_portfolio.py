def ids(response):
    return [i["company_id"] for i in response.json()["items"]]


def test_portfolio_default_sorts_by_score_desc_with_nulls_last(client):
    r = client.get("/portfolio")
    assert r.status_code == 200 and r.json()["total"] == 3
    assert ids(r) == ["C1", "C2", "C3"]
    assert r.json()["items"][2]["score"] is None  # null preservado, nunca 0 ni 50


def test_portfolio_filters_sort_and_pagination(client):
    assert ids(client.get("/portfolio?trajectory=deteriorating")) == ["C2"]
    assert ids(client.get("/portfolio?score_status=not_scored")) == ["C3"]
    assert ids(client.get("/portfolio?group_id=G1&sort=score&order=asc")) == ["C2", "C1"]
    assert ids(client.get("/portfolio?min_score=50")) == ["C1"]
    assert ids(client.get("/portfolio?confidence_band=low")) == ["C3"]
    page = client.get("/portfolio?limit=1&offset=1")
    assert ids(page) == ["C2"] and page.json()["total"] == 3
    assert client.get("/portfolio?sort=bogus").status_code == 400
    assert client.get("/portfolio?limit=0").status_code == 422


def test_export_csv_and_alerts_placeholder(client):
    r = client.get("/export/latest.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "C1,80" in r.text
    r = client.get("/alerts")
    assert r.status_code == 200 and r.json() == {"available": False, "total": 0, "items": []}
