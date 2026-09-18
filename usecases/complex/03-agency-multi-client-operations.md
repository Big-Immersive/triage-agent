# Complex use case 3 — Agency running triage for five clients on one account

**Context.** A mobile agency maintains five apps for five clients. Each client has its own tracker (two Jira, two GitHub, one Linear), its own severity policy, its own Slack, and a contractual requirement that their data is never visible to another client. The agency bills LLM usage back per client. Two agency engineers do the reviewing; one is on call at a time.

## Structure

| Project | Tracker | Approval floor | Notifications | Embeddings |
|---|---|---|---|---|
| `fintech-wallet` | Jira FW | medium, conf 0.8 | Slack `#fw-triage` + email | hosted (OpenAI-compatible) |
| `retail-loyalty` | GitHub `retailco/loyalty-app` | high | Slack `#rl-triage` | hosted |
| `fitness-tracker` | Linear FIT | high | Discord | hosted |
| `news-reader` | GitHub `newsco/reader` | critical only, auto-approve otherwise | webhook → client's own Slack bot | hosted |
| `kids-learning` | Jira KL | medium (COPPA sensitivity) | email to client PM | hosted |

One agency user owns all five (per-user OpenRouter key → usage is per project). Roadmap: teams/roles so the client PM can log in and approve their own project (`docs/FUTURE_RESEARCH.md`, D).

## Isolation, demonstrated

- `GET /api/projects/{fintech-wallet}/tickets` from any other user → **404** (no existence leak); from the owner it works. Slugs are per owner.
- The vector store is shared physically (one pgvector table per embedding size) but every node carries `project_id`; `search_tickets` in `retail-loyalty` cannot return `FW-…` tickets — the API test `test_runs_never_see_another_projects_tracker` asserts exactly this.
- Batch memory, knowledge, memories, files and approvals are all keyed by project; the control center shows counts and headlines only.
- Ticket ids: each project has its own `ticket_counters` row (prefix inferred from the client's tracker export: `FW-`, `RL-`, …).
- Integration credentials are per project and encrypted; rotating a client's key touches nothing else.

## Daily operation

1. **Inputs**: each client's feedback sources push to that project's intake endpoint (separate keys; a compromised key is rotated in settings › security without affecting other clients).
2. **Queue behaviour**: runs across projects proceed in parallel (per-project advisory locks only serialize within a project); with `RUN_WORKERS=4` per replica and two replicas, up to eight runs execute at once. A parked approval in `fintech-wallet` never blocks `news-reader`.
3. **Reviewing**: the on-call engineer works from the control center's cross-project APPROVAL QUEUE; each card links into its project; Slack/Discord/email routes per client.
4. **Client-specific policy** lives in three places: project instructions (tone, domain rules), `approval.config`, and agent instruction edits (e.g. `kids-learning` adds "flag anything mentioning chat, photos or location as critical").

## Billing back usage

`GET /api/me/usage` → `projects[]` with prompt/completion tokens, cost, runs and LLM calls per project. Month end: export, multiply by the agency's margin, invoice. Costs are estimates from token counts × OpenRouter list prices (roadmap: exact per-generation cost via OpenRouter's generation endpoint). Per-client model choice keeps cost proportional: `news-reader` uses a cheap model on all agents (`openrouter:qwen/qwen-2.5-72b-instruct`), `fintech-wallet` uses a strong model on `investigator` and `triage` only.

## Onboarding a sixth client in ten minutes

1. `* INITIALIZE PROJECT` → identity (name, instructions from the client brief).
2. STEP 02: upload their tracker export, crash export, CODEOWNERS (write one if they have none — component→team), release notes JSON; drop their product docs for `search_knowledge`.
3. STEP 03: `load bug-triage template`, then edit `investigator` to add `search_knowledge`, tweak severity wording in `triage`.
4. Review → initialize.
5. Integrations: connect tracker + notification channel, press TEST on each.
6. settings › security: generate the intake key; hand the curl example to the client's engineer.
7. Import last month's feedback CSV to seed batch memory and validate behaviour; check tickets and usage; adjust `approval.config`.

## Failure drills

| Drill | Expected |
|---|---|
| Replica B crashes mid-run | Heartbeat stops → sweeper marks the run `error: worker lost` after 90 s; task shows FAILED; RE-RUN. If it was parked at the gate, the approval stays pending and the decision re-runs it. |
| OpenRouter key revoked | Runs fail fast at preflight (`No OpenRouter API key saved…`); Slack `run.failed`; fix in settings › llm.config. Only this user's projects are affected. |
| Client asks for deletion | Project DELETE: cascade removes rows, storage prefix, and vector nodes (`purge_vectors`) — verified in `test_projects_are_invisible_across_users` for access and by the purge path for data. |
| Two engineers approve the same card | Second gets 409 `Approval already approved`. |
