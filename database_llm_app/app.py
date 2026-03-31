from __future__ import annotations

import contextlib
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .config import Settings, get_settings
from .mcp_server import _load_widget_markup, build_mcp_server
from .service import DatabaseChatService


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    chat_service = DatabaseChatService(resolved)
    mcp = build_mcp_server(settings=resolved, chat_service=chat_service)
    mcp_app = mcp.streamable_http_app()
    normalized_mcp_path = resolved.mcp_path if resolved.mcp_path.endswith("/") else f"{resolved.mcp_path}/"

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title=resolved.app_name, lifespan=lifespan)

    @app.middleware("http")
    async def normalize_mcp_slash(request, call_next):
        if request.scope["path"] == resolved.mcp_path:
            request.scope["path"] = normalized_mcp_path
            request.scope["raw_path"] = normalized_mcp_path.encode("utf-8")
        return await call_next(request)

    @app.get("/")
    def root():
        return {
            "service": resolved.app_name,
            "status": "ok",
            "health": "/health",
            "chat": "/chat",
            "mcp": resolved.mcp_path,
        }

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "environment": resolved.app_env,
            "database": resolved.mssql_database,
            "allowed_tables": list(resolved.db_allowed_tables),
        }

    @app.get("/chat", response_class=HTMLResponse)
    def chat_page(request: Request):
        return _load_widget_markup(api_base_url=_external_base_url(request))

    @app.get("/api/schema")
    def schema():
        try:
            return {
                "allowed_tables": list(resolved.db_allowed_tables),
                "schema_context": chat_service.get_schema_context(),
            }
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"스키마 조회 실패: {exc}") from exc

    @app.post("/api/chat")
    def ask_chat(payload: ChatRequest):
        try:
            result = chat_service.ask(payload.question, session_id=payload.session_id or "default")
            return {
                "answer": result.answer,
                "sql": result.sql,
                "reasoning": result.reasoning,
                "row_count": result.row_count,
                "rows": result.rows,
                "structured_query": result.structured_query,
                "validation_warnings": result.validation_warnings,
                "mode": result.mode,
                "sub_results": result.sub_results,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"질의 처리 실패: {exc}") from exc

    @app.get("/api/memory/{session_id}")
    def session_memory(session_id: str):
        try:
            return chat_service.get_memory(session_id)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"메모리 조회 실패: {exc}") from exc

    @app.get("/api/fund-docs/root")
    def fund_docs_root():
        try:
            return {"root": resolved.sftp_fund_root, "items": chat_service.list_fund_document_root()}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"SFTP 루트 조회 실패: {exc}") from exc

    @app.get("/api/fund-docs/search")
    def fund_docs_search(query: str):
        try:
            return {"query": query, "matches": chat_service.search_fund_documents(query)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"SFTP 문서 검색 실패: {exc}") from exc

    if resolved.enable_debug_endpoints:
        @app.get("/debug/db-test")
        def debug_db_test():
            try:
                return {
                    "ok": True,
                    "ping": chat_service.ping_database(),
                    "database": resolved.mssql_database,
                    "host": resolved.mssql_host,
                    "port": resolved.mssql_port,
                    "allowed_tables": list(resolved.db_allowed_tables),
                }
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"DB 조회 실패: {exc}") from exc

        @app.get("/debug/egress-ip")
        def debug_egress_ip():
            try:
                with urlopen("https://ifconfig.me/ip", timeout=10) as response:
                    ip = response.read().decode("utf-8").strip()
                return {"ip": ip}
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"외부 IP 조회 실패: {exc}") from exc

        @app.get("/debug/fund-docs-root")
        def debug_fund_docs_root():
            try:
                return {"root": resolved.sftp_fund_root, "items": chat_service.list_fund_document_root()}
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"SFTP 루트 조회 실패: {exc}") from exc

    app.mount(resolved.mcp_path, mcp_app)
    return app


def _external_url(request: Request, url: str) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        return str(url).replace("http://", f"{forwarded_proto}://", 1)
    if request.headers.get("host", "").endswith(".run.app"):
        return str(url).replace("http://", "https://", 1)
    return str(url)


def _external_base_url(request: Request) -> str:
    return _external_url(request, str(request.base_url)).rstrip("/")


app = create_app()
