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
        description="Ask questions about the database and get Korean answers generated from live query results.",
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
        description="Generate a read-only SQL query, execute it, and answer in Korean.",
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

    return mcp
