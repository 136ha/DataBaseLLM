from __future__ import annotations

import json

from openai import OpenAI

from .config import Settings
from .db import QueryResult
from .models import MemoryEntry


class LLMClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=2) if settings.openai_api_key else None

    def build_sql(self, *, question: str, schema_context: str, row_limit: int) -> dict:
        if not self._client:
            raise ValueError("OPENAI_API_KEY is not configured.")
        response = self._client.responses.create(
            model=self._settings.openai_chat_model,
            input=_sql_prompt(question=question, schema_context=schema_context, row_limit=row_limit),
            text={"format": {"type": "json_object"}},
        )
        payload = json.loads(response.output_text)
        if "sql" not in payload:
            raise ValueError("LLM response did not include 'sql'.")
        return payload

    def summarize_answer(self, *, question: str, query_result: QueryResult) -> str:
        if not self._client:
            raise ValueError("OPENAI_API_KEY is not configured.")
        preview_rows = query_result.rows[:20]
        response = self._client.responses.create(
            model=self._settings.openai_chat_model,
            input=_answer_prompt(question=question, query_result=query_result, preview_rows=preview_rows),
        )
        return response.output_text.strip()

    def parse_intent(self, *, question: str, memory: MemoryEntry) -> dict:
        if not self._client:
            raise ValueError("OPENAI_API_KEY is not configured.")
        response = self._client.responses.create(
            model=self._settings.openai_chat_model,
            input=_intent_prompt(question=question, memory=memory),
            text={"format": {"type": "json_object"}},
        )
        return json.loads(response.output_text)

    def split_question(self, *, question: str) -> dict:
        if not self._client:
            raise ValueError("OPENAI_API_KEY is not configured.")
        response = self._client.responses.create(
            model=self._settings.openai_chat_model,
            input=_splitter_prompt(question=question),
            text={"format": {"type": "json_object"}},
        )
        return json.loads(response.output_text)


def _sql_prompt(*, question: str, schema_context: str, row_limit: int) -> str:
    return f"""
You translate Korean business questions into safe Microsoft SQL Server read-only SQL.

Return JSON only with this exact shape:
{{
  "sql": "SELECT ...",
  "reasoning": "short explanation in Korean"
}}

Rules:
- Only use SELECT or WITH.
- Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, MERGE, EXEC, or multiple statements.
- Use only the tables and columns present in the schema context.
- Prefer simple queries over clever ones.
- Limit the result to at most {row_limit} rows. Use TOP when needed.
- If the question is ambiguous, choose a conservative query that helps answer it.
- Output must be valid JSON and nothing else.

Schema context:
{schema_context}

User question:
{question}
""".strip()


def _answer_prompt(*, question: str, query_result: QueryResult, preview_rows: list[dict]) -> str:
    return f"""
You are a data analyst answering in Korean.

Answer the user's question using only the SQL result below.
- If the result is empty, say no matching data was found.
- Mention important caveats when the data is partial or truncated.
- Keep the answer concise but useful.

User question:
{question}

Executed SQL:
{query_result.sql}

Row count:
{query_result.row_count}

Preview rows:
{json.dumps(preview_rows, ensure_ascii=False)}
""".strip()


