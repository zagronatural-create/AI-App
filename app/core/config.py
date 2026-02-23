from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default or []
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/supply_intel"
    )
    app_env: str = os.getenv("APP_ENV", "dev")
    storage_dir: str = os.getenv("STORAGE_DIR", "storage")
    auth_enabled: bool = _env_bool("AUTH_ENABLED", False)
    api_token_map_json: str = os.getenv("API_TOKEN_MAP_JSON", "{}")
    cors_allow_origins: list[str] = _env_list(
        "CORS_ALLOW_ORIGINS",
        default=["http://127.0.0.1:8000", "http://localhost:8000"],
    )
    rate_limit_enabled: bool = _env_bool("RATE_LIMIT_ENABLED", True)
    rate_limit_requests: int = _env_int("RATE_LIMIT_REQUESTS", 120)
    rate_limit_window_seconds: int = _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)


settings = Settings()
