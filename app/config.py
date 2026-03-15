# app/config.py
"""Central configuration + LangSmith tracing setup.

Importing this module turns on LangSmith tracing for every LangChain /
LangGraph / DeepAgents run in the process (one-time env setup).
"""
import os
from pathlib import Path

# LangSmith: one-time env setup traces every LangChain/LangGraph/DeepAgents run.
# These are only set if not already provided by the environment, so deployment
# overrides win.
os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_PROJECT", "ai-recruiter")
# LANGSMITH_API_KEY is read from the environment (never hard-coded).

# Any LangChain-supported model string, e.g.
#   "openai:gpt-4o-mini" | "anthropic:claude-sonnet-4-5" | "bedrock_converse:anthropic.claude-..."
DEFAULT_MODEL = os.getenv("MODEL", "openai:gpt-4o-mini")

# Where ChromaDB persists its collections. Defaults to app/rag/chroma so the
# store lives next to the RAG code (visible — no leading dot). Absolute path so
# it's stable regardless of the current working directory.
CHROMA_DIR = os.getenv("CHROMA_DIR", str(Path(__file__).parent / "rag" / "chroma"))

# Embeddings model used for job<->profile matching.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
