from app.main import create_app


def test_openapi_lists_exactly_the_api_routes():
    assert set(create_app().openapi()["paths"]) == {"/api/health", "/api/items", "/api/items/{item_id}"}


def test_openapi_documents_timestamps_as_date_time(client):
    properties = client.get("/api/openapi.json").json()["components"]["schemas"]["Item"]["properties"]
    for field in ("created_at", "updated_at"):
        assert properties[field]["type"] == "string"
        assert properties[field]["format"] == "date-time"


def test_items_are_unreachable_without_the_api_prefix(client):
    assert client.get("/items").status_code == 404
