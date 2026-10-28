from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Super Bajaar API"
    app_env: str = "development"
    # Public API routes are /api/...; do not expose a /v1 segment.
    api_prefix: str = "/api"
    database_url: str = ""
    cors_allowed_origins: str = "http://localhost:5173"
    jwt_secret_key: str = ""
    # Match the confirmed AWS backend listener. The process manager must also bind this port.
    port: int = 8001

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
