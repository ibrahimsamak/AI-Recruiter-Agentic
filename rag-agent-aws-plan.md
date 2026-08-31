# AWS Implementation Plan — FastAPI + Gradio RAG/Agent App (mounted, single service)

> Target architecture: **one** ECS Fargate task running FastAPI with Gradio **mounted**
> (`/api` → FastAPI, `/ui` → Gradio), behind an ALB with **sticky sessions + WebSocket**,
> backed by **RDS Postgres + pgvector**, **S3** for documents, **Secrets Manager** for keys,
> and egress to an **LLM API** (external, or Bedrock via VPC endpoint).
>
> All steps are **AWS Console (GUI)** unless a code/SQL/CLI block is unavoidable.
> Region assumed: `ca-central-1` (Toronto) — change consistently if different.

---

## 0. Decisions to make before you start

| Decision | Options | Recommendation |
|---|---|---|
| **LLM egress** | (A) Amazon **Bedrock** via VPC endpoint · (B) External API (OpenAI/Anthropic) via NAT | **A** for a bank-friendly "inference never leaves the VPC" story; B if you need a specific external model |
| **Network posture** | (A) Private subnets + NAT/endpoints · (B) Public subnets + public IP, no NAT | **A** (this plan's default). B is cheaper and matches your prior log — documented in §2 as the alternative |
| **Vector store** | pgvector on RDS · OpenSearch · dedicated vector DB | **pgvector on RDS** — one datastore, transactional, nothing new to secure |
| **Task size** | — | Start **1 vCPU / 2 GB**, measure, raise to 4 GB if the loaded models/queue need it |

> **Reuse note:** if the `app-vpc`, `app-cluster`, `app-alb`, and RDS from your prior build
> already exist, you can reuse them and skip the create-from-scratch steps — just apply the
> **stickiness, idle-timeout, task-role, and secrets** changes, which are the parts that differ.

---

## Phase 1 — Application code prep (do this first, locally)

The infra is only correct if the app is shaped for it. Three things matter: the mount, a light
health endpoint, and **a single worker**.

### 1a. Mount Gradio into FastAPI
```python
# app/main.py
import gradio as gr
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/health")           # light health check for the ALB (NOT the Gradio root)
def health():
    return {"status": "ok"}

# ... your /api routers (auth, ingest, query) ...

def build_ui() -> gr.Blocks:
    with gr.Blocks() as demo:
        # your RAG / agent chat UI
        ...
    return demo

demo = build_ui()
demo.queue()                       # enable Gradio's streaming queue

# Gate the UI. Simple built-in auth for now; move to ALB OIDC/Cognito later.
app = gr.mount_gradio_app(app, demo, path="/ui", auth=("admin", "CHANGE_ME"))
```

### 1b. Run a SINGLE worker — critical for mounted Gradio
Multiple gunicorn workers = multiple independent Gradio queues **inside one container**, so a
user's follow-up event can hit a different worker and the session breaks — the same failure as
un-sticky replicas, but one level down where the ALB can't help. Run one async worker; a
RAG/agent app is I/O-bound (waiting on the LLM/DB), so one `uvicorn` worker handles high
concurrency fine.

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# non-root
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
# ONE worker on purpose (see 1b)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 1c. Config via env (values injected in Phase 6)
`AWS_REGION`, `S3_BUCKET`, `S3_URL_TTL`, `DATABASE_URL`, `SECRET_KEY`, `BEDROCK_MODEL_ID`
(or `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`), `CORS_ORIGINS` (can be empty — UI and API are
same-origin), plus your `LANGCHAIN_*` / LangSmith vars if used.

### 1d. Create the pgvector extension at startup or via migration
RDS supports `pgvector`, but the extension must be created once. Cleanest is an Alembic
migration (or app-startup guard) so you never touch the DB by hand:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 1e. Long agent runs
Keep responses **streaming** (Gradio queue + FastAPI `StreamingResponse`) so the connection stays
active during "thinking" gaps. If runs routinely exceed ~1–2 min, plan the **SQS + worker** offload
in Phase 9 rather than holding the HTTP request open.

---

## Phase 2 — Networking (VPC, subnets, egress, security groups)

### 2a. VPC (default: private subnets)
1. **VPC → Create VPC → "VPC and more"**: name `rag-app`, CIDR `10.0.0.0/16`, **2 AZs**,
   **2 public + 2 private** subnets.
2. **NAT gateways: In 1 AZ** (single NAT — cheapest that still lets private tasks reach the
   internet). *If using Bedrock-only egress, you can set NAT to **None** and rely on VPC endpoints
   (2c).*
3. **VPC endpoints:** add **S3 Gateway endpoint** (free). DNS hostnames + resolution **ON**.

### 2b. Interface VPC endpoints (only if you chose NAT = None / full-private)
**VPC → Endpoints → Create endpoint**, one each (each ~$7/mo), attached to the **private** subnets
with a dedicated `endpoints-sg` allowing 443 from `ecs-sg`:
- `com.amazonaws.ca-central-1.ecr.api`
- `com.amazonaws.ca-central-1.ecr.dkr`
- `com.amazonaws.ca-central-1.logs`
- `com.amazonaws.ca-central-1.secretsmanager`
- `com.amazonaws.ca-central-1.sts`
- `com.amazonaws.ca-central-1.bedrock-runtime`  ← **the Bedrock egress path (Option A)**

> Rule of thumb: **one NAT** is simpler than six interface endpoints; go endpoints-only when a
> review demands zero internet egress.

### 2c. Security groups (restrict inbound, leave outbound open)
**VPC → Security groups → Create**, three tiers:
- `alb-sg` — inbound **80 & 443** from `0.0.0.0/0`
- `ecs-sg` — inbound **8000** from `alb-sg`
- `rds-sg` — inbound **5432** from `ecs-sg`

> **Alternative (Option B — cost-optimized, matches your prior log):** skip NAT and endpoints,
> place tasks in **public** subnets with **Public IP ON**. Cheaper, but task ENIs become
> internet-addressable and Bedrock loses its in-VPC advantage. Documented; not the default here.

---

## Phase 3 — Data & secrets

### 3a. RDS PostgreSQL (private)
1. **RDS → Create database → Standard → PostgreSQL** (15.x+ for pgvector).
2. Templates: **Dev/Test** (or Production for Multi-AZ). Credentials: set master user/password.
3. Connectivity: **app-vpc**, **do NOT connect to EC2**, **Public access: No**, VPC SG = `rds-sg`,
   place in a **DB subnet group on the private subnets**.
4. Create. Note the endpoint → this becomes `DATABASE_URL`
   (`postgresql+asyncpg://user:pass@<endpoint>:5432/dbname`).
5. Create the extension (Phase 1d) once the app or a migration can reach it.

### 3b. S3 bucket for documents
1. **S3 → Create bucket**: `rag-documents-<unique>`, **Block all public access ON**,
   **Default encryption ON** (SSE-S3 or SSE-KMS).
2. Objects live under a prefix like `docs/`; served back via **presigned GET URLs** (bucket private).

### 3c. Secrets Manager
1. **Secrets Manager → Store a new secret → Other type**.
2. Keys: `DATABASE_URL`, `SECRET_KEY`, and `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` **only if** using
   an external model (Bedrock uses IAM, no key). Name it `rag-app/production`. KMS = `aws/secretsmanager`.

> **Permissions-boundary caveat (from your prior account):** if the boundary blocks
> `secretsmanager:GetSecretValue` for the execution role, the injection in Phase 6 will fail.
> Either get the boundary updated (correct fix) or fall back to plain env vars **knowing the
> values are then visible in the task definition**. Prefer fixing the boundary.

---

## Phase 4 — Build & push image (ECR)

1. **ECR → Create repository**: `rag-app` (private, **scan on push ON**).
2. Build **for Fargate's arch** (Apple Silicon is arm64; Fargate default is x86):
   ```bash
   docker build --platform linux/amd64 -t rag-app .
   ```
3. Push (brace the tag so zsh doesn't parse `:latest` as a modifier):
   ```bash
   REG=<acct>.dkr.ecr.ca-central-1.amazonaws.com
   aws ecr get-login-password --region ca-central-1 | docker login --username AWS --password-stdin $REG
   docker tag rag-app:latest "${REG}/rag-app:latest"
   docker push "${REG}/rag-app:latest"
   ```

---

## Phase 5 — IAM roles

**IAM → Roles → Create role → AWS service → Elastic Container Service → ECS Task.**

### 5a. `rag-task-role` (the app's runtime identity — no keys in the image)
Inline policy — least privilege:
- `s3:PutObject`, `s3:GetObject` on `arn:aws:s3:::rag-documents-<unique>/docs/*`
- **If Bedrock:** `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` on your model ARN(s)

### 5b. `ecsTaskExecutionRole` (platform identity — pull image, logs, read secrets)
- Attach managed **`AmazonECSTaskExecutionRolePolicy`**.
- Add inline `secretsmanager:GetSecretValue` on `arn:aws:secretsmanager:ca-central-1:<acct>:secret:rag-app/production*`
  (needed for the Phase 6 `secrets` block).

---

## Phase 6 — ECS task definition + service

### 6a. Task definition
1. **ECS → Task definitions → Create new → Fargate.**
2. OS/Arch: **Linux / X86_64**. Size: **1 vCPU / 2 GB** (raise to 4 GB after measuring).
3. Task role = `rag-task-role`; Execution role = `ecsTaskExecutionRole`.
4. Container: name `rag-app`, image `${REG}/rag-app:latest`, **port 8000**.
5. **Environment variables** (plain): `AWS_REGION`, `S3_BUCKET`, `S3_URL_TTL`, `CORS_ORIGINS`,
   `BEDROCK_MODEL_ID` (if Bedrock).
6. **Secrets** (from Secrets Manager → resolves to env at launch): `DATABASE_URL`, `SECRET_KEY`,
   and the LLM API key if external.
7. Logging: **awslogs** → auto-create `/ecs/rag-app`.
8. **Do not set `AWS_PROFILE`** — boto3 uses the task role automatically.

### 6b. Service (create after the ALB target group in Phase 7 exists, or create together)
1. **ECS → Clusters → `app-cluster` (or create `rag-cluster`) → Create service.**
2. Launch type **Fargate**, task def `rag-app`, **desired = 1**.
3. Network: app-vpc, **private** subnets (Option A) *or* public + Public IP ON (Option B), SG `ecs-sg`.
4. Load balancing: attach to the ALB / listener / **target group from Phase 7**.
5. Health-check **grace period 300s** (cold task loads models before it's healthy).

> **Scaling:** because Gradio is sticky/stateful, prefer **vertical** growth (bigger task) over many
> replicas. If you later run >1 replica, stickiness (Phase 7c) is mandatory, and that's your signal
> the API may want to split from the UI.

---

## Phase 7 — ALB (target group, stickiness, WebSocket, idle timeout, HTTPS)

### 7a. Target group
1. **EC2 → Target groups → Create target group → IP addresses.**
2. Protocol **HTTP**, port **8000**, VPC app-vpc.
3. Health check path **`/api/health`**, success code **200**, healthy threshold 2, interval 15s.

### 7b. Load balancer + listener
1. **EC2 → Load balancers → Create → Application Load Balancer**, internet-facing, **both public
   subnets**, SG `alb-sg`.
2. Listener **HTTP :80** → forward to the target group (add path rules if you also route `/static`).

### 7c. Stickiness — required for Gradio
1. **EC2 → Target groups → [your tg] → Attributes → Edit.**
2. Toggle **Stickiness = On**, type **Load balancer generated cookie** (`lb_cookie`),
   duration e.g. **86400s** (1 day; shorten if sessions are short-lived).
3. Save. This pins a browser to one task so its Gradio queue/WebSocket events land consistently.

### 7d. WebSocket + idle timeout
- **WebSockets need no ALB toggle** — the ALB proxies the HTTP `Upgrade` natively as long as the
  target group is HTTP and the app upgrades correctly.
- **Raise the idle timeout:** **EC2 → Load balancers → [alb] → Attributes → Edit →
  "Connection idle timeout" → set 300** (or higher). The 60s default drops streaming connections
  during quiet "thinking" gaps in long agent runs.

### 7e. HTTPS (do before real use)
1. **ACM → Request a public certificate** for your domain, **DNS validation** (via Route 53).
2. **EC2 → Load balancers → [alb] → Add listener :443**, attach the ACM cert, forward to the same
   target group.
3. Edit the **:80** listener → **redirect to :443**.

---

## Phase 8 — Verify

```bash
BASE=https://<your-domain-or-alb-dns>
curl -s $BASE/api/health                       # -> {"status":"ok"}
# open $BASE/ui in a browser -> Gradio loads, prompts for auth
# run a query -> streams tokens; refresh mid-session -> same task (stickiness) -> session intact
```
Checklist: health 200 · `/ui` gated + loads · streaming works · a long run doesn't drop at ~60s ·
document upload lands in S3 under `docs/` · retrieval returns from pgvector.

---

## Phase 9 — Hardening & next steps

- [ ] **Availability:** raise desired to **2 across both AZs** once stickiness is confirmed.
- [ ] **Long jobs:** if agent runs exceed ~2 min, add **SQS + a worker** (same image, different
      `CMD`) and have the UI stream/poll status instead of holding the request.
- [ ] **UI auth:** move `/ui` from Gradio basic auth to **ALB OIDC / Cognito**.
- [ ] **WAF:** attach **AWS WAF** to the ALB (rate limits, managed rule sets) — expected for FinTech.
- [ ] **Observability:** LangSmith for agent traces + CloudWatch for infra; add a per-request
      timeout and a loop/step cap as a cost guard on the agent.
- [ ] **IaC:** codify all of the above in **Terraform** + a GitHub Actions deploy on image push.

---

## Gotchas (carried forward + new for this arch)
1. **Multiple workers break Gradio** — run **one** worker per task (Phase 1b).
2. **No stickiness → broken sessions** the moment you run >1 replica (Phase 7c).
3. **60s idle timeout drops long streams** — raise it (Phase 7d).
4. **Health check must be `/api/health`, not `/ui`** — the Gradio root is heavy and can flap.
5. **Permissions boundary can block Secrets Manager** — fix the boundary or accept plain env vars
   (with the exposure that implies).
6. **pgvector extension** must be created once (`CREATE EXTENSION vector`) — do it in a migration.
7. **Apple Silicon builds arm64**; Fargate is x86 → `--platform linux/amd64`.
8. **No NAT ⇒ Public IP must be ON** (Option B) or ECR/secrets pulls time out
   (`ResourceInitializationError`).
9. **Task too small** — 0.25 vCPU / 0.5 GB won't hold the models + Gradio queue; start at 1 vCPU / 2 GB.
10. **Bedrock via endpoint** keeps inference in-VPC (no NAT for the LLM call) — the strongest egress
    story for banking; confirm `bedrock-runtime` endpoint + `bedrock:InvokeModel*` on the task role.
