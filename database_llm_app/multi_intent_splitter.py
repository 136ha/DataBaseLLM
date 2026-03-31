from __future__ import annotations

from .llm import LLMClient
from .models import SplitQuestionResult


class MultiIntentSplitter:
    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def split(self, question: str) -> SplitQuestionResult:
        payload = self._llm.split_question(question=question)
        result = SplitQuestionResult.model_validate(payload)
        cleaned = [item.strip() for item in result.sub_questions if item and item.strip()]
        result.sub_questions = cleaned[:3]
        if len(result.sub_questions) <= 1:
            result.is_multi = False
        return result
