import logging
from collections.abc import Callable

from azure.cosmos.aio import ContainerProxy, CosmosClient

from app.config import Settings

logger = logging.getLogger(__name__)

ClientFactory = Callable[[str, str], CosmosClient]


def _default_client_factory(endpoint: str, key: str) -> CosmosClient:
    return CosmosClient(endpoint, credential=key)


class DatabaseNotConfiguredError(Exception):
    """COSMOS_ENDPOINT / COSMOS_KEY are not set."""


class CosmosClientManager:
    """One async CosmosClient per worker process, created on first use and reused.

    Creation is synchronous (no await between the None-check and the assignment),
    so concurrent first requests on the event loop cannot create two clients.
    """

    def __init__(self, settings: Settings, client_factory: ClientFactory | None = None) -> None:
        self._settings = settings
        self._client_factory = client_factory or _default_client_factory
        self._client: CosmosClient | None = None
        self._warned_not_configured = False

    def get_container(self) -> ContainerProxy:
        if self._client is None:
            if not self._settings.cosmos_configured:
                if not self._warned_not_configured:
                    logger.warning("COSMOS_ENDPOINT / COSMOS_KEY not set; item routes return 503")
                    self._warned_not_configured = True
                raise DatabaseNotConfiguredError()
            self._client = self._client_factory(
                self._settings.cosmos_endpoint, self._settings.cosmos_key
            )
        database = self._client.get_database_client(self._settings.cosmos_database)
        return database.get_container_client(self._settings.cosmos_container)

    async def close(self) -> None:
        """Idempotent, best-effort close.

        Under Azure Functions, AsgiFunctionApp triggers lifespan shutdown from
        __del__ via asyncio.run() - a different event loop than the one the client
        was created on - so a failure here is logged, not raised. Process exit
        releases the sockets anyway.
        """
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.close()
        except Exception:
            logger.warning("Failed to close Cosmos client cleanly", exc_info=True)
