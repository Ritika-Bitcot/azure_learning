import re
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import Item, ItemCreate, ItemUpdate, format_utc

UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def _item_doc(**overrides) -> dict:
    doc = {
        "id": "3f2b8c1e-8d4a-4c5e-9b1a-2f6d7e8a9b0c",
        "name": "Pen",
        "description": None,
        "price": 1.5,
        "created_at": "2026-01-01T00:00:00.000000Z",
        "updated_at": "2026-01-01T00:00:00.000000Z",
    }
    return doc | overrides


def test_new_item_serialises_timestamps_as_fixed_width_utc():
    doc = Item.new(ItemCreate(name="Pen", price=1.5)).to_document()
    assert UTC_RE.match(doc["created_at"])
    assert doc["created_at"] == doc["updated_at"]


def test_format_utc_keeps_six_fraction_digits_when_microseconds_are_zero():
    assert format_utc(datetime(2026, 1, 1, tzinfo=timezone.utc)) == "2026-01-01T00:00:00.000000Z"


def test_offset_datetime_is_normalised_to_utc():
    item = Item.model_validate(_item_doc(created_at="2026-01-01T05:30:00+05:30"))
    assert item.to_document()["created_at"] == "2026-01-01T00:00:00.000000Z"


def test_naive_datetime_is_rejected():
    with pytest.raises(ValidationError):
        Item.model_validate(_item_doc(created_at="2026-01-01T00:00:00"))


def test_cosmos_system_fields_are_dropped():
    item = Item.model_validate(_item_doc(_rid="r", _etag="e", _ts=1, _self="s", _attachments="a"))
    assert set(item.to_document()) == {"id", "name", "description", "price", "created_at", "updated_at"}


def test_item_create_strips_name_and_rejects_blank():
    assert ItemCreate(name="  Pen  ", price=1).name == "Pen"
    with pytest.raises(ValidationError):
        ItemCreate(name="   ", price=1)


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -0.01])
def test_item_create_rejects_bad_price(price):
    with pytest.raises(ValidationError):
        ItemCreate(name="Pen", price=price)


def test_item_update_changes_only_contains_sent_fields():
    assert ItemUpdate(price=2).changes() == {"price": 2.0}


def test_item_update_allows_clearing_description():
    assert ItemUpdate(description=None).changes() == {"description": None}


def test_item_update_rejects_empty():
    with pytest.raises(ValidationError, match="At least one field must be provided"):
        ItemUpdate()


@pytest.mark.parametrize("field", ["name", "price"])
def test_item_update_rejects_null_for_required_fields(field):
    with pytest.raises(ValidationError, match=f"{field} cannot be null"):
        ItemUpdate(**{field: None})
