"""FastAPI entry point for the inbound agent."""

from agents.base_agent import build_agent_app

app = build_agent_app(
    name="Inbound Agent",
    description="Handles inventory intake",
    port=8003,
    db_path="inbound.db",
).build()
