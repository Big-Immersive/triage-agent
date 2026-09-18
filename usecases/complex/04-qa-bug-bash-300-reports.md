# Complex use case 4 — QA bug bash: 300 internal reports in an afternoon

**Context.** Before a major release, 40 employees bash the beta for three hours and file reports through an internal form (Google Form → CSV). Historically QA spends two days deduplicating and filing. Internal reporters are trustworthy and severities are reviewed later in the bug-scrub meeting, so the human gate is not needed during the bash — but everything must be reviewable afterwards.

## Configuration choices

- Project `release-3-0-bash`, template agents, **no `triage` gate**: `approval.config` → default run mode = *auto-approve everything* (the gate is skipped; `approved_by=auto` is recorded on every ticket so the scrub meeting knows).
- Knowledge: current tracker export, a crash log from the beta build, `releases.json` with `current_version=3.0.0-beta.4`, CODEOWNERS.
- Integrations: Linear (team REL), no notifications (they would be noise at this volume).
- Agent tweak: `intake` instruction adds "reports from internal testers always include a build number; treat missing repro steps as needs_info even for internal reports".
- Cost control: `investigator` and `triage` on a mid-tier model; `intake` on a cheap model (per-agent model override).

## The afternoon

**14:00 — import.** The form CSV has columns `id,author,text,build,device,os,area`. Tasks › IMPORT FILE maps `build`→ignored, `device/os/app_version`→metadata (the importer keeps `device`, `os`, `app_version` columns; `build` is renamed to `app_version` in the sheet before export). 312 rows → `created: 312, skipped: 0, queued: 312` (auto-run on).

**14:00–16:40 — the queue drains.** Runs are serialized within the project (so duplicates cluster) at roughly 30 s per full run and 6 s per drop: ~2.5 h. Two replicas do not help inside one project — by design. If throughput matters more than dedup, split the bash into two projects by area (UI vs. backend) and run them in parallel.

**What happens to the 312:**

| Outcome | Count | Mechanism |
|---|---|---|
| New tickets | 41 | `verdict=new` + auto-approved `create_ticket` |
| +1 comments | 138 | STRONG batch-memory or tracker hits |
| needs_info replies | 27 | no symptom/device/version/steps → reply drafts to send to the tester (internal Slack) |
| dropped | 106 | feature ideas, praise, "works for me", duplicates of already-known *closed* issues on the beta (regression guard files those as new instead — 3 cases) |

**Live view.** The overview's AGENTS AT WORK panel cycles through intake → investigator → triage → writer for each item; the runs table fills; tickets › TICKETS grows in real time; the Linear team receives 41 issues with labels from severity and component.

## After the bash — the scrub meeting

- tickets › TICKETS sorted by the number of source reports (the +1 count is the popularity signal): the top three issues had 23, 19 and 12 reports.
- memory › DECISIONS lists every ticket with its auto-assigned severity; the scrub changes eight severities in Linear (roadmap: two-way sync brings those back).
- tickets › REPLIES: 27 drafts asking specific testers for steps; QA pastes them into the bash Slack thread.
- usage: 312 items ≈ $3.10 total; the intake-on-cheap-model choice saved ~40%.

## Where it strained, and what to do

| Strain | Handling now | Better |
|---|---|---|
| 2.5 h wall-clock inside one project | Split by area into parallel projects | Parallel runs within a project with a post-hoc dedup pass (roadmap B: clustering) |
| Testers used inconsistent area names | CODEOWNERS components are the source of truth; `record_triage` rejects unknown components and the agent picks the closest valid one | Component synonyms in project instructions |
| Two testers filed the same bug 40 s apart; the second ran before the first finished | Serialized runs → the second still found the first in batch memory (the first had completed) | — |
| A tester pasted a 4,000-line log | `intake` summarised it; the tool result was stored truncated to 20k chars | Attachments as files with a `read_file` tool (roadmap) |
