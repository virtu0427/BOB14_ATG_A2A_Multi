"""Standalone FastAPI application for the orchestration agent."""

from __future__ import annotations

import uuid
from typing import Any, AsyncGenerator

import httpx
from a2a.client.helpers import create_text_message_object
from a2a.client.legacy import A2AClient, SendMessageRequest
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


class OrchestrationHandler(BaseA2AHandler):
    """Routes messages to domain agents via A2A."""

    def __init__(self) -> None:
        self.targets = {
            "dispatch": ("http://localhost:8001", "Dispatch Agent"),
            "delivery": ("http://localhost:8002", "Delivery Agent"),
            "inbound": ("http://localhost:8003", "Inbound Agent"),
        }

    async def on_message_send(
        self, params: MessageSendParams, context: Any | None = None
    ) -> Message:
        text = extract_text(params.message)
        if ":" not in text:
            return Message(
                message_id=str(uuid.uuid4()),
                parts=[Part(TextPart(text="format: agent: message"))],
                role=Role.agent,
            )
        target, content = text.split(":", 1)
        target = target.strip().lower()
        info = self.targets.get(target)
        if not info:
            return Message(
                message_id=str(uuid.uuid4()),
                parts=[Part(TextPart(text=f"unknown agent: {target}"))],
                role=Role.agent,
            )
        url, name = info
        card = AgentCard(
            url=url,
            name=name,
            description=name,
            version="0.1.0",
            capabilities=AgentCapabilities(),
            skills=[],
            default_input_modes=["text/plain"],
            default_output_modes=["text/plain"],
            preferred_transport=TransportProtocol.http_json.value,
        )
        async with httpx.AsyncClient() as http_client:
            client = A2AClient(http_client, card)
            req = SendMessageRequest(
                id=str(uuid.uuid4()),
                params=MessageSendParams(
                    message=create_text_message_object(content=content.strip())
                ),
            )
            resp = await client.send_message(req)
        result = getattr(resp.root, "result", None)
        reply = ""
        if isinstance(result, Message):
            reply = extract_text(result)
        else:
            reply = "ok"
        return Message(
            message_id=str(uuid.uuid4()),
            parts=[Part(TextPart(text=reply))],
            role=Role.agent,
        )


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
    name="Orchestration Agent",
    description="Coordinates domain-specific agents",
    port=8000,
    handler=OrchestrationHandler(),
)

