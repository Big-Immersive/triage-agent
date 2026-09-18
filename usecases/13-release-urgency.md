# Release-aware urgency

**For:** Release managers

## The problem

Two bugs of similar severity: one affects the version 70% of users are on and the next code freeze is in two days.

## How the agents handle it

`release_info` exposes current version, user share per version and the next release/code-freeze dates; triage's rationale must cite them.

## Example outcomes

- '2.4.1 has 62% of users; code freeze for 2.5.0 is in 3 days' → severity high, flagged for the release.

## What to configure

- releases.json knowledge item kept current

## Value

Prioritisation reflects who is actually affected and when the next train leaves.
