import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.db import CosmosClientManager, DatabaseNotConfiguredError
from tests.cosmos_doubles import fake_cosmos_client

CONFIGURED = Settings(
    cosmos_endpoint="https://fake.documents.azure.com:443/",
    cosmos_key="fake-key",
    cosmos_database="appdb",
    cosmos_container="items",
)


class CountingFactory:
    def __init__(self, client: MagicMock | None = None) -> None:
        self.client = client or fake_cosmos_client()
        self.calls: list[tuple[str, str]] = []

    def __call__(self, endpoint: str, key: str) -> MagicMock:
        self.calls.append((endpoint, key))
        return self.client


def test_not_configured_raises_and_warns_once(caplog):
    factory = CountingFactory()
    manager = CosmosClientManager(Settings(cosmos_endpoint="", cosmos_key=""), factory)

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            with pytest.raises(DatabaseNotConfiguredError):
                manager.get_container()

    assert factory.calls == []
    assert caplog.text.count("COSMOS_ENDPOINT / COSMOS_KEY not set") == 1


def test_client_is_created_once_and_reused():
    factory = CountingFactory()
    manager = CosmosClientManager(CONFIGURED, factory)

    first, second = manager.get_container(), manager.get_container()

    assert factory.calls == [("https://fake.documents.azure.com:443/", "fake-key")]
    assert first is second
    factory.client.get_database_client.assert_called_with("appdb")
    factory.client.get_database_client.return_value.get_container_client.assert_called_with("items")


def test_concurrent_first_use_creates_one_client():
    factory = CountingFactory()
    manager = CosmosClientManager(CONFIGURED, factory)

    async def use() -> None:
        await asyncio.sleep(0)
        manager.get_container()

    async def main() -> None:
        await asyncio.gather(*(use() for _ in range(20)))

    asyncio.run(main())
    assert len(factory.calls) == 1


def test_close_is_idempotent_and_safe_before_first_use():
    factory = CountingFactory()
    manager = CosmosClientManager(CONFIGURED, factory)

    asyncio.run(manager.close())  # never created: no-op
    manager.get_container()
    asyncio.run(manager.close())
    asyncio.run(manager.close())

    factory.client.close.assert_awaited_once()


def test_close_failure_is_logged_not_raised(caplog):
    client = fake_cosmos_client()
    client.close = AsyncMock(side_effect=RuntimeError("different event loop"))
    manager = CosmosClientManager(CONFIGURED, CountingFactory(client))
    manager.get_container()

    asyncio.run(manager.close())

    assert "Failed to close Cosmos client cleanly" in caplog.text
