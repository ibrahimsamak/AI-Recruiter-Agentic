# AI-Recruiter-Agentic · job-boards MCP (LinkedIn via JobSpy)
# mcp_servers/job_boards_server.py
"""Job-board search exposed as an MCP server (FastMCP, HTTP transport).

Backed by JobSpy, restricted to LinkedIn. LinkedIn has no free official jobs
API, so this scrapes LinkedIn's public listings — it is ToS-gray and rate
limited, so results may be partial and a block returns an empty list rather
than crashing the campaign.
"""
import logging
import math
import sys
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs
from mcp.server.fastmcp import FastMCP

# This server is launched as `python mcp_servers/job_boards_server.py` (not
# `-m`), so the repo root isn't on sys.path by default — add it so `app.*`
# (a sibling package) is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.storage import JOBS_CACHE_KEY, load_json, save_json  # noqa: E402

logger = logging.getLogger("job-boards")

# The UI reads this (via app/storage.py) to populate its "Approve a job"
# dropdown — subagent tool results don't reach the parent stream, so results
# are handed off this way instead. This server and the UI run as SEPARATE ECS
# services/containers in prod, so this goes through S3 (app/storage.py),
# never a local path. The UI clears it at campaign start, so it holds only the
# current campaign's jobs.


def _cache_postings(postings: list[dict]) -> None:
    try:
        by_url = {j["url"]: j for j in (load_json(JOBS_CACHE_KEY, default=[]) or []) if j.get("url")}
        for j in postings:
            if j.get("url"):
                by_url[j["url"]] = j
        save_json(JOBS_CACHE_KEY, list(by_url.values()))
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
