from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .orchestrator import QueryOrchestrator


@dataclass
class ChatAnswer:
    answer: str
    sql: str
    reasoning: str
    row_count: int
    rows: list[dict]
    schema_context: str
    structured_query: dict | None = None
    validation_warnings: list[str] | None = None
    mode: str = "single"
    sub_results: list[dict] | None = None


class DatabaseChatService:
    def __init__(self, settings: Settings):
        self._orchestrator = QueryOrchestrator(settings)

    def get_schema_context(self) -> str:
        return self._orchestrator.get_schema_context()

    def ping_database(self) -> int:
        return self._orchestrator.ping_database()

    def get_memory(self, session_id: str) -> dict:
        return self._orchestrator.get_memory(session_id)

    def list_fund_document_root(self) -> list[str]:
        return self._orchestrator.list_fund_document_root()

    def search_fund_documents(self, query: str) -> list[dict]:
        return self._orchestrator.search_fund_documents(query)

    def ask(self, question: str, *, session_id: str = "default") -> ChatAnswer:
        result = self._orchestrator.ask(question=question, session_id=session_id)
        return ChatAnswer(
            answer=result.answer,
            sql=result.sql,
            reasoning=result.reasoning,
            row_count=result.row_count,
            rows=result.rows,
            schema_context=self._orchestrator.get_schema_context(),
            structured_query=result.structured_query,
            validation_warnings=result.validation_warnings,
            mode=result.mode,
            sub_results=result.sub_results,
        )
