from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SENTINELLA_", extra="ignore")

    # Core
    database_url: str = "sqlite:///./sentinella.db"
    secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    access_token_expire_minutes: int = 60 * 24

    # Bootstrap admin (created on first run if no users exist)
    admin_username: str = "admin"
    admin_password: str = "admin"

    # Token agents present to register a new server
    agent_enroll_token: str = "enroll-change-me"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Anthropic / AI remediation
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ai_enabled: bool = True

    # Mark a server offline after this many seconds without heartbeat
    offline_after_seconds: int = 90


settings = Settings()
