from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    database: Literal["configured", "not_configured"]


@router.get("/health", response_model=Health)
async def health(request: Request) -> Health:
    """Liveness only: reports whether Cosmos settings exist, never calls Cosmos."""
    configured = request.app.state.settings.cosmos_configured
    return Health(status="ok", database="configured" if configured else "not_configured")
