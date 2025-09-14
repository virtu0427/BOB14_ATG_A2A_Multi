# A2A Multi-Agent Environment

This repository demonstrates how to run multiple LLM-backed agents using the [Google Agent2Agent (A2A) protocol](https://github.com/a2aproject/A2A).

## Components

| Agent | Description | Port | Database |
|-------|-------------|------|----------|
| Orchestration Agent | Coordinates domain-specific agents | `8000` | `orchestrator.db` |
| Dispatch Agent | Manages vehicle assignments | `8001` | `dispatch.db` |
| Delivery Agent | Tracks shipment status | `8002` | `delivery.db` |
| Inbound Agent | Handles inventory intake | `8003` | `inbound.db` |

Each agent is exposed as a FastAPI application implementing the A2A protocol. A simple SQLite database is used to log incoming messages.

## Setup

```bash
pip install -r requirements.txt
```

Run each agent in a separate terminal:

```bash
uvicorn orchestrator:app --port 8000
uvicorn dispatch_agent:app --port 8001
uvicorn delivery_agent:app --port 8002
uvicorn inbound_agent:app --port 8003
```

These services can then communicate using the A2A client APIs.
