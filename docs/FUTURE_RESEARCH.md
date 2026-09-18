# What to add next — research & roadmap

Candidate directions, each with what it would take and the open questions. Ordered by expected value for a bug-triage product; the last section is for the platform as a general agent console.

## A. Inputs — get feedback in without exports

| Idea | What it takes | Open questions |
|---|---|---|
| **Native connectors** for App Store Connect / Google Play Developer APIs, Zendesk, Intercom, Freshdesk, Discord bot, Slack app, GitHub Issues/Discussions, Reddit/Twitter mentions | One poller/webhook adapter per source writing to the intake path; per-project credentials via the integrations model; cursor/dedup state per connector | Rate limits and review-API latency (App Store reviews lag ~24h); which fields become `metadata` |
| **Sentry / Crashlytics / Bugsnag import** (adapter is scaffolded as *planned*) | Scheduled sync converting issues → crash-log rows (signature, counts, versions, devices, first/last seen); replace the CSV knowledge item | Mapping stack-trace groups to a stable "signature"; keeping event counts fresh without hammering the API |
| **Email ingestion** (IMAP / Gmail push / Postmark inbound) | Inbound parser → task with thread id; reply drafts sent back on the same thread after approval | Threading, attachments (screenshots → vision model), PII |
| **Screenshots and video** | Vision-capable model in `intake` to extract error text/UI state from images; store attachments as files | Cost per image; model choice per provider |

## B. Smarter agents

| Idea | What it takes | Open questions |
|---|---|---|
| **Learning from human decisions** | Log every APPROVE/MODIFY/REJECT as labelled data; few-shot the triage agent with the project's recent overrides; optionally fine-tune a small severity classifier per project | Drift; explainability of "why high" |
| **Hybrid duplicate detection** | Combine vector similarity with BM25/keyword (pgvector + tsvector hybrid search is one flag in PGVectorStore), signature match, and version windows; learned thresholds per project | Threshold tuning without a labelled set; multilingual embeddings |
| **Clustering & trend detection** | Nightly job clustering open reports; "new cluster with 12 reports in 2h" alerts; trend charts on the overview | Choosing a clustering method robust to short texts |
| **Confidence calibration** | Compare investigator confidence against approval outcomes; show calibration in usage/analytics; auto-adjust the gate threshold | Sparse data per project early on |
| **Reflection / self-check step** | An optional reviewer agent that critiques the ticket before the gate (missing repro steps, contradictory evidence) | Extra cost per run; when to skip |
| **Model routing by task** | Cheap model for intake/spam, strong model for investigation; automatic fallback on provider errors | Per-agent budgets and SLAs |
| **Long-term memory retrieval** | Embed memories and retrieve the relevant ones per run (today: pinned PROJECT_CONTEXT only) | What to write vs. what to retrieve; memory decay |

## C. Outputs — close the loop

| Idea | What it takes | Open questions |
|---|---|---|
| **Two-way tracker sync** | Poll GitHub/Jira/Linear for status changes; reflect "fixed in x.y" back into the tracker knowledge so regressions are detected automatically | Conflict resolution; webhook vs. poll |
| **Reply delivery** | Send `draft_user_reply` output through the source channel (store reply APIs, Discord, email) after a human OK | Tone/brand guidelines per project; rate limits |
| **Release notes / weekly digest agent** | Fifth agent summarising the week's tickets by component with links; Slack/email digest | Template ownership |
| **Customer-impact scoring** | Join reports with account data (plan, MRR) via the custom-API tool to weight severity | Privacy; where the join happens |

## D. Platform

| Idea | What it takes | Open questions |
|---|---|---|
| **Teams & roles** | Organisations, membership, roles (viewer / reviewer / admin); per-project sharing; SSO (Google/GitHub OAuth, SAML later) | Billing entity = org; audit requirements |
| **Audit log & compliance** | Immutable audit table of every human decision and config change; export | Retention policy |
| **Resumable runs** | Persist workflow context at the gate (`ctx.to_dict()`) so a restart resumes exactly where it stopped instead of re-running | LlamaIndex context serialization stability across versions |
| **Retries, backoff, dead-letter** | Provider-error classification; automatic retry of transient failures; DLQ view | Idempotency of tool side effects (ticket creation) |
| **Evaluation harness in the UI** | Run `triage eval`-style scoring on a project's labelled set after prompt/model changes; show pass rate and cost side by side | Building labelled sets from approvals |
| **Prompt & agent versioning** | Version agent instructions; diff; roll back; attach the version to each run | Migration of in-flight runs |
| **Budgets & alerts** | Per-project monthly cost caps, alerts at 80%, auto-pause | Estimated vs. actual cost (OpenRouter generation stats API gives exact cost) |
| **Observability** | OpenTelemetry traces per run (LLM spans, tool spans), Prometheus metrics (queue depth, worker utilisation, gate wait time), structured logs | Trace storage cost |
| **Load & scale validation** | k6/Locust scenarios for 100k WebSocket clients and queue throughput; PgBouncer; read replicas; partitioning of `run_events` | Where the first bottleneck actually is (likely DB connections and NOTIFY fan-out) |
| **Rate limiting & abuse controls** | Per-user API quotas, intake key quotas, upload limits per plan | |
| **Plugin tools** | Load tools from a `tools/` directory or a Python entry point so custom tools ship without editing the registry; sandboxing | Trust boundary for user-supplied code |
| **Workflow templates marketplace** | Export/import a project's agents + tools + instructions as a template; ship more templates (QA bug bash, security intake, feature-request clustering, support macro suggestion) | Versioning templates |
| **Mobile & PWA** | Installable app for approving from a phone; push notifications for approvals | |

## E. Research questions worth a spike

1. **Does a reviewer/critic agent reduce human overrides enough to pay for itself?** Measure override rate and cost with/without on the sample set plus a real project's history.
2. **Hybrid search vs. pure vector for duplicates on short, multilingual reports** — precision/recall on labelled pairs; pgvector hybrid is a small change to test.
3. **Small-model viability** — with the guard rails in code, how far down can the chat model go (7B → 3B) before eval accuracy drops? Cost implications for 100k-user scale.
4. **Resumable gates** — serialize the LlamaIndex context at the gate and resume after restart; compare complexity against the current "re-run with decision" approach.
5. **Learning thresholds** — fit the duplicate STRONG threshold and the gate confidence per project from approval history; check for overfitting on small projects.
6. **Exact cost accounting** — use OpenRouter's `/generation` endpoint per response id to replace token-count estimates; measure the delta.

## Suggested order

1. Sentry/Crashlytics import and store-review connectors (removes the last manual step for the core use case).
2. Two-way tracker sync + reply delivery (closes the loop).
3. Teams/roles + audit log (needed before wider rollout).
4. Evaluation harness + learning from decisions (compounding quality).
5. Observability + load validation (before scaling replicas in production).
