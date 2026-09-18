# Knowledge-grounded triage with your own docs

**For:** Teams with architecture and product docs

## The problem

Agents make better decisions when they know what 'cloud save' actually is and which service owns it.

## How the agents handle it

Upload architecture docs, runbooks, PRDs or paste notes; they are chunked and embedded into the project knowledge base. Give agents the `search_knowledge` tool (agents page → edit → tools) and mention it in their instructions; pinned PROJECT_CONTEXT memories are injected into every run.

## Example outcomes

- Investigator searches 'cloud save sync' and learns it is backed by the sync-service; triage assigns component=cloudsave with a rationale referencing the doc.

## What to configure

- Knowledge page uploads (PDF, DOCX, Markdown, URLs, notes)
- Enable search_knowledge on the relevant agents

## Value

Decisions grounded in your documentation, not the model's guesses.
