from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"

def skill_loader(name:str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")

