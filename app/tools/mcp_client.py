# app/tools/mcp_client.py
"""Wire the MCP servers into LangChain-compatible tools."""
import os
import sys

from langchain_mcp_adapters.client import MultiServerMCPClient

# Default to localhost for local dev; override in Docker/ECS with the service
# names, e.g. JOB_BOARDS_MCP_URL=http://job-boards:8001/mcp
JOB_BOARDS_MCP_URL = os.getenv("JOB_BOARDS_MCP_URL", "http://localhost:8001/mcp")
ATS_MCP_URL = os.getenv("ATS_MCP_URL", "http://localhost:8002/mcp")


def build_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "job_boards": {
                "transport": "streamable_http",
                "url": JOB_BOARDS_MCP_URL,
            },
            "ats": {
                "transport": "streamable_http",
                "url": ATS_MCP_URL,
            },
            "browser": {
                "transport": "stdio",
                "command": sys.executable,  # same interpreter (this box has python3, not python)
                "args": ["mcp_servers/browser_server.py"],
            },
        }
    )


async def load_mcp_tools() -> list:
    """Return a flat list of LangChain-compatible tools from all MCP servers."""
    client = build_mcp_client()
    return await client.get_tools()
