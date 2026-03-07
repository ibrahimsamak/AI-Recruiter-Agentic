from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ats", port=8002)

SUPPORTED = ("greenhouse", "lever", "workday")


@mcp.tool()
def get_posting(provider: str, posting_id: str) -> dict:
    """Get a job posting from an ATS provider."""
    if provider not in SUPPORTED:
        return {"error": f"unsupported provider '{provider}'", "supported": list(SUPPORTED)}
    return {
        "provider": provider,
        "posting_id": posting_id,
        "title": "...",
        "questions": [],
    }


@mcp.tool()
def list_application_fields(provider: str, posting_id: str) -> list[dict]:
    """List the form fields needed to apply to a posting."""
    if provider not in SUPPORTED:
        return [{"error": f"unsupported provider '{provider}'"}]
    return [
        {"name": "first_name", "type": "text", "required": True},
        {"name": "last_name", "type": "text", "required": True},
        {"name": "email", "type": "email", "required": True},
        {"name": "resume", "type": "file", "required": True},
    ]


@mcp.tool()
def submit_to_ats(provider: str, posting_id: str, application: dict) -> dict:
    """Submit an application to an ATS. Only use after a human approved it."""
    if provider not in SUPPORTED:
        return {"status": "error", "reason": f"unsupported provider '{provider}'"}
    return {"status": "submitted", "provider": provider, "posting_id": posting_id}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
