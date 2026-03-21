import json
import logging
import math
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("job-boards")

# the ui reads this file to fill the approve dropdown
JOBS_CACHE = Path(__file__).resolve().parents[1] / "outputs" / "_jobs_cache.json"


def _cache_postings(postings: list[dict]) -> None:
    try:
        JOBS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        by_url = {}
        if JOBS_CACHE.exists():
            by_url = {j["url"]: j for j in json.loads(JOBS_CACHE.read_text()) if j.get("url")}
        for j in postings:
            if j.get("url"):
                by_url[j["url"]] = j
        JOBS_CACHE.write_text(json.dumps(list(by_url.values())))
    except Exception as exc:
        logger.warning("could not cache postings: %s", exc)

mcp = FastMCP("job-boards", port=8001)

# full descriptions were hitting the gpt-4o-mini rate limit, so keep them short
DEFAULT_LIMIT = 10
MAX_JOBS = 15
MAX_DESC_CHARS = 800


def _clean(value, default=""):
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return str(value)


def _snippet(text: str, limit: int = MAX_DESC_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


@mcp.tool()
def search_jobs(query: str, location: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Search LinkedIn for jobs by query and location.

    Returns up to 15 postings with job_id, title, company, location, a short
    description and url.
    """
    limit = max(1, min(limit, MAX_JOBS))
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
                "description": _snippet(_clean(row.get("description"))),
                "url": job_url,
            }
        )
    _cache_postings(postings)
    return postings


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
