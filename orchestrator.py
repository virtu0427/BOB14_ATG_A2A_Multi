"""FastAPI entry point for the orchestration agent."""

from agents.base_agent import build_agent_app

app = build_agent_app(
    name="Orchestration Agent",
    description="Coordinates domain-specific agents",
    port=8000,
    db_path="orchestrator.db",
).build()
