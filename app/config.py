from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiKeyConfig(BaseModel):
    client: str
    # None = nyckeln får skriva till alla source_types
    source_types: list[str] | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_")

    database_url: str = "postgresql://localhost:5432/environment_inventory"
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10
    max_request_body_bytes: int = 1_000_000
    # X-API-Key -> vilket klientsystem nyckeln tillhör och vilka source_types
    # den får skriva till. Sätts via APP_API_KEYS som en JSON-sträng.
    api_keys: dict[str, ApiKeyConfig] = {}
    # origins som frontend-appen (Vite dev-server m.fl.) tillåts anropa API:et från
    cors_allowed_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
