#!/usr/bin/env bash
# starts the two http mcp servers and the gradio ui
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a; source .env; set +a
else
  echo "WARNING: no .env found, OPENAI_API_KEY etc. must already be exported." >&2
fi

PY=${PYTHON:-python3}
LOGDIR=$(mktemp -d)
echo "logs: $LOGDIR"

"$PY" mcp_servers/job_boards_server.py >"$LOGDIR/job_boards.log" 2>&1 &
JB=$!
"$PY" mcp_servers/ats_server.py       >"$LOGDIR/ats.log"        2>&1 &
ATS=$!

cleanup() {
  echo; echo "stopping MCP servers..."
  kill "$JB" "$ATS" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo -n "waiting for MCP servers"
for _ in $(seq 1 40); do
  if curl -s -o /dev/null http://localhost:8001/mcp && curl -s -o /dev/null http://localhost:8002/mcp; then
    echo " ... up"; break
  fi
  echo -n "."; sleep 0.5
done

if ! curl -s -o /dev/null http://localhost:8001/mcp; then
  echo; echo "ERROR: job-boards MCP did not start. Log:"; cat "$LOGDIR/job_boards.log"; exit 1
fi
if ! curl -s -o /dev/null http://localhost:8002/mcp; then
  echo; echo "ERROR: ats MCP did not start. Log:"; cat "$LOGDIR/ats.log"; exit 1
fi

echo "starting Gradio UI on http://localhost:7860 (Ctrl+C to stop)"
exec "$PY" -m app.ui.gradio_app
