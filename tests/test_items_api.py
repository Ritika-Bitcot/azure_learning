import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_repository
from app.main import create_app
from app.repository import DatabaseBusyError

MISSING_ID = "00000000-0000-4000-8000-000000000000"


def _create(client, **body):
    response = client.post("/api/items", json={"name": "Pen", "price": 1.5} | body)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_201_item_and_location(client):
    response = client.post("/api/items", json={"name": "Pen", "description": "Blue", "price": 1.5})
    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["id"]).version == 4
    assert body["name"] == "Pen" and body["description"] == "Blue" and body["price"] == 1.5
    assert body["created_at"].endswith("Z") and body["created_at"] == body["updated_at"]
    assert response.headers["location"] == f"/api/items/{body['id']}"


@pytest.mark.parametrize(
    "body",
    [
        {"price": 1},
        {"name": "", "price": 1},
        {"name": "   ", "price": 1},
        {"name": "x" * 101, "price": 1},
        {"name": "Pen", "price": -1},
        {"name": "Pen", "price": 1, "description": "x" * 1001},
        {"name": "Pen", "price": 1, "colour": "red"},
    ],
)
def test_create_rejects_invalid_body(client, body):
    assert client.post("/api/items", json=body).status_code == 422


def test_create_rejects_nan_price_sent_as_raw_json(client):
    response = client.post(
        "/api/items", content='{"name": "Pen", "price": NaN}', headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert "input" not in response.json()["detail"][0]


def test_get_returns_item(client):
    created = _create(client)
    response = client.get(f"/api/items/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_accepts_uppercase_uuid(client):
    created = _create(client)
    assert client.get(f"/api/items/{created['id'].upper()}").json() == created


def test_get_missing_returns_404(client):
    response = client.get(f"/api/items/{MISSING_ID}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_non_uuid_id_returns_422(client, method):
    kwargs = {"json": {"price": 1}} if method == "patch" else {}
    assert getattr(client, method)("/api/items/not-a-uuid", **kwargs).status_code == 422


def test_list_is_newest_first_with_id_tiebreak(client, repo):
    first, second = _create(client, name="A"), _create(client, name="B")
    tie_a, tie_b = _create(client, name="C"), _create(client, name="D")
    same_time = "2030-01-01T00:00:00.000000Z"
    repo.docs[tie_a["id"]]["created_at"] = same_time
    repo.docs[tie_b["id"]]["created_at"] = same_time
    newest_tie = sorted([tie_a["id"], tie_b["id"]], reverse=True)

    ids = [item["id"] for item in client.get("/api/items").json()]
    assert ids == [*newest_tie, second["id"], first["id"]]


def test_list_defaults_to_50_and_honours_limit(client):
    for i in range(55):
        _create(client, name=f"item-{i}")
    assert len(client.get("/api/items").json()) == 50
    assert len(client.get("/api/items?limit=3").json()) == 3


@pytest.mark.parametrize("limit", ["0", "101", "abc"])
def test_list_rejects_bad_limit(client, limit):
    assert client.get(f"/api/items?limit={limit}").status_code == 422


def test_patch_updates_only_sent_fields_and_refreshes_updated_at(client):
    created = _create(client, description="Blue")
    response = client.patch(f"/api/items/{created['id']}", json={"price": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["price"] == 2 and body["name"] == "Pen" and body["description"] == "Blue"
    assert body["created_at"] == created["created_at"]
    assert body["updated_at"] > created["updated_at"]


def test_patch_null_description_clears_it(client):
    created = _create(client, description="Blue")
    response = client.patch(f"/api/items/{created['id']}", json={"description": None})
    assert response.json()["description"] is None


@pytest.mark.parametrize("body", [{}, {"name": None}, {"price": None}, {"colour": "red"}])
def test_patch_rejects_invalid_body_and_leaves_item_unchanged(client, body):
    created = _create(client)
    assert client.patch(f"/api/items/{created['id']}", json=body).status_code == 422
    assert client.get(f"/api/items/{created['id']}").json() == created


def test_patch_missing_returns_404(client):
    assert client.patch(f"/api/items/{MISSING_ID}", json={"price": 2}).status_code == 404


def test_delete_returns_204_then_404(client):
    created = _create(client)
    response = client.delete(f"/api/items/{created['id']}")
    assert response.status_code == 204 and response.content == b""
    assert client.get(f"/api/items/{created['id']}").status_code == 404
    assert client.delete(f"/api/items/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/items"), ("post", "/api/items"), ("get", f"/api/items/{MISSING_ID}")],
)
def test_item_routes_return_503_when_not_configured(unconfigured_client, method, path):
    kwargs = {"json": {"name": "Pen", "price": 1}} if method == "post" else {}
    response = getattr(unconfigured_client, method)(path, **kwargs)
    assert response.status_code == 503
    assert response.json() == {"detail": "Database not configured"}


class _FailingRepository:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def list_items(self, limit: int):
        raise self._error


def _client_with_repo(repo) -> TestClient:
    app = create_app(Settings(cosmos_endpoint="https://x", cosmos_key="k"))
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def test_throttled_database_returns_503_with_retry_after():
    with _client_with_repo(_FailingRepository(DatabaseBusyError())) as client:
        response = client.get("/api/items")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.json() == {"detail": "Database busy, retry later"}


def test_unexpected_error_returns_generic_500(caplog):
    with _client_with_repo(_FailingRepository(RuntimeError("secret connection string"))) as client:
        response = client.get("/api/items")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "secret" not in response.text
    assert "Unhandled error on GET /api/items" in caplog.text


@pytest.mark.parametrize("price", [True, "3", "1.5"])
def test_create_rejects_non_numeric_price(client, price):
    assert client.post("/api/items", json={"name": "Pen", "price": price}).status_code == 422


def test_create_accepts_integer_price(client):
    assert client.post("/api/items", json={"name": "Pen", "price": 3}).json()["price"] == 3.0


def test_patch_rejects_boolean_price(client):
    created = _create(client)
    assert client.patch(f"/api/items/{created['id']}", json={"price": True}).status_code == 422
