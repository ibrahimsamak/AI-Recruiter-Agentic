from langchain_core.tools import tool


@tool
def extract_profile(resume_text: str) -> dict:
    """Extract skills, years of experience and seniority from resume text."""
    return {"skills": [], "years_experience": 0.0, "seniority": "senior"}


@tool
def check_grounding(source_resume: str, tailored_resume: str) -> dict:
    """Check the tailored resume for claims that are not in the source resume."""
    return {"grounded": True, "unsupported_claims": []}
