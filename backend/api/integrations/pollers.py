"""Inbound (pull) integrations: sources that cannot push are polled by the sync
scheduler. Each poller: `async def poll(cfg, cursor) -> (items, new_cursor, note)`.
Items use the intake shape; `cursor` is whatever the poller needs to fetch only
new things next time. Knowledge-type pollers (Sentry issues → crash log, Drive
folder → documents) return items with `kind="knowledge"` instead of tasks.
"""

from __future__ import annotations

import base64
import csv
import email
import hashlib
import imaplib
import io
import json
import time
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from typing import Any

import httpx

INTERVALS = {"discord": 30, "email": 60, "sentry": 900, "gdrive": 900, "custom": 300, "github": 300, "jira": 300, "linear": 300}


# ---------------------------------------------------------------- discord ----
async def discord(cfg: dict, cursor: dict) -> tuple[list[dict], dict, str]:
    token, channel = cfg.get("bot_token"), str(cfg.get("intake_channel_id") or "")
    if not token or not channel:
        return [], cursor, "skipped: bot_token and intake_channel_id required for polling"
    params = {"limit": 100}
    if cursor.get("after"):
        params["after"] = cursor["after"]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"https://discord.com/api/v10/channels/{channel}/messages", params=params, headers={"Authorization": f"Bot {token}"})
        r.raise_for_status()
    msgs = sorted(r.json(), key=lambda m: int(m["id"]))
    if not cursor.get("after"):   # first sync: only establish the cursor, do not import history
        return [], {"after": msgs[-1]["id"] if msgs else "0"}, "cursor initialised; new messages will be imported from now on"
    items = [{"id": f"DC-{m['id']}", "source": "discord", "author": m.get("author", {}).get("username", ""), "text": m.get("content", ""),
              "received_at": m.get("timestamp"), "metadata": {"channel": channel, "url": f"https://discord.com/channels/@me/{channel}/{m['id']}"}}
             for m in msgs if m.get("content") and not m.get("author", {}).get("bot")]
    return items, {"after": msgs[-1]["id"]} if msgs else cursor, f"{len(items)} new message(s)"


# ------------------------------------------------------------------ email ----
def _imap_fetch(cfg: dict, since_uid: int) -> tuple[list[dict], int]:
    host, user, pw = cfg["imap_host"], cfg["username"], cfg["password"]
    folder = cfg.get("imap_folder") or "INBOX"
    M = imaplib.IMAP4_SSL(host, int(cfg.get("imap_port") or 993))
    try:
        M.login(user, pw)
        M.select(folder, readonly=True)
        typ, data = M.uid("search", None, f"UID {since_uid + 1}:*")
        uids = [int(u) for u in (data[0].split() if data and data[0] else [])]
        uids = [u for u in uids if u > since_uid][:50]
        items = []
        for u in uids:
            typ, msgdata = M.uid("fetch", str(u), "(RFC822)")
            msg = email.message_from_bytes(msgdata[0][1])
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            sender = str(make_header(decode_header(msg.get("From", ""))))
            body = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace"); break
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        import re
                        body = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace"))); break
            mid = msg.get("Message-ID", f"uid{u}")
            items.append({"id": f"EM-{hashlib.sha1(mid.encode()).hexdigest()[:10].upper()}", "source": "email", "author": sender,
                          "text": f"{subject}\n\n{body}".strip(), "received_at": msg.get("Date"), "metadata": {"subject": subject, "uid": u}})
        return items, (max(uids) if uids else since_uid)
    finally:
        try: M.logout()
        except Exception: pass


async def email_poll(cfg: dict, cursor: dict) -> tuple[list[dict], dict, str]:
    if not cfg.get("imap_host"):
        return [], cursor, "skipped: set imap_host/username/password to poll a mailbox (or use the inbound webhook URL)"
    import asyncio
    since = int(cursor.get("uid") or 0)
    if since == 0:   # first sync: establish the cursor at the current newest message
        items, newest = await asyncio.to_thread(_imap_fetch, cfg, 0)
        return [], {"uid": newest}, "cursor initialised at the newest message; new mail will be imported from now on"
    items, newest = await asyncio.to_thread(_imap_fetch, cfg, since)
    return items, {"uid": newest}, f"{len(items)} new message(s)"


