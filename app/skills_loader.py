# AI-Recruiter-Agentic · SKILL.md loader
# app/skills_loader.py
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def load_skill(name: str) -> str:
    """Read a SKILL.md as procedural knowledge to inject into an agent's context.

    In DeepAgents you can also seed these into the virtual filesystem so an agent
    reads them on demand through its file tools.
    """
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
