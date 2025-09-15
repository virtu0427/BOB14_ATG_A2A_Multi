"""Expose a SQLite database via the Model Context Protocol (MCP)."""

from __future__ import annotations

import argparse
import sqlite3
from typing import Any

from mcp.server.fastmcp import FastMCP, Context


def build_sqlite_mcp(db_path: str, name: str = "sqlite") -> FastMCP:
    """Create an MCP server with a single query tool for a SQLite DB."""
    server = FastMCP(name=name)

    @server.tool()
    def query(sql: str, ctx: Context) -> list[dict[str, Any]]:
        """Execute a read-only SQL query and return rows as dictionaries."""
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql)
            return [dict(row) for row in cur.fetchall()]

    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an MCP server for a SQLite DB")
    parser.add_argument("db_path", help="Path to the SQLite database")
    parser.add_argument("--name", default="sqlite", help="Name for the MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport protocol to use",
    )
    args = parser.parse_args()
    build_sqlite_mcp(args.db_path, args.name).run(transport=args.transport)

