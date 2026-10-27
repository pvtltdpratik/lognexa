"""API tests against an in-memory database seeded with a small synthetic dataset."""


def _error(resp, status, code):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["error"]["code"] == code
    return body["error"]


# --- health / analytics -----------------------------------------------------------
def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert body["counts"]["logs"] == 700


def test_overview_uses_real_counts(client):
    body = client.get("/analytics/overview").json()
    assert body["total_logs"] == 700
    assert sum(body["severity_counts"].values()) == 700
    assert len(body["hourly"]) == 24
    assert body["latest_run"]["status"] == "completed"


# --- logs --------------------------------------------------------------------
def test_logs_pagination(client):
    body = client.get("/logs", params={"page": 2, "page_size": 10}).json()
    assert body["page"] == 2 and len(body["items"]) == 10
    assert body["total"] == 700 and body["pages"] == 70


def test_logs_filters(client):
    body = client.get("/logs", params={"status": "failure", "page_size": 100}).json()
    assert body["total"] > 0
    assert all(i["status"] == "failure" for i in body["items"])
    crit = client.get("/logs", params={"severity": "critical", "page_size": 100}).json()
    assert all(i["severity"] == "critical" for i in crit["items"])


def test_logs_sort_by_risk(client):
    items = client.get("/logs", params={"sort": "risk_desc", "page_size": 20}).json()["items"]
    risks = [i["risk_score"] for i in items]
    assert risks == sorted(risks, reverse=True)


def test_logs_search(client):
    item = client.get("/logs", params={"page_size": 1}).json()["items"][0]
    body = client.get("/logs", params={"search": item["username"]}).json()
    assert all(i["username"] == item["username"] for i in body["items"])


def test_logs_invalid_params(client):
    _error(client.get("/logs", params={"page_size": 500}), 422, "validation_error")
    _error(client.get("/logs", params={"page": 0}), 422, "validation_error")
    _error(client.get("/logs", params={"severity": "extreme"}), 422, "validation_error")
    _error(client.get("/logs", params={"start": "not-a-date"}), 422, "validation_error")
    err = _error(
        client.get("/logs", params={"start": "2026-10-10T00:00:00", "end": "2026-10-01T00:00:00"}),
        422, "validation_error",
    )
    assert "end" in err["message"]


def test_log_detail_includes_risk_explanation(client):
    log_id = client.get("/logs", params={"sort": "risk_desc", "page_size": 1}).json()["items"][0]["id"]
    body = client.get(f"/logs/{log_id}").json()
    assert body["risk"]["triggered_rules"]
    assert body["risk"]["explanation"]
    assert body["user"]["username"] == body["username"]


def test_log_not_found(client):
    _error(client.get("/logs/999999"), 404, "not_found")


# --- risk scores -----------------------------------------------------------------
def test_risk_scores_filters(client):
    body = client.get("/risk-scores", params={"min_score": 50, "page_size": 100}).json()
    assert all(i["risk_score"] >= 50 for i in body["items"])
    _error(client.get("/risk-scores", params={"min_score": 80, "max_score": 10}), 422, "validation_error")
    _error(client.get("/risk-scores", params={"rule_code": "DROP TABLE"}), 422, "validation_error")


def test_risk_scores_rule_filter(client):
    body = client.get("/risk-scores", params={"rule_code": "R1A", "page_size": 100}).json()
    assert all("R1A" in i["rule_codes"] for i in body["items"])


def test_methodology_and_user_risk(client):
    m = client.get("/risk-scores/methodology").json()
    assert len(m["rules"]) >= 10 and m["severity_bands"][0]["severity"] == "critical"
    users = client.get("/risk-scores/users", params={"limit": 5}).json()
    assert len(users) == 5
    assert users[0]["max_risk"] >= users[-1]["max_risk"]


# --- alerts --------------------------------------------------------------------
def _first_open_alert(client):
    return client.get("/alerts", params={"status": "open", "page_size": 1}).json()["items"][0]


def test_alerts_list_and_detail(client):
    alert = _first_open_alert(client)
    detail = client.get(f"/alerts/{alert['id']}").json()
    assert detail["log"]["id"] == alert["log_id"]
    assert detail["risk"]["risk_score"] == alert["risk_score"]


def test_resolve_requires_note_and_analyst(client):
    alert = _first_open_alert(client)
    err = _error(client.patch(f"/alerts/{alert['id']}", json={"status": "resolved"}), 422, "validation_error")
    assert "resolution_note" in err["details"][0]["message"]
    _error(
        client.patch(f"/alerts/{alert['id']}", json={"status": "resolved", "resolution_note": "long enough note", "resolved_by": ""}),
        422, "validation_error",
    )
    _error(client.patch(f"/alerts/{alert['id']}", json={"status": "closed"}), 422, "validation_error")
    _error(client.patch(f"/alerts/{alert['id']}", json={"status": "open", "extra": 1}), 422, "validation_error")


def test_alert_lifecycle(client):
    alert = _first_open_alert(client)
    url = f"/alerts/{alert['id']}"
    assert client.patch(url, json={"status": "acknowledged"}).json()["status"] == "acknowledged"
    _error(client.patch(url, json={"status": "acknowledged"}), 409, "no_change")
    resolved = client.patch(url, json={"status": "resolved", "resolution_note": "Confirmed benign VPN login", "resolved_by": "Tester"}).json()
    assert resolved["status"] == "resolved" and resolved["resolved_by"] == "Tester" and resolved["resolved_at"]
    reopened = client.patch(url, json={"status": "open"}).json()
    assert reopened["status"] == "open" and reopened["resolved_at"] is None


def test_alert_not_found(client):
    _error(client.patch("/alerts/999999", json={"status": "open"}), 404, "not_found")


# --- analysis ------------------------------------------------------------------
def test_analyze_validation(client):
    _error(client.post("/analyze", json={"contamination": 0.9}), 422, "validation_error")
    _error(client.post("/analyze", json={"rule_weight": -1}), 422, "validation_error")
    _error(client.post("/analyze", json={"unknown": True}), 422, "validation_error")


def test_reanalysis_keeps_resolved_alerts(client):
    alert = _first_open_alert(client)
    client.patch(f"/alerts/{alert['id']}", json={"status": "resolved", "resolution_note": "Investigated and closed", "resolved_by": "Tester"})
    run = client.post("/analyze", json={"alert_threshold": 40}).json()
    assert run["status"] == "completed" and run["logs_analyzed"] == 700
    assert client.get(f"/alerts/{alert['id']}").json()["status"] == "resolved"
    assert "combined" in run["metrics"]
    assert client.get("/analyze/latest").json()["id"] == run["id"]


def test_dataset_generate_validation(client):
    _error(client.post("/dataset/generate", json={"n_users": 2}), 422, "validation_error")
    _error(client.post("/dataset/generate", json={"n_users": 100, "n_records": 300}), 422, "validation_error")


# --- empty database -------------------------------------------------------------
def test_empty_database_behaviour(empty_client):
    assert empty_client.get("/logs").json() == {"items": [], "total": 0, "page": 1, "page_size": 25, "pages": 0}
    assert empty_client.get("/analytics/overview").json()["total_logs"] == 0
    _error(empty_client.post("/analyze", json={}), 409, "no_data")
    _error(empty_client.get("/analyze/latest"), 404, "not_found")


def test_dataset_generate_on_empty_db(empty_client):
    body = empty_client.post("/dataset/generate", json={"seed": 3, "n_users": 12, "days": 3, "n_records": 300}).json()
    assert body["users"] == 12 and body["logs"] == 300
    assert body["analysis"]["status"] == "completed"
