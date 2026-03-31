from __future__ import annotations

import json
import re
from pathlib import Path

from .models import MemoryEntry, StructuredQuery


class MemoryStore:
    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str) -> MemoryEntry:
        path = self._path_for(session_id)
        if not path.exists():
            return MemoryEntry(session_id=session_id, last_query=None)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return MemoryEntry.model_validate(payload)

    def save(self, session_id: str, query: StructuredQuery) -> None:
        path = self._path_for(session_id)
        entry = MemoryEntry(session_id=session_id, last_query=query)
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")

    def _path_for(self, session_id: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", session_id.strip() or "default")
        return self._base_dir / f"{safe}.json"

