from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Super Bajaar API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = ""
    cors_allowed_origins: str = "http://localhost:5173"
    jwt_secret_key: str = ""
    # Match the confirmed AWS backend listener. The process manager must also bind this port.
    port: int = 8001

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
