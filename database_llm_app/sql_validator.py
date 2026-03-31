from __future__ import annotations

import re

from .models import StructuredQuery, ValidationResult

FORBIDDEN_PATTERNS = (
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


class SQLValidator:
    def __init__(self, row_limit: int):
        self._row_limit = row_limit

    def validate(self, sql: str, *, query: StructuredQuery) -> ValidationResult:
        normalized = re.sub(r";+\s*$", "", sql.strip())
        if not normalized:
            raise ValueError("Generated SQL is empty.")
        if ";" in normalized:
            raise ValueError("Multiple SQL statements are not allowed.")
        if not re.match(r"^(SELECT|WITH)\b", normalized, flags=re.IGNORECASE):
            raise ValueError("Only SELECT or WITH statements are allowed.")
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                raise ValueError(f"Forbidden SQL pattern detected: {pattern}")
        warnings: list[str] = []
        if not re.search(r"\bTOP\s+\d+\b", normalized, flags=re.IGNORECASE):
            warnings.append("TOP 절이 없어 결과 건수 제한이 약할 수 있습니다.")
        if query.intent in {"ranking", "trend"} and "metric_value" not in normalized:
            warnings.append("집계 별칭 metric_value가 없어 결과 설명이 불안정할 수 있습니다.")
        return ValidationResult(valid=True, normalized_sql=normalized, warnings=warnings)

