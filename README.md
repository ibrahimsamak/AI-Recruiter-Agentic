# AI Recruiting Platform

An agentic job-application assistant. Upload your résumé and it will **discover** real
LinkedIn jobs, **rank** them against your profile, **tailor** a résumé + cover letter for
the ones you choose, and open the **apply page in a real browser** for you to submit —
with a human in control at every consequential step.

Built on **DeepAgents** (orchestration) · **LangGraph** (durable graphs) ·
**LangChain** (models/tools) · **MCP** (external capabilities) · **ChromaDB** (matching) ·
**LangSmith** (tracing/eval) · **Gradio** (chat UI) · **JobSpy** (LinkedIn) ·
**Playwright** (assisted apply).

> Companion doc: **[ROADMAP.md](ROADMAP.md)** — a step-by-step guide to rebuild this
> project from scratch, with the gotchas we hit and how to verify each step.

---

## What it does (end-to-end flow)

```
Upload résumé (PDF/DOCX/TXT)
        │
        ▼
[Start campaign] ──► DeepAgents orchestrator (plans with todos)
        │                 │
        │                 ├─► discovery subagent ──► search_jobs (MCP) ──► JobSpy ──► LinkedIn
        │                 │                                   └─► writes outputs/_jobs_cache.json
        │                 └─► matching skill (in-context) ──► ranks jobs 0–100 with reasons
        ▼
   Streaming chat shows live progress → ranked list
        │
        │  you type "yes, proceed"
        ▼
   tailoring_worker subagent ──► tailored résumé + cover letter (grounded)
        │                              └─► written to DeepAgents virtual FS (state["files"])
        ▼
   Documents materialized to outputs/<thread>/ ──► 📎 download panel
        │
        │  pick a job in the "Approve a job" dropdown → [Approve & open apply page]
        ▼
   Visible, logged-in Chromium opens the posting ──► YOU review & submit  (Model B)
```

**Guiding principle:** the agent **prepares** materials; a **human performs** every
outward action. The orchestrator has no ability to submit applications (its submit
tools are physically removed), and applying is a deliberate, browser-based human step.

---

## Architecture

### How the layers map
- **DeepAgents** — the orchestrator harness: planning (`write_todos`), a virtual
  filesystem that holds generated documents, and a lean set of **subagents** each in an
  isolated context.
- **Subagents (2, by design)** — `discovery` (isolates bulky raw postings) and
  `tailoring_worker` (spawned per job for tailoring + cover letter). Subagent *count* is
  driven by context-isolation/parallelism, not by role names.
- **Skills** — portable procedural knowledge (`SKILL.md`): tailoring, matching,
  cover-letter, ats-formatting. The **matching** skill is applied by the orchestrator
  in-context; the tailoring worker loads tailoring + cover-letter.
- **LangGraph** — the durable `application_graph` with an `interrupt()` human-approval
  gate (built; reserved for future ATS auto-submit).
- **MCP servers** — external capabilities as decoupled services: `job-boards` (LinkedIn
  search), `ats` (Greenhouse/Lever/Workday), `browser` (Playwright submit).
- **ChromaDB** — vector store for semantic matching (built; see *Known limitations*).
- **LangSmith** — traces every run (enabled by importing `app.config`) and hosts the
  grounding eval.

### Directory layout
```
JobsAgent/
├── app/
│   ├── config.py              # settings + LangSmith tracing (import = tracing on)
│   ├── state.py               # Pydantic schemas
│   ├── skills_loader.py       # read SKILL.md into agent context
│   ├── orchestrator.py        # DeepAgents orchestrator (skills + 2 subagents, hardened)
│   ├── agents/
│   │   └── application_graph.py   # LangGraph HITL approval graph (interrupt gate)
│   ├── tools/
│   │   ├── resume_tools.py    # extract_profile, check_grounding (@tool)
│   │   ├── mcp_client.py      # MultiServerMCPClient wiring
│   │   └── browser_apply.py   # Model B: visible logged-in browser
│   ├── rag/
│   │   └── vectorstore.py     # ChromaDB index/match (built, not yet wired in)
│   └── ui/
│       └── gradio_app.py      # streaming chat UI + downloads + approve  ← entrypoint
├── mcp_servers/
│   ├── job_boards_server.py   # FastMCP :8001 — LinkedIn via JobSpy (+ jobs cache)
│   ├── ats_server.py          # FastMCP :8002 — ATS read/submit tools
│   └── browser_server.py      # FastMCP stdio — Playwright submit (approval-gated)
├── skills/{tailoring,matching,cover-letter,ats-formatting}/SKILL.md
├── evals/tailoring_eval.py    # LangSmith grounding eval
├── deploy/{Dockerfile, fargate.md}
├── outputs/                   # generated docs + _jobs_cache.json   (gitignored)
├── .browser-profile/          # persistent browser login for Model B (gitignored)
├── run_local.sh               # start MCP servers + UI with one command
├── requirements.txt
├── README.md                  # this file
└── ROADMAP.md                 # rebuild-from-scratch guide
```