def _intent_prompt(*, question: str, memory: MemoryEntry) -> str:
    memory_payload = memory.model_dump() if memory.last_query else {"session_id": memory.session_id, "last_query": None}
    return f"""
You convert a Korean business question into a compact JSON query plan for a MSSQL analytics app.

Return JSON only with this exact shape:
{{
  "intent": "lookup|ranking|aggregate|trend|compare",
  "subject": "transaction|fund|broker|item",
  "metric": "transaction_amount|contract_quantity|transaction_count",
  "dimensions": ["fund","broker","item","proc_date"],
  "filters": {{
    "proc_date": {{
      "type": "latest|exact|recent",
      "value": null,
      "recent_days": null
    }},
    "fund_code": null,
    "broker_code": null,
    "item_code": null,
    "buy_sell": null
  }},
  "limit": 10,
  "sort_direction": "desc",
  "output_style": "table|summary|single_value",
  "followup": false,
  "clarification_needed": false,
  "clarification_question": null,
  "reasoning": "short Korean explanation"
}}

Rules:
- Prefer conservative interpretation.
- If the user asks "그중", "이번엔", "방금", "이전", mark followup=true.
- Use only the allowed enum values above.
- If no metric is specified for ranking/aggregate/trend, default to transaction_amount.
- If no date is specified, use proc_date.latest.
- If the question is truly ambiguous, set clarification_needed=true and ask one short Korean question.
- Do not invent codes unless explicitly mentioned.
- For "상위", "top", "많은 순" use intent=ranking.
- For "합계", "총액", "총 수량" use intent=aggregate.
- For "추이", "일자별", "기간별" use intent=trend and include proc_date dimension.

Conversation memory:
{json.dumps(memory_payload, ensure_ascii=False)}

Examples:
Q: 가장 최근 기준으로 브로커별 거래금액 상위 3개 보여줘
A:
{{
  "intent": "ranking",
  "subject": "broker",
  "metric": "transaction_amount",
  "dimensions": ["broker", "proc_date"],
  "filters": {{
    "proc_date": {{"type": "latest", "value": null, "recent_days": null}},
    "fund_code": null,
    "broker_code": null,
    "item_code": null,
    "buy_sell": null
  }},
  "limit": 3,
  "sort_direction": "desc",
  "output_style": "table",
  "followup": false,
  "clarification_needed": false,
  "clarification_question": null,
  "reasoning": "브로커별 거래금액 순위 요청으로 해석했다."
}}

Q: 그중 상위 1개만
A:
{{
  "intent": "ranking",
  "subject": "broker",
  "metric": "transaction_amount",
  "dimensions": [],
  "filters": {{
    "proc_date": {{"type": "latest", "value": null, "recent_days": null}},
    "fund_code": null,
    "broker_code": null,
    "item_code": null,
    "buy_sell": null
  }},
  "limit": 1,
  "sort_direction": "desc",
  "output_style": "table",
  "followup": true,
  "clarification_needed": false,
  "clarification_question": null,
  "reasoning": "직전 질의를 이어받는 후속 요청으로 해석했다."
}}

Q: 최근 7일 기준 거래금액 추이를 보여줘
A:
{{
  "intent": "trend",
  "subject": "transaction",
  "metric": "transaction_amount",
  "dimensions": ["proc_date"],
  "filters": {{
    "proc_date": {{"type": "recent", "value": null, "recent_days": 7}},
    "fund_code": null,
    "broker_code": null,
    "item_code": null,
    "buy_sell": null
  }},
  "limit": 30,
  "sort_direction": "desc",
  "output_style": "summary",
  "followup": false,
  "clarification_needed": false,
  "clarification_question": null,
  "reasoning": "최근 7일의 일자별 추이 조회로 해석했다."
}}

Q: 가장 최근 기준으로 매수 거래금액 상위 펀드 5개 보여줘
A:
{{
  "intent": "ranking",
  "subject": "fund",
  "metric": "transaction_amount",
  "dimensions": ["fund", "proc_date"],
  "filters": {{
    "proc_date": {{"type": "latest", "value": null, "recent_days": null}},
    "fund_code": null,
    "broker_code": null,
    "item_code": null,
    "buy_sell": "B"
  }},
  "limit": 5,
  "sort_direction": "desc",
  "output_style": "table",
  "followup": false,
  "clarification_needed": false,
  "clarification_question": null,
  "reasoning": "최신일 기준 매수 거래금액 상위 펀드 요청으로 해석했다."
}}

User question:
{question}
""".strip()


def _splitter_prompt(*, question: str) -> str:
    return f"""
You determine whether a Korean user input contains one database question or multiple independent database questions.

Return JSON only with this exact shape:
{{
  "is_multi": false,
  "sub_questions": [],
  "reasoning": "short Korean explanation"
}}

Rules:
- Use is_multi=true only when the input contains 2 or 3 independent data questions that should be answered separately.
- If the user asks for one query plus one formatting preference, keep it as a single question.
- If the user asks for one query plus explanation, keep it as a single question.
- If the user clearly asks A and B together, split into sub_questions in natural Korean.
- Never return more than 3 sub_questions.
- If uncertain, prefer is_multi=false.

Examples:
Q: 최근 기준 브로커 상위 3개 보여주고, 매수 상위 펀드 5개도 알려줘
A:
{{
  "is_multi": true,
  "sub_questions": [
    "최근 기준 브로커 상위 3개 보여줘",
    "최근 기준 매수 상위 펀드 5개 알려줘"
  ],
  "reasoning": "브로커 순위와 펀드 순위라는 독립 질의 2개로 분해했다."
}}

Q: 최근 기준 브로커 상위 3개를 표로 보여주고 설명해줘
A:
{{
  "is_multi": false,
  "sub_questions": [],
  "reasoning": "하나의 데이터 질의와 표현 방식 요청으로 판단했다."
}}

User input:
{question}
""".strip()
