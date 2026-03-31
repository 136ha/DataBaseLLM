from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWED_TABLES = (
    "PFO_FTOP_INTG_TR",
    "TRU_FUND_INFR_BS",
    "TRU_FTOP_ITMS_BS",
    "TRU_TRPL_BS",
)


def _first_env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _require_env(*names: str) -> str:
    value = _first_env(*names)
    if value:
        return value
    raise ValueError(f"Missing required environment variable. Expected one of: {', '.join(names)}")


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    parsed = tuple(item.strip() for item in raw.split(",") if item.strip())
    return parsed or default


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    public_base_url: str | None
    app_host: str
    app_port: int
    mcp_path: str
    openai_api_key: str | None
    openai_chat_model: str
    mssql_host: str
    mssql_port: int
    mssql_database: str
    mssql_user: str
    mssql_password: str
    mssql_charset: str
    db_allowed_tables: tuple[str, ...]
    db_query_row_limit: int
    enable_debug_endpoints: bool
    enable_dns_rebinding_protection: bool

    @classmethod
    def from_env(cls) -> "Settings":
        app_env = _first_env("APP_ENV", default="dev") or "dev"
        mcp_path = _first_env("MCP_PATH", default="/mcp") or "/mcp"
        if not mcp_path.startswith("/"):
            mcp_path = f"/{mcp_path}"
        row_limit = int(_first_env("DB_QUERY_ROW_LIMIT", default="200") or "200")
        if row_limit <= 0:
            raise ValueError("DB_QUERY_ROW_LIMIT must be positive.")

        return cls(
            app_name=_first_env("APP_NAME", default="database-llm-app") or "database-llm-app",
            app_env=app_env,
            public_base_url=_first_env("PUBLIC_BASE_URL"),
            app_host=_first_env("APP_HOST", default="0.0.0.0") or "0.0.0.0",
            app_port=int(_first_env("APP_PORT", default="8010") or "8010"),
            mcp_path=mcp_path,
            openai_api_key=_first_env("OPENAI_API_KEY"),
            openai_chat_model=_first_env("OPENAI_CHAT_MODEL", default="gpt-5.4-mini") or "gpt-5.4-mini",
            mssql_host=_require_env("MSSQL_HOST"),
            mssql_port=int(_first_env("MSSQL_PORT", default="1433") or "1433"),
            mssql_database=_require_env("MSSQL_DATABASE"),
            mssql_user=_require_env("MSSQL_USER"),
            mssql_password=_require_env("MSSQL_PASSWORD"),
            mssql_charset=_first_env("MSSQL_CHARSET", default="CP949") or "CP949",
            db_allowed_tables=_csv_env("DB_ALLOWED_TABLES", DEFAULT_ALLOWED_TABLES),
            db_query_row_limit=row_limit,
            enable_debug_endpoints=_env_flag("APP_ENABLE_DEBUG_ENDPOINTS", default=app_env != "prod"),
            enable_dns_rebinding_protection=_env_flag(
                "MCP_ENABLE_DNS_REBINDING_PROTECTION", default=app_env == "prod"
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
