from __future__ import annotations

from importlib.resources import files

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .config import Settings
from .service import DatabaseChatService

WIDGET_URI = "ui://widget/database-llm-chat.html"


def _load_widget_markup(*, api_base_url: str | None = None) -> str:
    markup = files("database_llm_app.ui").joinpath("chat.html").read_text(encoding="utf-8")
    return markup.replace("__API_BASE_URL__", api_base_url or "")


def build_mcp_server(*, settings: Settings, chat_service: DatabaseChatService) -> FastMCP:
    mcp = FastMCP(
        settings.app_name,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=settings.enable_dns_rebinding_protection
        ),
    )

    @mcp.resource(
        WIDGET_URI,
        name="database-llm-chat-widget",
        title="Database LLM Chat",
        description="Ask questions about the database or fund documents and get Korean answers from live data.",
        mime_type="text/html;profile=mcp-app",
    )
    def chat_widget() -> str:
        return _load_widget_markup(api_base_url=settings.public_base_url)

    @mcp.tool(
        name="open_database_chat_app",
        title="Open Database Chat App",
        description="Open the database chat UI.",
        annotations=ToolAnnotations(readOnlyHint=True),
        meta={
            "openai/outputTemplate": WIDGET_URI,
            "openai/widgetAccessible": True,
            "openai/toolInvocation/invoking": "DB 챗 앱을 여는 중…",
            "openai/toolInvocation/invoked": "DB 챗 앱이 준비되었습니다.",
        },
    )
    def open_database_chat_app() -> dict:
        return {"message": "Database chat UI ready."}

    @mcp.tool(
        name="ask_database_question",
        title="Ask Database Question",
        description="Answer a database question in Korean, or search fund document paths when the question is about regulations or prospectuses.",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    def ask_database_question(question: str) -> dict:
        result = chat_service.ask(question)
        return {
            "answer": result.answer,
            "sql": result.sql,
            "reasoning": result.reasoning,
            "row_count": result.row_count,
            "rows": result.rows,
        }

    @mcp.tool(
        name="search_fund_documents",
        title="Search Fund Documents",
        description="Search fund regulation and prospectus files from the SFTP /FUND tree.",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    def search_fund_documents(query: str) -> dict:
        matches = chat_service.search_fund_documents(query)
        return {
            "query": query,
            "matches": matches,
        }

    @mcp.tool(
        name="list_fund_document_root",
        title="List Fund Document Root",
        description="List top-level directories and files under the SFTP fund document root.",
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    def list_fund_document_root() -> dict:
        items = chat_service.list_fund_document_root()
        return {"items": items}

    return mcp
