def test_search_audits_scores_and_persists(client, auth_headers, stub_places):
    r = client.post("/api/search", json={"category": "plumbers", "city": "Orlando, FL"}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    assert data["searches_used"] == 1
    # Sorted by score, every lead carries an audit + score.
    scores = [l["score"] for l in data["leads"]]
    assert scores == sorted(scores, reverse=True)
    assert all(l["score"] is not None and l["audit"] for l in data["leads"])

    # Persisted to the pipeline.
    leads = client.get("/api/leads", headers=auth_headers).json()
    assert len(leads) == 2


def test_search_requires_places_key_when_unstubbed(client, auth_headers):
    # No stub + no API key configured -> clear 503.
    r = client.post("/api/search", json={"category": "x", "city": "y"}, headers=auth_headers)
    assert r.status_code == 503


def test_starter_search_limit_enforced(client, auth_headers, stub_places):
    for _ in range(10):
        assert client.post("/api/search", json={"category": "x", "city": "y"}, headers=auth_headers).status_code == 200
    r = client.post("/api/search", json={"category": "x", "city": "y"}, headers=auth_headers)
    assert r.status_code == 402


def test_pipeline_update_filter_and_csv(client, auth_headers, stub_places):
    client.post("/api/search", json={"category": "plumbers", "city": "Orlando"}, headers=auth_headers)
    lead_id = client.get("/api/leads", headers=auth_headers).json()[0]["id"]

    upd = client.patch(f"/api/leads/{lead_id}", json={"status": "contacted", "notes": "called"}, headers=auth_headers)
    assert upd.status_code == 200 and upd.json()["status"] == "contacted"

    assert len(client.get("/api/leads?status=contacted", headers=auth_headers).json()) == 1
    assert client.patch(f"/api/leads/{lead_id}", json={"status": "bogus"}, headers=auth_headers).status_code == 422

    csv = client.get("/api/leads/export.csv", headers=auth_headers)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert "name,score,status" in csv.text


def test_pdf_report(client, auth_headers, stub_places):
    client.post("/api/search", json={"category": "plumbers", "city": "Orlando"}, headers=auth_headers)
    lead_id = client.get("/api/leads", headers=auth_headers).json()[0]["id"]
    r = client.get(f"/api/leads/{lead_id}/report.pdf", headers=auth_headers)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_watch_detects_new_leads(client, auth_headers, stub_places):
    w = client.post("/api/watches", json={"category": "plumbers", "city": "Orlando"}, headers=auth_headers)
    assert w.status_code == 201
    wid = w.json()["id"]

    # First scan establishes a baseline.
    first = client.post(f"/api/watches/{wid}/scan", headers=auth_headers).json()
    assert first["new_count"] == 0

    # A new business appears; second scan flags exactly that one.
    stub_places["results"].append(
        {"place_id": "p3", "name": "New Co", "address": "9 New St", "phone": "1", "website": None, "rating": 5.0, "review_count": 3}
    )
    second = client.post(f"/api/watches/{wid}/scan", headers=auth_headers).json()
    assert second["new_count"] == 1
    assert second["new_leads"][0]["name"] == "New Co"

    assert client.delete(f"/api/watches/{wid}", headers=auth_headers).status_code == 204
