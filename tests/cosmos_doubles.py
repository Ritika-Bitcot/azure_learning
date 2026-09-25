from unittest.mock import AsyncMock, MagicMock


class AsyncIter:
    """Stands in for the SDK's async pager returned by query_items."""

    def __init__(self, items: list[dict]) -> None:
        self._items = items

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item


def fake_cosmos_client(container: MagicMock | None = None) -> MagicMock:
    """A CosmosClient double: get_database_client().get_container_client() -> container."""
    client = MagicMock()
    client.close = AsyncMock()
    client.get_database_client.return_value.get_container_client.return_value = (
        container if container is not None else MagicMock()
    )
    return client
