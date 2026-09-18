"""The integration catalog: for every provider, what it does in triage, how it
works, how to obtain credentials, which fields it needs, and how to verify it.

Single source of truth — the API serves it to the UI and `docs/INTEGRATIONS.md`
is generated from it (`python -m api.integrations.catalog > ../docs/INTEGRATIONS.md`).
"""

from __future__ import annotations

SECRET_FIELDS = {"token", "api_token", "api_key", "auth_token", "password", "secret", "service_account_json", "auth_header", "webhook_url", "webhook_secret", "signing_secret", "bot_token", "client_secret", "inbound_secret"}

# status: "live" = implemented end to end; "planned" = configuration is stored, adapter not built yet.
CATALOG: dict[str, dict] = {
    "github": {
        "label": "GITHUB", "status": "live", "category": "issue tracker",
        "summary": "Mirror every ticket the writer agent creates as a GitHub issue in one repository.",
        "how_it_works": [
            "When a run ends with outcome new_ticket, the server POSTs to GitHub's REST API (POST /repos/{owner}/{repo}/issues) using your token.",
            "The issue title is the ticket title; the body is the ticket markdown (severity, component, owner, repro steps, expected/actual, evidence, source feedback).",
            "Labels are added from severity and component (e.g. `severity:high`, `component:billing`) — they are created on the fly if the token allows it.",
            "The issue URL is written back into the project activity feed (`GITHUB issue #12 created for OR-118`) and the ticket JSON under /out/tickets gets an `external_url`.",
            "If the call fails (bad token, missing repo) the integration flips to ● ERROR with the reason, and the run itself still completes — mirroring never blocks triage.",
        ],
        "steps": [
            "Open github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token.",
            "Resource owner: the organization or user that owns the repository. Repository access: only the target repo.",
            "Permissions: Repository permissions → Issues: Read and write. (Metadata: Read is added automatically.) Nothing else is needed.",
            "Set an expiry, generate, and copy the token (it starts with `github_pat_`). Classic tokens with the `repo` scope also work.",
            "In triage: repository = `owner/name` (e.g. `acme/payments-platform`), token = the value you copied. Press TEST — it reads the repository and reports the issue count. Then CONNECT.",
        ],
        "fields": {
            "repository": {"label": "repository", "help": "owner/name, e.g. acme/payments-platform"},
            "token": {"label": "personal access token", "help": "fine-grained token with Issues: read & write on that repo"},
            "labels": {"label": "extra labels (optional)", "help": "comma-separated labels added to every issue, e.g. triage,from-feedback"},
        },
        "permissions": ["Issues: read & write on the selected repository"],
        "test": "GET /repos/{repository} — verifies the token can see the repo; no issue is created.",
        "events": ["ticket.created"],
        "inbound": {
            "mode": "push", "summary": "New GitHub issues (optionally only with a label) become tasks the moment they are opened.",
            "fields": {"webhook_secret": {"label": "webhook secret", "help": "the secret you set on the GitHub webhook (used to verify X-Hub-Signature-256)"},
                       "intake_label": {"label": "only issues with label (optional)", "help": "comma-separated, e.g. from-users,triage"},
                       "include_comments": {"label": "also import new comments (optional)", "help": "true / false"},
                       "poll_issues": {"label": "also poll open issues every 5 min (optional)", "help": "true to catch missed webhooks"}},
            "steps": ["Repository → Settings → Webhooks → Add webhook.", "Payload URL: the inbound URL shown on this card. Content type: application/json. Secret: generate one (openssl rand -hex 24) and paste it here as webhook_secret.",
                      "Events: 'Issues' (and 'Issue comments' if include_comments). Save; GitHub sends a ping — the card's inbound counter does not change for pings.",
                      "Open a test issue with the intake label → it appears under tasks within a second."],
            "events": ["issues.opened", "issues.reopened", "issue_comment.created"],
        },
    },
    "jira": {
        "label": "JIRA", "status": "live", "category": "issue tracker",
        "summary": "Create a Jira Cloud issue for every new ticket.",
        "how_it_works": [
            "On outcome new_ticket the server calls POST {site_url}/rest/api/3/issue with Basic auth (your Atlassian email + API token).",
            "Issue type defaults to `Bug` (configurable). Summary = ticket title; description is the ticket content in Atlassian Document Format; priority is mapped from severity (critical→Highest, high→High, medium→Medium, low→Low) when the project has those priorities.",
            "The Jira key (e.g. PAY-42) and URL are recorded in the activity feed and the ticket JSON.",
            "Failures set the integration to ● ERROR with Jira's error message (typically: wrong project key, or the issue type does not exist in that project).",
        ],
        "steps": [
            "Go to id.atlassian.com → Security → API tokens → Create API token. Name it `triage`, copy it.",
            "Find your site URL: it is the host you use for Jira, e.g. https://acme.atlassian.net (no trailing path).",
            "Find the project key: open the Jira project; the key is the prefix of its issue ids (PAY in PAY-42), also shown in Project settings → Details.",
            "Make sure the account that owns the token has 'Create Issues' permission in that project and that an issue type named Bug (or the one you configure) exists.",
            "In triage: site_url, project_key, email (the Atlassian account), api_token, optionally issue_type. Press TEST — it fetches the project and lists its issue types. Then CONNECT.",
        ],
        "fields": {
            "site_url": {"label": "site url", "help": "https://<your-site>.atlassian.net"},
            "project_key": {"label": "project key", "help": "e.g. PAY"},
            "email": {"label": "atlassian account email", "help": "the account the API token belongs to"},
            "api_token": {"label": "api token", "help": "from id.atlassian.com → Security → API tokens"},
            "issue_type": {"label": "issue type (optional)", "help": "default: Bug"},
        },
        "permissions": ["Browse projects + Create issues in the target project"],
        "test": "GET /rest/api/3/project/{project_key} — verifies auth and the project key; nothing is created.",
        "events": ["ticket.created"],
        "inbound": {
            "mode": "push", "summary": "Issues created in the Jira project (optionally one issue type) become tasks.",
            "fields": {"intake_issue_type": {"label": "only this issue type (optional)", "help": "e.g. Bug"}, "poll_issues": {"label": "also poll new issues every 5 min (optional)", "help": "true / false"}},
            "steps": ["Jira → Settings (gear) → System → WebHooks → Create a WebHook.", "URL: the inbound URL shown on this card — it already contains ?token=…; Jira Cloud does not sign webhooks, the token is the authentication.",
                      "Events: Issue → created. Optional JQL filter: project = KEY. Save.", "Create a test issue → it appears under tasks."],
            "events": ["jira:issue_created"],
        },
    },
    "linear": {
        "label": "LINEAR", "status": "live", "category": "issue tracker",
        "summary": "Create a Linear issue in one team for every new ticket.",
        "how_it_works": [
            "On outcome new_ticket the server sends the `issueCreate` GraphQL mutation to https://api.linear.app/graphql with your API key.",
            "Title = ticket title; description = ticket markdown; priority is mapped from severity (critical→Urgent, high→High, medium→Medium, low→Low).",
            "The Linear identifier (e.g. PAY-118) and URL are recorded in the activity feed and the ticket JSON.",
        ],
        "steps": [
            "Linear → Settings → Security & access → Personal API keys → Create key. Copy it (starts with `lin_api_`).",
            "Find the team key: Settings → Teams → the short identifier used in issue ids (PAY in PAY-118).",
            "In triage: team_key + api_key. Press TEST — it resolves the team id via GraphQL. Then CONNECT.",
        ],
        "fields": {
            "team_key": {"label": "team key", "help": "e.g. PAY"},
            "api_key": {"label": "personal api key", "help": "lin_api_…"},
        },
        "permissions": ["The key acts as you; you need to be a member of the team"],
        "test": "GraphQL query { teams(filter:{key:{eq:…}}) } — verifies the key and team.",
        "events": ["ticket.created"],
        "inbound": {
            "mode": "push", "summary": "Issues created in the Linear team become tasks.",
            "fields": {"webhook_secret": {"label": "webhook signing secret", "help": "shown once by Linear when you create the webhook"}, "poll_issues": {"label": "also poll every 5 min (optional)", "help": "true / false"}},
            "steps": ["Linear → Settings → API → Webhooks → New webhook.", "URL: the inbound URL shown on this card. Resource types: Issues. Team: the same team. Copy the signing secret into webhook_secret.", "Create a test issue → it appears under tasks."],
            "events": ["Issue.create"],
        },
    },
    "slack": {
        "label": "SLACK", "status": "live", "category": "notifications",
        "summary": "Post approval requests, created tickets and failed runs to a Slack channel.",
        "how_it_works": [
            "The server POSTs a message to your Incoming Webhook URL. No bot token or OAuth app scopes beyond the webhook are needed.",
            "Events sent: approval.requested (amber, with agent, action, confidence and a link to the approval queue), ticket.created (green, ticket id + severity + component), run.failed (red, run id + error).",
            "Messages are fire-and-forget: a Slack outage never delays a run. Delivery errors are logged to the activity feed and the integration shows ● ERROR.",
        ],
        "steps": [
            "Go to api.slack.com/apps → Create New App → From scratch. Name it `triage`, pick your workspace.",
            "In the app: Incoming Webhooks → toggle Activate Incoming Webhooks on → Add New Webhook to Workspace → choose the channel → Allow.",
            "Copy the Webhook URL (https://hooks.slack.com/services/T…/B…/…).",
            "In triage: webhook_url = that URL; channel is informational (the webhook decides the channel). Press TEST — a `triage connected` message appears in the channel. Then CONNECT.",
        ],
        "fields": {
            "webhook_url": {"label": "incoming webhook url", "help": "https://hooks.slack.com/services/…"},
            "channel": {"label": "channel (label only)", "help": "#eng-triage — shown in the UI; the webhook itself decides where messages go"},
        },
        "permissions": ["incoming-webhook (granted when you add the webhook to a channel)"],
        "test": "Posts a one-line test message to the webhook.",
        "events": ["approval.requested", "ticket.created", "run.failed"],
        "inbound": {
            "mode": "push", "summary": "Every message posted in one Slack channel becomes a task, instantly, via the Slack Events API.",
            "fields": {"signing_secret": {"label": "app signing secret", "help": "Slack app → Basic Information → App Credentials"},
                       "intake_channel": {"label": "channel id to read", "help": "C0123ABCD (channel details → copy channel ID)"},
                       "workspace_domain": {"label": "workspace domain (optional)", "help": "acme (from acme.slack.com) — used to build permalinks"},
                       "include_threads": {"label": "include thread replies (optional)", "help": "true / false"}},
            "steps": ["api.slack.com/apps → your app (the same one that owns the incoming webhook) → Event Subscriptions → Enable.",
                      "Request URL: the inbound URL shown on this card. Slack sends a challenge; the card shows ● VERIFIED once it succeeded (save signing_secret first).",
                      "Subscribe to bot events: message.channels (public) and/or message.groups (private). Save changes, then reinstall the app to the workspace.",
                      "OAuth & Permissions → scopes channels:history (and groups:history). Invite the bot to the channel: /invite @triage.",
                      "Post a message in the channel → it appears under tasks and, with auto-run on, starts a run. Bot messages and edits are ignored."],
            "events": ["message.channels", "message.groups"],
        },
    },
    "discord": {
        "label": "DISCORD", "status": "live", "category": "notifications",
        "summary": "Post approval requests, created tickets and failed runs to a Discord channel.",
        "how_it_works": [
            "Same as Slack: the server POSTs to a channel Webhook URL. Messages use Discord embeds coloured amber/green/red by event type.",
            "Events: approval.requested, ticket.created, run.failed.",
        ],
        "steps": [
            "In Discord open the target channel → Edit Channel (gear) → Integrations → Webhooks → New Webhook.",
            "Name it `triage`, optionally set an avatar, then Copy Webhook URL (https://discord.com/api/webhooks/…).",
            "In triage: webhook_url = that URL. Press TEST — a test embed appears in the channel. Then CONNECT.",
        ],
        "fields": {"webhook_url": {"label": "channel webhook url", "help": "https://discord.com/api/webhooks/…"}},
        "permissions": ["Manage Webhooks on the channel (to create the webhook)"],
        "test": "Posts a test embed to the webhook.",
        "events": ["approval.requested", "ticket.created", "run.failed"],
        "inbound": {
            "mode": "poll", "summary": "Messages in one Discord channel are read by a bot every 30 seconds (Discord has no outbound message webhooks).",
            "fields": {"bot_token": {"label": "bot token", "help": "Discord Developer Portal → your application → Bot → Reset Token"},
                       "intake_channel_id": {"label": "channel id to read", "help": "enable Developer Mode in Discord, right-click the channel → Copy Channel ID"}},
            "steps": ["discord.com/developers/applications → New Application → Bot → Add Bot → copy the token.", "Bot → Privileged Gateway Intents → enable Message Content Intent (required to read message text).",
                      "OAuth2 → URL Generator → scope bot, permissions View Channels + Read Message History → open the URL → add the bot to your server.",
                      "Paste bot_token and intake_channel_id here → CONNECT. The first sync sets the cursor at the newest message; only later messages are imported. Press SYNC NOW to test."],
            "events": [],
        },
    },
    "email": {
        "label": "EMAIL", "status": "live", "category": "notifications",
        "summary": "Email a reviewer when a run needs human approval, and when a run fails.",
        "how_it_works": [
            "The server sends plain-text mail over SMTP (STARTTLS on 587, or implicit TLS on 465) from a background thread.",
            "approval.requested → subject `[triage] approval needed: APPROVAL_REQ_… (project)` with the agent, action, confidence and a link to the approval queue. run.failed → subject `[triage] run failed: RUN_…`.",
            "One mail per event to the `to_address` list (comma-separated).",
        ],
        "steps": [
            "Use any SMTP account. Gmail: enable 2-step verification, then Google Account → Security → App passwords → create one for `triage`; host smtp.gmail.com, port 587, username = your address, password = the app password.",
            "Transactional providers (Postmark, SendGrid, Resend, SES): create SMTP credentials in their dashboard; use the host/port/username/password they show.",
            "from_address must be an address the SMTP account is allowed to send as (Gmail: your own address; providers: a verified sender).",
            "In triage fill the fields and press TEST — a test mail is sent to to_address. Then CONNECT.",
        ],
        "fields": {
            "smtp_host": {"label": "smtp host", "help": "smtp.gmail.com, smtp.postmarkapp.com, …"},
            "smtp_port": {"label": "smtp port", "help": "587 (STARTTLS) or 465 (TLS)"},
            "username": {"label": "username", "help": ""},
            "password": {"label": "password / app password", "help": ""},
            "from_address": {"label": "from address", "help": "triage@yourcompany.com"},
            "to_address": {"label": "to address(es)", "help": "comma-separated reviewers"},
        },
        "permissions": ["An SMTP login that may send as from_address"],
        "test": "Sends one test email to to_address.",
        "events": ["approval.requested", "run.failed"],
        "inbound": {
            "mode": "both", "summary": "Inbound mail becomes tasks: either your mail provider POSTs to the inbound URL (Postmark / SendGrid / Mailgun inbound parse) or triage polls an IMAP mailbox every minute.",
            "fields": {"imap_host": {"label": "imap host (for polling)", "help": "imap.gmail.com — leave empty to use the inbound webhook instead"},
                       "imap_port": {"label": "imap port", "help": "993"}, "imap_folder": {"label": "folder", "help": "INBOX or a label like triage"}},
            "steps": ["Push (recommended): Postmark → Servers → Inbound → set the inbound URL from this card as the webhook (JSON). SendGrid: Inbound Parse → add host + URL. Mailgun: Receiving → Routes → forward to the URL. The URL carries ?token=… as authentication.",
                      "Pull (any mailbox): fill imap_host/port/folder; username/password are the SMTP ones already configured (Gmail: app password). The first sync only sets the cursor; new mail is imported from then on.",
                      "Send a test mail → it appears under tasks with the subject as the first line."],
            "events": ["inbound message"],
        },
    },
    "webhook": {
        "label": "WEBHOOKS", "status": "live", "category": "automation",
        "summary": "POST a JSON payload to your own endpoint for every project event — wire triage into anything.",
        "how_it_works": [
            "Every event in the project (approval.requested/resolved, run.started/complete/failed, ticket.created, knowledge.indexed, …) is POSTed as JSON: {\"event\", \"project\": {id, slug}, \"ts\", \"data\"}.",
            "If you set a secret, each request carries `X-Triage-Signature: sha256=<hex HMAC-SHA256 of the raw body>` so your endpoint can verify authenticity, and `X-Triage-Event` names the event.",
            "Use the events field to subscribe to a subset (comma-separated; empty = all). Deliveries have a 10 s timeout and are not retried; failures are logged in the activity feed.",
        ],
        "steps": [
            "Expose an HTTPS endpoint that accepts POST with a JSON body (a serverless function, n8n/Zapier/Make catch-hook, or your own service).",
            "Generate a random secret (e.g. `openssl rand -hex 32`) and store it on your endpoint; verify `X-Triage-Signature` by computing HMAC-SHA256(secret, body).",
            "In triage: url, secret, optional events list (e.g. `approval.requested,ticket.created`). Press TEST — a `{\"event\":\"test\"}` payload is delivered. Then CONNECT.",
        ],
        "fields": {
            "url": {"label": "endpoint url", "help": "https://…"},
            "secret": {"label": "signing secret (optional)", "help": "used for X-Triage-Signature"},
            "events": {"label": "events (optional)", "help": "comma-separated subset; empty = all events"},
        },
        "permissions": ["None — outbound only"],
        "test": "POSTs {\"event\":\"test\"} to the URL and expects a 2xx.",
        "events": ["*"],
        "inbound": {
            "mode": "push", "summary": "Anything can POST intake-shaped items to the inbound URL — Zapier, n8n, Make, your own services.",
            "fields": {"inbound_secret": {"label": "inbound signing secret (optional)", "help": "if set, senders must include X-Triage-Signature: sha256=HMAC(body); otherwise the ?token= in the URL authenticates"}},
            "steps": ["Copy the inbound URL from this card.", "POST JSON: {\"items\":[{\"id\":\"X-1\",\"source\":\"zapier\",\"author\":\"…\",\"text\":\"…\",\"metadata\":{\"app_version\":\"2.4.1\"}}]} (a single object works too).",
                      "Optional: sign the body with inbound_secret and send X-Triage-Signature.", "Items with an id you already sent are skipped — safe to retry."],
            "events": ["items"],
        },
    },
    "sentry": {
        "label": "SENTRY", "status": "planned", "category": "telemetry",
        "summary": "Pull crash data from Sentry so the investigator's query_crashes tool uses real telemetry instead of an uploaded CSV.",
        "how_it_works": [
            "Planned: a scheduled import calls GET /api/0/projects/{org}/{project}/issues/ and converts each issue (title/culprit as signature, count, first/last seen, top devices from tags) into the crash-log format, replacing the project's crashlog knowledge item.",
            "Until the adapter ships, export crashes from Sentry (Discover → export CSV with columns signature, stack_top, app_version, device, os, user_id, timestamp) and upload it under knowledge as a crash log — the agents already work with that.",
        ],
        "steps": [
            "Sentry → Settings → Developer Settings → Personal Tokens (or an internal integration) → create a token with `project:read` and `event:read`.",
            "org = your organization slug (in the URL: sentry.io/organizations/<org>/), project = the project slug.",
            "Store them here now; they will be used automatically once the import adapter is enabled.",
        ],
        "fields": {
            "org": {"label": "organization slug", "help": ""},
            "project": {"label": "project slug", "help": ""},
            "auth_token": {"label": "auth token", "help": "scopes: project:read, event:read"},
        },
        "permissions": ["project:read, event:read"],
        "test": "GET /api/0/projects/{org}/{project}/ — verifies the token and slugs.",
        "events": [],
        "inbound": {
            "mode": "both", "summary": "New Sentry issues become tasks (webhook) and the project's crash log is rebuilt from Sentry's unresolved issues every 15 minutes, so query_crashes uses live telemetry.",
            "fields": {"client_secret": {"label": "internal integration client secret (optional)", "help": "Settings → Developer Settings → your integration → Client Secret; used to verify Sentry-Hook-Signature. Without it the ?token= in the URL authenticates."}},
            "steps": ["Polling needs org, project and auth_token (above) — CONNECT starts it; SYNC NOW forces a refresh. A knowledge item sentry-issues.csv appears and is kept current.",
                      "Push: Sentry → Settings → Developer Settings → Custom Integrations → New internal integration → Webhook URL = the inbound URL from this card; Permissions: Issue & Event read; Webhooks: issue created. Copy the Client Secret into client_secret.",
                      "Alternatively an Alert rule → action 'Send a notification via an integration' → your integration."],
            "events": ["issue.created", "event.created"],
        },
    },
    "gdrive": {
        "label": "GOOGLE DRIVE", "status": "planned", "category": "knowledge",
        "summary": "Sync a Drive folder into the project knowledge base so documents stay indexed as they change.",
        "how_it_works": [
            "Planned: a scheduled job lists the folder via the Drive API using a service account, downloads new/changed Google Docs (exported as text) and files, and creates/re-indexes knowledge items.",
            "Until then, download the documents and upload them under knowledge (PDF, DOCX, Markdown and text are supported).",
        ],
        "steps": [
            "Google Cloud Console → create/select a project → APIs & Services → Enable the Google Drive API.",
            "IAM & Admin → Service accounts → Create service account → Keys → Add key → JSON. Download the JSON.",
            "In Drive, share the folder with the service account's email (Viewer). Copy the folder id from the URL (drive.google.com/drive/folders/<id>).",
            "In triage: folder_id + paste the whole JSON key into service_account_json. Stored encrypted.",
        ],
        "fields": {
            "folder_id": {"label": "folder id", "help": "from the folder URL"},
            "service_account_json": {"label": "service account key (json)", "help": "paste the downloaded JSON"},
        },
        "permissions": ["Drive API enabled; folder shared with the service account (Viewer)"],
        "test": "Lists the folder with the service account — verifies sharing and the key.",
        "events": [],
        "inbound": {
            "mode": "poll", "summary": "Every 15 minutes new or changed files in the shared folder are pulled into the knowledge base (Google Docs exported as text, Sheets as CSV, other files as-is).",
            "fields": {},
            "steps": ["Share the folder with the service account email (Viewer). CONNECT starts the sync; SYNC NOW forces one.", "Synced files land under files › /uploads/synced and are indexed like uploads; edits in Drive re-index the item."],
            "events": [],
        },
    },
    "custom": {
        "label": "CUSTOM API", "status": "planned", "category": "tools",
        "summary": "Give the agents a tool that calls your own HTTP API (e.g. an internal ticket tracker or customer database).",
        "how_it_works": [
            "Planned: a generic `call_custom_api` tool that the investigator/triage agents can be granted; it sends GET/POST requests to base_url with auth_header attached and returns the JSON to the model.",
            "Today the tool registry is code (triage/tools/registry.py): add a Python function there and it appears in the agent editor. The tracker interface in triage/tools/tracker.py is the easiest place to plug in a real tracker.",
        ],
        "steps": [
            "base_url = the root of your API (https://api.internal.example.com).",
            "auth_header = the full header value to send, e.g. `Bearer eyJ…` or `ApiKey abc123`. Stored encrypted.",
        ],
        "fields": {
            "base_url": {"label": "base url", "help": ""},
            "auth_header": {"label": "authorization header value", "help": "e.g. Bearer …"},
        },
        "permissions": ["Whatever your API grants that credential"],
        "test": "GET base_url with the header — expects any non-5xx response.",
        "events": [],
        "inbound": {
            "mode": "both", "summary": "Pull: every 5 minutes GET base_url + poll_path with your auth header, expecting a JSON array (or {items:[…]}) of intake-shaped items; ?since= carries the last cursor. Push: POST to the inbound URL.",
            "fields": {"poll_path": {"label": "poll path (optional)", "help": "/feedback?status=new — appended to base_url; leave empty to disable polling"},
                       "inbound_secret": {"label": "inbound signing secret (optional)", "help": "for pushes: X-Triage-Signature: sha256=HMAC(body)"}},
            "steps": ["Expose an endpoint returning [{\"id\":…,\"text\":…,\"author\":…,\"received_at\":…,\"metadata\":{…}}] and honour ?since=<last received_at or id>.", "Or push to the inbound URL exactly like the Webhooks integration."],
            "events": ["items"],
        },
    },
}


