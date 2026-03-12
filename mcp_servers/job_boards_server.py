# AI-Recruiter-Agentic · job-boards MCP (LinkedIn via JobSpy)
# mcp_servers/job_boards_server.py
"""Job-board search exposed as an MCP server (FastMCP, HTTP transport).

Backed by JobSpy, restricted to LinkedIn. LinkedIn has no free official jobs
API, so this scrapes LinkedIn's public listings — it is ToS-gray and rate
limited, so results may be partial and a block returns an empty list rather
than crashing the campaign.
"""
import json
import logging
import math
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("job-boards")

# The UI reads this to populate its "Approve a job" dropdown (subagent tool
# results don't reach the parent stream, so we hand results off via disk). The
# UI clears it at campaign start, so it holds only the current campaign's jobs.
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

# Keep the agent context small. Full LinkedIn JDs are ~1.5–2.5k chars each; at 20
# jobs that blows past gpt-4o-mini's 200k tokens/min limit (429s + slow retries).
# Cap the count and truncate each description to a matching-sufficient snippet.
DEFAULT_LIMIT = 10
MAX_JOBS = 15
MAX_DESC_CHARS = 800


def _clean(value, default=""):
    """JobSpy returns NaN for missing cells; turn those into clean strings."""
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return str(value)


def _snippet(text: str, limit: int = MAX_DESC_CHARS) -> str:
    """Truncate a description to keep the agent context (and token bill) small."""
    text = " ".join(text.split())  # collapse whitespace
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


@mcp.tool()
def search_jobs(query: str, location: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Search LinkedIn for job postings matching a query and location.

    Returns up to `limit` (hard-capped at 15) normalized postings:
    job_id, title, company, location, description (truncated), url.
    Descriptions are truncated to keep the agent's token usage under control.
    """
    limit = max(1, min(limit, MAX_JOBS))
    try:
        df = scrape_jobs(
            site_name=["linkedin"],
            search_term=query,
            location=location,
            results_wanted=limit,
            linkedin_fetch_description=True,  # pull JD text for matching/tailoring
        )
    except Exception as exc:  # rate-limited / blocked / network — degrade gracefully
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
    _cache_postings(postings)  # hand results to the UI's approve dropdown
    return postings


if __name__ == "__main__":
    mcp.run(transport="streamable-http")  # served at /mcp
