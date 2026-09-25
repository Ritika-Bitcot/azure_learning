from fastapi import Request

from app.repository import CosmosItemRepository, ItemRepository


def get_repository(request: Request) -> ItemRepository:
    return CosmosItemRepository(request.app.state.cosmos.get_container())
