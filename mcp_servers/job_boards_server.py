import logging
import math

import pandas as pd
from jobspy import scrape_jobs
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("job-boards")

mcp = FastMCP("job-boards", port=8001)

def _clean(value, default=""):
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return str(value)


@mcp.tool()
def search_jobs(query: str, location: str, limit: int = 20) -> list[dict]:
    """Search LinkedIn for jobs by query and location.

    Returns postings with job_id, title, company, location, description and url.
    """
    try:
        df = scrape_jobs(
            site_name=["linkedin"],
            search_term=query,
            location=location,
            results_wanted=limit,
            linkedin_fetch_description=True,
        )
    except Exception as exc:
        logger.warning("LinkedIn search failed for %r in %r: %s", query, location, exc)
        return []

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []

    postings = []
    for idx, row in df.iterrows():
        job_url = _clean(row.get("job_url"))
        postings.append(
            {
                "job_id": _clean(row.get("id")) or job_url or f"linkedin-{idx}",
                "title": _clean(row.get("title")),
                "company": _clean(row.get("company")),
                "location": _clean(row.get("location")) or location,
                "description": _clean(row.get("description")),
                "url": job_url,
            }
        )
    return postings


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
