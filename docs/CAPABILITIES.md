# What the platform can do today

A precise inventory of shipped capabilities. Everything here is implemented and covered by tests unless marked *(config only)*. For scenarios see `../usecases/`; for what is planned see `FUTURE_RESEARCH.md`.

## 1. The agent engine (`backend/triage`)

**Multi-agent workflow on LlamaIndex `AgentWorkflow`.** Agents hand work to each other through an auto-generated `handoff(to_agent, reason)` tool, restricted by each agent's `can_handoff_to`. Routing is the model's decision, nudged by the return strings of the `record_*` tools ("NOW call handoff(...)"), which is what makes small models follow the graph reliably.

**The shipped bug-triage template (4 agents):**

| Agent | Decides | Tools |
|---|---|---|
| `intake` | bug / feature_request / praise / spam / support_question; extracts device, OS, version, steps, language, English summary | `record_intake`, `close_as_non_bug` |
| `investigator` | new / duplicate / needs_info | `search_recent_reports`, `search_tickets`, `get_ticket`, `query_crashes`, `search_knowledge`, `record_investigation` |
| `triage` | severity (low/medium/high/critical), component, owner, affected versions | `release_info`, `query_crashes`, `list_components`, `lookup_owner`, `record_triage` |
| `writer` | the artifact | `create_ticket` (holds the human gate), `comment_on_ticket`, `draft_user_reply` |

**Deterministic guard rails (code, not prompt):**
- Pydantic validation of every `record_*` call; the model self-corrects from validation errors returned as tool output.
- Duplicate-claim guard: a duplicate verdict is accepted only for a candidate that appeared as a STRONG hit (similarity ≥ 0.65) in *this item's* searches — the model cannot promote a weak hit or invent an id. Batch hits that already resolved to a ticket count as evidence for that ticket.
- Regression guard: a closed ticket whose `fixed_in` is older than the reported version cannot be a duplicate; the agent is told to file a new ticket referencing it.
- Actionability guard: `verdict=new` needs at least one of device, version, reproduction steps, or a crash signature; otherwise `needs_info`.
- Ticket-id guard in `comment_on_ticket`: a feedback id in place of a ticket id is resolved from the investigation or rejected with instructions.
- Coercion helpers tolerate list-as-string, "1. 2. 3." step lists, and numbers-as-words from small models.

**Human gate** inside `create_ticket`: pauses via `ctx.wait_for_event(HumanResponseEvent)` when severity ≥ floor (default high) or investigator confidence < threshold (default 0.7). Answers: `y`, `n`, or a corrected severity. `auto_approve` bypasses it; a `preapproved` answer (from an interrupted earlier attempt) is applied without asking.

**Per-project runtime (`ProjectRuntime`)**: tracker tickets, crash rows, owners, releases, ticket-id allocation, and three vector collections (tracker, batch memory of processed reports, uploaded knowledge) in one pluggable vector store — in-memory for CLI/tests, pgvector in the server — with every node tagged `project_id` + `kind` and every search filtered on both.

**Tool registry** (`tools/registry.py`): the catalog the UI shows; adding a tool is one function + one row.

**Model factories**: OpenRouter (any hosted model) or Ollama (local) chat models per agent; embeddings via Ollama or any OpenAI-compatible endpoint.

**CLI** (`triage inbox | run | eval`): runs the engine standalone on the sample dataset; `eval` scores category, outcome, duplicate target, component and minimum severity against `expected.json` (15/15 with the default model).

## 2. Workspace model (API)

