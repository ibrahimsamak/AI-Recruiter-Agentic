# AI-Recruiter-Agentic · DeepAgents orchestrator
# app/orchestrator.py
"""DeepAgents orchestrator: matching skill in-context + 2 lean subagents.

Skills carry the procedure; only discovery and per-job tailoring become
subagents (justified by context isolation + parallelism). Matching is a skill
the orchestrator applies in its own context.
"""
from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware

from app.config import DEFAULT_MODEL
from app.skills_loader import load_skill
from app.tools.resume_tools import check_grounding, extract_profile

# HARD guardrail: the orchestrator must never be able to submit. These tools are
# stripped from its tool list so no chat message ("yes", "apply", etc.) can ever
# trigger a submission. Submission is only reachable through the explicit
# human-approval graph (app/agents/application_graph.py).
BLOCKED_ORCHESTRATOR_TOOLS = {"submit_to_ats", "submit_application"}


def build_orchestrator(mcp_tools: list, checkpointer=None):
    # Procedural knowledge -> skills (loaded into context), NOT agents.
    matching_skill = load_skill("matching")
    tailoring_skill = load_skill("tailoring")
    cover_skill = load_skill("cover-letter")

    # Strip any submission tools before the orchestrator ever sees them.
    safe_tools = [t for t in mcp_tools if t.name not in BLOCKED_ORCHESTRATOR_TOOLS]

    # Only tasks needing context ISOLATION or PARALLELISM become subagents.
    discovery = {
        "name": "discovery",
        "description": (
            "Search boards; return a normalized job list. Isolated so bulky "
            "raw postings never flood the main context."
        ),
        "system_prompt": (
            "Search boards for the candidate's target roles; return normalized "
            "postings only."
        ),
        "tools": [t for t in safe_tools if "search_jobs" in t.name],
    }
    tailoring_worker = {
        "name": "tailoring_worker",
        "description": (
            "Tailor the resume + draft a cover letter for ONE job. Spawned "
            "per-job so many run in parallel, each in isolated context."
        ),
        "system_prompt": tailoring_skill + "\n\n---\n\n" + cover_skill,  # skills = the procedure
        "tools": [check_grounding],
    }

    return create_deep_agent(
        model=DEFAULT_MODEL,
        tools=[extract_profile, *safe_tools],
        subagents=[discovery, tailoring_worker],  # 2 subagents, driven by isolation — not 5 roles
        middleware=[TodoListMiddleware()],
        checkpointer=checkpointer,  # pass an InMemorySaver (etc.) to persist chat threads
        system_prompt=(
            "Run a job-application campaign. Plan with todos.\n"
            "Apply the MATCHING SKILL yourself, in-context (rank jobs, explain each score):\n"
            f"{matching_skill}\n"
            "Delegate discovery and per-job tailoring to subagents. "
            "You have NO ability to submit applications — only prepare tailored "
            "resumes and cover letters. Submission happens elsewhere, behind human approval."
        ),
    )
