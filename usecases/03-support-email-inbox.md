# Support email → engineering tickets

**For:** Support team + engineering

## The problem

Support agents forward 'this looks like a bug' emails to engineering with no structure; engineering asks the same clarifying questions every time.

## How the agents handle it

Emails are forwarded (or piped by a mail rule → webhook) into a project as tasks with `source=support_email` and the sender as author. Duplicate detection against the tracker prevents re-filing known issues; billing complaints are always at least high severity and stop at the human gate before a ticket is created.

## Example outcomes

- 'Apple charged me TWICE for the 500 gem pack' → high · billing → paused for approval → approved → ticket + Jira issue.
- 'How do I restore my purchases on a new phone?' → support_question → dropped with reason (not a bug).

## What to configure

- Email integration for approval notifications
- approval.config: which severities require a human

## Value

Engineering receives only structured, deduplicated, evidence-backed tickets; support gets a paste-ready reply for vague reports.
