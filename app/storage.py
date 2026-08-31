# AI-Recruiter-Agentic · shared blob storage (documents + jobs cache)
# app/storage.py
"""Persist generated résumés/cover letters (+ the jobs cache) and hand back a
URL/value to read them back.

Uses S3 when S3_BUCKET is set — Fargate task disk is ephemeral and NOT shared
across separate ECS services (the GUI and job-boards run as different tasks),
so both documents and the jobs cache must live somewhere reachable by every
container, not on one task's local disk. Falls back to local disk under
./outputs, served by app/main.py's /outputs route, so local dev works without
AWS credentials — that fallback is fine for a single-process local run, but
not across containers, which is the whole reason this module exists.
"""
import json
from pathlib import Path

from app.config import AWS_REGION, S3_BUCKET, S3_URL_TTL

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_OUTPUT_ROOT = PROJECT_ROOT / "outputs"

# Written by mcp_servers/job_boards_server.py, read by app/ui/gradio_app.py —
# two different processes/containers, hence going through this module.
JOBS_CACHE_KEY = "cache/jobs_cache.json"

_s3_client = None


def _s3():
    global _s3_client
    if _s3_client is None:
        import boto3

        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


def save_document(thread_id: str, filename: str, data: bytes) -> str:
    """Persist one generated document; return a URL the browser can download from."""
    if S3_BUCKET:
        key = f"docs/{thread_id}/{filename}"
        _s3().put_object(Bucket=S3_BUCKET, Key=key, Body=data)
        return _s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=S3_URL_TTL,
        )
    out_dir = LOCAL_OUTPUT_ROOT / thread_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / filename).write_bytes(data)
    return f"/outputs/{thread_id}/{filename}"


def save_json(key: str, obj) -> None:
    """Write a small JSON blob under `key` (e.g. JOBS_CACHE_KEY)."""
    data = json.dumps(obj).encode("utf-8")
    if S3_BUCKET:
        _s3().put_object(Bucket=S3_BUCKET, Key=key, Body=data)
        return
    path = LOCAL_OUTPUT_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def load_json(key: str, default=None):
    """Read back a blob written by save_json; `default` if it doesn't exist."""
    if S3_BUCKET:
        try:
            obj = _s3().get_object(Bucket=S3_BUCKET, Key=key)
            return json.loads(obj["Body"].read())
        except Exception:
            return default
    path = LOCAL_OUTPUT_ROOT / key
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def delete_json(key: str) -> None:
    """Best-effort delete (e.g. clearing the jobs cache at campaign start)."""
    if S3_BUCKET:
        try:
            _s3().delete_object(Bucket=S3_BUCKET, Key=key)
        except Exception:
            pass
        return
    try:
        (LOCAL_OUTPUT_ROOT / key).unlink()
    except Exception:
        pass
