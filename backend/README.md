# backend

Python service: the `triage` engine (LlamaIndex agents, tools, per-project runtime) and the `api`
package (FastAPI + WebSocket + run workers). See `../docs/ARCHITECTURE.md`.

```sh
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[server,dev]"
cp .env.example .env            # DATABASE_URL, TRIAGE_SECRET_KEY, ...
.venv/bin/alembic upgrade head
.venv/bin/uvicorn api.main:app --reload --port 8000
.venv/bin/pytest -q             # engine + API tests (needs Postgres; no LLM key)
.venv/bin/triage run FB-001     # the CLI still works standalone
```
