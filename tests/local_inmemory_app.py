"""The API backed by an in-memory store, for exercising infra/smoke.sh locally:

    .venv/bin/uvicorn tests.local_inmemory_app:app --port 8000
    ./infra/smoke.sh http://localhost:8000
"""

from app.config import Settings
from app.dependencies import get_repository
from app.main import create_app
from tests.fakes import InMemoryItemRepository

repository = InMemoryItemRepository()
app = create_app(Settings(cosmos_endpoint="https://in-memory.invalid", cosmos_key="in-memory"))
app.dependency_overrides[get_repository] = lambda: repository
