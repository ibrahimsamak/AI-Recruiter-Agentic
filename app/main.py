# AI-Recruiter-Agentic · FastAPI entrypoint (mounts Gradio at /ui)
# app/main.py
"""FastAPI app: a light health check for the ALB, Gradio mounted at /ui.

Run with a SINGLE uvicorn worker (see deploy/Dockerfile) — multiple workers
would give the mounted Gradio app multiple independent queues in one task, so
a session's follow-up events could land on a different worker and break.
"""
from contextlib import asynccontextmanager

import gradio as gr
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import GRADIO_AUTH_PASS, GRADIO_AUTH_USER, S3_BUCKET
from app.db import close_checkpointer, ensure_pgvector_extension
from app.storage import LOCAL_OUTPUT_ROOT
from app.ui.gradio_app import build_ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_pgvector_extension()
    yield
    await close_checkpointer()


app = FastAPI(lifespan=lifespan)


@app.get("/api/health")  # light check for the ALB (NOT the Gradio root)
def health():
    return {"status": "ok"}


if not S3_BUCKET:
    # Local-dev fallback only: in prod, S3_BUCKET is set and documents are
    # served via presigned URLs instead (see app/storage.py).
    LOCAL_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=str(LOCAL_OUTPUT_ROOT)), name="outputs")

demo = build_ui()
demo.queue()

_auth = (GRADIO_AUTH_USER, GRADIO_AUTH_PASS) if GRADIO_AUTH_USER and GRADIO_AUTH_PASS else None
app = gr.mount_gradio_app(app, demo, path="/ui", auth=_auth)
