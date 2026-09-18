# Corroborating reports with crash telemetry

**For:** Engineering

## The problem

A single user report is anecdote; the same crash 28 times in telemetry is a priority.

## How the agents handle it

`query_crashes` aggregates the project's crash log by signature (events, users, versions, platforms, first/last seen, top devices). Investigator uses it to confirm and attach a crash signature; triage uses counts and the user share on the affected version (from releases.json) to set severity.

## Example outcomes

- 'crash opening shop' → signature NPE:ShopScreen.renderFeatured, 28 events across 19 users → severity high with a rationale citing the numbers.

## What to configure

- Crash log CSV (columns signature, stack_top, app_version, device, os, user_id, timestamp) — export from Sentry/Crashlytics; the Sentry adapter is on the roadmap

## Value

Severity decisions cite data, not vibes.
