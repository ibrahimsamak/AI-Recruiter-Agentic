# Run locally: ./run_local.sh  ·  see README.md
# AI-Recruiter-Agentic · Gradio chat UI (entrypoint)
# app/ui/gradio_app.py
"""Gradio chat UI — streaming, document downloads, and Model B assisted apply.

Flow:
  1. Upload a resume → Start campaign → agent searches LinkedIn, ranks (streaming).
     The ranked jobs are captured into an "Approve a job" dropdown.
  2. Chat "yes, proceed" → agent drafts tailored resumes + cover letters, which are
     materialized to ./outputs/<thread_id>/ and offered as downloads.
  3. Pick a job + "Approve & open apply page" → a VISIBLE, logged-in Chromium opens
     at that job's page for you to review and submit manually (Model B). The agent
     itself cannot submit (its submit tools are stripped); apply is a deliberate,
     human-driven action outside the agent.
"""
import asyncio
import base64
import json
import subprocess
import sys
import uuid
from pathlib import Path

import gradio as gr
from deepagents.backends.utils import file_data_to_string
from langgraph.checkpoint.memory import InMemorySaver

from app.orchestrator import build_orchestrator
from app.tools.mcp_client import load_mcp_tools

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs"
JOBS_CACHE = OUTPUT_ROOT / "_jobs_cache.json"  # written by the job-boards MCP server


def _read_jobs_cache() -> dict:
    """Return {label: url} for the current campaign's discovered jobs."""
    try:
        data = json.loads(JOBS_CACHE.read_text())
        return {
            f"{j.get('title', '?')} — {j.get('company', '?')}": j["url"]
            for j in data
            if j.get("url")
        }
    except Exception:
        return {}


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
            _agent = build_orchestrator(mcp_tools, checkpointer=InMemorySaver())
    return _agent


async def _collect_files(thread_id: str) -> list[str]:
    """Materialize the agent's virtual files for this thread to real disk paths."""
    agent = await get_agent()
    snap = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    files = (snap.values or {}).get("files") or {}
    if not files:
        return []
    out_dir = OUTPUT_ROOT / thread_id
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for vpath, fdata in files.items():
        real = out_dir / (Path(vpath).name or "file")
        try:
            encoding = fdata.get("encoding", "utf-8") if isinstance(fdata, dict) else "utf-8"
            if encoding == "base64":
                real.write_bytes(base64.b64decode(fdata["content"]))
            else:
                text = file_data_to_string(fdata) if isinstance(fdata, dict) else str(fdata)
                real.write_text(text, encoding="utf-8")
            paths.append(str(real))
        except Exception:
            continue
    return sorted(paths)


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


_DOWNLOAD_NOTE = "\n\n---\n**📎 Generated documents are ready — download them from the panel below.**"


async def start_campaign(resume_file, location):
    """Seed a new thread from the uploaded resume (streaming). Captures jobs."""
    if resume_file is None:
        yield [], None, "", None, gr.update(), {}
        return
    resume_text = read_resume(resume_file)
    thread_id = str(uuid.uuid4())
    # Scope the approve list to THIS campaign: clear the cache the MCP server fills.
    try:
        JOBS_CACHE.unlink()
    except Exception:
        pass
    seed = (
        f"Candidate resume:\n{resume_text}\n\n"
        f"Find, rank, and tailor for jobs in {location}. Do not submit anything."
    )
    base = [{"role": "user", "content": f"📄 Started a campaign for **{location}**."}]

    yield base + [{"role": "assistant", "content": "⏳ **Working…** (searching LinkedIn — can take ~30s)"}], thread_id, "", [], gr.update(), {}
    last = ""
    async for bubble in _stream_reply(seed, thread_id):
        last = bubble
        yield base + [{"role": "assistant", "content": bubble}], thread_id, "", gr.update(), gr.update(), {}

    files = await _collect_files(thread_id)
    jobs = _read_jobs_cache()
    labels = list(jobs.keys())
    dd = gr.update(choices=labels, value=(labels[0] if labels else None))
    note = _DOWNLOAD_NOTE if files else ""
    yield base + [{"role": "assistant", "content": last + note}], thread_id, "", (files or []), dd, jobs


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
    note = _DOWNLOAD_NOTE if files else ""
    yield base + [{"role": "assistant", "content": last + note}], "", (files or gr.update())


def approve_and_open(selected_label, job_map):
    """Model B: open the approved job's page in a visible, logged-in browser."""
    job_map = job_map or {}
    if not selected_label or selected_label not in job_map:
        return "⚠️ Pick a job from the **Approve a job** list first (run a campaign to populate it)."
    url = job_map[selected_label]
    # Detached subprocess so the browser window outlives this request.
    subprocess.Popen(
        [sys.executable, "-m", "app.tools.browser_apply", url],
        cwd=str(PROJECT_ROOT),
    )
    return (
        f"🌐 Opening a **visible browser** at:\n\n{url}\n\n"
        "Review the posting, click **Apply**, and submit it yourself. "
        "First time only: log into LinkedIn in that window — the login is remembered."
    )


with gr.Blocks(title="AI Recruiter") as demo:
    gr.Markdown(
        "## AI Recruiting Platform\n"
        "Upload your resume and start a campaign, then chat with the agent — "
        "reply **“yes, proceed”** to draft tailored resumes and cover letters. "
        "To apply, pick a job below and **Approve & open apply page** — a real browser "
        "opens for you to submit. _(The agent never submits; applying is your action.)_"
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
    generated = gr.Files(label="📎 Generated documents (download)", interactive=False)

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


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
