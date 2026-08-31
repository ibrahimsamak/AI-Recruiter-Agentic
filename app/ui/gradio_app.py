# Run locally: ./run_local.sh  ·  see README.md
# AI-Recruiter-Agentic · Gradio chat UI (mounted into FastAPI, see app/main.py)
# app/ui/gradio_app.py
"""Gradio chat UI — streaming, document downloads, and (parked) assisted apply.

Flow:
  1. Upload a resume → Start campaign → agent searches LinkedIn, ranks (streaming).
     The ranked jobs are captured into an "Approve a job" dropdown.
  2. Chat "yes, proceed" → agent drafts tailored resumes + cover letters, persisted
     via app/storage.py (S3 presigned URLs, or ./outputs/<thread_id>/ locally) and
     linked in the chat.
  3. Pick a job + "Approve & open apply page" → parked: returns the posting link for
     you to open and apply yourself. The agent itself cannot submit (its submit tools
     are stripped) regardless.
"""
import asyncio
import base64
import uuid
from pathlib import Path

import gradio as gr
from deepagents.backends.utils import file_data_to_string

from app.db import get_checkpointer
from app.orchestrator import build_orchestrator
from app.storage import JOBS_CACHE_KEY, delete_json, load_json, save_document
from app.tools.mcp_client import load_mcp_tools


def _read_jobs_cache() -> dict:
    """Return {label: url} for the current campaign's discovered jobs."""
    data = load_json(JOBS_CACHE_KEY, default=[]) or []
    return {
        f"{j.get('title', '?')} — {j.get('company', '?')}": j["url"]
        for j in data
        if j.get("url")
    }


def read_resume(file_path: str) -> str:
    """Extract plain text from a resume file (PDF, DOCX, or TXT)."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if ext == ".docx":
        import docx

        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs).strip()
    return Path(file_path).read_text(encoding="utf-8", errors="ignore").strip()


def _content_to_text(content) -> str:
    """Flatten a LangChain message content (str OR list of blocks) to markdown."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
        return "\n".join(p for p in parts if p)
    return str(content)


# --- one shared agent (MCP tools loaded once), threads isolate conversations ---
_agent = None
_agent_lock = asyncio.Lock()


async def get_agent():
    global _agent
    async with _agent_lock:
        if _agent is None:
            mcp_tools = await load_mcp_tools()
            checkpointer = await get_checkpointer()
            _agent = build_orchestrator(mcp_tools, checkpointer=checkpointer)
    return _agent


async def _collect_files(thread_id: str) -> list[tuple[str, str]]:
    """Persist the agent's virtual files for this thread; return [(filename, url), ...]."""
    agent = await get_agent()
    snap = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    files = (snap.values or {}).get("files") or {}
    if not files:
        return []
    results: list[tuple[str, str]] = []
    for vpath, fdata in files.items():
        filename = Path(vpath).name or "file"
        try:
            encoding = fdata.get("encoding", "utf-8") if isinstance(fdata, dict) else "utf-8"
            if encoding == "base64":
                data = base64.b64decode(fdata["content"])
            else:
                text = file_data_to_string(fdata) if isinstance(fdata, dict) else str(fdata)
                data = text.encode("utf-8")
            url = save_document(thread_id, filename, data)
            results.append((filename, url))
        except Exception:
            continue
    return sorted(results)


