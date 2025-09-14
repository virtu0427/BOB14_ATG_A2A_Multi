"""Utilities for building simple LLM-backed A2A agents."""

from __future__ import annotations

import sqlite3
import uuid
from typing import AsyncGenerator, Any

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
    ListTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
)
from a2a.server.apps.jsonrpc import A2AFastAPIApplication
from a2a.utils.errors import ServerError
from a2a.types import UnsupportedOperationError

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - fallback when OpenAI SDK missing
    OpenAI = None  # type: ignore


class SimpleLLMAgent(RequestHandler):
    """Minimal request handler using an LLM and a SQLite backing store."""

    def __init__(self, db_path: str, system_prompt: str) -> None:
        self.db = sqlite3.connect(db_path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS logs (id TEXT PRIMARY KEY, content TEXT)"
        )
        self.db.commit()
        self.system_prompt = system_prompt
        try:
            self.client = OpenAI() if OpenAI else None
        except Exception:  # pragma: no cover - missing API key
            self.client = None

    async def on_message_send(
        self, params: MessageSendParams, context: Any | None = None
    ) -> Message:
        """Process a message via LLM and log the request."""
        text = ""
        if params.message.parts:
            part = params.message.parts[0].root
            if isinstance(part, TextPart):
                text = part.text
        self.db.execute(
            "INSERT INTO logs VALUES (?, ?)", (str(uuid.uuid4()), text)
        )
        self.db.commit()

        reply_text = f"{self.system_prompt}: {text}"
        if self.client:
            try:  # pragma: no cover - network call best effort
                response = self.client.responses.create(
                    model="gpt-4o-mini", input=reply_text
                )
                reply_text = response.output_text
            except Exception:  # pragma: no cover - fall back to echo
                pass

        return Message(
            message_id=str(uuid.uuid4()),
            parts=[Part(TextPart(text=reply_text))],
            role=Role.agent,
        )

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


def build_agent_app(
    name: str, description: str, port: int, db_path: str
) -> A2AFastAPIApplication:
    """Create a FastAPI application for a simple agent."""
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
    handler = SimpleLLMAgent(db_path=db_path, system_prompt=description)
    return A2AFastAPIApplication(agent_card=card, http_handler=handler)
