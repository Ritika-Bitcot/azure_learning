import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

CONFIGURED = Settings(cosmos_endpoint="https://fake.documents.azure.com:443/", cosmos_key="fake-key")
NOT_CONFIGURED = Settings(cosmos_endpoint="", cosmos_key="")


@pytest.fixture
def client():
    with TestClient(create_app(CONFIGURED)) as test_client:
        yield test_client


@pytest.fixture
def unconfigured_client():
    with TestClient(create_app(NOT_CONFIGURED)) as test_client:
        yield test_client
