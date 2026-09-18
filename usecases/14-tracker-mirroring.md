# Mirroring tickets to GitHub / Jira / Linear

**For:** Teams living in their tracker

## The problem

Nobody wants another tool; tickets must appear where engineers already work.

## How the agents handle it

On ticket.created the GitHub/Jira/Linear integration creates the issue (labels/priority mapped from severity and component); the external URL is stored on the ticket and shown in the tickets page.

## Example outcomes

- OR-118 → github.com/acme/app/issues/412 with labels severity:high, component:shop.

## What to configure

- integrations page: connect + TEST

## Value

The dashboard stays the control room; the tracker stays the system of record.
