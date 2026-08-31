# AI-Recruiter-Agentic · pgvector (RDS) job/profile matching
# app/rag/vectorstore.py
"""Postgres/pgvector-backed semantic matching between candidate profiles and jobs.

Requires the `vector` extension on the target database — created once at app
startup (see app/db.py:ensure_pgvector_extension), not by hand.
"""
from langchain_postgres import PGVector

from app.config import AWS_REGION, EMBEDDING_MODEL, sqlalchemy_database_url


def get_embeddings():
    """EMBEDDING_MODEL="bedrock:<model-id>" -> Bedrock (no OPENAI_API_KEY needed);
    anything else -> OpenAI. Mirrors DEFAULT_MODEL's "provider:model" convention."""
    if EMBEDDING_MODEL.startswith("bedrock:"):
        from langchain_aws import BedrockEmbeddings

        return BedrockEmbeddings(model_id=EMBEDDING_MODEL.split(":", 1)[1], region_name=AWS_REGION)
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=EMBEDDING_MODEL)


def get_vectorstore(collection: str = "jobs") -> PGVector:
    return PGVector(
        embeddings=get_embeddings(),
        collection_name=collection,
        connection=sqlalchemy_database_url(),
        use_jsonb=True,
    )


def index_jobs(jobs: list[dict]) -> None:
    """Index (or upsert) job postings into the `jobs` collection."""
    if not jobs:
        return
    vs = get_vectorstore("jobs")
    vs.add_texts(
        texts=[j["description"] for j in jobs],
        metadatas=[
            {"job_id": j["job_id"], "title": j["title"], "url": j["url"]}
            for j in jobs
        ],
        ids=[j["job_id"] for j in jobs],
    )


def match_jobs(profile_text: str, k: int = 10):
    """Return [(Document, relevance_score)] ranked by fit to the candidate profile."""
    vs = get_vectorstore("jobs")
    return vs.similarity_search_with_relevance_scores(profile_text, k=k)
