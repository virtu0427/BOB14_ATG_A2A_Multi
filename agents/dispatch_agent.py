"""Standalone FastAPI application for the dispatch agent."""

from __future__ import annotations

import os
import sqlite3
import uuid
from typing import Any, AsyncGenerator

import httpx
from a2a.server.apps.jsonrpc import A2AFastAPIApplication
from a2a.server.request_handlers.request_handler import RequestHandler
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Message,
    MessageSendParams,
    Part,
    Role,
    Task,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TextPart,
    TransportProtocol,
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
)
from a2a.utils.errors import ServerError
from a2a.types import UnsupportedOperationError
from openai import AsyncOpenAI


def extract_text(message: Message) -> str:
    """Return the first text part from a message if present."""
    if message.parts:
        part = message.parts[0].root
        if isinstance(part, TextPart):
            return part.text
    return ""


class BaseA2AHandler(RequestHandler):
    """Request handler with unimplemented task management APIs."""

    async def on_get_task(
        self, params: TaskQueryParams, context: Any | None = None
    ) -> Task | None:
        return None

    async def on_cancel_task(
        self, params: TaskIdParams, context: Any | None = None
    ) -> Task | None:
        return None

    async def on_message_send_stream(
        self, params: MessageSendParams, context: Any | None = None
    ) -> AsyncGenerator[Any, None]:
        raise ServerError(error=UnsupportedOperationError())
        yield  # pragma: no cover

    async def on_set_task_push_notification_config(
        self, params: TaskPushNotificationConfig, context: Any | None = None
    ) -> TaskPushNotificationConfig:
        raise ServerError(error=UnsupportedOperationError())

    async def on_get_task_push_notification_config(
        self,
        params: TaskIdParams | GetTaskPushNotificationConfigParams,
        context: Any | None = None,
    ) -> TaskPushNotificationConfig:
        raise ServerError(error=UnsupportedOperationError())

    async def on_resubscribe_to_task(
        self, params: TaskIdParams, context: Any | None = None
    ) -> AsyncGenerator[Any, None]:
        raise ServerError(error=UnsupportedOperationError())
        yield  # pragma: no cover

    async def on_list_task_push_notification_config(
        self, params: ListTaskPushNotificationConfigParams, context: Any | None = None
    ) -> list[TaskPushNotificationConfig]:
        raise ServerError(error=UnsupportedOperationError())

    async def on_delete_task_push_notification_config(
        self, params: DeleteTaskPushNotificationConfigParams, context: Any | None = None
    ) -> None:
        raise ServerError(error=UnsupportedOperationError())


class LLMClient:
    """Wrapper around OpenAI or a local Ollama server."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai = AsyncOpenAI(api_key=api_key) if api_key else None
        self.ollama_model = os.getenv("OLLAMA_MODEL")
        self.ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    async def complete(self, prompt: str, default: str) -> str:
        if self.openai:
            try:
                completion = await self.openai.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return completion.choices[0].message.content.strip()
            except Exception:
                pass
        if self.ollama_model:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{self.ollama_base}/api/chat",
                        json={
                            "model": self.ollama_model,
                            "messages": [{"role": "user", "content": prompt}],
                        },
                        timeout=30,
                    )
                    data = resp.json()
                    return data.get("message", {}).get("content", default)
            except Exception:
                pass
        return default


class SQLiteAgent(BaseA2AHandler):
    """Simple agent that stores incoming text in a SQLite table."""

    def __init__(self, db_path: str, table: str, column: str, prefix: str) -> None:
        self.db = sqlite3.connect(db_path)
        self.table = table
        self.column = column
        self.prefix = prefix
        self.db.execute(
            f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, {column} TEXT)"
        )
        self.db.commit()
        self.llm = LLMClient()

    async def on_message_send(
        self, params: MessageSendParams, context: Any | None = None
    ) -> Message:
        text = extract_text(params.message)
        self.db.execute(
            f"INSERT INTO {self.table} (id, {self.column}) VALUES (?, ?)",
            (str(uuid.uuid4()), text),
        )
        self.db.commit()
        reply = await self.llm.complete(text, f"{self.prefix}: {text}")
        return Message(
            message_id=str(uuid.uuid4()),
            parts=[Part(TextPart(text=reply))],
            role=Role.agent,
        )


class DispatchHandler(SQLiteAgent):
    """Handles vehicle assignment logging."""

    def __init__(self) -> None:
        super().__init__("dispatch.db", "vehicles", "info", "vehicle stored")


def build_agent_app(name: str, description: str, port: int, handler: RequestHandler):
    """Create and return a FastAPI app for a given handler."""
    card = AgentCard(
        url=f"http://localhost:{port}",
        name=name,
        description=description,
        version="0.1.0",
        capabilities=AgentCapabilities(),
        skills=[
            AgentSkill(
                id="default",
                name=name,
                description=description,
                tags=["llm"],
            )
        ],
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        preferred_transport=TransportProtocol.http_json.value,
    )
    return A2AFastAPIApplication(agent_card=card, http_handler=handler).build()


app = build_agent_app(
    name="Dispatch Agent",
    description="Manages vehicle assignments",
    port=8001,
    handler=DispatchHandler(),
)

