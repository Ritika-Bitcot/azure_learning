from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.cosmos_doubles import AsyncIter, fake_cosmos_client

CONFIGURED = Settings(cosmos_endpoint="https://fake.documents.azure.com:443/", cosmos_key="fake-key")


def test_app_reuses_one_client_and_closes_it_on_shutdown():
    container = MagicMock()
    container.query_items.side_effect = lambda **_: AsyncIter([])
    client_double = fake_cosmos_client(container)
    calls = []

    def factory(endpoint: str, key: str):
        calls.append((endpoint, key))
        return client_double

    with TestClient(create_app(CONFIGURED, factory)) as client:
        assert client.get("/api/items").json() == []
        assert client.get("/api/items").json() == []
        client_double.close.assert_not_awaited()

    assert len(calls) == 1
    client_double.close.assert_awaited_once()
