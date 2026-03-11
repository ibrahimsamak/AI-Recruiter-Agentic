from typing import Optional, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class AppState(TypedDict, total=False):
    job_id: str
    resume: str
    cover_letter: str
    approved: bool
    result: dict
    # {"provider": "greenhouse" | "lever" | "workday", "posting_id": str, "application": dict}
    ats: dict


def review_node(state: AppState):
    decision = interrupt(
        {
            "job_id": state["job_id"],
            "resume": state["resume"],
            "cover_letter": state["cover_letter"],
            "prompt": "Approve this application? (approve / reject)",
        }
    )
    return {"approved": decision == "approve"}


def build_application_graph(mcp_tools: Optional[list] = None):
    submit_to_ats = None
    if mcp_tools:
        submit_to_ats = next((t for t in mcp_tools if t.name == "submit_to_ats"), None)

    async def submit_node(state: AppState):
        if not state.get("approved"):
            return {"result": {"status": "skipped"}}

        ats = state.get("ats")
        if submit_to_ats is not None and ats:
            result = await submit_to_ats.ainvoke(
                {
                    "provider": ats["provider"],
                    "posting_id": ats["posting_id"],
                    "application": ats["application"],
                }
            )
            return {"result": result}

        return {"result": {"status": "applied", "note": "no ATS tool wired"}}

    g = StateGraph(AppState)
    g.add_node("review", review_node)
    g.add_node("submit", submit_node)
    g.add_edge(START, "review")
    g.add_edge("review", "submit")
    g.add_edge("submit", END)
    return g.compile(checkpointer=InMemorySaver())
