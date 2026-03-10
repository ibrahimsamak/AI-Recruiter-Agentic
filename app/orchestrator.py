from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware

from app.config import DEFAULT_MODEL
from app.skills_loader import load_skill
from app.tools.resume_tools import check_grounding, extract_profile


def build_orchestrator(mcp_tools: list, checkpointer=None):
    matching_skill = load_skill("matching")
    tailoring_skill = load_skill("tailoring")
    cover_skill = load_skill("cover-letter")

    safe_tools = mcp_tools

    discovery = {
        "name": "discovery",
        "description": "Search job boards and return a normalized job list.",
        "system_prompt": (
            "Search boards for the candidate's target roles; return normalized "
            "postings only."
        ),
        "tools": [t for t in safe_tools if "search_jobs" in t.name],
    }
    tailoring_worker = {
        "name": "tailoring_worker",
        "description": "Tailor the resume and write a cover letter for one job.",
        "system_prompt": tailoring_skill + "\n\n---\n\n" + cover_skill,
        "tools": [check_grounding],
    }

    return create_deep_agent(
        model=DEFAULT_MODEL,
        tools=[extract_profile, *safe_tools],
        subagents=[discovery, tailoring_worker],
        middleware=[TodoListMiddleware()],
        checkpointer=checkpointer,
        system_prompt=(
            "Run a job-application campaign. Plan with todos.\n"
            "Apply the MATCHING SKILL yourself, in-context (rank jobs, explain each score):\n"
            f"{matching_skill}\n"
            "Delegate discovery and per-job tailoring to subagents. "
            "Do not submit anything without asking the user first."
        ),
    )
