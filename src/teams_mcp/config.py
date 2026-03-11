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

    # ── Persona mode (browser-based, no Azure registration) ──
    persona_chrome_path: str | None = None          # Custom Chromium path (auto-detect if None)
    persona_face_dir: str = "./data/faces"          # Directory for persona face images
    persona_tts_voice: str = "en_US-amy-medium"     # Default piper-tts voice model
    persona_headless: bool = True                   # Run browser headless by default
    persona_stt_backend: str = "whisper"            # STT backend for persona listening


settings = Settings()
