import os
from pathlib import Path

os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_PROJECT", "ai-recruiter")

# any langchain model string, e.g. openai:gpt-4o-mini or anthropic:claude-sonnet-4-5
DEFAULT_MODEL = os.getenv("MODEL", "openai:gpt-4o-mini")

CHROMA_DIR = os.getenv("CHROMA_DIR", str(Path(__file__).parent / "rag" / "chroma"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
