from __future__ import annotations

import re
import stat
import time
from dataclasses import dataclass

import paramiko

from .config import Settings

DOC_KEYWORDS = ("규약", "투자설명서", "설명서", "약관", "상품설명서", "fund", "prospectus")
STOPWORDS = {
    "펀드",
    "별",
    "관련",
    "파일",
    "문서",
    "보여줘",
    "찾아줘",
    "알려줘",
    "접근",
    "어디",
    "있어",
}


@dataclass
class FundDocumentMatch:
    path: str
    filename: str
    score: int
    note: str | None = None


class FundDocumentService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._cache_expires_at = 0.0
        self._cached_paths: list[str] = []
        self._cached_warning: str | None = None
        self._last_warning: str | None = None

    def is_configured(self) -> bool:
        return bool(self._settings.sftp_host and self._settings.sftp_user and self._settings.sftp_password)

    def is_document_question(self, question: str) -> bool:
        lowered = question.lower()
        return any(keyword in question for keyword in DOC_KEYWORDS) or "prospectus" in lowered

    def list_root(self) -> list[str]:
        self._last_warning = None
        paths_to_try = self._candidate_root_paths()
        for path in paths_to_try:
            try:
                return self._listdir(path)
            except OSError:
                continue
        warning = self._build_root_warning()
        root_items = self._listdir(".")
        return [warning, *root_items]

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        if not self.is_configured():
            raise ValueError("SFTP document access is not configured.")
        paths = self._get_all_paths()
        tokens = self._extract_tokens(query)
        matches: list[FundDocumentMatch] = []
        for path in paths:
            score = self._score_path(path, tokens)
            if score <= 0:
                continue
            filename = path.rsplit("/", 1)[-1]
            matches.append(FundDocumentMatch(path=path, filename=filename, score=score))
        matches.sort(key=lambda item: (-item.score, item.path))
        result = [
            {"path": item.path, "filename": item.filename, "score": item.score}
            for item in matches[:limit]
        ]
        if result:
            return result
        if self._last_warning:
            root_path = self._candidate_root_paths()[0]
            return [
                {
                    "path": root_path,
                    "filename": root_path.rsplit("/", 1)[-1] or root_path,
                    "score": 1,
                    "note": self._last_warning,
                }
            ]
        return []

    def answer(self, question: str) -> tuple[str, list[dict]]:
        matches = self.search(question)
        if not matches:
            return "SFTP의 /FUND 경로에서 관련 규약/투자설명서 파일을 찾지 못했습니다.", []
        if matches[0].get("note"):
            return (
                f"{matches[0]['note']}\n필요하면 SFTP 서버 담당자에게 FUND 폴더 listing 권한/설정을 확인해달라고 요청하는 게 좋습니다.",
                matches,
            )
        lines = ["관련 문서 후보를 찾았습니다."]
        for item in matches:
            lines.append(f"- {item['filename']} ({item['path']})")
        lines.append("필요하면 다음 단계로 특정 파일 다운로드나 본문 추출까지 연결할 수 있습니다.")
        return "\n".join(lines), matches

    def _get_all_paths(self) -> list[str]:
        self._last_warning = None
        now = time.time()
        if now < self._cache_expires_at and self._cached_paths:
            self._last_warning = self._cached_warning
            return self._cached_paths
        with self._connect() as sftp:
            paths: list[str] = []
            for root_path in self._candidate_root_paths():
                try:
                    paths = self._walk(sftp, root_path, depth=3)
                    break
                except OSError:
                    continue
            if not paths:
                self._last_warning = self._build_root_warning()
                paths = [self._candidate_root_paths()[0]]
        self._cached_paths = paths
        self._cached_warning = self._last_warning
        self._cache_expires_at = now + 300
        return paths

    def _connect(self):
        transport = paramiko.Transport((self._settings.sftp_host, self._settings.sftp_port))
        transport.connect(username=self._settings.sftp_user, password=self._settings.sftp_password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        class _Context:
            def __enter__(self_nonlocal):
                return sftp

            def __exit__(self_nonlocal, exc_type, exc, tb):
                sftp.close()
                transport.close()

        return _Context()

    def _listdir(self, path: str) -> list[str]:
        with self._connect() as sftp:
            return sorted(sftp.listdir(path))

    def _walk(self, sftp, path: str, *, depth: int) -> list[str]:
        items: list[str] = []
        if depth < 0:
            return items
        for entry in sftp.listdir_attr(path):
            child = f"{path.rstrip('/')}/{entry.filename}"
            if stat.S_ISDIR(entry.st_mode):
                items.extend(self._walk(sftp, child, depth=depth - 1))
            else:
                items.append(child)
        return items

    def _extract_tokens(self, query: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z0-9가-힣]+", query)
        result = []
        for token in tokens:
            lowered = token.lower()
            if lowered in STOPWORDS or len(lowered) <= 1:
                continue
            result.append(lowered)
        return result

    def _score_path(self, path: str, tokens: list[str]) -> int:
        lowered = path.lower()
        score = 0
        for token in tokens:
            if token in lowered:
                score += 3
        if any(keyword in path for keyword in DOC_KEYWORDS):
            score += 1
        return score

    def _candidate_root_paths(self) -> list[str]:
        configured = self._settings.sftp_fund_root.strip() or "/FUND"
        stripped = configured.lstrip("/")
        candidates = [configured]
        if stripped and stripped not in candidates:
            candidates.append(stripped)
        return candidates

    def _build_root_warning(self) -> str:
        root = self._candidate_root_paths()[0]
        return (
            f"SFTP 연결은 성공했지만 {root} 디렉터리 내부를 조회할 때 서버가 비정상 응답(Bad message)을 반환했습니다."
        )
