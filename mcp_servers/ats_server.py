# mcp_servers/ats_server.py
"""ATS integrations (Greenhouse / Lever / Workday) exposed as an MCP server.

Read-side tools (fetch a posting, list required fields) are safe to call any
time. The write-side `submit_to_ats` MUST only be invoked after human approval
in the LangGraph application subgraph.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ats", port=8002)

SUPPORTED = ("greenhouse", "lever", "workday")


@mcp.tool()
def get_posting(provider: str, posting_id: str) -> dict:
    """Fetch a single posting's details from an ATS provider."""
    if provider not in SUPPORTED:
        return {"error": f"unsupported provider '{provider}'", "supported": list(SUPPORTED)}
    # call the provider's API here (Greenhouse Harvest / Lever / Workday REST).
    return {
        "provider": provider,
        "posting_id": posting_id,
        "title": "...",
        "questions": [],
    }


@mcp.tool()
def list_application_fields(provider: str, posting_id: str) -> list[dict]:
    """Return the form fields an application to this posting requires."""
    if provider not in SUPPORTED:
        return [{"error": f"unsupported provider '{provider}'"}]
    # call the provider's API here.
    return [
        {"name": "first_name", "type": "text", "required": True},
        {"name": "last_name", "type": "text", "required": True},
        {"name": "email", "type": "email", "required": True},
        {"name": "resume", "type": "file", "required": True},
    ]


@mcp.tool()
def submit_to_ats(provider: str, posting_id: str, application: dict) -> dict:
    """Submit an application to an ATS. Only called AFTER human approval upstream."""
    if provider not in SUPPORTED:
        return {"status": "error", "reason": f"unsupported provider '{provider}'"}
    # call the provider's submit endpoint here.
    return {"status": "submitted", "provider": provider, "posting_id": posting_id}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")  # served at /mcp
