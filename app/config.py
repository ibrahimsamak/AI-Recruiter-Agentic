# AI-Recruiter-Agentic · configuration & LangSmith tracing
# app/config.py
"""Central configuration + LangSmith tracing setup.

Importing this module turns on LangSmith tracing for every LangChain /
LangGraph / DeepAgents run in the process (one-time env setup).
"""
import os

# LangSmith: one-time env setup traces every LangChain/LangGraph/DeepAgents run.
# These are only set if not already provided by the environment, so deployment
# overrides win.
os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_PROJECT", "ai-recruiter")
# LANGSMITH_API_KEY is read from the environment (never hard-coded).

# Any LangChain-supported model string, e.g.
#   "openai:gpt-4o-mini" | "anthropic:claude-sonnet-4-5" | "bedrock_converse:anthropic.claude-..."
DEFAULT_MODEL = os.getenv("MODEL", "openai:gpt-4o-mini")

# Embeddings model used for job<->profile matching.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# --- Postgres (pgvector matching store + LangGraph checkpointer) ---
# Plain psycopg conninfo, e.g. postgresql://user:pass@<rds-endpoint>:5432/dbname
DATABASE_URL = os.getenv("DATABASE_URL", "")


def sqlalchemy_database_url() -> str:
    """PGVector needs the SQLAlchemy-style `postgresql+psycopg://` scheme."""
    if not DATABASE_URL or DATABASE_URL.startswith("postgresql+"):
        return DATABASE_URL
    return DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


# --- S3 (generated documents) — local disk under ./outputs when unset, so
# local dev works without AWS credentials (see app/storage.py) ---
AWS_REGION = os.getenv("AWS_REGION", "ca-central-1")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_URL_TTL = int(os.getenv("S3_URL_TTL", "3600"))

# --- /ui gate (interim Gradio basic auth; move to ALB OIDC/Cognito later) ---
GRADIO_AUTH_USER = os.getenv("GRADIO_AUTH_USER", "")
GRADIO_AUTH_PASS = os.getenv("GRADIO_AUTH_PASS", "")
