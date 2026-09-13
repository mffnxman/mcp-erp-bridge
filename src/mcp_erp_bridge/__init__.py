"""mcp-erp-bridge — MCP server wrapping a session-cookie-auth enterprise ERP.

Reference implementation for the FDE deployment pattern: take an internal
enterprise web app, reverse the auth flow, wrap it as an MCP server, and
hand it to Claude as a structured tool.
"""

__version__ = "0.1.0"
__author__ = "Rafael Garcia"
__license__ = "MIT"
