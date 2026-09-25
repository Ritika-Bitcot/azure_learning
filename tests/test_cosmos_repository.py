import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from app.models import Item, ItemCreate, ItemUpdate
from app.repository import (
    LIST_QUERY,
    CosmosItemRepository,
    DatabaseBusyError,
    ItemNotFoundError,
)
from tests.cosmos_doubles import AsyncIter

ITEM_ID = UUID("3f2b8c1e-8d4a-4c5e-9b1a-2f6d7e8a9b0c")
KEY = str(ITEM_ID)
SYSTEM_FIELDS = {"_rid": "r", "_etag": "e", "_ts": 1, "_self": "s", "_attachments": "a"}


def _doc(**overrides) -> dict:
    return {
        "id": KEY,
        "name": "Pen",
        "description": None,
        "price": 1.5,
        "created_at": "2026-01-01T00:00:00.000000Z",
        "updated_at": "2026-01-01T00:00:00.000000Z",
        **SYSTEM_FIELDS,
    } | overrides


def _not_found() -> CosmosResourceNotFoundError:
    return CosmosResourceNotFoundError(status_code=404, message="Not found")


def _throttled() -> CosmosHttpResponseError:
    return CosmosHttpResponseError(status_code=429, message="Too many requests")


def test_add_item_writes_json_document_and_strips_system_fields():
    container = MagicMock()
    container.create_item = AsyncMock(side_effect=lambda body: body | SYSTEM_FIELDS)
    item = Item.new(ItemCreate(name="Pen", price=1.5))

    result = asyncio.run(CosmosItemRepository(container).add_item(item))

    body = container.create_item.await_args.kwargs["body"]
    assert body == item.to_document() and body["created_at"].endswith("Z")
    assert result == item


def test_list_items_runs_ordered_cross_partition_query():
    container = MagicMock()
    container.query_items.return_value = AsyncIter([_doc()])

    result = asyncio.run(CosmosItemRepository(container).list_items(limit=7))

    container.query_items.assert_called_once_with(
        query=LIST_QUERY, parameters=[{"name": "@limit", "value": 7}]
    )
    assert "partition_key" not in container.query_items.call_args.kwargs
    assert LIST_QUERY == "SELECT TOP @limit * FROM c ORDER BY c.created_at DESC, c.id DESC"
    assert [i.id for i in result] == [ITEM_ID]


def test_get_item_is_a_point_read_on_its_own_partition():
    container = MagicMock()
    container.read_item = AsyncMock(return_value=_doc())

    result = asyncio.run(CosmosItemRepository(container).get_item(ITEM_ID))

    container.read_item.assert_awaited_once_with(item=KEY, partition_key=KEY)
    assert result.id == ITEM_ID


def test_update_item_patches_only_sent_fields_plus_updated_at():
    container = MagicMock()
    container.patch_item = AsyncMock(return_value=_doc(price=2.0))
    when = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)

    asyncio.run(CosmosItemRepository(container).update_item(ITEM_ID, ItemUpdate(price=2, description=None), when))

    container.patch_item.assert_awaited_once_with(
        item=KEY,
        partition_key=KEY,
        patch_operations=[
            {"op": "set", "path": "/description", "value": None},
            {"op": "set", "path": "/price", "value": 2.0},
            {"op": "set", "path": "/updated_at", "value": "2026-02-01T12:00:00.000000Z"},
        ],
    )


def test_delete_item_is_a_point_delete():
    container = MagicMock()
    container.delete_item = AsyncMock(return_value=None)

    asyncio.run(CosmosItemRepository(container).delete_item(ITEM_ID))

    container.delete_item.assert_awaited_once_with(item=KEY, partition_key=KEY)


@pytest.mark.parametrize(
    ("method", "call"),
    [
        ("read_item", lambda repo: repo.get_item(ITEM_ID)),
        ("patch_item", lambda repo: repo.update_item(ITEM_ID, ItemUpdate(price=1), datetime.now(timezone.utc))),
        ("delete_item", lambda repo: repo.delete_item(ITEM_ID)),
    ],
)
def test_not_found_maps_to_item_not_found(method, call):
    container = MagicMock()
    setattr(container, method, AsyncMock(side_effect=_not_found()))

    with pytest.raises(ItemNotFoundError):
        asyncio.run(call(CosmosItemRepository(container)))


def test_throttling_maps_to_database_busy():
    container = MagicMock()
    container.read_item = AsyncMock(side_effect=_throttled())

    with pytest.raises(DatabaseBusyError):
        asyncio.run(CosmosItemRepository(container).get_item(ITEM_ID))


def test_throttling_during_list_iteration_maps_to_database_busy():
    class ThrottledPager:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise _throttled()

    container = MagicMock()
    container.query_items.return_value = ThrottledPager()

    with pytest.raises(DatabaseBusyError):
        asyncio.run(CosmosItemRepository(container).list_items(limit=5))


def test_other_cosmos_errors_propagate():
    container = MagicMock()
    container.read_item = AsyncMock(side_effect=CosmosHttpResponseError(status_code=500, message="boom"))

    with pytest.raises(CosmosHttpResponseError):
        asyncio.run(CosmosItemRepository(container).get_item(ITEM_ID))
