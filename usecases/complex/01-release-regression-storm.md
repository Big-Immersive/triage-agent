# Complex use case 1 — Release-day regression storm across four channels

**Context.** Orbit Run 2.4.1 ships Tuesday 09:00. By 10:30 the shop screen is crashing for a subset of Android users; a cloud-save bug is silently resetting progress for a smaller group. Reports arrive through Play Store reviews, Discord, support email and the in-app form, in English and Spanish, interleaved with normal praise, spam and feature requests. The team is three engineers and one community manager.

**Goal.** One ticket per real bug, with live impact numbers, routed to the right team, high-severity ones approved by a human, mirrored to Jira, and the community manager armed with replies — without anyone reading 200 messages.

## Setup (once)

| Where | What |
|---|---|
| Project `orbit-run` | Instructions: product summary, "billing and data-loss ≥ high", release line 2.4.x |
| Knowledge | `tickets.json` (Jira export, incl. closed tickets with `fixed_in`), `crashes.csv` (Crashlytics export, re-uploaded hourly by a cron via `POST /knowledge/upload` — see *what's manual*), `releases.json` (2.4.1 = 62% of users, code freeze for 2.5.0 in 3 days), `CODEOWNERS` (shop→team-monetization, cloudsave→team-platform) |
| approval.config | floor = high, min confidence = 0.7 |
| Integrations | Jira (project ORB), Slack `#eng-triage` (approvals + failures), Webhooks → n8n (every event, HMAC) |
| Intake | key generated; Play Store scraper, Discord bot, Zendesk trigger and the app's form backend all POST to `/api/intake/{project}` with `source` set per channel |
| auto-run | on; default run mode = pause at gate |

## Timeline

**09:00–10:30 — quiet.** Praise and a feature request arrive. `intake` drops them (`close_as_non_bug`) in ~6 s each. Cost so far: cents.

**10:31 — first crash report (Play Store, English, Pixel 8, 2.4.1).**

```
intake       record_intake(category=bug, summary="Game crashes when opening the shop after updating", app_version=2.4.1, device=Pixel 8, os=Android 15, steps=[...])
             handoff → investigator
investigator search_recent_reports("crash opening shop")      → No earlier reports match.
             search_tickets("crash when opening shop 2.4.1")  → OR-101 score=0.52 (weak), OR-104 score=0.31 (weak)
             query_crashes("shop", "2.4.1")                    → 28 events / 19 users, signature NPE:ShopScreen.renderFeatured, Android 19 · iOS 9
             record_investigation(verdict=new, confidence=0.9, crash_signature=NPE:ShopScreen.renderFeatured, evidence="…")
             handoff → triage
triage       release_info()  → 2.4.1 has 62% of users; freeze in 3 days
             list_components() → shop: team-monetization
             record_triage(severity=high, component=shop, rationale="28 crash events on the current release with 62% of users; core purchase flow", affected_versions=[2.4.1])
             handoff → writer
writer       create_ticket(...)  → GATE: severity=high → run parks, slot released
```

Slack: *approval needed: APPROVAL_REQ_9C1 (orbit-run) — writer: Create high severity ticket: Shop screen crashes on open in 2.4.1 (NPE in renderFeatured) · confidence 0.90 → link*. The approval card shows component, owner, evidence and the run.

**10:33 — while that run is parked, 6 more shop-crash reports arrive** (Discord ×3, form ×2, a Spanish Play review). Because the parked run released the project slot, they run immediately. But the ticket does not exist yet, so batch memory has no entry for the first report → each of them also reaches the gate as a *new* high-severity ticket. **This is the known trade-off of not blocking the queue.** What the team sees: 7 amber cards for the same crash.

Mitigation as shipped: approve the first, **REJECT** the other six with one click each (the run ends as `dropped`; nothing is filed). Roadmap: clustering pending approvals by similarity and "approve as duplicate of …" (see `docs/FUTURE_RESEARCH.md`, B).

**10:35 — lead approves APPROVAL_REQ_9C1.** The run resumes, allocates `OR-118` from the project counter (atomic, replica-safe), writes `/out/tickets/OR-118.{md,json}`, `register_ticket` inserts it into the tracker vector collection, `remember_report` writes the batch-memory node `FB-001 → OR-118`. Integrations fire: Jira `ORB-412` created with priority High and description = ticket markdown; the Jira URL is written back into the ticket JSON (`external_links.jira`) and shows under tickets › MIRRORED; Slack posts *ticket OR-118 created (high, shop)*; the n8n webhook receives `ticket.created` with a valid `X-Triage-Signature`.

**10:36 onward — every further shop-crash report becomes a +1.** `search_recent_reports("crash shop")` now returns `FB-001 outcome=new_ticket ticket_id=OR-118 score=0.81 STRONG`; `record_investigation(verdict=duplicate, matched_report_id=FB-001)` is accepted by the guard (STRONG hit seen in this item's search) and resolved to `OR-118`; `writer` → `comment_on_ticket("OR-118", "+1 from Discord user Mo#4412, Galaxy S23, Android 14 …")`. The Spanish review ("se cierra al abrir la tienda") matches through the English summary. Thirty-one comments accumulate on one ticket; the tickets page shows OR-118 with the source list growing.

**11:10 — the cloud-save bug surfaces** ("I LOST ALL MY PROGRESS. Updated to 2.4.1, logged in with Google, it asked about cloud save, now I'm level 1"). `query_crashes("cloudsave")` finds nothing (it is a logic bug, not a crash). `record_investigation(verdict=new, confidence=0.72, evidence="no telemetry; clear repro steps and version")` — allowed because device+version+steps are present. `triage` → **critical** (data loss, project instructions). Gate → approved → `OR-119` → Jira `ORB-413` Highest → Slack. A support-email report of the same problem two hours later becomes a +1 on OR-119.

**11:40 — a regression, not a duplicate.** "Google sign-in sends me back to the title screen" on 2.4.1. `search_tickets` returns `OR-101 score=0.88 STRONG` — but OR-101 is **closed, fixed_in 2.3.8**. `record_investigation(verdict=duplicate, matched_ticket_id=OR-101)` is refused by the regression guard with an instruction; the agent re-records `verdict=new`, evidence mentions OR-101, triage sets high, and after approval `OR-120 "possible regression of OR-101"` is filed.

**12:05 — a vague one.** "doesnt work anymore. fix it." → `needs_info`; `writer` drafts the reply; the community manager copies it from tickets › REPLIES.

**13:00 — the backend is redeployed** (new build) while two runs are parked at the gate. Graceful shutdown marks them `error: interrupted while awaiting approval; your decision will re-run it`; their approvals stay **pending**. When the lead approves them at 13:20, the tasks re-run automatically with the decision carried over (`APPROVAL HUMAN decision carried over from the interrupted attempt`), and the tickets are created without asking twice.

## End of day

- 214 items processed: 3 tickets (OR-118 high, OR-119 critical, OR-120 high), 47 +1 comments, 9 clarification replies, 155 dropped (praise/spam/feature/support).
- Human time: 11 approvals (one click each), 6 rejections of duplicate-gate cards, reading 9 replies. Roughly 20 minutes.
- Cost (settings › usage): ≈ $0.02 per full ticket run, ≈ $0.004 per dropped item → about $1.60 for the day on `z-ai/glm-5`.
- Memory: DECISIONS ("Created OR-119 (critical, cloudsave)…", "Reviewer overrode…"), COMPLETED_WORK per item, AGENT_NOTES for duplicates — searchable, and the pinned PROJECT_CONTEXT stays injected into every run.

## What is manual today and where it is going

| Manual today | Roadmap item |
|---|---|
| Re-uploading `crashes.csv` from Crashlytics | Sentry/Crashlytics import adapter (A) |
| Rejecting duplicate gate cards during a storm | Cluster pending approvals / approve-as-duplicate (B) |
| Pasting clarification replies back to users | Reply delivery through the source channel (C) |
| Marking OR-118 fixed in Jira and updating the tracker export | Two-way tracker sync (C) |
