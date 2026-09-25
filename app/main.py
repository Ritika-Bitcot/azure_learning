from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.config import Settings
from app.db import ClientFactory, CosmosClientManager
from app.routers import health


def create_app(settings: Settings | None = None, client_factory: ClientFactory | None = None) -> FastAPI:
    settings = settings or Settings()
    cosmos = CosmosClientManager(settings, client_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await cosmos.close()

    # host.json sets routePrefix "" so FastAPI owns the whole /api path.
    app = FastAPI(
        title="Items API",
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.cosmos = cosmos

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    app.include_router(api)

    return app
