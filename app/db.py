# AI-Recruiter-Agentic · Postgres checkpointer + pgvector bootstrap
# app/db.py
"""Durable LangGraph checkpointer, backed by Postgres, plus the one-time
`CREATE EXTENSION vector` needed before app/rag/vectorstore.py can be used.

Replaces the InMemorySaver the app previously used, which lost every chat
thread on task restart and couldn't be shared across replicas.
"""
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import DATABASE_URL

_cm = None
_saver: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Return the process-wide Postgres checkpointer, creating it on first use."""
    global _cm, _saver
    if _saver is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set — required for the Postgres checkpointer")
        _cm = AsyncPostgresSaver.from_conn_string(DATABASE_URL)
        _saver = await _cm.__aenter__()
        await _saver.setup()
    return _saver


async def close_checkpointer() -> None:
    """Release the checkpointer's connection pool (call on app shutdown)."""
    global _cm, _saver
    if _cm is not None:
        await _cm.__aexit__(None, None, None)
        _cm = None
        _saver = None


async def ensure_pgvector_extension() -> None:
    """Create the `vector` extension once, if missing. Safe to call every startup."""
    if not DATABASE_URL:
        return
    import psycopg

    async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
