# Integrations

How each integration works in triage and how to set it up. Generated from `server/integrations_catalog.py`.

## GITHUB (`github`) — live

Mirror every ticket the writer agent creates as a GitHub issue in one repository.

**How it works**

- When a run ends with outcome new_ticket, the server POSTs to GitHub's REST API (POST /repos/{owner}/{repo}/issues) using your token.
- The issue title is the ticket title; the body is the ticket markdown (severity, component, owner, repro steps, expected/actual, evidence, source feedback).
- Labels are added from severity and component (e.g. `severity:high`, `component:billing`) — they are created on the fly if the token allows it.
- The issue URL is written back into the project activity feed (`GITHUB issue #12 created for OR-118`) and the ticket JSON under /out/tickets gets an `external_url`.
- If the call fails (bad token, missing repo) the integration flips to ● ERROR with the reason, and the run itself still completes — mirroring never blocks triage.

**Setup steps**

1. Open github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token.
2. Resource owner: the organization or user that owns the repository. Repository access: only the target repo.
3. Permissions: Repository permissions → Issues: Read and write. (Metadata: Read is added automatically.) Nothing else is needed.
4. Set an expiry, generate, and copy the token (it starts with `github_pat_`). Classic tokens with the `repo` scope also work.
5. In triage: repository = `owner/name` (e.g. `acme/payments-platform`), token = the value you copied. Press TEST — it reads the repository and reports the issue count. Then CONNECT.

**Fields**

- `repository` — repository: owner/name, e.g. acme/payments-platform
- `token` — personal access token: fine-grained token with Issues: read & write on that repo *(secret, encrypted at rest)*
- `labels` — extra labels (optional): comma-separated labels added to every issue, e.g. triage,from-feedback

**Permissions:** Issues: read & write on the selected repository

**TEST button:** GET /repos/{repository} — verifies the token can see the repo; no issue is created.

**Events sent:** ticket.created

**Inbound (push):** New GitHub issues (optionally only with a label) become tasks the moment they are opened.

1. Repository → Settings → Webhooks → Add webhook.
2. Payload URL: the inbound URL shown on this card. Content type: application/json. Secret: generate one (openssl rand -hex 24) and paste it here as webhook_secret.
3. Events: 'Issues' (and 'Issue comments' if include_comments). Save; GitHub sends a ping — the card's inbound counter does not change for pings.
4. Open a test issue with the intake label → it appears under tasks within a second.

Inbound fields: `webhook_secret` — webhook secret; `intake_label` — only issues with label (optional); `include_comments` — also import new comments (optional); `poll_issues` — also poll open issues every 5 min (optional)

## JIRA (`jira`) — live

Create a Jira Cloud issue for every new ticket.

**How it works**

- On outcome new_ticket the server calls POST {site_url}/rest/api/3/issue with Basic auth (your Atlassian email + API token).
- Issue type defaults to `Bug` (configurable). Summary = ticket title; description is the ticket content in Atlassian Document Format; priority is mapped from severity (critical→Highest, high→High, medium→Medium, low→Low) when the project has those priorities.
- The Jira key (e.g. PAY-42) and URL are recorded in the activity feed and the ticket JSON.
- Failures set the integration to ● ERROR with Jira's error message (typically: wrong project key, or the issue type does not exist in that project).

**Setup steps**

1. Go to id.atlassian.com → Security → API tokens → Create API token. Name it `triage`, copy it.
2. Find your site URL: it is the host you use for Jira, e.g. https://acme.atlassian.net (no trailing path).
3. Find the project key: open the Jira project; the key is the prefix of its issue ids (PAY in PAY-42), also shown in Project settings → Details.
4. Make sure the account that owns the token has 'Create Issues' permission in that project and that an issue type named Bug (or the one you configure) exists.
5. In triage: site_url, project_key, email (the Atlassian account), api_token, optionally issue_type. Press TEST — it fetches the project and lists its issue types. Then CONNECT.

**Fields**

