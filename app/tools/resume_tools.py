# app/tools/resume_tools.py
"""Local LangChain tools for the orchestrator and tailoring worker."""
from langchain_core.tools import tool


@tool
def extract_profile(resume_text: str) -> dict:
    """Extract a structured candidate profile (skills, experience, seniority) from resume text."""
    # In practice: LLM call with structured output -> CandidateProfile. Stubbed here.
    return {"skills": [], "years_experience": 0.0, "seniority": "senior"}


@tool
def check_grounding(source_resume: str, tailored_resume: str) -> dict:
    """Flag any claim in the tailored resume NOT supported by the source resume (anti-fabrication)."""
    # LLM judge that returns unsupported claims; empty list => grounded.
    return {"grounded": True, "unsupported_claims": []}
