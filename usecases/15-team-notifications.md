# Notifying the team where they are

**For:** Everyone

## The problem

Approvals sit unnoticed; failures go unseen.

## How the agents handle it

Slack, Discord and Email integrations post approval requests (with a deep link), created tickets and failed runs. Generic webhooks deliver every event with an HMAC signature for custom automation.

## Example outcomes

- 'approval needed: APPROVAL_REQ_32B (payments-platform)' in #eng-triage within a second of the gate.

## What to configure

- integrations page

## Value

Humans respond faster, so the queue never stalls.
