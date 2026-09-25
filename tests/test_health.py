def test_health_when_configured(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "configured"}


def test_health_when_not_configured(unconfigured_client):
    response = unconfigured_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "not_configured"}
