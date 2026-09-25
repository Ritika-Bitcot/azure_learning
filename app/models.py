from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    model_validator,
)

UTC_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    """Fixed-width UTC string, e.g. 2026-09-25T10:15:30.123456Z (sorts chronologically)."""
    return value.astimezone(timezone.utc).strftime(UTC_FORMAT)


UtcDatetime = Annotated[
    AwareDatetime,
    AfterValidator(lambda value: value.astimezone(timezone.utc)),
    PlainSerializer(format_utc, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    price: float = Field(ge=0, allow_inf_nan=False)


class ItemUpdate(BaseModel):
    """Partial update: only fields the client sends are applied (exclude_unset)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    price: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def check_fields(self) -> "ItemUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        for field in ("name", "price"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    def changes(self) -> dict:
        """JSON-ready dict of only the fields the client sent."""
        return self.model_dump(mode="json", exclude_unset=True)


class Item(BaseModel):
    # extra="ignore" drops Cosmos system fields (_rid, _etag, _ts, _self, _attachments).
    model_config = ConfigDict(extra="ignore")

    id: UUID
    name: str
    description: str | None
    price: float
    created_at: UtcDatetime
    updated_at: UtcDatetime

    @classmethod
    def new(cls, data: ItemCreate) -> "Item":
        now = utc_now()
        return cls(id=uuid4(), created_at=now, updated_at=now, **data.model_dump())

    def to_document(self) -> dict:
        """The exact JSON document stored in Cosmos."""
        return self.model_dump(mode="json")
