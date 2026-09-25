from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.dependencies import get_repository
from app.models import Item, ItemCreate, ItemUpdate, utc_now
from app.repository import ItemRepository

router = APIRouter(prefix="/items", tags=["items"])

Repository = Annotated[ItemRepository, Depends(get_repository)]


@router.post("", response_model=Item, status_code=status.HTTP_201_CREATED)
async def create_item(data: ItemCreate, response: Response, repo: Repository) -> Item:
    item = await repo.add_item(Item.new(data))
    response.headers["Location"] = f"/api/items/{item.id}"
    return item


@router.get("", response_model=list[Item])
async def list_items(repo: Repository, limit: Annotated[int, Query(ge=1, le=100)] = 50) -> list[Item]:
    return await repo.list_items(limit)


@router.get("/{item_id}", response_model=Item)
async def get_item(item_id: UUID, repo: Repository) -> Item:
    return await repo.get_item(item_id)


@router.patch("/{item_id}", response_model=Item)
async def update_item(item_id: UUID, data: ItemUpdate, repo: Repository) -> Item:
    return await repo.update_item(item_id, data, utc_now())


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: UUID, repo: Repository) -> Response:
    await repo.delete_item(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
