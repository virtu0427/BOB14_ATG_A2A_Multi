"""Flask user client for interacting with A2A agents."""
from __future__ import annotations

import sqlite3
import uuid
import asyncio

import httpx
from flask import Flask, render_template, request, redirect, url_for
from a2a.client.helpers import create_text_message_object
from a2a.client.legacy import A2AClient, SendMessageRequest
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    Message,
    MessageSendParams,
    TransportProtocol,
    Part,
    TextPart,
    Role,
)


def extract_text(message: Message) -> str:
    """Return the first text part from a message if present."""
    if message.parts:
        part = message.parts[0].root
        if isinstance(part, TextPart):
            return part.text
    return ""


def send_a2a_message(url: str, name: str, text: str) -> str:
    """Send a text message to the given agent and return the reply."""
    async def _send() -> str:
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
        if isinstance(result, Message):
            return extract_text(result)
        return ""

    return asyncio.run(_send())


app = Flask(__name__)

db = sqlite3.connect("client.db", check_same_thread=False)
db.execute(
    "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, name TEXT, url TEXT)"
)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        role TEXT,
        content TEXT
    )
    """
)
db.commit()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form["name"].strip()
        host = request.form["url"].strip()
        port = request.form["port"].strip()
        session_id = str(uuid.uuid4())
        full_url = f"http://{host}:{port}"
        db.execute(
            "INSERT INTO sessions (id, name, url) VALUES (?, ?, ?)",
            (session_id, name, full_url),
        )
        db.commit()
        return redirect(url_for("chat", session_id=session_id))
    cur = db.execute("SELECT id, name, url FROM sessions")
    sessions = cur.fetchall()
    return render_template("index.html", sessions=sessions)


@app.route("/chat/<session_id>", methods=["GET", "POST"])
def chat(session_id: str):
    cur = db.execute(
        "SELECT id, name, url FROM sessions WHERE id=?", (session_id,)
    )
    session = cur.fetchone()
    if not session:
        return redirect(url_for("index"))
    if request.method == "POST":
        text = request.form["message"].strip()
        if text:
            db.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, "user", text),
            )
            db.commit()
            reply = send_a2a_message(session[2], session[1], text)
            db.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, "agent", reply),
            )
            db.commit()
        return redirect(url_for("chat", session_id=session_id))
    cur = db.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (session_id,)
    )
    messages = cur.fetchall()
    return render_template("chat.html", session=session, messages=messages)


if __name__ == "__main__":
    app.run(port=5004)
