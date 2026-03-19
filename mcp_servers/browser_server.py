# AI-Recruiter-Agentic · browser MCP (Playwright submit)
# mcp_servers/browser_server.py  — wraps a Playwright browser agent
"""Browser automation exposed as an MCP server (stdio transport).

Wraps Playwright to fill and submit application forms on arbitrary sites that
lack a first-class ATS API. Only invoked AFTER human approval upstream.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("browser")


@mcp.tool()
def submit_application(url: str, form: dict) -> dict:
    """Fill and submit an application form. Only called AFTER human approval upstream."""
    # Imported lazily so the server can start (and list its tool) without
    # Playwright installed; only submission actually needs the browser.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        page = p.chromium.launch(headless=True).new_page()
        page.goto(url)
        for selector, value in form.items():
            page.fill(selector, value)
        page.click("button[type=submit]")
        return {"status": "submitted", "url": url}


if __name__ == "__main__":
    mcp.run(transport="stdio")
