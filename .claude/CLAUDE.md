# triage.agents — how to run and test this project locally

Monorepo: `backend/` (Python: `triage` engine + `api` FastAPI service), `frontend/` (React/Vite), `docs/`, `usecases/`, `deploy/`. Layout details: `docs/ARCHITECTURE.md`.

## Prerequisites

- Python 3.12 and `uv` (`brew install uv`)
- Node 22+ and npm
- PostgreSQL 16+ with the **pgvector** extension. Either:
  - native: `brew install postgresql@17 pgvector` (or build pgvector for your PG version), then `createdb triage && psql triage -c "CREATE EXTENSION vector"`; also `createdb triage_test && psql triage_test -c "CREATE EXTENSION vector"` for the API tests, or
  - docker: `make db-up` (uses `deploy/docker-compose.yml`, user/password/db = `triage`; then set `DATABASE_URL=postgresql+asyncpg://triage:triage@localhost:5432/triage` and create `triage_test` inside that container).
- For real agent runs: an OpenRouter API key (entered in the UI under settings › llm.config) **or** a local Ollama with `qwen2.5:7b`; embeddings need Ollama with `nomic-embed-text` (`ollama pull nomic-embed-text`) or an OpenAI-compatible embeddings endpoint configured in the UI. Tests do not need any model.

## First-time setup

```sh
make setup                                  # backend/.venv + frontend/node_modules
cp backend/.env.example backend/.env        # edit DATABASE_URL and TRIAGE_SECRET_KEY (any long random string)
make migrate                                # alembic upgrade head
```

## Run

```sh
make dev            # API on :8000 (uvicorn --reload) + UI on :5173 (Vite proxies /api and /ws)
# or separately: make api / make web
```

Open http://localhost:5173 → register → settings › llm.config (paste key, TEST CONNECTION) → `* INITIALIZE PROJECT` → in the wizard press `* LOAD SAMPLE DATASET` (STEP 02) and `load bug-triage template` (STEP 03), tick "load the 15 sample feedback items", initialize → tasks → RUN FB-014 → approvals (amber) → approve → tickets.

API docs: http://localhost:8000/api/docs. Health: `GET /api/system/health` (needs a Bearer token; register/login returns one).

## Test

```sh
make test               # all three suites
make test-engine        # backend/tests/test_tools.py — engine only, no DB, no model (~1 s)
make test-server        # backend/tests/server — real Postgres (triage_test DB) + scripted fake LLM (~15 s)
make test-web           # frontend: tsc typecheck + vitest
```

Notes:
- Server tests read `TRIAGE_TEST_DATABASE_URL` (default `postgresql+asyncpg://triage:triage@localhost:5432/triage_test`); they `drop_all/create_all` the schema from the models and truncate between tests. Never point them at the dev DB.
- The engine test that hits Ollama embeddings is skipped automatically when Ollama is not running.
- `backend/.venv/bin/triage eval` runs the engine standalone on `backend/samples/orbit_run` against `expected.json` (needs a model; costs a few cents on OpenRouter). Expected: 15/15.

## Common tasks

| Task | Command |
|---|---|
| New migration after editing `backend/api/models/*` | `make revision m="describe change"` then `make migrate` |
| Regenerate `docs/INTEGRATIONS.md` after editing the catalog | `make docs` |
| Production UI build | `make build` (→ `frontend/dist`) |
| Run the CLI on one sample item | `cd backend && .venv/bin/triage run FB-004 --auto-approve` |
| Reset local data | drop and recreate the `triage` DB, `rm -rf backend/data`, `make migrate` |

## Conventions

- Backend imports: `from api.core...`, `from api.models import ...`, `from api.schemas import ...`; routers are thin, logic lives in `api/services`, outbound integrations in `api/integrations/adapters.py`, their docs in `api/integrations/catalog.py` (single source for the UI and `docs/INTEGRATIONS.md`).
- Every project-scoped query goes through the `ProjectDep` dependency (owner check → 404). Never query by id without the project.
- All DB work inside a run goes through the single drain coroutine in `api/services/runs.py` (AsyncSession is not safe for concurrent use). Publish events with `bus.publish_project(session, ...)` so they fire on commit.
- Engine (`backend/triage`) must stay free of API/DB imports; it receives a `ProjectRuntime` and callbacks.
- Frontend: data hooks in `src/api/queries.ts` (add the WS invalidation there too), primitives in `src/components/ui`, one route file per page under `src/routes/_app`. Tailwind v4 syntax (`w-auto!`, not `!w-auto`).
- Keep secrets out of responses: mask keys, never return `intake_key_hash` or integration secrets.
- Do not commit `backend/.env`, `backend/data`, `frontend/dist`.

## Deploy

Railway, three services: Postgres (pgvector) · backend (root dir `backend`, Dockerfile) · frontend (root dir `frontend`, Dockerfile, build arg `VITE_API_URL`). Details in `README.md` › Deploy on Railway.
