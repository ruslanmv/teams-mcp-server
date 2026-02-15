from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEAMS_MCP_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 9106
    log_level: str = "INFO"

    # MS Entra
    ms_tenant_id: str = "common"
    ms_client_id: str = ""

    # Encryption
    token_key: str = ""

    # Optional restrictions
    ms_allowed_upn: str | None = None


settings = Settings()
