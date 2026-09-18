# Designing your own agent workflow

**For:** Anyone with a different triage shape

## The problem

Bug triage is one shape; QA bug-bash triage, security report intake, or feature-request clustering need different agents.

## How the agents handle it

Agents are data: name, role, instructions, tools from the registry, model, permissions, handoff targets. Build a 2-agent security-intake flow (classifier → writer with human gate on everything), or add a fifth 'release-notes' agent after writer. The graph updates automatically; new tools are one Python function in the registry.

## Example outcomes

- A 'qa-bash' project: intake → investigator → writer (no triage agent), auto-approve on, tickets mirrored to Linear.
- A 'security-intake' project: single agent with create_ticket only and approval on every severity.

## What to configure

- Agents page or the wizard's STEP 03
- triage/tools/registry.py for new tools

## Value

The platform is a general multi-agent operations console; bug triage is the shipped template.
