# app/agents/application_graph.py
"""LangGraph subgraph: pause for human approval, then submit via the ATS.

The checkpointer makes the interrupt durable so the run can be resumed after a
human decision arrives (potentially in a different process). Submission is
delegated to the `submit_to_ats` MCP tool (mcp_servers/ats_server.py); it is
only ever reached AFTER the human approval gate.
"""
from typing import Optional, TypedDict

from langgraph.checkpoint.memory import InMemorySaver  # -> Postgres/DynamoDB in prod
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class AppState(TypedDict, total=False):
    job_id: str
    resume: str
    cover_letter: str
    approved: bool
    result: dict
    # Where + how to submit once approved (consumed by submit_to_ats):
    #   {"provider": "greenhouse"|"lever"|"workday", "posting_id": str, "application": dict}
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
    """Compile the HITL application graph.

    Pass the MCP tools (from `load_mcp_tools`) to enable real ATS submission via
    the `submit_to_ats` tool. Without them, submit_node degrades to a no-op
    "applied" result so the graph stays runnable in isolation.
    """
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

        # No ATS tool/target wired — leave a clear, non-submitting result.
        return {"result": {"status": "applied", "note": "no ATS tool wired"}}

    g = StateGraph(AppState)
    g.add_node("review", review_node)
    g.add_node("submit", submit_node)
    g.add_edge(START, "review")
    g.add_edge("review", "submit")
    g.add_edge("submit", END)
    return g.compile(checkpointer=InMemorySaver())


# Resume after human decides:
#   graph.invoke(Command(resume="approve"),
#                config={"configurable": {"thread_id": job_id}})
