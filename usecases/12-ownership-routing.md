# Routing to the owning team via CODEOWNERS

**For:** Engineering managers

## The problem

Tickets sit unassigned because nobody knows which team owns 'the shop'.

## How the agents handle it

A CODEOWNERS-style knowledge item maps components to teams and channels. `triage` must pick a valid component (`list_components`) and `record_triage` resolves the owner; the ticket carries owner and channel, and Slack notifications can target the team.

## Example outcomes

- component=billing → owner team-monetization, channel #eng-monetization.

## What to configure

- CODEOWNERS knowledge item

## Value

Every ticket is born with an owner.
