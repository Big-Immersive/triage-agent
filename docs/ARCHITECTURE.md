# Architecture & repository layout

```
bug-triage-agents/
├── backend/                     Python service (one package install, two packages)
│   ├── triage/                  ENGINE — LlamaIndex multi-agent workflow (framework-agnostic, no DB)
│   │   ├── agents.py            AgentSpec + build_workflow(); DEFAULT_AGENTS = the bug-triage template
│   │   ├── runner.py            streams engine events, drives the human gate (on_event / ask_human)
│   │   ├── runtime.py           ProjectRuntime: per-project tracker/crash/owners/releases + vector collections
│   │   ├── schemas.py           Intake / Investigation / Triage / Ticket / Result models
│   │   ├── settings.py          make_llm() / make_embed() factories, CLI env config
│   │   ├── state.py             shared workflow state helpers
│   │   ├── cli.py               `triage inbox|run|eval` — runs the engine standalone on the sample data
│   │   └── tools/               agent tools (+ registry.py = the catalog the UI shows)
│   ├── api/                     API — FastAPI + WebSocket + run workers
│   │   ├── main.py              app factory, lifespan (bus + workers), /ws endpoint
│   │   ├── core/                config, db (SQLAlchemy async), security (argon2/JWT/Fernet), ids, deps, bus (LISTEN/NOTIFY), ws (hub)
│   │   ├── models/              ORM by domain: user, project, work (tasks/runs/approvals), knowledge, activity
│   │   ├── schemas/             Pydantic request/response shapes, same split
│   │   ├── routers/             one file per resource: auth, me, projects, agents, tasks, runs, approvals,
│   │   │                        memories, knowledge, files, activity, integrations, tickets, intake, dashboard
│   │   ├── services/            business logic: runs (queue + worker + gate), runtimes (pgvector-backed ProjectRuntime),
│   │   │                        knowledge (indexing), storage (local/S3), usage (token accounting), llm, activity
│   │   ├── integrations/        catalog.py (guides + fields, single source of docs) and adapters.py (outbound senders)
│   │   └── templates/           bug_triage.py — the sample project template (agents + knowledge + tasks)
│   ├── alembic/                 migrations (PostgreSQL + pgvector)
│   ├── samples/orbit_run/       demo dataset: tickets.json, crashes.csv, releases.json, CODEOWNERS, inbox/, expected.json
│   ├── tests/                   test_tools.py (engine, no DB) · server/ (API, Postgres + scripted fake LLM)
│   ├── pyproject.toml · Dockerfile · railway.toml · .env.example
│   └── data/ · out/             runtime storage (gitignored)
├── frontend/                    React 19 + Vite + TypeScript + Tailwind v4
│   └── src/
│       ├── api/                 client.ts (fetch + auth), queries.ts (TanStack Query + WS invalidation), ws.ts, types.ts
│       ├── stores/              auth.ts, ui.ts (zustand)
│       ├── components/          ui/ (primitives) · layout/ (shell, sidebar, project frame) · features/ (domain widgets)
│       ├── routes/              file-based routes (TanStack Router): _app/… mirrors the URL tree
│       ├── styles/              design tokens + global css
│       ├── utils/               format.ts
│       └── tests/               vitest
├── docs/                        CAPABILITIES.md · FUTURE_RESEARCH.md · INTEGRATIONS.md (generated) · this file
├── deploy/                      docker-compose.yml (local Postgres with pgvector)
└── Makefile                     setup / dev / test / migrate / build / docs
```

## Runtime topology

```
 browser ──HTTPS──▶ frontend (nginx, static)            Railway service 1
    │
    └──Bearer/WS──▶ backend replicas (FastAPI)            Railway service 2 (scale N)
                       │  ├─ REST routers
                       │  ├─ WebSocket hub  ◀── Postgres LISTEN/NOTIFY bus ──▶ every replica
                       │  └─ run workers: claim queued runs (SKIP-LOCKED + per-project advisory lock)
                       ▼
                    PostgreSQL + pgvector                 Railway service 3
                    (tables, vectors, job queue, event bus)
                    object storage (S3-compatible) for files when > 1 replica
```

## Key invariants

- **Isolation**: every project-scoped row has `project_id`; repository helpers take the owner + project; a foreign project is a 404. Vector nodes carry `project_id` + `kind` and every search filters on both.
- **Stateless API**: no per-process truth. Per-process caches (project runtimes) are invalidated via the bus.
- **Runs are a queue**: `runs.status = queued` rows are claimed by any replica; runs in one project are serialized (batch memory is order-dependent), projects run in parallel; a run parked at the human gate releases its slot.
- **The human gate is code, not prompt**: `create_ticket` pauses itself; approvals survive worker loss (pending → re-run with the decision carried over).
- **Secrets**: user LLM keys and integration secrets are Fernet-encrypted at rest and masked on read.