- `site_url` — site url: https://<your-site>.atlassian.net
- `project_key` — project key: e.g. PAY
- `email` — atlassian account email: the account the API token belongs to
- `api_token` — api token: from id.atlassian.com → Security → API tokens *(secret, encrypted at rest)*
- `issue_type` — issue type (optional): default: Bug

**Permissions:** Browse projects + Create issues in the target project

**TEST button:** GET /rest/api/3/project/{project_key} — verifies auth and the project key; nothing is created.

**Events sent:** ticket.created

**Inbound (push):** Issues created in the Jira project (optionally one issue type) become tasks.

1. Jira → Settings (gear) → System → WebHooks → Create a WebHook.
2. URL: the inbound URL shown on this card — it already contains ?token=…; Jira Cloud does not sign webhooks, the token is the authentication.
3. Events: Issue → created. Optional JQL filter: project = KEY. Save.
4. Create a test issue → it appears under tasks.

Inbound fields: `intake_issue_type` — only this issue type (optional); `poll_issues` — also poll new issues every 5 min (optional)

## LINEAR (`linear`) — live

Create a Linear issue in one team for every new ticket.

**How it works**

- On outcome new_ticket the server sends the `issueCreate` GraphQL mutation to https://api.linear.app/graphql with your API key.
- Title = ticket title; description = ticket markdown; priority is mapped from severity (critical→Urgent, high→High, medium→Medium, low→Low).
- The Linear identifier (e.g. PAY-118) and URL are recorded in the activity feed and the ticket JSON.

**Setup steps**

1. Linear → Settings → Security & access → Personal API keys → Create key. Copy it (starts with `lin_api_`).
2. Find the team key: Settings → Teams → the short identifier used in issue ids (PAY in PAY-118).
3. In triage: team_key + api_key. Press TEST — it resolves the team id via GraphQL. Then CONNECT.

**Fields**

- `team_key` — team key: e.g. PAY
- `api_key` — personal api key: lin_api_… *(secret, encrypted at rest)*

**Permissions:** The key acts as you; you need to be a member of the team

**TEST button:** GraphQL query { teams(filter:{key:{eq:…}}) } — verifies the key and team.

**Events sent:** ticket.created

**Inbound (push):** Issues created in the Linear team become tasks.

1. Linear → Settings → API → Webhooks → New webhook.
2. URL: the inbound URL shown on this card. Resource types: Issues. Team: the same team. Copy the signing secret into webhook_secret.
3. Create a test issue → it appears under tasks.

Inbound fields: `webhook_secret` — webhook signing secret; `poll_issues` — also poll every 5 min (optional)

## SLACK (`slack`) — live

Post approval requests, created tickets and failed runs to a Slack channel.

**How it works**

- The server POSTs a message to your Incoming Webhook URL. No bot token or OAuth app scopes beyond the webhook are needed.
- Events sent: approval.requested (amber, with agent, action, confidence and a link to the approval queue), ticket.created (green, ticket id + severity + component), run.failed (red, run id + error).
- Messages are fire-and-forget: a Slack outage never delays a run. Delivery errors are logged to the activity feed and the integration shows ● ERROR.

**Setup steps**

