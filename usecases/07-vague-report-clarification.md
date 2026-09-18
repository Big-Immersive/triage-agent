# Vague report → clarification instead of a bad ticket

**For:** Support / community

## The problem

'Doesn't work, fix it' reports either get ignored or become useless tickets.

## How the agents handle it

`investigator` marks reports without a symptom and without device/version as needs_info; the code also rejects a 'new' verdict that has no device, version, steps or crash signature. `writer` drafts a friendly reply in the user's language asking for the specific missing details.

## Example outcomes

- FB-008 'doesnt work anymore. fix it.' → reply asking for device, version and what happens.
- The reply is stored under tickets › REPLIES and files /out/replies, ready to paste.

## What to configure

- Nothing beyond the bug-triage template.

## Value

Engineering never receives unactionable tickets; users get a consistent, polite request for details.
