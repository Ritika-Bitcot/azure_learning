from datetime import datetime
from uuid import UUID

from app.models import Item, ItemUpdate, format_utc
from app.repository import ItemNotFoundError


class InMemoryItemRepository:
    """Stores the same JSON documents Cosmos would, with the same ordering and PATCH rules."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    async def add_item(self, item: Item) -> Item:
        doc = item.to_document()
        self.docs[doc["id"]] = doc
        return Item.model_validate(doc)

    async def list_items(self, limit: int) -> list[Item]:
        ordered = sorted(self.docs.values(), key=lambda d: (d["created_at"], d["id"]), reverse=True)
        return [Item.model_validate(doc) for doc in ordered[:limit]]

    async def get_item(self, item_id: UUID) -> Item:
        return Item.model_validate(self._doc(item_id))

    async def update_item(self, item_id: UUID, update: ItemUpdate, updated_at: datetime) -> Item:
        doc = self._doc(item_id)
        doc.update(update.changes())
        doc["updated_at"] = format_utc(updated_at)
        return Item.model_validate(doc)

    async def delete_item(self, item_id: UUID) -> None:
        self._doc(item_id)
        del self.docs[str(item_id)]

    def _doc(self, item_id: UUID) -> dict:
        try:
            return self.docs[str(item_id)]
        except KeyError:
            raise ItemNotFoundError(item_id) from None
