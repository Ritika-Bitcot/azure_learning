import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings
from app.db import ClientFactory, CosmosClientManager, DatabaseNotConfiguredError
from app.repository import DatabaseBusyError, ItemNotFoundError
from app.routers import health, items

logger = logging.getLogger(__name__)


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
    api.include_router(items.router)
    app.include_router(api)

    _register_error_handlers(app)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Drop the echoed "input": it can hold NaN/Infinity (valid for Python's json
        # parser, not encodable in a response) and needlessly reflects client data.
        errors = [{k: v for k, v in error.items() if k != "input"} for error in exc.errors()]
        return JSONResponse(
            {"detail": jsonable_encoder(errors)}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        )

    @app.exception_handler(ItemNotFoundError)
    async def item_not_found(_: Request, __: ItemNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": "Item not found"}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(DatabaseNotConfiguredError)
    async def not_configured(_: Request, __: DatabaseNotConfiguredError) -> JSONResponse:
        return JSONResponse(
            {"detail": "Database not configured"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    @app.exception_handler(DatabaseBusyError)
    async def busy(_: Request, __: DatabaseBusyError) -> JSONResponse:
        logger.warning("Cosmos DB throttled the request (429) after SDK retries")
        return JSONResponse(
            {"detail": "Database busy, retry later"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "1"},
        )

    # Middleware (not an exception handler) so the 500 is returned without the
    # exception being re-raised to the Functions host.
    @app.middleware("http")
    async def unhandled_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            return JSONResponse(
                {"detail": "Internal server error"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
