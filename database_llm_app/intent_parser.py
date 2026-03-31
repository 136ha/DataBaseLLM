from __future__ import annotations

import json

from .llm import LLMClient
from .models import MemoryEntry, StructuredQuery


class IntentParser:
    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def parse(self, *, question: str, memory: MemoryEntry) -> StructuredQuery:
        payload = self._llm.parse_intent(question=question, memory=memory)
        query = StructuredQuery.model_validate(payload)
        query.limit = max(1, min(query.limit, 200))
        return query

