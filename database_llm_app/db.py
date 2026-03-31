from __future__ import annotations

from decimal import Decimal
import re
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import Settings

FORBIDDEN_SQL_PATTERNS = (
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bMERGE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bCREATE\b",
)


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[dict]
    row_count: int


class DatabaseClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._engine = self._build_engine()

    def _build_engine(self) -> Engine:
        user = urllib.parse.quote_plus(self._settings.mssql_user)
        password = urllib.parse.quote_plus(self._settings.mssql_password)
        return create_engine(
            f"mssql+pymssql://{user}:{password}@{self._settings.mssql_host}:{self._settings.mssql_port}/{self._settings.mssql_database}",
            connect_args={"timeout": 10, "login_timeout": 10, "charset": self._settings.mssql_charset},
        )

    def ping(self) -> int:
        with self._engine.connect() as conn:
            return conn.execute(text("SELECT 1 AS ok")).scalar_one()

    def fetch_schema_context(self) -> str:
        placeholders = ", ".join(f":table_{index}" for index, _ in enumerate(self._settings.db_allowed_tables))
        bind_params = {f"table_{index}": table for index, table in enumerate(self._settings.db_allowed_tables)}
        schema_sql = text(
            f"""
            SELECT
                TABLE_NAME AS table_name,
                COLUMN_NAME AS column_name,
                DATA_TYPE AS data_type
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME IN ({placeholders})
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
        )
        lines: list[str] = []
        current_table = None
        with self._engine.connect() as conn:
            for row in conn.execute(schema_sql, bind_params):
                data = dict(row._mapping)
                table_name = data["table_name"]
                if table_name != current_table:
                    current_table = table_name
                    lines.append(f"[{table_name}]")
                lines.append(f"- {data['column_name']} ({data['data_type']})")
        if not lines:
            joined = ", ".join(self._settings.db_allowed_tables)
            return f"Allowed tables are configured, but schema lookup returned no columns. Tables: {joined}"
        return "\n".join(lines)

    def execute_read_only_query(self, sql: str) -> QueryResult:
        sanitized = _sanitize_sql(sql)
        limited_sql = _ensure_row_limit(sanitized, self._settings.db_query_row_limit)
        with self._engine.connect() as conn:
            rows = conn.execute(text(limited_sql)).fetchall()
        mapped_rows = [{key: _normalize_value(value) for key, value in dict(row._mapping).items()} for row in rows]
        columns = list(mapped_rows[0].keys()) if mapped_rows else []
        return QueryResult(sql=limited_sql, columns=columns, rows=mapped_rows, row_count=len(mapped_rows))


def _sanitize_sql(sql: str) -> str:
    candidate = sql.strip()
    candidate = re.sub(r";+\s*$", "", candidate)
    if not candidate:
        raise ValueError("SQL is empty.")
    if not re.match(r"^(SELECT|WITH)\b", candidate, flags=re.IGNORECASE):
        raise ValueError("Only SELECT or WITH queries are allowed.")
    if ";" in candidate:
        raise ValueError("Multiple SQL statements are not allowed.")
    for pattern in FORBIDDEN_SQL_PATTERNS:
        if re.search(pattern, candidate, flags=re.IGNORECASE):
            raise ValueError(f"Forbidden SQL pattern detected: {pattern}")
    return candidate


def _ensure_row_limit(sql: str, row_limit: int) -> str:
    if re.search(r"\bTOP\s+\d+\b", sql, flags=re.IGNORECASE):
        return sql
    if re.match(r"^SELECT\b", sql, flags=re.IGNORECASE):
        return re.sub(r"^SELECT\b", f"SELECT TOP {row_limit}", sql, count=1, flags=re.IGNORECASE)
    return sql


def _normalize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
