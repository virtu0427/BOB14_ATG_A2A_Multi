"""Standalone FastAPI application for the orchestration agent."""

from __future__ import annotations

import os
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
from a2a.types import UnsupportedOperationError
from a2a.utils.errors import ServerError
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


class OrchestrationHandler(BaseA2AHandler):
    """Routes messages to domain agents via A2A."""

    def __init__(self) -> None:
        self.targets = {
            "dispatch": (
                "http://localhost:8001",
                "Dispatch Agent",
                "Manages vehicle assignments",
            ),
            "delivery": (
                "http://localhost:8002",
                "Delivery Agent",
                "Tracks shipment status",
            ),
            "inbound": (
                "http://localhost:8003",
                "Inbound Agent",
                "Handles inventory intake",
            ),
        }
        self.llm = LLMClient()

    async def on_message_send(
        self, params: MessageSendParams, context: Any | None = None
    ) -> Message:
        text = extract_text(params.message)
        prompt = [
            "You are a router that chooses the best agent for a request.",
            "Agents:",
        ]
        for key, (_, _, desc) in self.targets.items():
            prompt.append(f"- {key}: {desc}")
        prompt.append(f"User message: {text}")
        prompt.append("Return only the agent name or 'unknown'.")
        choice = (
            await self.llm.complete("\n".join(prompt), "unknown")
        ).strip().lower()
        info = self.targets.get(choice)
        if not info:
            return Message(
                message_id=str(uuid.uuid4()),
                parts=[Part(TextPart(text="unable to route request"))],
                role=Role.agent,
            )
        url, name, _ = info
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
                    message=create_text_message_object(content=text)
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

