# A2A Multi-Agent Environment


This repository demonstrates how to run multiple LLM-backed agents using the [Google Agent2Agent (A2A) protocol](https://github.com/a2aproject/A2A). Code is grouped into `agents/` for the services, `client/` for the Flask UI, and `tools/` for utilities such as the SQLite MCP server.


## Components

| Agent | Description | Port | Database |
|-------|-------------|------|----------|
| Orchestration Agent | Coordinates domain-specific agents | `8000` | – |
| Dispatch Agent | Manages vehicle assignments | `8001` | `dispatch.db` (vehicles) |
| Delivery Agent | Tracks shipment status | `8002` | `delivery.db` (deliveries) |
| Inbound Agent | Handles inventory intake | `8003` | `inbound.db` (items) |

Each service runs as an independent FastAPI application speaking the A2A protocol. Domain agents persist their own data in dedicated SQLite databases, while the orchestration agent forwards messages to them over HTTP JSON.

Every agent has its own standalone module with all required logic, allowing deployment in completely separate environments without shared code.

Domain agents invoke an LLM when generating responses. They support either the OpenAI API or a local [Ollama](https://ollama.com/) server for free testing.

- To use OpenAI, set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`).
- To use a local model, run an Ollama instance and set `OLLAMA_MODEL` (and optionally `OLLAMA_BASE_URL`).
- If neither option is available, agents fall back to echoing the stored text.


## Setup

```bash
pip install -r requirements.txt
```


Run each agent from the `agents/` package in a separate terminal:

```bash
uvicorn agents.orchestrator:app --port 8000
uvicorn agents.dispatch_agent:app --port 8001
uvicorn agents.delivery_agent:app --port 8002
uvicorn agents.inbound_agent:app --port 8003
```

These services can then communicate using the A2A client APIs.

### Accessing Databases via MCP

Each SQLite database can be exposed through the Model Context Protocol for direct LLM access:

```bash
python tools/sqlite_mcp_server.py dispatch.db --name dispatch-db
```

Use the `--transport` flag (`stdio`, `sse`, or `streamable-http`) to choose how the MCP server is hosted. Similar commands apply for `delivery.db` and `inbound.db`.

### Chat Client

A simple Flask interface lets you chat with any agent over A2A.

```bash
flask --app client.app run --port 5004
```

Open `http://localhost:5004` in your browser. Provide the agent's host, port, and a
display name to create a chat window. Conversations are stored in `client.db` and
can be revisited later from the home page.
