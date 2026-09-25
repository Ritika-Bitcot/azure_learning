from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from azure.cosmos.aio import ContainerProxy
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from app.models import Item, ItemUpdate, format_utc

# Newest first; id breaks ties so the order is fully deterministic.
# Needs the composite index in infra/cosmos-index-policy.json.
LIST_QUERY = "SELECT TOP @limit * FROM c ORDER BY c.created_at DESC, c.id DESC"


class ItemNotFoundError(Exception):
    def __init__(self, item_id: UUID) -> None:
        super().__init__(f"Item {item_id} not found")
        self.item_id = item_id


class DatabaseBusyError(Exception):
    """Cosmos kept returning 429 after the SDK's built-in retries."""


class ItemRepository(Protocol):
    async def add_item(self, item: Item) -> Item: ...
    async def list_items(self, limit: int) -> list[Item]: ...
    async def get_item(self, item_id: UUID) -> Item: ...
    async def update_item(self, item_id: UUID, update: ItemUpdate, updated_at: datetime) -> Item: ...
    async def delete_item(self, item_id: UUID) -> None: ...


@contextmanager
def _cosmos_errors(item_id: UUID | None = None) -> Iterator[None]:
    try:
        yield
    except CosmosResourceNotFoundError as exc:
        if item_id is None:
            raise
        raise ItemNotFoundError(item_id) from exc
    except CosmosHttpResponseError as exc:
        if exc.status_code == 429:
            raise DatabaseBusyError() from exc
        raise


class CosmosItemRepository:
    """Items stored one per logical partition (partition key /id)."""

    def __init__(self, container: ContainerProxy) -> None:
        self._container = container

    async def add_item(self, item: Item) -> Item:
        with _cosmos_errors():
            doc = await self._container.create_item(body=item.to_document())
        return Item.model_validate(doc)

    async def list_items(self, limit: int) -> list[Item]:
        # No partition_key -> the SDK runs a cross-partition query.
        with _cosmos_errors():
            pager = self._container.query_items(
                query=LIST_QUERY, parameters=[{"name": "@limit", "value": limit}]
            )
            return [Item.model_validate(doc) async for doc in pager]

    async def get_item(self, item_id: UUID) -> Item:
        key = str(item_id)
        with _cosmos_errors(item_id):
            doc = await self._container.read_item(item=key, partition_key=key)
        return Item.model_validate(doc)

    async def update_item(self, item_id: UUID, update: ItemUpdate, updated_at: datetime) -> Item:
        key = str(item_id)
        operations = [
            {"op": "set", "path": f"/{field}", "value": value}
            for field, value in update.changes().items()
        ]
        operations.append({"op": "set", "path": "/updated_at", "value": format_utc(updated_at)})
        with _cosmos_errors(item_id):
            doc = await self._container.patch_item(
                item=key, partition_key=key, patch_operations=operations
            )
        return Item.model_validate(doc)

    async def delete_item(self, item_id: UUID) -> None:
        key = str(item_id)
        with _cosmos_errors(item_id):
            await self._container.delete_item(item=key, partition_key=key)