# ----------------------------------------------------------------- sentry ----
async def sentry(cfg: dict, cursor: dict) -> tuple[list[dict], dict, str]:
    """Pull unresolved issues and hand them back as a crash-log knowledge item (query_crashes uses it),
    plus one task per *new* issue so it gets triaged."""
    org, proj, token = cfg.get("org"), cfg.get("project"), cfg.get("auth_token")
    if not (org and proj and token):
        return [], cursor, "skipped: org, project and auth_token required"
    async with httpx.AsyncClient(timeout=20, headers={"Authorization": f"Bearer {token}"}) as c:
        r = await c.get(f"https://sentry.io/api/0/projects/{org}/{proj}/issues/", params={"query": "is:unresolved", "limit": 100, "statsPeriod": "14d"})
        r.raise_for_status()
        issues = r.json()
    buf = io.StringIO()
    w = csv.writer(buf); w.writerow(["signature", "stack_top", "app_version", "device", "os", "user_id", "timestamp"])
    seen = set(cursor.get("seen") or [])
    items = []
    for i in issues:
        sig = (i.get("metadata") or {}).get("type") or i.get("title", "")
        sig = f"{sig}:{i.get('culprit', '')}"[:120]
        count = int(i.get("count") or 1)
        # one row per event is the crash-log contract; Sentry gives aggregates, so we expand up to 50 rows per issue
        for n in range(min(count, 50)):
            w.writerow([sig, i.get("culprit", ""), (i.get("firstRelease") or {}).get("shortVersion", "") if isinstance(i.get("firstRelease"), dict) else "", "", (i.get("platform") or ""), f"u{n}", i.get("lastSeen", "")])
        if i["id"] not in seen:
            items.append({"id": f"SEN-{i['id']}", "source": "sentry", "author": "sentry", "text": f"{i.get('title')}\n{i.get('culprit', '')}\nevents: {count} · users: {i.get('userCount')}",
                          "received_at": i.get("firstSeen"), "metadata": {"url": i.get("permalink"), "level": i.get("level"), "count": count}})
            seen.add(i["id"])
    knowledge = {"kind": "knowledge", "name": "sentry-issues.csv", "type": "crashlog", "data": buf.getvalue().encode()}
    return items + [knowledge], {"seen": sorted(seen)[-2000:]}, f"{len(issues)} unresolved issue(s), {len(items)} new task(s), crash log refreshed"


