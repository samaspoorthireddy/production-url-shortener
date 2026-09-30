# app/config.py
from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    development = "development"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Environment
    port: int
    database_url: str
    redis_url: str
    jwt_secret: str
    cors_origin: str
    log_level: str = "info"


settings = Settings()
