from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Super Bajaar API"
    app_env: str = "development"
    # Public API routes are /api/...; do not expose a /v1 segment.
    api_prefix: str = "/api"
    database_url: str = ""
    cors_allowed_origins: str = "http://localhost:5173"
    # Reuse the existing legacy secret during migration if JWT_SECRET_KEY is not set.
    # Do not hardcode a production secret in source control.
    jwt_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("JWT_SECRET_KEY", "SB_SECRET_KEY"),
    )
    # Match the confirmed AWS backend listener. The process manager must also bind this port.
    port: int = 8001
    media_bucket: str = ""
    media_public_base_url: str = ""
    aws_region: str = "ap-south-1"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
