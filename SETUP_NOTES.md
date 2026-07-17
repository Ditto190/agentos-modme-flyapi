# ModMe Agent Platform — Setup Notes

This document records the exact setup steps, ports, health-check URLs, and
next-step guidance for the `modme-agent-platform` (a fork of
[agno-agi/agentos-fly](https://github.com/agno-agi/agentos-fly)).

---

## Prerequisites

| Tool | Minimum version |
|---|---|
| Docker + Docker Compose | Docker 24+ / Compose v2 |
| Python | 3.12+ |
| pip / uv | recent |
| git | any recent |

---

## One-time Environment Setup

```bash
# 1. Copy the example env file (gitignored — never commit .env)
cp example.env .env

# 2. Open .env and set your OpenAI key
#    OPENAI_API_KEY=sk-...

# Dev-mode defaults (already set by compose.yaml — no manual edits needed):
#   RUNTIME_ENV=dev         → JWT auth disabled
#   AGNO_DEBUG=True         → verbose logs
#   WAIT_FOR_DB=True        → API waits for Postgres before serving

# Do NOT set JWT_VERIFICATION_KEY in local dev.
```

---

## Boot the Platform

```bash
docker compose up -d --build
```

Compose starts two services:

| Service | Container | Port |
|---|---|---|
| **API** | `agentos-api` | 8000 |
| **Postgres** | `agentos-db` | 5432 |

### Health-check URLs

| Surface | URL |
|---|---|
| Swagger / OpenAPI | http://127.0.0.1:8000/docs |
| MCP endpoint | http://127.0.0.1:8000/mcp |
| Health probe | http://127.0.0.1:8000/health |

Tail logs:
```bash
docker compose logs -f agentos-api
docker compose logs -f agentos-db
```

---

## Verify MCP Endpoint

Run the template's built-in smoke check (requires the containers to be running):

```bash
./scripts/mcp_check.sh
```

Or perform a manual JSON-RPC handshake:

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
| python3 -m json.tool
```

The response should include `"result": { "protocolVersion": "...", ... }`.

---

## Rebuild After Code Changes

```bash
# Hot-reload is on for agents/, app/, db/, workflows/ — edits take effect
# automatically while containers are running.

# After dependency (pyproject.toml) or env (.env) changes, restart the API:
docker compose restart agentos-api

# Full rebuild (e.g. after Dockerfile or requirements.txt changes):
docker compose up -d --build
```

---

## How to Add a New Agent

1. Create `agents/<slug>.py` following the pattern in `agents/web_search.py`.
2. Import and add the agent in `app/main.py` (`agents=[..., my_agent]`).
3. Add a manifest entry in `app/config.yaml`.
4. The scoped uvicorn reload picks up changes instantly; restart `agentos-api`
   for dependency or env changes.

Alternatively, use the `/create-new-agent` Claude Code skill — run it in a
Claude Code session pointed at this repo and describe what the agent should do.

---

## Connect the AgentOS UI

1. Go to [os.agno.com](https://os.agno.com).
2. **Connect OS → Live** → name it `ModMe Agent Platform`.
3. Enter the public URL (or `http://127.0.0.1:8000` for local tunnelling via
   `ngrok` or Fly.io deploy).
4. Follow the JWT setup prompt to paste your `JWT_VERIFICATION_KEY` if using
   production auth (not required for local `RUNTIME_ENV=dev`).

For a Fly.io deploy: `./scripts/fly/up.sh` provisions the app and sets
`AGENTOS_URL` automatically — see the main README for the full flow.

---

## Agents in This Platform

| Agent ID | File | Purpose |
|---|---|---|
| `agent-builder` | `agents/agent_builder.py` | Creates agents / teams / workflows via Studio |
| `platform-manager` | `agents/platform_manager.py` | Read-only diagnostics and codebase context |
| `web-search` | `agents/web_search.py` | Web search with grounded citations |
| `genui-orchestrator` | `agents/genui_orchestrator.py` | GenUI layout schema generation for the Next.js frontend |

---

## How the GenUI Frontend (port 3000) Connects to This Backend (port 8000)

### Option A — REST API

```typescript
// From the Next.js frontend (e.g. a CopilotKit action)
const response = await fetch("http://localhost:8000/v1/agents/genui-orchestrator/runs", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "Show me a KPI dashboard", stream: false }),
});
const { content } = await response.json();
// Parse the fenced JSON code block in `content` to get the layout_schema array
```

### Option B — MCP via CopilotKit

Configure CopilotKit to use `http://localhost:8000/mcp` as its MCP server.
The `run_agent` tool accepts `agent_id="genui-orchestrator"` and a `message`.
The response `structuredContent` carries `{run_id, session_id, status}` and
`content[0].text` is the plain answer (with the fenced JSON schema).

### Wire Contract

The agent returns a `layout_schema` JSON array (validated by `render_dashboard`).
The frontend Zod schema should mirror `_COMPONENT_REGISTRY` in
`agents/genui_orchestrator.py`.  See `.modme-context.md` for the full schema
example and molecule prop contracts.

---

## Format & Validate

These scripts run on the host (requires a venv):

```bash
./scripts/venv_setup.sh
source .venv/bin/activate

./scripts/format.sh     # ruff format + import sort
./scripts/validate.sh   # ruff check + mypy
```

Or run inside the container:

```bash
docker compose exec agentos-api ruff check .
docker compose exec agentos-api ruff format .
```

---

## Security Notes

- `.env` is gitignored — never commit it.
- `RUNTIME_ENV=dev` disables JWT auth; set `RUNTIME_ENV=prd` and provide
  `JWT_VERIFICATION_KEY` before any public-facing deploy.
- Do not set `MCP_CONNECT_SECRET` locally unless you need OAuth for claude.ai
  or ChatGPT connectors.

---

## Warnings & Follow-up Items

1. **OpenAI API key** — must be set in `.env` before `docker compose up`.
   Without it, all agent runs will fail at model invocation.
2. **pgvector on Fly.io** — the stock `postgres-flex` image does not ship
   pgvector.  If you deploy to Fly.io and want knowledge bases (RAG), use a
   custom image (see README's "Deploying to Fly.io" section).
3. **Fly.io deploy** — not configured here; kept local per project constraints.
   When ready, run `./scripts/fly/up.sh`.
4. **GenUI molecule library** — `_COMPONENT_REGISTRY` in
   `agents/genui_orchestrator.py` is the source of truth.  Extend it as new
   molecules land in the Next.js frontend library.
5. **CopilotKit wiring** — the frontend must parse the fenced `` ```json ``
   code block in the agent's response to extract the `layout_schema` array.
   Use a consistent extraction helper in the GenUIIsland route group.
