"""Entry point for running the OneNote Organizer MCP Server.

Usage:
    python -m onenote_organizer [--transport stdio|http] [--port PORT]
"""

from __future__ import annotations

import argparse


def main() -> None:
    """Parse CLI arguments and start the MCP server with the selected transport."""
    parser = argparse.ArgumentParser(
        description="OneNote Organizer MCP Server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport protocol: stdio (default) or http",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for HTTP transport (default: 8080)",
    )
    args = parser.parse_args()

    from onenote_organizer.server import mcp

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "http":
        mcp.settings.port = args.port
        mcp.run(transport="sse")


if __name__ == "__main__":
    main()
