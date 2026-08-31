# AI Recruiting Platform

<p align="center">
  <img src="img/img1.png" alt="AI Recruiting Platform — discovered & ranked jobs" width="880">
</p>

An agentic job-application assistant. Upload your résumé and it will **discover** real
LinkedIn jobs, **rank** them against your profile, and **tailor** a résumé + cover letter
for the ones you choose — with a human in control at every consequential step.
(Automated apply — opening a real browser for you to submit — is currently **parked**;
see *Known limitations*.)

Built on **DeepAgents** (orchestration) · **LangGraph** (durable graphs, Postgres
checkpointer) · **LangChain** (models/tools) · **MCP** (external capabilities) ·
**FastAPI + Gradio** (mounted chat UI) · **Postgres/pgvector** (matching) · **S3**
(generated documents) · **LangSmith** (tracing/eval) · **JobSpy** (LinkedIn).

---

## What it does (end-to-end flow)

```
Upload résumé (PDF/DOCX/TXT)
        │
        ▼
[Start campaign] ──► DeepAgents orchestrator (plans with todos)
        │                 │
        │                 ├─► discovery subagent ──► search_jobs (MCP) ──► JobSpy ──► LinkedIn
        │                 │                                   └─► writes the jobs cache (app/storage.py)
        │                 └─► matching skill (in-context) ──► ranks jobs 0–100 with reasons
        ▼
   Streaming chat shows live progress → ranked list
        │
        │  you type "yes, proceed"
        ▼
   tailoring_worker subagent ──► tailored résumé + cover letter (grounded)
        │                              └─► written to DeepAgents virtual FS (state["files"])
        ▼
   Documents uploaded to S3 (or ./outputs locally) ──► 📎 download links in chat
        │
        │  pick a job in the "Approve a job" dropdown → [Approve & open apply page]
        ▼
   Parked: returns the posting link for YOU to open and apply yourself
```

**Guiding principle:** the agent **prepares** materials; a **human performs** every
outward action. The orchestrator has no ability to submit applications (its submit
tools are physically removed).

---

## Architecture

### How the layers map

- **DeepAgents** — the orchestrator harness: planning (`write_todos`), a virtual
  filesystem that holds generated documents, and a lean set of **subagents** each in an
  isolated context.
- **Subagents (2, by design)** — `discovery` (isolates bulky raw postings) and
  `tailoring_worker` (spawned per job for tailoring + cover letter). Subagent _count_ is
  driven by context-isolation/parallelism, not by role names.
- **Skills** — portable procedural knowledge (`SKILL.md`): tailoring, matching,
  cover-letter, ats-formatting. The **matching** skill is applied by the orchestrator
  in-context; the tailoring worker loads tailoring + cover-letter.
- **LangGraph** — the durable `application_graph` with an `interrupt()` human-approval
  gate (built; reserved for future ATS auto-submit). Chat threads persist via a
  Postgres checkpointer (`app/db.py`) so they survive process restarts.
- **MCP servers** — external capabilities as decoupled services: `job-boards` (LinkedIn
  search), `ats` (Greenhouse/Lever/Workday), `browser` (Playwright submit, unreachable —
  stripped from the orchestrator and not wired to the UI).
- **Postgres/pgvector** — vector store for semantic matching (built; see _Known
  limitations_), same RDS instance as the checkpointer.
- **FastAPI** — mounts the Gradio UI at `/ui` and exposes a light `/api/health` for the
  load balancer (`app/main.py`).
- **LangSmith** — traces every run (enabled by importing `app.config`) and hosts the
  grounding eval.

### Directory layout

```
JobsAgent/
├── app/
│   ├── main.py                 # FastAPI entrypoint: /api/health + mounts Gradio at /ui
│   ├── config.py                # settings + LangSmith tracing (import = tracing on)
│   ├── db.py                    # Postgres checkpointer + pgvector extension bootstrap
│   ├── storage.py                # generated-document storage (S3, local disk fallback)
│   ├── state.py                # Pydantic schemas
│   ├── skills_loader.py       # read SKILL.md into agent context
│   ├── orchestrator.py        # DeepAgents orchestrator (skills + 2 subagents, hardened)
│   ├── agents/
│   │   └── application_graph.py   # LangGraph HITL approval graph (interrupt gate)
│   ├── tools/
│   │   ├── resume_tools.py    # extract_profile, check_grounding (@tool)
│   │   ├── mcp_client.py      # MultiServerMCPClient wiring
│   │   └── browser_apply.py   # visible logged-in browser for applying (parked, unused)
│   ├── rag/
│   │   └── vectorstore.py     # pgvector index/match (built, not yet wired into ranking)
│   └── ui/
│       └── gradio_app.py      # streaming chat UI + downloads + approve; build_ui()
├── mcp_servers/
│   ├── job_boards_server.py   # FastMCP :8001 — LinkedIn via JobSpy (+ jobs cache)
│   ├── ats_server.py          # FastMCP :8002 — ATS read/submit tools
│   └── browser_server.py      # FastMCP stdio — Playwright submit (unreachable, parked)
├── skills/{tailoring,matching,cover-letter,ats-formatting}/SKILL.md
├── evals/tailoring_eval.py    # LangSmith grounding eval
├── deploy/{Dockerfile, fargate.md}
├── docker-compose.yml          # local Postgres+pgvector for DATABASE_URL
├── outputs/                   # local-fallback docs + _jobs_cache.json   (gitignored)
├── run_local.sh               # start MCP servers + the FastAPI/Gradio app
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
docker compose up -d postgres        # local Postgres+pgvector for DATABASE_URL
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
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_recruiter

# Optional (defaults live in app/config.py)
MODEL=openai:gpt-4o-mini
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=ai-recruiter
EMBEDDING_MODEL=text-embedding-3-small
S3_BUCKET=                       # unset locally → documents land in ./outputs instead
GRADIO_AUTH_USER=
GRADIO_AUTH_PASS=
```

