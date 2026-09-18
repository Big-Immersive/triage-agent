# Agency / platform team with many isolated products

**For:** Agencies, platform teams, multi-brand companies

## The problem

One team triages for several clients; data must never mix, and each client wants its own tracker and severity rules.

## How the agents handle it

Every project is an isolated workspace: its own agents, instructions, knowledge, memory, files, integrations and approval rules. Agents can only read their own project (enforced in the API and in the vector store). The control center summarises all projects without merging their content.

## Example outcomes

- payments-platform mirrors to Jira; orbit-run-demo posts to Discord; neither can see the other's tickets.

## What to configure

- One project per client; per-project integrations and approval.config

## Value

Safe multi-tenancy inside one account (and per-user accounts on top).
