# Complex use case 6 — Operating at scale: three backend replicas on Railway

**Context.** The product is offered as SaaS. Thousands of workspaces, a few hundred concurrently active users with the dashboard open, bursts of intake traffic when app stores publish reviews. The team wants to scale the backend horizontally and understand what happens to runs, WebSockets and approvals when replicas come and go.

## Deployment

- Railway: Postgres (pgvector) · `backend` ×3 replicas · `frontend` (nginx). Backend env: `DATABASE_URL`, `TRIAGE_SECRET_KEY`, `CORS_ORIGINS=https://app.example.com`, `APP_URL=https://app.example.com`, `COOKIE_SECURE=true`, `STORAGE_BACKEND=s3` + R2 credentials, `RUN_WORKERS=6`, `DB_POOL_SIZE=8`, `DB_MAX_OVERFLOW=8`.
- PgBouncer (transaction pooling) in front of Postgres once replicas × (pool + overflow + worker connections) approaches the DB's connection limit: each active run holds one extra dedicated connection for its advisory lock, so 3 replicas × 6 workers = 18 on top of the pools.

## What each mechanism does under load

**Intake burst (2,000 POSTs in a minute).** Requests land on any replica; each creates tasks and enqueues runs in a transaction. Nothing runs in the request path. Response ≈ 20 ms each.

**Queue drain.** Every replica's poll loop claims queued runs with `UPDATE runs SET status='running' … WHERE id=$1 AND status='queued' RETURNING id`, guarded by `pg_try_advisory_lock('project-run:{pid}')` on a dedicated connection. Runs from the same project never execute concurrently (batch-memory ordering); different projects spread across replicas. With 18 workers and ~25 s per run, ≈ 2,600 runs/hour; LLM provider throughput, not the server, is the practical ceiling — each user's own OpenRouter limits apply to their runs.

**Live UI for hundreds of viewers.** A browser holds one WebSocket to whichever replica the load balancer picked. Every state change is written to Postgres inside the run's transaction and published with `pg_notify` in that same transaction, so a subscriber never sees an event before the row exists. Each replica LISTENs and fans out to its own sockets; no replica-affinity is needed. Payloads over 7 kB are trimmed (`_trimmed: true`) — the REST API has the full record.

**Approvals across replicas.** A run parked at the gate on replica A releases its slot and advisory lock. The user's APPROVE request may hit replica C: it updates the row and publishes `approval.answer`; A receives it on the bus and resumes (after re-acquiring the project lock). If the NOTIFY is missed, A polls the row every 5 s as a fallback.

**Replica loss.** Heartbeats every 15 s; the sweeper (on any replica) marks runs with heartbeats older than 90 s. Running → `error: worker lost` (task FAILED, RE-RUN). Parked → `error: interrupted while awaiting approval`, approval **kept pending**; the decision later re-runs the task with it carried over. Graceful deploys do the same immediately at shutdown, bounded to 10 s.

**Per-process caches.** Each replica caches `ProjectRuntime` objects (tracker rows, owners, releases; vectors are in Postgres). Uploading a new tracker export publishes `runtime.invalidate` so every replica drops its copy.

**Files.** Local disk is per replica, so multi-replica deployments must use S3-compatible storage — the `files` table stores opaque object keys; renames never copy bytes.

## Observability (what exists, what to add)

Exists: `/api/system/health` (DB, Ollama, LLM, embeddings, replica id, WS client count, storage backend, worker count); run rows carry `worker_id` and `heartbeat_at`; activity feed for every state change; usage per user/project.

Add (roadmap D): OpenTelemetry spans per run/tool/LLM call, Prometheus metrics (queue depth = `count(*) where status='queued'`, gate wait = `resolved_at - requested_at`, worker utilisation), structured logs with `run_id`, alerting on sweeper actions.

## Capacity checklist before promising "100k users"

1. Load test WebSocket fan-out: NOTIFY throughput and per-replica socket counts (expect ~10k sockets per uvicorn process; scale horizontally).
2. Load test the queue with a fake LLM (the test suite's `ScriptedLLM` is reusable) to find the DB-bound ceiling.
3. Size Postgres for `run_events` growth (one row per step; partition by month or archive) and add retention.
4. PgBouncer + `DB_POOL_SIZE` tuning; watch `pg_stat_activity`.
5. Rate limits per user and per intake key (roadmap D).
6. Chaos drill: kill a replica mid-run and mid-approval; confirm the behaviour above.
