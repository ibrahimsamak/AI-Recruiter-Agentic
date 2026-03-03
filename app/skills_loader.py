from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def load_skill(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
