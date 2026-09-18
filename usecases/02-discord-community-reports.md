# Discord community bug channel

**For:** Community managers / live-ops

## The problem

Players report problems in a #bugs channel in fragmented messages with slang, screenshots and no device info. Real issues get lost between memes.

## How the agents handle it

A Discord bot (or n8n/Zapier) forwards each message to the intake endpoint with `source=discord` and the author handle. The workflow is the same as for reviews; vague messages ('doesnt work anymore, fix it') do not become tickets — `investigator` marks them needs_info and `writer` drafts a clarification reply the community manager can paste back.

## Example outcomes

- 'anyone else getting a crash when opening the shop?? galaxy s23' → matched to the batch report from earlier the same day → +1 comment with the new device.
- 'doesnt work anymore. fix it.' → clarification reply asking for device, version and what exactly happens.

## What to configure

- Intake endpoint key (settings › security) wired into a Discord bot
- Discord webhook integration so approvals/failures post back to a staff channel

## Value

The channel becomes a real input stream; nothing actionable is missed and users get consistent follow-up questions.