- **Users** with email/password (argon2), JWT sessions (Bearer for the separate UI origin, httpOnly cookie for same-origin), 10/min/IP limiter on credential endpoints.
- **Per-user LLM configuration**: provider, default model, OpenRouter key (Fernet-encrypted at rest, masked on read), Ollama URL, embedding provider/model/base URL/key. TEST CONNECTION checks Ollama models, the OpenRouter key, and a live embedding call.
- **Projects**: name/slug/icon/description/instructions, status draft→active→archived, per-project config (approval floor, min confidence, default auto-approve, auto-run, memory write/pin policy), rename/archive/restore/delete (cascade, storage and vectors purged).
- **Agents per project**: name, role, description, instructions, model override (`openrouter:` / `ollama:` prefixes), tools from the registry, permissions, handoff targets, enabled flag, position. Live status (idle · thinking · running · tool call · waiting · human input · complete · error) and current process.
- **Tasks**: create, import JSON/CSV, load the sample inbox, run / run-all / cancel / delete; **auto-run** starts a run for every new task; **intake endpoint** (`POST /api/intake/{project}` + `X-Intake-Key`) accepts single items or batches from external systems, key rotation/revocation, hash-only storage.
- **Runs**: queued → running → waiting_approval → complete | error | cancelled; starting/current agent, duration, tool-call and handoff counts, result, final text, error; full event timeline (SYSTEM, AGENT, MEMORY, TOOL, TOOL_RESULT, HANDOFF, APPROVAL, ERROR, FINAL) with inputs, outputs, metadata and per-tool timing; tool-call log.
- **Approvals**: pending/approved/modified/rejected/expired with agent, action, reason, confidence, parsed details; APPROVE / MODIFY(severity) / REJECT; resolved cards link to the resulting ticket; approvals **survive worker loss** (pending stays pending; deciding re-runs the task with the decision carried over).
- **Memory**: 9 categories (PROJECT_CONTEXT, DECISIONS, REQUIREMENTS, ARCHITECTURE, KNOWN_ISSUES, COMPLETED_WORK, CURRENT_WORK, AGENT_NOTES, CUSTOM_MEMORY); automatic COMPLETED_WORK / DECISIONS / AGENT_NOTES after each run; pinned PROJECT_CONTEXT injected into every agent prompt; search, edit, pin, delete.
- **Knowledge**: upload (PDF, DOCX, Markdown, code, text; tracker JSON; crash-log CSV; releases JSON; CODEOWNERS), URL fetch, pasted notes; type sniffing by content; background indexing with live progress; re-index; delete. Structured kinds feed the tools; text kinds feed `search_knowledge`.
- **Files**: virtual tree per project, upload, mkdir, rename/move, delete, download, preview (text/markdown/json/pdf); run artifacts land under `/out`.
- **Tickets page**: every writer output — tickets (with severity, owner, approved-by, source feedback, mirrored issue links, producing run), +1 comments, clarification replies, dropped items — with full markdown detail.
- **Activity**: per-project timestamped feed (PROJECT/AGENT/RUN/MEMORY/FILE/KNOWLEDGE/APPROVAL/SYSTEM) with filters; global headline feed across projects that never carries memory/knowledge content.
- **Integrations**: GitHub, Jira, Linear (issue creation on ticket.created with labels/priority), Slack, Discord (approval/ticket/failure posts), Email (SMTP), Webhooks (all events, HMAC-signed, event filter); Sentry, Google Drive, Custom API *(config only, TEST validates credentials)*. Secrets encrypted; per-integration TEST; error state with last failure.
- **Usage**: tokens and estimated cost per user, per project, per model, per run/agent (OpenRouter list prices; Ollama free).
- **Dashboard / control center**: totals, recent projects, cross-project approval queue, live activity, system health (DB, Ollama, LLM, embeddings, replica, storage, WS clients).
- **Data isolation**: every project-scoped row has `project_id`; foreign projects are 404 (no existence leak); slugs are per owner; vector search is filtered by project; agents cannot reach another project's runtime.

## 3. Runtime & scale

- Stateless API replicas; Postgres LISTEN/NOTIFY bus fans events to every replica's WebSocket clients; per-process caches invalidated over the bus.
- Runs are a Postgres job queue: claimed with `UPDATE … WHERE status='queued'` under a per-project session advisory lock (ordered within a project, parallel across projects); heartbeats + stale-worker sweeper; a run parked at the human gate releases its slot and re-acquires one on resume; graceful shutdown is bounded.
- pgvector tables per embedding dimension with HNSW indexes; storage backend local or S3-compatible.
- Deployable as three Railway services (Postgres, backend Dockerfile, frontend nginx Dockerfile); migrations run at boot; `PORT`, `DATABASE_URL`, `CORS_ORIGINS`, `APP_URL`, S3 and worker settings from env.

## 4. The UI

Terminal-inspired command center (JetBrains Mono, near-black + neon green, amber for human input, red for errors): sidebar with SYSTEM ONLINE and connection state, `~/projects/…` path bar, ⌘K project switcher, four-step project wizard with live indexing, project overview leading with identity + AGENTS AT WORK (live per-agent steps) + LIVE EXECUTION, agents/agent detail (identity · live execution · memory/files/tools/handoffs), dynamic handoff graph with the active edge animated, runs table + execution console with expandable rows, tasks with auto-run/cancel/re-run, tickets, memory, knowledge, files explorer, approvals (amber), activity, integrations with per-provider guides, project settings (7 terminal-named sections incl. intake key + danger zone), user settings (llm.config, usage, profile). Live via WebSocket with polling fallbacks; responsive down to phone width; reduced-motion aware.

## 5. Quality gates

- 24 engine tests (no DB, no model): coercion, crash aggregation, ownership, human gate (skip / wait / override / reject / auto), artifact hook, cross-project isolation, duplicate-claim and regression guards, actionability guard, live embedding search when Ollama is present.
- 16 API tests on a real Postgres with a scripted function-calling LLM: auth and key masking, per-user 404 isolation across every endpoint, a run in one project not seeing another's tracker, approval round trips (approve/modify/reject), parked run letting the next task start, approval surviving worker loss with carried-over decision, sample-data idempotency, CSV import, files/memory/knowledge CRUD, integrations catalog + encrypted secrets + signed webhook delivery, auto-run and intake key lifecycle, outputs page.
- 11 frontend tests: formatters, status mapping, table variants, path bar, route tree + auth redirect.
- `triage eval`: 15/15 on the sample dataset with `z-ai/glm-5` / `qwen2.5:7b`.
