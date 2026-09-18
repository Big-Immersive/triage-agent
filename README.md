<div align="center">

# triage

**Multi-agent bug-report triage on LlamaIndex**

Raw user feedback in — store reviews, Discord, support email, in-app forms.<br>
De-duplicated, severity-rated, owner-assigned engineering tickets out.<br>
A human approves anything high-severity before it is written.

[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](backend/pyproject.toml)
[![LlamaIndex AgentWorkflow](https://img.shields.io/badge/LlamaIndex-AgentWorkflow-8A2BE2)](https://docs.llamaindex.ai)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)](backend/api)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](frontend)
[![PostgreSQL + pgvector](https://img.shields.io/badge/Postgres-pgvector-4169E1?logo=postgresql&logoColor=white)](deploy/docker-compose.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[Quick start](#quick-start) · [How it works](#how-it-works) · [Results](#results) · [Dashboard](#the-dashboard) · [Deploy](#deploy-on-railway) · [Docs](#documentation)

</div>

---

> [!NOTE]
> **This is a reference implementation.** Everything here runs end-to-end — CLI, API, UI, tests — but the numbers below were measured on the bundled sample dataset: 15 fictional feedback items for a made-up mobile game called *Orbit Run*. Treat it as a working example to read, run and adapt, not as a hosted product with proven scale. [Results](#results) lists what has actually been measured; [Scaling notes](#scaling-notes-untested) lists what has not.

---

## What it does

| | |
|---|---|
| **Classifies** | bug · feature request · praise · spam · support question — noise is dropped at intake |
| **De-duplicates** | against the ticket tracker (vector search) *and* against other reports in the same batch |
| **Corroborates** | with crash telemetry — "28 crash events on 2.4.1" turns a vague review into a confirmed bug |
| **Rates & routes** | severity (low → critical), component, owning team via `CODEOWNERS`, affected versions |
| **Asks before acting** | high-severity or low-confidence tickets pause for a human: approve, change severity, or reject |
| **Writes the artifact** | a new ticket, a +1 comment on an existing one, or a clarification reply to the user |
| **Measures itself** | `triage eval` scores every run against an expected outcome, so prompt and model changes are compared, not eyeballed |

Runs on **any OpenRouter model** (GLM-5 by default) or **fully local on Ollama** (`qwen2.5:7b`) with one environment variable.

---

## How it works

Four agents hand work to each other through a LlamaIndex `AgentWorkflow`, share state through the workflow `Context`, and use tools to search the tracker, query the crash log and record their decisions.

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
              │  triage  │ ─────────────────────────────────┘ ─▶ new ticket   ⏸ human gate if high severity
              └──────────┘                                                      or low confidence
```

| Agent | Decides | Tools |
|---|---|---|
| **`intake`** | bug / feature / praise / spam / support; extracts device, version, steps | `record_intake` · `close_as_non_bug` |
| **`investigator`** | new / duplicate / needs_info | `search_recent_reports` (batch memory) · `search_tickets` (tracker RAG) · `get_ticket` · `query_crashes` · `search_knowledge` · `record_investigation` |
| **`triage`** | severity, component, owner | `release_info` · `query_crashes` · `list_components` · `lookup_owner` · `record_triage` |
| **`writer`** | the artifact | `create_ticket` (holds the human gate) · `comment_on_ticket` · `draft_user_reply` |

**Routing is the model's decision** — each agent calls the auto-generated `handoff(to_agent, reason)` tool — but every `record_*` tool ends its return string with an explicit *"NOW call handoff(...)"* instruction. That one line is what makes a 7B model follow the graph reliably.

<details>
<summary><b>Guard rails that live in code, not in the prompt</b></summary>
<br>

- **Pydantic validation** of every `record_*` call — the model self-corrects from validation errors returned as tool output.
- **Duplicate-claim guard** — a duplicate verdict is only accepted for a candidate that appeared as a *strong* hit (similarity ≥ 0.65) in this item's own searches. The model cannot promote a weak hit or invent an id.
- **Regression guard** — a closed ticket whose `fixed_in` is older than the reported version cannot be a duplicate; the agent is told to file a new ticket referencing it.
- **Actionability guard** — `verdict=new` needs at least one of device, version, reproduction steps or a crash signature; otherwise it becomes `needs_info`.
- **Human gate enforced inside the tool** — `create_ticket` blocks on `ctx.wait_for_event(HumanResponseEvent)` when severity ≥ floor or confidence < threshold. The model cannot route around it.
- **Coercion helpers** tolerate list-as-string, `"1. 2. 3."` step lists and numbers-as-words from small models.

</details>

---

## Quick start

### Engine only (CLI)

```sh
# 1. Local embeddings (always needed — OpenRouter serves no embedding models)
brew install ollama && brew services start ollama
ollama pull nomic-embed-text            # ~275 MB
ollama pull qwen2.5:7b                  # optional: fully-local chat model, ~4.7 GB

# 2. Python env
cd backend
cp .env.example .env                    # put your OPENROUTER_API_KEY in it (or skip for Ollama)
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[server,dev]"
source .venv/bin/activate
```

```sh
triage inbox                            # list the 15 raw sample items
triage run FB-001 -v                    # one item, with tool outputs
triage run FB-001 FB-002 FB-015         # watch in-batch de-duplication
triage run FB-014                       # billing bug → hits the human gate (answer y / n / a severity)
triage run --auto-approve               # whole inbox, no pauses
triage eval                             # whole inbox, scored against samples/orbit_run/expected.json
```

```sh
# Pick a model
triage eval                                            # GLM-5 via OpenRouter (default when .env has a key)
TRIAGE_LLM=z-ai/glm-5.3 triage eval                    # any other OpenRouter model
TRIAGE_PROVIDER=ollama triage eval                     # fully local, qwen2.5:7b
TRIAGE_PROVIDER=ollama TRIAGE_LLM=qwen3:8b triage eval
```

### Full stack (API + dashboard)

```sh
# Postgres 16+ with pgvector
make db-up                              # docker; or: createdb triage && psql triage -c "CREATE EXTENSION vector"

make setup                              # backend/.venv + frontend/node_modules
cp backend/.env.example backend/.env    # set DATABASE_URL and TRIAGE_SECRET_KEY
make migrate
make dev                                # API :8000 · UI :5173
```

Open <http://localhost:5173> → register → **settings › llm.config** (paste your key, TEST CONNECTION) → **INITIALIZE PROJECT** → **LOAD SAMPLE DATASET** + **load bug-triage template** → **tasks › RUN FB-014** → watch it reach the human gate under **approvals**.

<details>
<summary><b>What the sample items exercise</b></summary>
<br>

| Item | Expected outcome |
|---|---|
| FB-001 | shop crash → **new ticket** (crash log confirms 28 events on 2.4.1) |
| FB-002 · 003 · 015 | same crash, other users/devices → **duplicates** of the FB-001 ticket via batch memory |
| FB-006 | Spanish sign-in report → **duplicate** of existing `OR-104` |
| FB-008 · 013 | too vague → **clarification reply** drafted |
| FB-010 | cloud-save data loss → new ticket, **critical** → human gate |
| FB-014 | double charge → new ticket, **high** → human gate |
| FB-004 · 005 · 007 · 009 | praise / spam / feature / support → **dropped** at intake |

</details>

---

## Results

| | qwen2.5:7b (local, Ollama) | GLM-5 (OpenRouter) |
|---|---|---|
| **`triage eval`** | 15 / 15 *(best of 3)* | 14 / 15 first run → guard added → 15 / 15 |
| **severity calibration** | everything `high` | low / medium / high / critical as appropriate |
| **median time per item** | 39 s | 27 s |
| **cost per eval run** | $0 | ≈ $0.20 |

These are the **only** performance figures this project claims: one `triage eval` pass over the 15-item sample inbox, scored on category, outcome, duplicate target, component and minimum severity against `samples/orbit_run/expected.json`. Model prices change — re-run the eval and read the real cost from **settings › usage** or OpenRouter's dashboard rather than quoting this table.

**Tests:** `make test` runs all three suites — no model or API key needed.

| Suite | Count | Needs | Covers |
|---|---|---|---|
| `make test-engine` | 24 | nothing | coercion, crash aggregation, human gate, duplicate-claim & regression guards, project isolation |
| `make test-server` | 16 | Postgres (`triage_test`) | auth & key masking, per-user 404 isolation, approval round-trips, approvals surviving worker loss, intake keys, signed webhooks |
| `make test-web` | 11 | Node | typecheck, formatters, status mapping, route tree & auth redirect |

---

## The dashboard

A project-based, multi-user workspace on top of the engine. Every project has its own agents, tasks, runs, memory, knowledge, files, approvals and activity — and agents can only read their own project.

| Area | What you get |
|---|---|
| **Agents** | per-project agent definitions (role, instructions, model override, tools, handoff targets), live status per agent, animated handoff graph |
| **Tasks & runs** | import JSON/CSV, load the sample inbox, run / run-all / cancel; full event timeline per run with tool inputs, outputs and timing |
| **Approvals** | the human gate as a queue: approve · modify severity · reject; approvals survive worker loss |
| **Tickets** | every writer output — tickets, +1 comments, clarification replies, dropped items — with links to the producing run |
| **Memory & knowledge** | 9 memory categories with pinned project context injected into every prompt; upload PDFs, docs, tracker exports, crash logs, `CODEOWNERS`, URLs |
| **Intake endpoint** | `POST /api/intake/{project}` with a rotatable key, so external systems can feed reports directly |
| **Integrations** | GitHub · Jira · Linear (issue mirroring) · Slack · Discord · Email · HMAC-signed webhooks — secrets encrypted at rest, TEST button per integration |
| **Usage** | tokens and estimated cost per project, model, run and agent |

Bring your own data: **tasks › IMPORT FILE** takes a JSON array or a CSV with a `text` column; **knowledge** takes a tracker export (`tickets.json`), a crash-log CSV, `releases.json`, `CODEOWNERS`, and any documents for `search_knowledge`.

---

## Repository layout

```
backend/
  triage/            the engine — agents, tools, runtime, CLI  (no API/DB imports)
  api/               FastAPI service — routers, services, models, integrations, run workers
  alembic/           database migrations (PostgreSQL + pgvector)
  samples/orbit_run/ 15 feedback items · tickets.json · crashes.csv · releases.json · CODEOWNERS · expected.json
  tests/             engine tests (no DB) and server tests (real Postgres + scripted fake LLM)
frontend/            React 19 · Vite · TypeScript · Tailwind v4 · TanStack Router/Query
docs/                ARCHITECTURE · CAPABILITIES · INTEGRATIONS (generated) · FUTURE_RESEARCH
usecases/            20 scenario write-ups + 7 long-form end-to-end walkthroughs
deploy/              docker-compose for a local pgvector Postgres
```

---

## Scaling notes (untested)

The backend is designed to be stateless so it *can* run as several replicas behind a load balancer, with all coordination in Postgres. **None of this has been load-tested.** The table describes the mechanisms in the code, not measured capacity.

| Concern | Mechanism |
|---|---|
| Vector search | **pgvector** — one table per embedding size, every node tagged `project_id` + `kind`, every query filtered on both |
| Live events to browsers | **LISTEN/NOTIFY** bus → each replica fans out to its own WebSocket clients |
| Run execution | **job queue in `runs`** — replicas claim `queued` rows with `UPDATE … WHERE status='queued'` under a per-project advisory lock; heartbeats + a sweeper recover dead workers |
| Human gate across replicas | approval API updates the row and publishes on the bus; whichever replica holds the run resumes it |
| Files / artifacts | `STORAGE_BACKEND=local` (single replica, volume) or `s3` (any S3-compatible bucket) |
| Ticket ids | `ticket_counters` row updated atomically |
| Per-process caches | project runtimes cached per replica, invalidated over the bus |

Taking this to a large concurrent-user deployment would need, beyond this code: several replicas, a Postgres sized for the connection count (PgBouncer in front, `DB_POOL_SIZE` per replica), S3 storage, and — above all — a load test against your real traffic shape, which has not been done here. LLM throughput is bounded by each user's own provider limits, not by the server. `docs/FUTURE_RESEARCH.md` lists load validation as open work.

---

## Deploy on Railway

Three services from this repo:

| Service | Source | Key variables |
|---|---|---|
| **Postgres** | Railway's Postgres template (ships pgvector) | — |
| **backend** | root dir `backend`, Dockerfile (`backend/railway.toml`) | `DATABASE_URL` · `TRIAGE_SECRET_KEY` · `CORS_ORIGINS` · `COOKIE_SECURE=true` · for >1 replica: `STORAGE_BACKEND=s3` + `S3_*`, or mount a volume at `/data` |
| **frontend** | root dir `frontend`, Dockerfile (`frontend/railway.toml`) | build arg `VITE_API_URL` = the backend's public URL |

Migrations run at boot; health check is `/api/ping`. Because the UI and API sit on different origins, the browser authenticates with a Bearer token and the WebSocket passes it as `?token=`. Hosted deployments have no local Ollama, so each user sets an **OpenAI-compatible embedding endpoint** in **settings › llm.config** alongside their OpenRouter key.

> Changing `TRIAGE_SECRET_KEY` after launch makes stored LLM keys unreadable.

---

## Concepts this project exercises

- `AgentWorkflow` + `FunctionAgent` with `can_handoff_to` — multi-agent routing
- Shared state via `ctx.store["state"]`; tools that take `ctx: Context`
- Pydantic-validated `record_*` tools as the structured-output mechanism
- Two `VectorStoreIndex`es with local embeddings, one grown incrementally during the run for in-batch de-duplication
- Human-in-the-loop with `ctx.wait_for_event(HumanResponseEvent, waiter_event=InputRequiredEvent(...))`, enforced inside a tool
- Streaming `AgentInput` / `ToolCall` / `ToolCallResult` events for a live trace
- An eval so prompt or model changes can be measured, not eyeballed

### Things to try

- `TRIAGE_LLM=qwen3:8b triage eval` — compare models on the same eval
- Delete the *"NOW call handoff"* sentence from `record_intake` and watch what a small model does without it
- Replace the sample tracker with a real Jira/GitHub client — only `tools/tracker.py` changes
- Add a fifth agent that drafts release notes from the day's new tickets

---

## Documentation

| | |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | repository layout, request flow, run lifecycle |
| [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) | everything the platform does today, in detail |
| [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) | per-provider setup guides (generated from the catalog) |
| [`docs/FUTURE_RESEARCH.md`](docs/FUTURE_RESEARCH.md) | open questions and roadmap, including load validation |
| [`usecases/`](usecases/README.md) | 20 scenarios + 7 end-to-end walkthroughs with real tool sequences |
| [`.claude/CLAUDE.md`](.claude/CLAUDE.md) | how to run and test the project locally |

## License

[MIT](LICENSE) © 2026 Big Immersive
