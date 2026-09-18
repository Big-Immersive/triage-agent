# Release-day incident: many reports, one bug

**For:** On-call engineers

## The problem

A bad release ships. 40 reports about the same crash arrive in an hour from four channels. Filing them individually floods the tracker and hides the pattern.

## How the agents handle it

Runs inside a project execute in order, and each finished report is written to batch memory. The first report becomes a ticket; every following report finds it via `search_recent_reports` (vector similarity, STRONG threshold) and becomes a +1 comment. Crash telemetry corroboration (`query_crashes`) gives the ticket the event count and affected versions.

## Example outcomes

- FB-001 → OR-118 (28 crash events on 2.4.1, Android + iOS). FB-002, FB-003, FB-015 → comments on OR-118 within minutes.
- The ticket's evidence cites 'signature NPE:ShopScreen.renderFeatured, 28 events, 19 users'.

## What to configure

- Crash log knowledge item (CSV export from Sentry/Crashlytics) kept fresh
- RUN ALL QUEUED for backfills

## Value

One ticket with a live count instead of 40; the on-call engineer sees scale immediately.
