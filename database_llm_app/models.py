from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


IntentType = Literal["lookup", "ranking", "aggregate", "trend", "compare"]
SubjectType = Literal["transaction", "fund", "broker", "item"]
DateFilterType = Literal["latest", "exact", "recent"]
SortDirection = Literal["asc", "desc"]


class DateFilter(BaseModel):
    type: DateFilterType = "latest"
    value: str | None = None
    recent_days: int | None = None


class QueryFilters(BaseModel):
    proc_date: DateFilter = Field(default_factory=DateFilter)
    fund_code: str | None = None
    broker_code: str | None = None
    item_code: str | None = None
    buy_sell: str | None = None


class StructuredQuery(BaseModel):
    intent: IntentType = "lookup"
    subject: SubjectType = "transaction"
    metric: str = "transaction_amount"
    dimensions: list[str] = Field(default_factory=list)
    filters: QueryFilters = Field(default_factory=QueryFilters)
    limit: int = 10
    sort_direction: SortDirection = "desc"
    output_style: str = "table"
    followup: bool = False
    clarification_needed: bool = False
    clarification_question: str | None = None
    reasoning: str = ""


class MemoryEntry(BaseModel):
    session_id: str
    last_query: StructuredQuery | None = None


class ValidationResult(BaseModel):
    valid: bool
    normalized_sql: str
    warnings: list[str] = Field(default_factory=list)


class SplitQuestionResult(BaseModel):
    is_multi: bool = False
    sub_questions: list[str] = Field(default_factory=list)
    reasoning: str = ""
