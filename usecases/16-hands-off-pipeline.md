# Fully hands-off pipeline via the intake endpoint

**For:** Ops / automation owners

## The problem

Feedback lives in five tools; nobody wants to export CSVs by hand.

## How the agents handle it

Each source (review scraper, Discord bot, support tool webhook, form backend, n8n/Zapier flow) POSTs to `/api/intake/{project}` with the project's key. Auto-run triages each item immediately; approvals notify Slack; tickets mirror to the tracker.

## Example outcomes

- Zapier: 'New App Store review' → Webhooks POST → task → run → ticket, no human until the gate.

## What to configure

- settings › security → generate intake key
- auto-run on (default)

## Value

Triage becomes infrastructure, not a chore.
