"""Application configuration management with Pydantic Settings and YAML loader."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml

# Windows event loop fix for async psycopg/asyncpg
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass


def _find_project_root() -> Path:
    """Find repository root containing config/ or pyproject.toml."""
    curr = Path(__file__).resolve().parent
    for _ in range(5):
        if (curr / "config").exists() or (curr / "pyproject.toml").exists():
            return curr
        curr = curr.parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root()
CONFIG_DIR = PROJECT_ROOT / "config"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    """Environment-based settings."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    INTEGRATION_MODE: str = "simulated"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/shopagent"
    DATABASE_URL_SYNC: str = "postgresql+psycopg://postgres:postgres@localhost:5432/shopagent"
    DATABASE_TEST_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/shopagent_test"

    # LLM
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    LLM_PRIMARY_PROVIDER: str = "gemini"
    LLM_PRIMARY_MODEL: str = "gemini-2.5-flash"
    LLM_FALLBACK_PROVIDER: str = "fake"
    LLM_FALLBACK_MODEL: str = "fake-model"
    LLM_CHEAP_PROVIDER: str = "gemini"
    LLM_CHEAP_MODEL: str = "gemini-2.5-flash-lite"
    LLM_SIM_PROVIDER: str = "gemini"
    LLM_SIM_MODEL: str = "gemini-2.5-flash"

    # Auth
    JWT_SECRET: str = "dev_secret_change_in_production_32charsmin!"
    JWT_REFRESH_SECRET: str = "dev_refresh_secret_change_in_production_32c!"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:6006/v1/traces"
    PHOENIX_PROJECT_NAME: str = "shop-support-agent"

    # VNPay Sandbox
    VNPAY_TMN_CODE: str = ""
    VNPAY_HASH_SECRET: str = ""
    VNPAY_PAY_URL: str = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
    VNPAY_API_URL: str = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"


_settings: Settings | None = None
_app_config: dict[str, Any] | None = None
_models_config: dict[str, Any] | None = None
_rules_config: dict[str, Any] | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        # Synchronize Google API key to prevent SDK from picking up stale OS environment variables
        if _settings.GEMINI_API_KEY:
            import os
            os.environ["GOOGLE_API_KEY"] = _settings.GEMINI_API_KEY
            os.environ["GEMINI_API_KEY"] = _settings.GEMINI_API_KEY
    return _settings


def get_app_config() -> dict[str, Any]:
    global _app_config
    if _app_config is None:
        _app_config = load_yaml(CONFIG_DIR / "app.yaml")
    return _app_config


def get_models_config() -> dict[str, Any]:
    global _models_config
    if _models_config is None:
        _models_config = load_yaml(CONFIG_DIR / "models.yaml")
    return _models_config


def get_rules_config() -> dict[str, Any]:
    global _rules_config
    if _rules_config is None:
        _rules_config = load_yaml(CONFIG_DIR / "policy" / "rules.yaml")
    return _rules_config