def _summarize(update: dict, steps: list) -> str:
    """Progress lines; return the latest assistant text seen in this update."""
    final_text = ""
    for payload in (update or {}).values():
        messages = payload.get("messages") if isinstance(payload, dict) else None
        for m in messages or []:
            mtype = getattr(m, "type", None)
            tool_calls = getattr(m, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    steps.append(f"🔧 calling `{tc.get('name', 'tool')}`")
            elif mtype == "tool":
                steps.append(f"✓ `{getattr(m, 'name', 'tool')}` returned")
            elif mtype == "ai":
                txt = _content_to_text(getattr(m, "content", "")).strip()
                if txt:
                    final_text = txt
    return final_text


async def _stream_reply(content: str, thread_id: str):
    """Async-generator yielding the assistant bubble text as the agent works."""
    agent = await get_agent()
    steps: list[str] = []
    final_text = ""
    async for update in agent.astream(
        {"messages": [{"role": "user", "content": content}]},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="updates",
    ):
        maybe_final = _summarize(update, steps)
        if maybe_final:
            final_text = maybe_final
        recent = "\n".join(f"- {s}" for s in steps[-12:])
        yield f"⏳ **Working…**\n\n{recent}"
    yield final_text or ("\n".join(f"- {s}" for s in steps) or "_(no output)_")


def _render_downloads(files: list[tuple[str, str]]) -> str:
    if not files:
        return ""
    links = "\n".join(f"- [{name}]({url})" for name, url in files)
    return f"\n\n---\n**📎 Generated documents:**\n\n{links}"


async def start_campaign(resume_file, location):
    """Seed a new thread from the uploaded resume (streaming). Captures jobs."""
    if resume_file is None:
        yield [], None, "", "", gr.update(), {}
        return
    resume_text = read_resume(resume_file)
    thread_id = str(uuid.uuid4())
    # Scope the approve list to THIS campaign: clear the cache the MCP server fills.
    delete_json(JOBS_CACHE_KEY)
    seed = (
        f"Candidate resume:\n{resume_text}\n\n"
        f"Find, rank, and tailor for jobs in {location}. Do not submit anything."
    )
    base = [{"role": "user", "content": f"📄 Started a campaign for **{location}**."}]

    yield base + [{"role": "assistant", "content": "⏳ **Working…** (searching LinkedIn — can take ~30s)"}], thread_id, "", "", gr.update(), {}
    last = ""
    async for bubble in _stream_reply(seed, thread_id):
        last = bubble
        yield base + [{"role": "assistant", "content": bubble}], thread_id, "", gr.update(), gr.update(), {}

    files = await _collect_files(thread_id)
    jobs = _read_jobs_cache()
    labels = list(jobs.keys())
    dd = gr.update(choices=labels, value=(labels[0] if labels else None))
    yield base + [{"role": "assistant", "content": last + _render_downloads(files)}], thread_id, "", _render_downloads(files), dd, jobs


async def respond(message, history, thread_id):
    """Continue the conversation on the existing thread (streaming)."""
    history = history or []
    if not message or not message.strip():
        yield history, "", gr.update()
        return
    if not thread_id:
        yield history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": "Please upload a resume and click **Start campaign** first."},
        ], "", gr.update()
        return

    base = history + [{"role": "user", "content": message}]
    yield base + [{"role": "assistant", "content": "⏳ **Working…**"}], "", gr.update()
    last = ""
    async for bubble in _stream_reply(message, thread_id):
        last = bubble
        yield base + [{"role": "assistant", "content": bubble}], "", gr.update()

    files = await _collect_files(thread_id)
    yield base + [{"role": "assistant", "content": last + _render_downloads(files)}], "", (_render_downloads(files) or gr.update())


def approve_and_open(selected_label, job_map):
    """Parked: server-side browser automation can't run in a headless ECS task
    (no display, no persistent local profile across replicas/restarts). Until
    that's redesigned (e.g. hand the candidate a link to open themselves), this
    is a deliberate no-op."""
    job_map = job_map or {}
    if not selected_label or selected_label not in job_map:
        return "⚠️ Pick a job from the **Approve a job** list first (run a campaign to populate it)."
    url = job_map[selected_label]
    return (
        "🚧 **Apply automation is parked for now.** Open this link yourself to apply:\n\n"
        f"{url}"
    )


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="AI Recruiter") as demo:
        gr.Markdown(
            "## AI Recruiting Platform\n"
            "Upload your resume and start a campaign, then chat with the agent — "
            "reply **“yes, proceed”** to draft tailored resumes and cover letters. "
            "_(Automated apply is currently parked — pick a job below for its link.)_"
        )

        thread_id = gr.State(None)
        job_map = gr.State({})

        with gr.Row():
            resume = gr.File(
                label="Resume (PDF / DOCX / TXT)",
                file_types=[".pdf", ".docx", ".txt"],
                type="filepath",
                scale=3,
            )
            location = gr.Textbox(label="Target location", value="Toronto, ON", scale=2)
            start_btn = gr.Button("Start campaign", variant="primary", scale=1)

        chatbot = gr.Chatbot(label="Campaign", height=440)
        generated = gr.Markdown(label="📎 Generated documents")

        with gr.Row():
            msg = gr.Textbox(
                label="Message",
                placeholder="e.g. yes, proceed  ·  focus on the top 3  ·  draft a cover letter for the Bentley role",
                scale=5,
            )
            send_btn = gr.Button("Send", scale=1)

        with gr.Row():
            approve_dd = gr.Dropdown(label="Approve a job to apply", choices=[], scale=4)
            approve_btn = gr.Button("Approve & open apply page", variant="secondary", scale=2)
        approve_status = gr.Markdown()

        start_btn.click(
            fn=start_campaign,
            inputs=[resume, location],
            outputs=[chatbot, thread_id, msg, generated, approve_dd, job_map],
        )
        send_btn.click(fn=respond, inputs=[msg, chatbot, thread_id], outputs=[chatbot, msg, generated])
        msg.submit(fn=respond, inputs=[msg, chatbot, thread_id], outputs=[chatbot, msg, generated])
        approve_btn.click(fn=approve_and_open, inputs=[approve_dd, job_map], outputs=[approve_status])

    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="0.0.0.0", server_port=7860)
