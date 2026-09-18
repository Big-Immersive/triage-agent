# Root task runner. Backend lives in backend/ (Python), UI in frontend/ (Vite).
PY      ?= backend/.venv/bin/python
UVICORN ?= backend/.venv/bin/uvicorn
ALEMBIC ?= backend/.venv/bin/alembic

.PHONY: dev api web setup migrate revision test test-engine test-server test-web db-up build docs

setup: ## create the venv, install backend + frontend deps
	cd backend && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[server,dev]"
	cd frontend && npm install

dev: ## run API (8000) and Vite (5173) together
	@trap 'kill 0' INT TERM; \
	(cd backend && .venv/bin/uvicorn api.main:app --reload --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

api:
	cd backend && .venv/bin/uvicorn api.main:app --reload --port 8000

web:
	cd frontend && npm run dev

migrate:
	cd backend && .venv/bin/alembic upgrade head

revision:  ## make revision m="message"
	cd backend && .venv/bin/alembic revision --autogenerate -m "$(m)"

test: test-engine test-server test-web

test-engine:
	cd backend && .venv/bin/python -m pytest tests/test_tools.py -q

test-server:
	cd backend && .venv/bin/python -m pytest tests/server -q

test-web:
	cd frontend && npm run typecheck && npm test

db-up:
	docker compose -f deploy/docker-compose.yml up -d db

build:
	cd frontend && npm run build

docs:  ## regenerate generated docs
	cd backend && .venv/bin/python -m api.integrations.catalog > ../docs/INTEGRATIONS.md
