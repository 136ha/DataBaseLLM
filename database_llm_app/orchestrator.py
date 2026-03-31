from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import PROJECT_ROOT, Settings
from .db import DatabaseClient
from .intent_parser import IntentParser
from .llm import LLMClient
from .memory_store import MemoryStore
from .multi_intent_splitter import MultiIntentSplitter
from .models import StructuredQuery, ValidationResult
from .schema_graph import SchemaGraph
from .semantic_dictionary import SemanticDictionary
from .sftp_docs import FundDocumentService
from .sql_builder import SQLBuilder
from .sql_validator import SQLValidator


@dataclass
class OrchestratedAnswer:
    answer: str
    sql: str
    reasoning: str
    row_count: int
    rows: list[dict]
    structured_query: dict
    validation_warnings: list[str]
    mode: str = "single"
    sub_results: list[dict] | None = None


class QueryOrchestrator:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._db = DatabaseClient(settings)
        self._llm = LLMClient(settings)
        self._dictionary = SemanticDictionary()
        self._schema_graph = SchemaGraph()
        self._documents = FundDocumentService(settings)
        self._memory = MemoryStore(PROJECT_ROOT / "artifacts" / "memory")
        self._intent_parser = IntentParser(self._llm)
        self._splitter = MultiIntentSplitter(self._llm)
        self._sql_builder = SQLBuilder(
            dictionary=self._dictionary,
            schema_graph=self._schema_graph,
            row_limit=settings.db_query_row_limit,
        )
        self._validator = SQLValidator(settings.db_query_row_limit)

    def ping_database(self) -> int:
        return self._db.ping()

    def get_schema_context(self) -> str:
        return self._db.fetch_schema_context()

    def get_memory(self, session_id: str) -> dict:
        return self._memory.load(session_id).model_dump()

    def list_fund_document_root(self) -> list[str]:
        return self._documents.list_root()

    def search_fund_documents(self, query: str) -> list[dict]:
        return self._documents.search(query)

    def ask(self, *, question: str, session_id: str) -> OrchestratedAnswer:
        question = question.strip()
        if not question:
            raise ValueError("question is empty.")
        split = self._splitter.split(question)
        if split.is_multi and split.sub_questions:
            return self._ask_multi(question=question, session_id=session_id, sub_questions=split.sub_questions)
        return self._ask_single(question=question, session_id=session_id)

    def _ask_single(self, *, question: str, session_id: str) -> OrchestratedAnswer:
        if self._documents.is_document_question(question):
            answer, matches = self._documents.answer(question)
            return OrchestratedAnswer(
                answer=answer,
                sql="",
                reasoning="규약/투자설명서 질문으로 판단해 SFTP 문서 경로를 검색했습니다.",
                row_count=len(matches),
                rows=matches,
                structured_query={"type": "document_search", "query": question},
                validation_warnings=[],
                mode="single",
                sub_results=[],
            )
        memory = self._memory.load(session_id)
        structured_query = self._intent_parser.parse(question=question, memory=memory)
        structured_query = self._dictionary.normalize(structured_query)
        if structured_query.followup and memory.last_query:
            structured_query = self._merge_with_memory(structured_query, memory.last_query)
        if structured_query.clarification_needed and structured_query.clarification_question:
            raise ValueError(structured_query.clarification_question)

        sql = self._sql_builder.build(structured_query)
        validation = self._validator.validate(sql, query=structured_query)
        query_result = self._db.execute_read_only_query(validation.normalized_sql)
        answer = self._llm.summarize_answer(question=question, query_result=query_result)
        self._memory.save(session_id, structured_query)
        return OrchestratedAnswer(
            answer=answer,
            sql=validation.normalized_sql,
            reasoning=structured_query.reasoning,
            row_count=query_result.row_count,
            rows=query_result.rows[:20],
            structured_query=structured_query.model_dump(),
            validation_warnings=validation.warnings,
            mode="single",
            sub_results=[],
        )

    def _ask_multi(self, *, question: str, session_id: str, sub_questions: list[str]) -> OrchestratedAnswer:
        sub_results: list[dict] = []
        answer_blocks: list[str] = []
        sql_blocks: list[str] = []
        all_rows: list[dict] = []
        for index, sub_question in enumerate(sub_questions, start=1):
            sub_session_id = f"{session_id}__part{index}"
            result = self._ask_single(question=sub_question, session_id=sub_session_id)
            sub_results.append(
                {
                    "index": index,
                    "question": sub_question,
                    "answer": result.answer,
                    "sql": result.sql,
                    "structured_query": result.structured_query,
                    "row_count": result.row_count,
                    "rows": result.rows,
                }
            )
            answer_blocks.append(result.answer.strip())
            sql_blocks.append(f"-- Question {index}: {sub_question}\n{result.sql}")
            all_rows.extend(result.rows[:5])

        if sub_results:
            last_structured = sub_results[-1]["structured_query"]
            self._memory.save(session_id, StructuredQuery.model_validate(last_structured))
        return OrchestratedAnswer(
            answer="\n\n".join(answer_blocks),
            sql="\n\n".join(sql_blocks),
            reasoning=f"{len(sub_results)}개의 독립 질문으로 분해해 순차 실행했습니다.",
            row_count=sum(item["row_count"] for item in sub_results),
            rows=all_rows[:20],
            structured_query={"type": "multi", "sub_questions": sub_questions},
            validation_warnings=[],
            mode="multi",
            sub_results=sub_results,
        )

    def _merge_with_memory(self, query: StructuredQuery, previous: StructuredQuery) -> StructuredQuery:
        if not query.dimensions:
            query.dimensions = previous.dimensions
        if query.metric == "transaction_amount" and previous.metric != "transaction_amount":
            query.metric = previous.metric
        if query.subject == "transaction" and previous.subject != "transaction":
            query.subject = previous.subject
        if query.filters.fund_code is None:
            query.filters.fund_code = previous.filters.fund_code
        if query.filters.broker_code is None:
            query.filters.broker_code = previous.filters.broker_code
        if query.filters.item_code is None:
            query.filters.item_code = previous.filters.item_code
        if query.filters.buy_sell is None:
            query.filters.buy_sell = previous.filters.buy_sell
        if query.filters.proc_date.type == "latest" and previous.filters.proc_date.type != "latest":
            query.filters.proc_date = previous.filters.proc_date
        return query
