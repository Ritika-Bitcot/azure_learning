import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_repository
from app.main import create_app
from tests.fakes import InMemoryItemRepository

CONFIGURED = Settings(cosmos_endpoint="https://fake.documents.azure.com:443/", cosmos_key="fake-key")
NOT_CONFIGURED = Settings(cosmos_endpoint="", cosmos_key="")


@pytest.fixture
def repo() -> InMemoryItemRepository:
    return InMemoryItemRepository()


@pytest.fixture
def client(repo):
    app = create_app(CONFIGURED)
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def unconfigured_client():
    with TestClient(create_app(NOT_CONFIGURED)) as test_client:
        yield test_client
