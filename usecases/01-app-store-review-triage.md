# App / Play Store review triage

**For:** Product team of a mobile game or app

## The problem

Hundreds of 1–3★ reviews land every week. Someone reads them, guesses which are real bugs, checks the tracker by hand and files tickets — usually days late.

## How the agents handle it

Reviews are exported (or pushed via the intake endpoint) as tasks. `intake` classifies each review (bug / praise / feature / spam / support) and extracts device, OS, version. Bugs go to `investigator`, which searches the tracker and batch memory for duplicates and checks the crash log; new bugs go to `triage` for severity/component/owner; `writer` creates the ticket or a +1 comment.

## Example outcomes

- A review 'crashes every time I open the shop, Pixel 8, 2.4.1' becomes ticket OR-118 (high · shop · team-monetization) with repro steps, the crash signature from telemetry, and the review as source.
- Ten further reviews about the same crash become +1 comments on OR-118, not ten tickets.
- 5★ praise and 'GET FREE GEMS' spam are dropped with a recorded reason.

## What to configure

- Tasks page → IMPORT FILE (CSV export from App Store Connect / Play Console) or the intake endpoint
- Knowledge: tracker export (tickets.json), crash log CSV, releases.json, CODEOWNERS
- Integrations: GitHub/Jira/Linear to mirror tickets

## Value

Hours of manual reading per week → minutes of approving high-severity tickets. Every ticket has evidence and an owner.