1. Go to api.slack.com/apps → Create New App → From scratch. Name it `triage`, pick your workspace.
2. In the app: Incoming Webhooks → toggle Activate Incoming Webhooks on → Add New Webhook to Workspace → choose the channel → Allow.
3. Copy the Webhook URL (https://hooks.slack.com/services/T…/B…/…).
4. In triage: webhook_url = that URL; channel is informational (the webhook decides the channel). Press TEST — a `triage connected` message appears in the channel. Then CONNECT.

**Fields**

- `webhook_url` — incoming webhook url: https://hooks.slack.com/services/… *(secret, encrypted at rest)*
- `channel` — channel (label only): #eng-triage — shown in the UI; the webhook itself decides where messages go

**Permissions:** incoming-webhook (granted when you add the webhook to a channel)

**TEST button:** Posts a one-line test message to the webhook.

**Events sent:** approval.requested, ticket.created, run.failed

**Inbound (push):** Every message posted in one Slack channel becomes a task, instantly, via the Slack Events API.

1. api.slack.com/apps → your app (the same one that owns the incoming webhook) → Event Subscriptions → Enable.
2. Request URL: the inbound URL shown on this card. Slack sends a challenge; the card shows ● VERIFIED once it succeeded (save signing_secret first).
3. Subscribe to bot events: message.channels (public) and/or message.groups (private). Save changes, then reinstall the app to the workspace.
4. OAuth & Permissions → scopes channels:history (and groups:history). Invite the bot to the channel: /invite @triage.
5. Post a message in the channel → it appears under tasks and, with auto-run on, starts a run. Bot messages and edits are ignored.

Inbound fields: `signing_secret` — app signing secret; `intake_channel` — channel id to read; `workspace_domain` — workspace domain (optional); `include_threads` — include thread replies (optional)

## DISCORD (`discord`) — live

Post approval requests, created tickets and failed runs to a Discord channel.

**How it works**

- Same as Slack: the server POSTs to a channel Webhook URL. Messages use Discord embeds coloured amber/green/red by event type.
- Events: approval.requested, ticket.created, run.failed.

**Setup steps**

1. In Discord open the target channel → Edit Channel (gear) → Integrations → Webhooks → New Webhook.
2. Name it `triage`, optionally set an avatar, then Copy Webhook URL (https://discord.com/api/webhooks/…).
3. In triage: webhook_url = that URL. Press TEST — a test embed appears in the channel. Then CONNECT.

**Fields**

- `webhook_url` — channel webhook url: https://discord.com/api/webhooks/… *(secret, encrypted at rest)*

**Permissions:** Manage Webhooks on the channel (to create the webhook)

**TEST button:** Posts a test embed to the webhook.

**Events sent:** approval.requested, ticket.created, run.failed

**Inbound (poll):** Messages in one Discord channel are read by a bot every 30 seconds (Discord has no outbound message webhooks).

1. discord.com/developers/applications → New Application → Bot → Add Bot → copy the token.
2. Bot → Privileged Gateway Intents → enable Message Content Intent (required to read message text).
3. OAuth2 → URL Generator → scope bot, permissions View Channels + Read Message History → open the URL → add the bot to your server.
4. Paste bot_token and intake_channel_id here → CONNECT. The first sync sets the cursor at the newest message; only later messages are imported. Press SYNC NOW to test.

Inbound fields: `bot_token` — bot token; `intake_channel_id` — channel id to read

## EMAIL (`email`) — live

Email a reviewer when a run needs human approval, and when a run fails.

**How it works**

- The server sends plain-text mail over SMTP (STARTTLS on 587, or implicit TLS on 465) from a background thread.
- approval.requested → subject `[triage] approval needed: APPROVAL_REQ_… (project)` with the agent, action, confidence and a link to the approval queue. run.failed → subject `[triage] run failed: RUN_…`.
- One mail per event to the `to_address` list (comma-separated).

**Setup steps**

1. Use any SMTP account. Gmail: enable 2-step verification, then Google Account → Security → App passwords → create one for `triage`; host smtp.gmail.com, port 587, username = your address, password = the app password.
2. Transactional providers (Postmark, SendGrid, Resend, SES): create SMTP credentials in their dashboard; use the host/port/username/password they show.
3. from_address must be an address the SMTP account is allowed to send as (Gmail: your own address; providers: a verified sender).
4. In triage fill the fields and press TEST — a test mail is sent to to_address. Then CONNECT.

**Fields**

- `smtp_host` — smtp host: smtp.gmail.com, smtp.postmarkapp.com, …
- `smtp_port` — smtp port: 587 (STARTTLS) or 465 (TLS)
- `username` — username
- `password` — password / app password *(secret, encrypted at rest)*
- `from_address` — from address: triage@yourcompany.com
- `to_address` — to address(es): comma-separated reviewers

**Permissions:** An SMTP login that may send as from_address

**TEST button:** Sends one test email to to_address.

**Events sent:** approval.requested, run.failed

**Inbound (both):** Inbound mail becomes tasks: either your mail provider POSTs to the inbound URL (Postmark / SendGrid / Mailgun inbound parse) or triage polls an IMAP mailbox every minute.

1. Push (recommended): Postmark → Servers → Inbound → set the inbound URL from this card as the webhook (JSON). SendGrid: Inbound Parse → add host + URL. Mailgun: Receiving → Routes → forward to the URL. The URL carries ?token=… as authentication.
2. Pull (any mailbox): fill imap_host/port/folder; username/password are the SMTP ones already configured (Gmail: app password). The first sync only sets the cursor; new mail is imported from then on.
3. Send a test mail → it appears under tasks with the subject as the first line.

Inbound fields: `imap_host` — imap host (for polling); `imap_port` — imap port; `imap_folder` — folder

## WEBHOOKS (`webhook`) — live

POST a JSON payload to your own endpoint for every project event — wire triage into anything.

**How it works**

- Every event in the project (approval.requested/resolved, run.started/complete/failed, ticket.created, knowledge.indexed, …) is POSTed as JSON: {"event", "project": {id, slug}, "ts", "data"}.
- If you set a secret, each request carries `X-Triage-Signature: sha256=<hex HMAC-SHA256 of the raw body>` so your endpoint can verify authenticity, and `X-Triage-Event` names the event.
- Use the events field to subscribe to a subset (comma-separated; empty = all). Deliveries have a 10 s timeout and are not retried; failures are logged in the activity feed.

**Setup steps**

1. Expose an HTTPS endpoint that accepts POST with a JSON body (a serverless function, n8n/Zapier/Make catch-hook, or your own service).
2. Generate a random secret (e.g. `openssl rand -hex 32`) and store it on your endpoint; verify `X-Triage-Signature` by computing HMAC-SHA256(secret, body).
3. In triage: url, secret, optional events list (e.g. `approval.requested,ticket.created`). Press TEST — a `{"event":"test"}` payload is delivered. Then CONNECT.

**Fields**

- `url` — endpoint url: https://…
- `secret` — signing secret (optional): used for X-Triage-Signature *(secret, encrypted at rest)*
- `events` — events (optional): comma-separated subset; empty = all events

**Permissions:** None — outbound only

**TEST button:** POSTs {"event":"test"} to the URL and expects a 2xx.

**Events sent:** *

**Inbound (push):** Anything can POST intake-shaped items to the inbound URL — Zapier, n8n, Make, your own services.

1. Copy the inbound URL from this card.
2. POST JSON: {"items":[{"id":"X-1","source":"zapier","author":"…","text":"…","metadata":{"app_version":"2.4.1"}}]} (a single object works too).
3. Optional: sign the body with inbound_secret and send X-Triage-Signature.
4. Items with an id you already sent are skipped — safe to retry.

Inbound fields: `inbound_secret` — inbound signing secret (optional)

## SENTRY (`sentry`) — planned

Pull crash data from Sentry so the investigator's query_crashes tool uses real telemetry instead of an uploaded CSV.

**How it works**

- Planned: a scheduled import calls GET /api/0/projects/{org}/{project}/issues/ and converts each issue (title/culprit as signature, count, first/last seen, top devices from tags) into the crash-log format, replacing the project's crashlog knowledge item.
- Until the adapter ships, export crashes from Sentry (Discover → export CSV with columns signature, stack_top, app_version, device, os, user_id, timestamp) and upload it under knowledge as a crash log — the agents already work with that.

**Setup steps**

1. Sentry → Settings → Developer Settings → Personal Tokens (or an internal integration) → create a token with `project:read` and `event:read`.
2. org = your organization slug (in the URL: sentry.io/organizations/<org>/), project = the project slug.
3. Store them here now; they will be used automatically once the import adapter is enabled.

**Fields**

- `org` — organization slug
- `project` — project slug
- `auth_token` — auth token: scopes: project:read, event:read *(secret, encrypted at rest)*

**Permissions:** project:read, event:read

**TEST button:** GET /api/0/projects/{org}/{project}/ — verifies the token and slugs.

**Inbound (both):** New Sentry issues become tasks (webhook) and the project's crash log is rebuilt from Sentry's unresolved issues every 15 minutes, so query_crashes uses live telemetry.

1. Polling needs org, project and auth_token (above) — CONNECT starts it; SYNC NOW forces a refresh. A knowledge item sentry-issues.csv appears and is kept current.
2. Push: Sentry → Settings → Developer Settings → Custom Integrations → New internal integration → Webhook URL = the inbound URL from this card; Permissions: Issue & Event read; Webhooks: issue created. Copy the Client Secret into client_secret.
3. Alternatively an Alert rule → action 'Send a notification via an integration' → your integration.

Inbound fields: `client_secret` — internal integration client secret (optional)

## GOOGLE DRIVE (`gdrive`) — planned

Sync a Drive folder into the project knowledge base so documents stay indexed as they change.

**How it works**

- Planned: a scheduled job lists the folder via the Drive API using a service account, downloads new/changed Google Docs (exported as text) and files, and creates/re-indexes knowledge items.
- Until then, download the documents and upload them under knowledge (PDF, DOCX, Markdown and text are supported).

**Setup steps**

1. Google Cloud Console → create/select a project → APIs & Services → Enable the Google Drive API.
2. IAM & Admin → Service accounts → Create service account → Keys → Add key → JSON. Download the JSON.
3. In Drive, share the folder with the service account's email (Viewer). Copy the folder id from the URL (drive.google.com/drive/folders/<id>).
4. In triage: folder_id + paste the whole JSON key into service_account_json. Stored encrypted.

**Fields**

- `folder_id` — folder id: from the folder URL
- `service_account_json` — service account key (json): paste the downloaded JSON *(secret, encrypted at rest)*

**Permissions:** Drive API enabled; folder shared with the service account (Viewer)

**TEST button:** Lists the folder with the service account — verifies sharing and the key.

**Inbound (poll):** Every 15 minutes new or changed files in the shared folder are pulled into the knowledge base (Google Docs exported as text, Sheets as CSV, other files as-is).

1. Share the folder with the service account email (Viewer). CONNECT starts the sync; SYNC NOW forces one.
2. Synced files land under files › /uploads/synced and are indexed like uploads; edits in Drive re-index the item.

## CUSTOM API (`custom`) — planned

Give the agents a tool that calls your own HTTP API (e.g. an internal ticket tracker or customer database).

**How it works**

- Planned: a generic `call_custom_api` tool that the investigator/triage agents can be granted; it sends GET/POST requests to base_url with auth_header attached and returns the JSON to the model.
- Today the tool registry is code (triage/tools/registry.py): add a Python function there and it appears in the agent editor. The tracker interface in triage/tools/tracker.py is the easiest place to plug in a real tracker.

**Setup steps**

1. base_url = the root of your API (https://api.internal.example.com).
2. auth_header = the full header value to send, e.g. `Bearer eyJ…` or `ApiKey abc123`. Stored encrypted.

**Fields**

- `base_url` — base url
- `auth_header` — authorization header value: e.g. Bearer … *(secret, encrypted at rest)*

**Permissions:** Whatever your API grants that credential

**TEST button:** GET base_url with the header — expects any non-5xx response.

**Inbound (both):** Pull: every 5 minutes GET base_url + poll_path with your auth header, expecting a JSON array (or {items:[…]}) of intake-shaped items; ?since= carries the last cursor. Push: POST to the inbound URL.

1. Expose an endpoint returning [{"id":…,"text":…,"author":…,"received_at":…,"metadata":{…}}] and honour ?since=<last received_at or id>.
2. Or push to the inbound URL exactly like the Webhooks integration.

Inbound fields: `poll_path` — poll path (optional); `inbound_secret` — inbound signing secret (optional)

