"""FastAPI entry point for the delivery agent."""

from agents.base_agent import build_agent_app

app = build_agent_app(
    name="Delivery Agent",
    description="Tracks shipment status",
    port=8002,
    db_path="delivery.db",
).build()
