from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings read from environment variables (Function App settings in Azure).

    Every field has a default, so constructing Settings never fails - a missing
    Cosmos endpoint/key only surfaces as a 503 when an item route is called.
    """

    model_config = SettingsConfigDict(extra="ignore")

    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database: str = "appdb"
    cosmos_container: str = "items"

    @property
    def cosmos_configured(self) -> bool:
        return bool(self.cosmos_endpoint and self.cosmos_key)
