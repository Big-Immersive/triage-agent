# Filtering praise, spam, feature requests and support questions

**For:** Anyone drowning in feedback

## The problem

80% of feedback is not a bug. Reading it all to find the 20% is the actual cost.

## How the agents handle it

`intake` classifies every item; non-bugs are closed by `close_as_non_bug` with a one-line reason and never reach the investigator. Everything is still recorded (tickets › DROPPED) so product can mine feature requests separately.

## Example outcomes

- Praise, spam links and 'how do I…' questions dropped in ~6 s each, at fractions of a cent.
- Feature requests remain queryable as a list for the roadmap.

## What to configure

- Nothing beyond the bug-triage template.

## Value

Engineering attention is spent only on real defects; nothing is deleted.
