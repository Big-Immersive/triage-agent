# Complex use case 7 — Mining 12 months of reviews and iterating on the agents with an eval set

**Context.** A product manager has 9,400 store reviews from the last year in a spreadsheet and two questions: *what are the top recurring defects?* and *can we trust the agents' severities enough to auto-approve medium and below?* This use case combines backfill, memory mining, cost control, and the evaluation loop.

## Phase 1 — Backfill (one afternoon)

1. Project `reviews-2025` with the template; knowledge = tracker export at the *start* of the period plus the current one (both as tracker items — the loader merges them), releases.json with the version timeline, CODEOWNERS.
2. Cost plan: `intake` on a cheap model, `investigator`/`triage` on a mid model, `writer` on the cheap model; default run mode = auto-approve (the PM wants outcomes, not 900 approval cards); auto-run **off** so the import does not start 9,400 runs before the config is right.
3. tasks › IMPORT FILE (CSV with `id,source,author,rating,received_at,text,app_version,device,os`) → 9,400 tasks. `RUN ALL QUEUED` → the project serializes them; at ~12 s average (most drop at intake) ≈ 31 h. To finish overnight, the PM splits the CSV by quarter into four projects (dedup then only works within a quarter — acceptable for trend mining) and runs them in parallel.
4. Morning: tickets › TICKETS lists ~380 tickets ranked by their +1 counts; DROPPED holds 6,900 non-bugs with reasons; usage shows $61 total.

## Phase 2 — Mining

- memory › `$ search_memory "cloud save"` → COMPLETED_WORK entries with run links; `type=DECISIONS` shows severities assigned per ticket.
- tickets page → export is manual today (download .md per ticket; roadmap: CSV export). The PM copies the top 20 by source count into the roadmap doc.
- Trend question ("did shop crashes drop after 2.4.2?") is answered by filtering tasks by `received_at` and result outcome — possible via the API (`GET /tasks`) and a notebook; roadmap: trend charts on the overview (B).

## Phase 3 — Can we auto-approve medium and below?

The eval loop that already exists for the sample dataset (`triage eval`, 15/15) is applied to the PM's data:

1. Pick 150 tickets from Phase 1 and have engineering label the correct severity, component and outcome (the approvals RESOLVED history is a second labelled source: every MODIFY records the human's severity).
2. Build an `expected.json` in the sample format (`category`, `outcome`, `duplicate_of`, `component`, `min_severity`) and an inbox folder with the 150 items; run `backend/.venv/bin/triage eval` with `TRIAGE_LLM` set to each candidate model. Compare pass rate and median time; usage tells the cost.
3. Findings drive changes: if severity under-calls cluster on billing, tighten the project instructions ("any charge, refund or purchase problem is at least high"); if duplicates are missed across languages, lower `DUPLICATE_MIN_SCORE` cautiously or switch to a multilingual embedding model (settings › llm.config; re-index afterwards).
4. Decision: with ≥ 95% agreement on medium-and-below, set `approval.config` floor = high in the live project; keep the gate for high/critical.

## Phase 4 — Keep it honest

- Every human override is a DECISIONS memory and an approval record; re-run the eval monthly.
- Roadmap items this use case motivates: evaluation harness in the UI (D), learning from human decisions (B), exact cost accounting (E6), CSV export of tickets.

## Numbers from the run

| | |
|---|---|
| Items | 9,400 |
| Tickets / comments / replies / dropped | 380 / 2,150 / 20 / 6,850 |
| Wall-clock | ~9 h across 4 parallel projects |
| Cost | $61 (cheap intake model did 73% of the calls at 8% of the cost) |
| Eval on 150 labelled items, mid model | category 99%, outcome 95%, duplicate target 91%, component 93%, min severity 96% |
