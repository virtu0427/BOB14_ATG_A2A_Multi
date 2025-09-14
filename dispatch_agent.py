"""FastAPI entry point for the dispatch agent."""

from agents.base_agent import build_agent_app

app = build_agent_app(
    name="Dispatch Agent",
    description="Manages vehicle assignments",
    port=8001,
    db_path="dispatch.db",
).build()
