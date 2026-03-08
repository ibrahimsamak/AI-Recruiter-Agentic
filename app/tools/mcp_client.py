import os
import sys

from langchain_mcp_adapters.client import MultiServerMCPClient

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
                "command": sys.executable,
                "args": ["mcp_servers/browser_server.py"],
            },
        }
    )


async def load_mcp_tools() -> list:
    client = build_mcp_client()
    return await client.get_tools()