`app/config.py` reads these with `os.getenv`; nothing auto-loads `.env`, so either
`source` it (the launcher does this) or add `python-dotenv` yourself.

---

## Running locally

### One command (recommended)

```bash
docker compose up -d postgres        # first time only
./run_local.sh
```

This loads `.env`, starts the two HTTP MCP servers (`:8001`, `:8002`), **waits** for both
ports, launches FastAPI + the mounted Gradio UI at **http://localhost:8000/ui**
(health check at `/api/health`), and stops the servers on `Ctrl+C`. The `browser` MCP
server is stdio (auto-spawned) — no separate process.

### Manual (3 terminals)

```bash
# Terminal 1
python3 mcp_servers/job_boards_server.py     # → http://localhost:8001/mcp
# Terminal 2
python3 mcp_servers/ats_server.py            # → http://localhost:8002/mcp
# Terminal 3
set -a; source .env; set +a
uvicorn app.main:app --host 0.0.0.0 --port 8000   # → http://localhost:8000/ui
```

If the UI starts before the servers, campaigns fail with
`httpx.ConnectError: All connection attempts failed` — start the servers first.

### Using the app

1. Upload a résumé (**PDF / DOCX / TXT**), set a location, click **Start campaign**.
   Progress streams live; a ranked list appears and the **Approve a job** dropdown fills.
2. Reply **"yes, proceed"** (or "focus on the top 3", "draft a cover letter for X").
   Tailored résumés + cover letters appear as download links in the chat.
3. Pick a job → **Approve & open apply page** → currently returns the posting link
   (automated apply is parked; see *Known limitations*) — open it yourself to apply.

<p align="center">
  <img src="img/img2.png" alt="Tailored cover letter generated in-app" width="880">
</p>

---

## How the pieces work

### MCP servers

- **`job-boards` (:8001)** — `search_jobs(query, location, limit=10)` scrapes LinkedIn via
  JobSpy, returns normalized postings with **descriptions truncated to ~800 chars** and
  **capped at 10** jobs (this keeps the agent under gpt-4o-mini's 200k tokens/min limit;
  without it, runs stall on `429` retries). Also writes results via `app/storage.py`
  (`JOBS_CACHE_KEY`) for the UI's approve dropdown, since subagent tool results don't
  reach the parent stream — this goes through S3 in prod because `job-boards` and the
  UI run as separate ECS services with no shared disk.
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

`app/ui/gradio_app.py` exposes `build_ui()`, mounted into FastAPI by `app/main.py`
(`gr.mount_gradio_app(app, demo, path="/ui")`) rather than launched standalone. Handlers
iterate `agent.astream(..., stream_mode="updates")` and `yield` live progress. After each
turn it reads the agent's virtual filesystem (`state["files"]`), persists documents via
`app/storage.py` (S3 presigned URLs when `S3_BUCKET` is set, `./outputs/<thread_id>/`
otherwise), and links them in the chat. The **Approve a job** dropdown is filled from the
jobs cache; **Approve & open apply page** is parked — it returns the posting link instead
of opening a browser (see *Known limitations*).

---

## Safety & guardrails

- **No autonomous submission.** Orchestrator can't submit (tools removed); applying is a
  human action (currently: opening the posting link yourself — see *Known limitations*).
- **Anti-fabrication.** The tailoring skill forbids inventing experience and calls
  `check_grounding`; a LangSmith eval scores "no fabrication" (`evals/tailoring_eval.py`).
- **LinkedIn ToS.** JobSpy scrapes public listings (gray-area, low-volume only); Easy
  Apply automation is deliberately avoided.
- **Secrets.** `.env` and `outputs/` are gitignored.

---

## Deployment

See `rag-agent-aws-plan.md` for the FastAPI+Gradio ECS Fargate build (VPC, ALB, RDS,
S3, IAM, step by step). `deploy/` has the app-specific parts on top of that plan:
`Dockerfile` builds the image (`uvicorn app.main:app`, one worker, port 8000);
`deploy/fargate.md` covers running `job-boards`/`ats` as separate ECS services, the
known jobs-cache cross-container gap, and **Bedrock AgentCore** as an alternative path.

---

## Known limitations / open items

- **pgvector isn't wired into matching yet.** `app/rag/vectorstore.py` works, but the
  orchestrator ranks in-context; the vector store only fills when called directly. Wiring
  retrieval→rubric is a planned improvement.
- **Tailoring quality.** `extract_profile` and `check_grounding` are stubs; tailored
  résumés can contain template placeholders (`[Your Name]`) instead of grounding in the
  uploaded résumé. Tightening the tailoring prompt + implementing `check_grounding` is next.
- **Apply automation is parked.** The old visible-Chromium apply flow
  (`app/tools/browser_apply.py`) needed a display and a persistent local browser
  profile — incompatible with a headless ECS task. `approve_and_open` now returns the
  posting link instead. The `application_graph` auto-submit path exists but isn't wired
  to the UI either.
- **Single-campaign jobs cache.** `job-boards` hands discovered postings to the UI via
  `app/storage.py` (S3 in prod, local disk in dev) under one shared key, cleared at
  each campaign start — works across separate ECS tasks now, but two campaigns running
  concurrently (multiple users) would still clobber each other's "Approve a job" list.
  Scoping the cache per-thread is a planned improvement.