---

## Setup

### 1. Python env + dependencies
Requires **Python 3.12**. This project runs on the **LangChain 1.x** line — do not let
any `0.3.x` sibling (`langchain`, `langchain-openai`, …) sneak in, or the resolver
breaks (see ROADMAP Step 0).

```bash
cd JobsAgent
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
playwright install chromium          # headed Chromium for Model B + browser MCP
```

Verify the stack is coherent:
```bash
pip check     # no langchain/langgraph conflicts
python -c "from deepagents import create_deep_agent; \
from langchain.agents.middleware import TodoListMiddleware; print('stack OK')"
```

### 2. Configuration — `.env`
Create `.env` in the project root (it's gitignored):

```ini
# Required
OPENAI_API_KEY=sk-...            # default model openai:gpt-4o-mini + embeddings
LANGSMITH_API_KEY=lsv2_...       # tracing + the grounding eval

# Optional (defaults live in app/config.py)
MODEL=openai:gpt-4o-mini
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=ai-recruiter
# CHROMA_DIR unset → defaults to app/rag/chroma  (don't set ./.chroma)
EMBEDDING_MODEL=text-embedding-3-small
```

`app/config.py` reads these with `os.getenv`; nothing auto-loads `.env`, so either
`source` it (the launcher does this) or add `python-dotenv` yourself.

---

## Running locally

### One command (recommended)
```bash
./run_local.sh
```
This loads `.env`, starts the two HTTP MCP servers (`:8001`, `:8002`), **waits** for both
ports, launches the Gradio UI at **http://localhost:7860**, and stops the servers on
`Ctrl+C`. The `browser` MCP server is stdio (auto-spawned) — no separate process.

### Manual (3 terminals)
```bash
# Terminal 1
python3 mcp_servers/job_boards_server.py     # → http://localhost:8001/mcp
# Terminal 2
python3 mcp_servers/ats_server.py            # → http://localhost:8002/mcp
# Terminal 3
set -a; source .env; set +a
python3 -m app.ui.gradio_app                 # → http://localhost:7860
```
If the UI starts before the servers, campaigns fail with
`httpx.ConnectError: All connection attempts failed` — start the servers first.

### Using the app
1. Upload a résumé (**PDF / DOCX / TXT**), set a location, click **Start campaign**.
   Progress streams live; a ranked list appears and the **Approve a job** dropdown fills.
2. Reply **"yes, proceed"** (or "focus on the top 3", "draft a cover letter for X").
   Tailored résumés + cover letters appear in the **📎 Generated documents** panel.
3. Pick a job → **Approve & open apply page** → a real browser opens at the posting.
   First time, log into LinkedIn there (it's remembered); review and submit yourself.

---

## How the pieces work

### MCP servers
- **`job-boards` (:8001)** — `search_jobs(query, location, limit=10)` scrapes LinkedIn via
  JobSpy, returns normalized postings with **descriptions truncated to ~800 chars** and
  **capped at 10** jobs (this keeps the agent under gpt-4o-mini's 200k tokens/min limit;
  without it, runs stall on `429` retries). Also writes results to `outputs/_jobs_cache.json`
  for the UI's approve dropdown, since subagent tool results don't reach the parent stream.
- **`ats` (:8002)** — `get_posting`, `list_application_fields` (safe reads) and
  `submit_to_ats` (write, approval-gated) for Greenhouse/Lever/Workday.
- **`browser` (stdio)** — `submit_application(url, form)` drives Playwright; Playwright is
  imported lazily so the server starts even without it. Approval-gated.
- **Client** (`app/tools/mcp_client.py`) — `MultiServerMCPClient` with env-overridable
  URLs defaulting to `localhost`; the stdio command uses `sys.executable` (not `"python"`).

### Orchestrator (hardened)
`build_orchestrator(mcp_tools, checkpointer)` builds a DeepAgents agent that plans with
todos, applies the matching skill in-context, and delegates to `discovery` +
`tailoring_worker`. **Submit tools are stripped** (`BLOCKED_ORCHESTRATOR_TOOLS =
{"submit_to_ats", "submit_application"}`) so no chat message can ever trigger a
submission — the guardrail is structural, not just a prompt instruction. A checkpointer
gives per-session chat memory (keyed by `thread_id`).

### UI (streaming + documents + approve)
`app/ui/gradio_app.py` is an async, streaming chat. Handlers iterate
`agent.astream(..., stream_mode="updates")` and `yield` live progress. After each turn it
reads the agent's virtual filesystem (`state["files"]`), writes documents to
`outputs/<thread_id>/`, and offers them as downloads. The **Approve a job** dropdown is
filled from the jobs cache; **Approve & open apply page** spawns Model B as a detached
subprocess.

### Model B — assisted apply
`app/tools/browser_apply.py` opens the job URL in a **visible** Chromium
(`launch_persistent_context(".browser-profile", headless=False)`), best-effort pre-fills
obvious fields, and keeps the window open until you close it. The persistent profile
keeps you logged in across runs. It **never auto-submits** — you click submit. Fully
automating LinkedIn's Easy Apply is intentionally not done (ToS + anti-bot + it needs
your session).

---

## Safety & guardrails
- **No autonomous submission.** Orchestrator can't submit (tools removed); applying is a
  human browser action.
- **Anti-fabrication.** The tailoring skill forbids inventing experience and calls
  `check_grounding`; a LangSmith eval scores "no fabrication" (`evals/tailoring_eval.py`).
- **LinkedIn ToS.** JobSpy scrapes public listings (gray-area, low-volume only); Easy
  Apply automation is deliberately avoided.
- **Secrets.** `.env`, `outputs/`, and `.browser-profile/` are gitignored.

---

## Deployment
See `deploy/`. `Dockerfile` builds the image (`python -m app.ui.gradio_app`, port 7860).
`deploy/fargate.md` covers **ECS Fargate** (Gradio+orchestrator service + separate MCP
services, ChromaDB on EFS, Postgres/DynamoDB checkpointer) and **Bedrock AgentCore**.
For real use, swap `InMemorySaver` for a durable checkpointer.

---

## Known limitations / open items
- **ChromaDB isn't wired into matching yet.** `app/rag/vectorstore.py` works, but the
  orchestrator ranks in-context; the vector store only fills when called directly. Wiring
  retrieval→rubric is a planned improvement.
- **Tailoring quality.** `extract_profile` and `check_grounding` are stubs; tailored
  résumés can contain template placeholders (`[Your Name]`) instead of grounding in the
  uploaded résumé. Tightening the tailoring prompt + implementing `check_grounding` is next.
- **Assisted, not automatic, apply.** Model B is human-in-the-loop by design. The
  `application_graph` auto-submit path exists but isn't wired to the UI.
- **Single-user local assumptions.** The jobs cache and browser profile are shared on
  disk; fine for local single-user, not multi-tenant.

---

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| `httpx.ConnectError: All connection attempts failed` | MCP servers not running — use `./run_local.sh` or start them first. |
| Campaign runs for minutes with no output | Token volume → `429` retries. Ensure the `search_jobs` cap (limit 10 + truncation) is in place; watch for very long résumés. |
| `TypeError: unexpected keyword argument 'instructions'` | `deepagents 0.7.x` renamed it to `system_prompt` (top-level and per-subagent). |
| `AttributeError: 'list' object has no attribute 'expandtabs'` | LangChain 1.x message content is a list of blocks — flatten with `_content_to_text`. |
| `gr.Chatbot ... unexpected keyword argument 'type'` | Gradio 6 removed `type="messages"`; drop it. |
| Generated files link to dead `sandbox:/...` | Use the **📎 download panel** — files are materialized to `outputs/<thread>/`. |
| `pip` dependency conflict on `langchain-core` | A `0.3.x` sibling crept in; reinstall on the 1.x line (ROADMAP Step 0). |
| Model B browser doesn't appear | Needs a desktop session (won't show over headless SSH); confirm headed Chromium via `playwright install chromium`. |
