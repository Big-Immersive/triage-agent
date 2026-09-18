# triage — multi-agent bug-report triage on LlamaIndex

> **Status: reference implementation.** Everything here runs end-to-end, but
> the numbers in this README were measured on the bundled sample dataset
> (15 fictional feedback items for a made-up mobile game), not on production
> traffic. Treat it as a working example to read, run and adapt — not as a
> hosted product with proven scale. See [Results](#results) for what has
> actually been measured and [Scaling notes](#scaling-notes-untested) for what
> has not.

Raw user feedback in (store reviews, Discord, support email, in-app forms) →
de-duplicated, severity-rated engineering tickets out. Four agents hand work to
each other through a LlamaIndex `AgentWorkflow`, share state through the
workflow `Context`, search a ticket tracker and a crash log with tools, and
pause for a human before anything high-severity is written.

The agents run on **GLM-5 via OpenRouter** by default, or fully locally on
`qwen2.5:7b` via Ollama with one env var. Retrieval always uses the local
`nomic-embed-text` (OpenRouter serves no embedding models), so Ollama must be
running either way.

```
backend/triage/              the engine (agents, tools, runtime, CLI)
backend/samples/orbit_run/   15 raw feedback items (fictional mobile game "Orbit Run"), tickets.json (tracker),
                             crashes.csv (telemetry), CODEOWNERS, releases.json, expected.json (eval)
backend/out/                 what the CLI produces: tickets/ comments/ replies/ dropped/ results.json
backend/api/                 the dashboard API · frontend/  the dashboard UI · docs/  specs & architecture
```

## The agents

```
              ┌──────────┐  not a bug   ┌─────────────────┐
 feedback ──▶ │  intake  │ ───────────▶ │ close_as_non_bug│
              └────┬─────┘              └─────────────────┘
                   │ bug
              ┌────▼─────────┐  duplicate / needs_info  ┌────────┐
              │ investigator │ ───────────────────────▶ │ writer │ ─▶ +1 comment / clarification reply
              └────┬─────────┘                          └───▲────┘
                   │ new                                    │
              ┌────▼─────┐                                  │
              │  triage  │ ─────────────────────────────────┘ ─▶ new ticket  (⏸ human gate if high severity
              └──────────┘                                                     or low confidence)
```

| Agent | Decides | Tools |
|---|---|---|
| `intake` | bug / feature / praise / spam / support; extracts device, version, steps | `record_intake`, `close_as_non_bug` |
| `investigator` | new / duplicate / needs_info | `search_recent_reports` (batch memory), `search_tickets` (tracker RAG), `get_ticket`, `query_crashes`, `record_investigation` |
| `triage` | severity, component, owner | `release_info`, `query_crashes`, `list_components`, `lookup_owner`, `record_triage` |
| `writer` | produces the artifact | `create_ticket` (holds the human gate), `comment_on_ticket`, `draft_user_reply` |

Routing is the model's decision — each agent calls the auto-generated
`handoff(to_agent, reason)` tool — but every `record_*` tool ends its return
string with an explicit "NOW call handoff(...)" instruction, which is what
makes a 7B model follow the graph reliably.

## Setup

```sh
brew install ollama && brew services start ollama
ollama pull nomic-embed-text    # embeddings, ~275 MB (always needed)
ollama pull qwen2.5:7b          # only for the fully-local mode, ~4.7 GB

cd backend
cp .env.example .env            # put your OPENROUTER_API_KEY in it
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[server,dev]"
source .venv/bin/activate
```

## Use

```sh
triage inbox                       # see the raw items
triage run FB-001 -v               # one item, show tool outputs
triage run FB-001 FB-002 FB-015    # watch in-batch de-duplication
triage run FB-014                  # billing bug → hits the human gate, answer y / n / a severity
triage run --auto-approve          # whole inbox, no pauses
triage eval                        # whole inbox + score vs samples/orbit_run/expected.json
```

Interesting items:

| Item | What should happen |
|---|---|
| FB-001 | shop crash → new ticket (crash log confirms 28 events on 2.4.1) |
| FB-002, 003, 015 | same crash, other users/devices → duplicates of the FB-001 ticket via batch memory |
| FB-006 | Spanish sign-in report → duplicate of existing OR-104 |
| FB-008, 013 | too vague → clarification reply drafted |
| FB-010 | cloud-save data loss → new ticket, critical → human gate |
| FB-014 | double charge → new ticket, high → human gate |
| FB-004/005/007/009 | praise / spam / feature / support → dropped at intake |

## Choosing the model

```sh
triage eval                                          # GLM-5 via OpenRouter (default when .env has a key)
TRIAGE_LLM=z-ai/glm-5.3 triage eval                  # another OpenRouter model
TRIAGE_PROVIDER=ollama triage eval                   # fully local, qwen2.5:7b
TRIAGE_PROVIDER=ollama TRIAGE_LLM=qwen3:8b triage eval
```

## Results

| | qwen2.5:7b (local) | GLM-5 (OpenRouter) |
|---|---|---|
| `triage eval` | 15/15 (best of 3) | 14/15 first run → guard added |
| severity calibration | all `high` | low / medium / high / critical as appropriate |
| median time per item | 39 s | 27 s |
| cost per eval | $0 | ≈ $0.20 |

These are the only performance figures this project claims: one `triage eval`
pass over the 15-item sample inbox, scored against `samples/orbit_run/expected.json`.
Model prices change, so re-run the eval and read the real cost from
**settings › usage** or OpenRouter's dashboard rather than quoting this table.

The deterministic half (coercion, crash aggregation, human gate, duplicate-claim
guard) is covered by the 24 engine tests in `backend/tests/test_tools.py`.

## Concepts this project exercises

- `AgentWorkflow` + `FunctionAgent` with `can_handoff_to` — multi-agent routing
- Shared state via `ctx.store["state"]`; tools that take `ctx: Context`
- Pydantic-validated `record_*` tools as the structured-output mechanism (the
  model self-corrects from validation errors returned as tool output)
- Two `VectorStoreIndex`es with local embeddings, one grown incrementally
  (`index.insert`) during the run for in-batch de-duplication
- Human-in-the-loop with `ctx.wait_for_event(HumanResponseEvent, waiter_event=InputRequiredEvent(...))`,
  enforced inside a tool so the model can't bypass it
- Streaming `AgentInput` / `ToolCall` / `ToolCallResult` events for a live trace
- An eval (`triage eval`) so prompt or model changes can be measured, not eyeballed

## Things to try next

- `TRIAGE_LLM=qwen3:8b triage eval` — compare models on the same eval
- Break the routing on purpose: delete the "NOW call handoff" sentence from
  `record_intake` and watch what a small model does without it
- Replace the sample tracker with a real Jira/GitHub client — only
  `tools/tracker.py` changes
- Add a fifth agent that drafts release notes from the day's new tickets

---

## Dashboard

A project-based, multi-user web workspace on top of the engine: every project
has its own agents, tasks, runs, memory, knowledge, files, approvals and
activity, and agents can only read their own project. Layout: `docs/ARCHITECTURE.md`.

```
backend/api/       FastAPI API + WebSocket + run workers (same venv as the engine)
backend/alembic/   database migrations (PostgreSQL + pgvector)
frontend/          React 19 / Vite / TypeScript / Tailwind UI
docs/              architecture, capabilities, integrations, roadmap
```
Full layout: `docs/ARCHITECTURE.md` · capabilities: `docs/CAPABILITIES.md` · roadmap: `docs/FUTURE_RESEARCH.md` · scenarios: `usecases/`.

### Run locally

```sh
# 1. Postgres 16+ with the pgvector extension, and a database:
createdb triage && psql triage -c "CREATE EXTENSION vector"      # or: make db-up (docker)

# 2. Backend venv + UI deps
make setup
cp backend/.env.example backend/.env    # set DATABASE_URL and TRIAGE_SECRET_KEY
make migrate

# 3. Both servers (API :8000, UI :5173; Vite proxies /api and /ws)
make dev
```

Open http://localhost:5173, register, then **settings › llm.config** — paste
your OpenRouter key (or point at Ollama) and press TEST CONNECTION. Create a
project; in the wizard press **LOAD SAMPLE DATASET** / **load bug-triage
template** to get the four agents, the Orbit Run tracker/crash log/releases/
CODEOWNERS, and the 15 sample feedback items as tasks. Then **tasks › RUN**
FB-014 and watch it reach the human gate under **approvals**.

Your own data: **tasks › IMPORT FILE** takes a JSON array (the `inbox/*.json`
shape) or a CSV with a `text` column; **knowledge** takes a tracker export
(`tickets.json`), a crash log CSV, `releases.json`, `CODEOWNERS`, and any
documents/URLs/notes for `search_knowledge`.

Tests: `make test` (engine 24 · server 8 · web 11). Server tests use the
`triage_test` database and a scripted fake LLM, so they need Postgres but no
model or key.

### Scaling notes (untested)

The backend is designed to be stateless so it *can* run as several replicas
behind a load balancer, with all coordination in Postgres. **None of this has
been load-tested.** The table below describes the mechanisms in the code, not
measured capacity:

| Concern | Mechanism |
|---|---|
| Vector search (tracker, batch memory, knowledge) | **pgvector** — one table per embedding size, every node tagged `project_id` + `kind`, every query filtered on both |
| Live events to browsers | **LISTEN/NOTIFY** bus → each replica fans out to its own WebSocket clients |
| Run execution | **job queue in `runs`**: replicas claim `queued` rows with an `UPDATE … WHERE status='queued'` guarded by a per-project advisory lock (runs in one project stay ordered; projects run in parallel); heartbeats + a sweeper recover dead workers |
| Human gate across replicas | the approval API updates the row and publishes on the bus; whichever replica holds the run resumes it |
| Files / artifacts | `STORAGE_BACKEND=local` (single replica, volume) or `s3` (any S3-compatible bucket) |
| Ticket ids | `ticket_counters` row updated atomically |
| Per-process caches | project runtimes are cached per replica and invalidated via a bus message |

If you wanted to take this towards a large concurrent-user deployment you would
need, beyond this code: several backend replicas, a Postgres sized for the
connection count (PgBouncer in front, `DB_POOL_SIZE` set per replica), S3
storage, and — most importantly — a load test against your real traffic shape,
which has not been done here. LLM throughput is bounded by each user's own
provider limits, not by the server. Auth endpoints are rate-limited per replica
(10/min/IP). `docs/FUTURE_RESEARCH.md` lists load validation as open work.

### Deploy on Railway (3 services)

1. **Postgres** — Railway's Postgres template (it ships pgvector). Note its
   `DATABASE_URL`.
2. **backend** — new service from this repo, root directory `backend`, Dockerfile
   build (`backend/railway.toml`). Variables:
   `DATABASE_URL` (reference the Postgres service), `TRIAGE_SECRET_KEY` (long
   random string — changing it makes stored keys unreadable), `CORS_ORIGINS`
   (the UI service's public URL), `COOKIE_SECURE=true`, and for more than one
   replica `STORAGE_BACKEND=s3` + the `S3_*` variables (Cloudflare R2, AWS,
   Backblaze…). For a single replica you can instead mount a volume at `/data`.
   Migrations run at boot. Health check: `/api/ping`.
3. **ui** — new service from the same repo, root directory `frontend`, Dockerfile
   build (`frontend/railway.toml`). Build variable `VITE_API_URL` = the backend
   service's public URL (it is baked into the bundle at build time).

Because the UI and API are on different origins, the browser authenticates with
a Bearer token (kept in localStorage) rather than a cookie; the WebSocket passes
it as `?token=`. Hosted deployments have no local Ollama, so each user sets an
**OpenAI-compatible embedding endpoint** in settings › llm.config (OpenAI,
Together, a hosted Ollama URL, …) alongside their OpenRouter key.

### Usage & cost

Every run records prompt/completion tokens per agent and model
(`llm_usage`), priced from OpenRouter's public model list (Ollama = $0). Users
see spend per project, per model and per run under **settings › usage**.
Counts come from LlamaIndex's token counter, so they are estimates; OpenRouter's
own dashboard is the source of truth for billing.
