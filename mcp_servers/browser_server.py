from mcp.server.fastmcp import FastMCP

mcp = FastMCP("browser")


@mcp.tool()
def submit_application(url: str, form: dict) -> dict:
    """Fill in and submit an application form. Only use after a human approved it."""
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
