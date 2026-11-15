"""
Goddard FastMCP Server package.
Exposes MCP tools for mission requirements, CAD-to-Physics evaluation,
and constraint verification.
"""

from goddard.server.goddard_mcp import main, mcp

__all__ = ["mcp", "main"]
