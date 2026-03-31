from __future__ import annotations

import json
from importlib.resources import files

from .models import StructuredQuery


class SemanticDictionary:
    def __init__(self) -> None:
        raw = files("database_llm_app.metadata").joinpath("semantic_dictionary.json").read_text(encoding="utf-8")
        self._payload = json.loads(raw)

    @property
    def payload(self) -> dict:
        return self._payload

    def normalize(self, query: StructuredQuery) -> StructuredQuery:
        query.metric = self._normalize_metric(query.metric)
        query.dimensions = [self._normalize_dimension(item) for item in query.dimensions]
        seen: set[str] = set()
        query.dimensions = [item for item in query.dimensions if not (item in seen or seen.add(item))]
        if query.filters.buy_sell:
            query.filters.buy_sell = self._normalize_buy_sell(query.filters.buy_sell)
        if query.subject in {"fund", "broker", "item"} and query.subject not in query.dimensions:
            query.dimensions.insert(0, query.subject)
        if query.intent == "trend" and "proc_date" not in query.dimensions:
            query.dimensions.append("proc_date")
        return query

    def _normalize_metric(self, metric: str) -> str:
        metric = self._payload["synonyms"].get(metric, metric)
        if metric in self._payload["metrics"]:
            return metric
        return "transaction_amount"

    def _normalize_dimension(self, dimension: str) -> str:
        dimension = self._payload["synonyms"].get(dimension, dimension)
        if dimension in self._payload["dimensions"]:
            return dimension
        return dimension

    def _normalize_buy_sell(self, raw: str) -> str | None:
        normalized = self._payload["synonyms"].get(raw, raw).lower()
        if normalized in {"b", "buy"}:
            return "B"
        if normalized in {"s", "sell"}:
            return "S"
        return None