def to_markdown() -> str:
    out = ["# Integrations", "", "How each integration works in triage and how to set it up. Generated from `server/integrations_catalog.py`.", ""]
    for key, c in CATALOG.items():
        out += [f"## {c['label']} (`{key}`) — {c['status']}", "", c["summary"], "", "**How it works**", ""]
        out += [f"- {h}" for h in c["how_it_works"]]
        out += ["", "**Setup steps**", ""]
        out += [f"{i}. {s}" for i, s in enumerate(c["steps"], 1)]
        out += ["", "**Fields**", ""]
        out += [f"- `{f}` — {m['label']}" + (f": {m['help']}" if m["help"] else "") + (" *(secret, encrypted at rest)*" if f in SECRET_FIELDS else "") for f, m in c["fields"].items()]
        out += ["", "**Permissions:** " + "; ".join(c["permissions"]), "", f"**TEST button:** {c['test']}", ""]
        if c["events"]:
            out += ["**Events sent:** " + ", ".join(c["events"]), ""]
        ib = c.get("inbound")
        if ib:
            out += [f"**Inbound ({ib['mode']}):** {ib['summary']}", ""]
            out += [f"{i}. {st}" for i, st in enumerate(ib["steps"], 1)]
            if ib["fields"]:
                out += ["", "Inbound fields: " + "; ".join(f"`{f}` — {m['label']}" for f, m in ib["fields"].items())]
            out += [""]
    return "\n".join(out)


if __name__ == "__main__":
    print(to_markdown())