# ------------------------------------------------------------------ gdrive ----
def _sa_token(sa: dict) -> str:
    """Service-account JWT → access token (no google libs needed)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    hdr = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=")
    claim = base64.urlsafe_b64encode(json.dumps({"iss": sa["client_email"], "scope": "https://www.googleapis.com/auth/drive.readonly", "aud": sa["token_uri"], "iat": now, "exp": now + 3600}).encode()).rstrip(b"=")
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    sig = base64.urlsafe_b64encode(key.sign(hdr + b"." + claim, padding.PKCS1v15(), hashes.SHA256())).rstrip(b"=")
    r = httpx.post(sa["token_uri"], data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": (hdr + b"." + claim + b"." + sig).decode()}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


async def gdrive(cfg: dict, cursor: dict) -> tuple[list[dict], dict, str]:
    import asyncio
    folder = cfg.get("folder_id")
    try:
        sa = json.loads(cfg.get("service_account_json") or "{}")
    except json.JSONDecodeError:
        return [], cursor, "error: service_account_json is not valid JSON"
    if not folder or not sa.get("client_email"):
        return [], cursor, "skipped: folder_id and service_account_json required"
    token = await asyncio.to_thread(_sa_token, sa)
    since = cursor.get("since")
    q = f"'{folder}' in parents and trashed = false" + (f" and modifiedTime > '{since}'" if since else "")
    async with httpx.AsyncClient(timeout=30, headers={"Authorization": f"Bearer {token}"}) as c:
        r = await c.get("https://www.googleapis.com/drive/v3/files", params={"q": q, "fields": "files(id,name,mimeType,modifiedTime,size)", "pageSize": 50})
        r.raise_for_status()
        files = r.json().get("files", [])
        items = []
        for f in files:
            mt = f["mimeType"]
            if mt.startswith("application/vnd.google-apps."):
                export = {"application/vnd.google-apps.document": ("text/plain", ".txt"), "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
                          "application/vnd.google-apps.presentation": ("text/plain", ".txt")}.get(mt)
                if not export:
                    continue
                d = await c.get(f"https://www.googleapis.com/drive/v3/files/{f['id']}/export", params={"mimeType": export[0]})
                name = f["name"] + export[1]
            else:
                if int(f.get("size") or 0) > 25 * 1024 * 1024:
                    continue
                d = await c.get(f"https://www.googleapis.com/drive/v3/files/{f['id']}", params={"alt": "media"})
                name = f["name"]
            d.raise_for_status()
            items.append({"kind": "knowledge", "name": name, "type": "auto", "data": d.content, "drive_id": f["id"]})
    newest = max((f["modifiedTime"] for f in files), default=since)
    return items, {"since": newest} if newest else cursor, f"{len(items)} file(s) synced"


# ----------------------------------------------------------------- custom ----
async def custom(cfg: dict, cursor: dict) -> tuple[list[dict], dict, str]:
    """GET base_url (or base_url + poll_path) with the auth header; expects a JSON array of intake-shaped
    items (or {items:[...]}). `since` cursor is passed as ?since=<last received_at or id>."""
    url = str(cfg.get("base_url") or "").rstrip("/") + str(cfg.get("poll_path") or "")
    if not url.startswith("http"):
        return [], cursor, "skipped: base_url required"
    params = {"since": cursor["since"]} if cursor.get("since") else {}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(url, params=params, headers={"Authorization": cfg.get("auth_header", "")})
        r.raise_for_status()
        data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    items = [i for i in (items or []) if isinstance(i, dict)]
    newest = max((str(i.get("received_at") or i.get("id") or "") for i in items), default=cursor.get("since"))
    return items, {"since": newest} if newest else cursor, f"{len(items)} item(s)"


# --------------------------------------- trackers: catch-up polling (push is primary) ----
async def github(cfg: dict, cursor: dict) -> tuple[list[dict], dict, str]:
    repo, token = cfg.get("repository"), cfg.get("token")
    if not (repo and token) or not cfg.get("poll_issues"):
        return [], cursor, "skipped: push webhook is the primary path; set poll_issues=true to also poll"
    since = cursor.get("since") or (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    async with httpx.AsyncClient(timeout=20, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}) as c:
        r = await c.get(f"https://api.github.com/repos/{repo}/issues", params={"since": since, "state": "open", "per_page": 50})
        r.raise_for_status()
    label = str(cfg.get("intake_label") or "")
    items = [{"id": f"GH-{i['number']}", "source": "github", "author": i.get("user", {}).get("login", ""), "text": f"{i.get('title', '')}\n\n{i.get('body') or ''}",
              "received_at": i.get("created_at"), "metadata": {"url": i.get("html_url")}}
             for i in r.json() if "pull_request" not in i and (not label or label in [l["name"] for l in i.get("labels", [])])]
    return items, {"since": datetime.now(timezone.utc).isoformat()}, f"{len(items)} issue(s)"


async def jira(cfg: dict, cursor: dict) -> tuple[list[dict], dict, str]:
    if not cfg.get("poll_issues"):
        return [], cursor, "skipped: webhook is the primary path; set poll_issues=true to also poll"
    base = str(cfg.get("site_url", "")).rstrip("/")
    jql = f'project = {cfg.get("project_key")} AND created >= -1d ORDER BY created ASC'
    async with httpx.AsyncClient(timeout=20, auth=(cfg.get("email", ""), cfg.get("api_token", ""))) as c:
        r = await c.get(f"{base}/rest/api/3/search", params={"jql": jql, "maxResults": 50, "fields": "summary,description,reporter,created"})
        r.raise_for_status()
    items = []
    for i in r.json().get("issues", []):
        f = i.get("fields", {})
        desc = f.get("description")
        from .inbound import _adf_text
        if isinstance(desc, dict): desc = " ".join(_adf_text(desc))
        items.append({"id": i["key"], "source": "jira", "author": (f.get("reporter") or {}).get("displayName", ""), "text": f"{f.get('summary', '')}\n\n{desc or ''}",
                      "received_at": f.get("created"), "metadata": {"url": f"{base}/browse/{i['key']}"}})
    return items, cursor, f"{len(items)} issue(s)"


async def linear(cfg: dict, cursor: dict) -> tuple[list[dict], dict, str]:
    if not cfg.get("poll_issues"):
        return [], cursor, "skipped: webhook is the primary path; set poll_issues=true to also poll"
    q = {"query": "query($k:String!){ teams(filter:{key:{eq:$k}}){ nodes { issues(first:50, orderBy:createdAt){ nodes { identifier title description url createdAt creator { name } } } } } }", "variables": {"k": cfg.get("team_key")}}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://api.linear.app/graphql", json=q, headers={"Authorization": cfg.get("api_key", "")})
        r.raise_for_status()
    nodes = ((r.json().get("data") or {}).get("teams") or {}).get("nodes") or []
    issues = nodes[0]["issues"]["nodes"] if nodes else []
    items = [{"id": i["identifier"], "source": "linear", "author": (i.get("creator") or {}).get("name", ""), "text": f"{i['title']}\n\n{i.get('description') or ''}",
              "received_at": i.get("createdAt"), "metadata": {"url": i.get("url")}} for i in issues]
    return items, cursor, f"{len(items)} issue(s)"


POLLERS = {"discord": discord, "email": email_poll, "sentry": sentry, "gdrive": gdrive, "custom": custom, "github": github, "jira": jira, "linear": linear}
