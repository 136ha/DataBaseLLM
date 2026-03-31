from __future__ import annotations

import json
from importlib.resources import files


class SchemaGraph:
    def __init__(self) -> None:
        raw = files("database_llm_app.metadata").joinpath("schema_graph.json").read_text(encoding="utf-8")
        self._payload = json.loads(raw)

    @property
    def payload(self) -> dict:
        return self._payload

