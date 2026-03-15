# app/rag/vectorstore.py
"""ChromaDB-backed semantic matching between candidate profiles and jobs."""
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings  # swap for any embeddings provider

from app.config import CHROMA_DIR, EMBEDDING_MODEL


def get_vectorstore(collection: str = "jobs") -> Chroma:
    return Chroma(
        collection_name=collection,
        embedding_function=OpenAIEmbeddings(model=EMBEDDING_MODEL),
        persist_directory=CHROMA_DIR,
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
