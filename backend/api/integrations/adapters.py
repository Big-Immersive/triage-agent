"""Outbound integrations: notifications (Slack, Discord, Email, Webhooks) and
issue mirroring (GitHub, Jira, Linear). Fire-and-forget: a failing integration
is recorded (activity + integration status) and never blocks a run.

`notify(project_id, event, data)` is the only entry point; the run service
calls it on approval.requested, ticket.created and run.failed. Secrets are
stored encrypted in Integration.config and decrypted here.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import select

from ..core.config import settings
from ..core.db import SessionLocal
from .catalog import CATALOG, SECRET_FIELDS
from ..models import Integration, Project, now
from ..core.security import decrypt
from ..services import activity

log = logging.getLogger("triage.integrations")
_jobs: set[asyncio.Task] = set()


def _plain(cfg: dict) -> dict:
    out = {}
    for k, v in (cfg or {}).items():
        if k in SECRET_FIELDS and isinstance(v, str) and v.startswith("enc:"):
            try:
                v = decrypt(v[4:])
            except Exception:
                v = ""
        out[k] = v
    return out


def app_link(project: Project, path: str) -> str:
    return f"{settings.APP_URL.rstrip('/')}/projects/{project.slug}/{path}".rstrip("/")


# ------------------------------------------------------------- senders -----
async def _post_json(url: str, body: dict, headers: dict | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(url, json=body, headers=headers or {})
        r.raise_for_status()
        return r


async def slack(cfg: dict, event: str, data: dict, project: Project) -> str:
    color = {"approval.requested": "#ffb547", "ticket.created": "#00ff66", "run.failed": "#ff5c5c"}.get(event, "#8daf98")
    text = _headline(event, data, project)
    await _post_json(cfg["webhook_url"], {"text": text, "attachments": [{"color": color, "text": _details(event, data, project)}]})
    return "posted"


async def discord(cfg: dict, event: str, data: dict, project: Project) -> str:
    color = {"approval.requested": 0xFFB547, "ticket.created": 0x00FF66, "run.failed": 0xFF5C5C}.get(event, 0x8DAF98)
    await _post_json(cfg["webhook_url"], {"embeds": [{"title": _headline(event, data, project), "description": _details(event, data, project), "color": color}]})
    return "posted"


async def webhook(cfg: dict, event: str, data: dict, project: Project) -> str:
    wanted = [e.strip() for e in str(cfg.get("events") or "").split(",") if e.strip()]
    if wanted and event not in wanted and event != "test":
        return "skipped (not subscribed)"
    body = json.dumps({"event": event, "project": {"id": project.id, "slug": project.slug}, "ts": datetime.now(timezone.utc).isoformat(), "data": data}, default=str).encode()
    headers = {"Content-Type": "application/json", "X-Triage-Event": event}
    if cfg.get("secret"):
        headers["X-Triage-Signature"] = "sha256=" + hmac.new(str(cfg["secret"]).encode(), body, hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(cfg["url"], content=body, headers=headers)
        r.raise_for_status()
    return f"delivered ({r.status_code})"


def _send_mail_sync(cfg: dict, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg["from_address"], cfg["to_address"]
    msg.set_content(body)
    port = int(cfg.get("smtp_port") or 587)
    if port == 465:
        with smtplib.SMTP_SSL(cfg["smtp_host"], port, timeout=20) as s:
            s.login(cfg["username"], cfg["password"]); s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["smtp_host"], port, timeout=20) as s:
            s.starttls(); s.login(cfg["username"], cfg["password"]); s.send_message(msg)


async def email(cfg: dict, event: str, data: dict, project: Project) -> str:
    if event not in ("approval.requested", "run.failed", "test"):
        return "skipped"
    await asyncio.to_thread(_send_mail_sync, cfg, f"[triage] {_headline(event, data, project)}", _details(event, data, project))
    return f"sent to {cfg['to_address']}"


async def github(cfg: dict, event: str, data: dict, project: Project) -> str:
    if event == "test":
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://api.github.com/repos/{cfg['repository']}", headers=_gh_headers(cfg))
            r.raise_for_status()
        return f"repository ok ({r.json().get('open_issues_count', 0)} open issues)"
    if event != "ticket.created":
        return "skipped"
    t = data["ticket"]
    labels = [f"severity:{t['severity']}", f"component:{t['component']}"] + [x.strip() for x in str(cfg.get("labels") or "").split(",") if x.strip()]
    r = await _post_json(f"https://api.github.com/repos/{cfg['repository']}/issues", {"title": f"{t['id']}: {t['title']}", "body": data.get("markdown", ""), "labels": labels}, _gh_headers(cfg))
    j = r.json()
    data["external_url"] = j.get("html_url")
    return f"issue #{j.get('number')} created {j.get('html_url')}"


def _gh_headers(cfg: dict) -> dict:
    return {"Authorization": f"Bearer {cfg['token']}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


async def jira(cfg: dict, event: str, data: dict, project: Project) -> str:
    auth = (cfg["email"], cfg["api_token"])
    base = str(cfg["site_url"]).rstrip("/")
    if event == "test":
        async with httpx.AsyncClient(timeout=10, auth=auth) as c:
            r = await c.get(f"{base}/rest/api/3/project/{cfg['project_key']}")
            r.raise_for_status()
        types = [t["name"] for t in r.json().get("issueTypes", [])]
        return f"project {r.json().get('name')} ok; issue types: {', '.join(types) or '?'}"
    if event != "ticket.created":
        return "skipped"
    t = data["ticket"]
    pr = {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low"}.get(t["severity"], "Medium")
    fields: dict[str, Any] = {
        "project": {"key": cfg["project_key"]}, "summary": f"{t['id']}: {t['title']}",
        "issuetype": {"name": cfg.get("issue_type") or "Bug"},
        "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": data.get("markdown", "")[:30000]}]}]},
    }
    async with httpx.AsyncClient(timeout=15, auth=auth) as c:
        r = await c.post(f"{base}/rest/api/3/issue", json={"fields": {**fields, "priority": {"name": pr}}})
        if r.status_code == 400 and "priority" in r.text:
            r = await c.post(f"{base}/rest/api/3/issue", json={"fields": fields})
        r.raise_for_status()
    key = r.json().get("key")
    data["external_url"] = f"{base}/browse/{key}"
    return f"issue {key} created {data['external_url']}"


async def linear(cfg: dict, event: str, data: dict, project: Project) -> str:
    headers = {"Authorization": cfg["api_key"], "Content-Type": "application/json"}
    q_team = {"query": "query($k:String!){ teams(filter:{key:{eq:$k}}){ nodes { id name } } }", "variables": {"k": cfg["team_key"]}}
    r = await _post_json("https://api.linear.app/graphql", q_team, headers)
    nodes = r.json().get("data", {}).get("teams", {}).get("nodes", [])
    if not nodes:
        raise ValueError(f"team {cfg['team_key']} not found")
    if event == "test":
        return f"team {nodes[0]['name']} ok"
    if event != "ticket.created":
        return "skipped"
    t = data["ticket"]
    prio = {"critical": 1, "high": 2, "medium": 3, "low": 4}.get(t["severity"], 3)
    m = {"query": "mutation($i:IssueCreateInput!){ issueCreate(input:$i){ success issue { identifier url } } }",
         "variables": {"i": {"teamId": nodes[0]["id"], "title": f"{t['id']}: {t['title']}", "description": data.get("markdown", ""), "priority": prio}}}
    r = await _post_json("https://api.linear.app/graphql", m, headers)
    issue = r.json().get("data", {}).get("issueCreate", {}).get("issue") or {}
    data["external_url"] = issue.get("url")
    return f"issue {issue.get('identifier')} created {issue.get('url')}"


async def sentry(cfg: dict, event: str, data: dict, project: Project) -> str:
    if event != "test":
        return "skipped (adapter planned)"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"https://sentry.io/api/0/projects/{cfg['org']}/{cfg['project']}/", headers={"Authorization": f"Bearer {cfg['auth_token']}"})
        r.raise_for_status()
    return f"project {r.json().get('slug')} ok"


async def gdrive(cfg: dict, event: str, data: dict, project: Project) -> str:
    if event != "test":
        return "skipped (adapter planned)"
    json.loads(cfg["service_account_json"])   # at least valid JSON
    return "key parsed; folder listing requires the Drive adapter (planned)"


async def custom(cfg: dict, event: str, data: dict, project: Project) -> str:
    if event != "test":
        return "skipped (adapter planned)"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(cfg["base_url"], headers={"Authorization": cfg.get("auth_header", "")})
    if r.status_code >= 500:
        raise ValueError(f"HTTP {r.status_code}")
    return f"reachable (HTTP {r.status_code})"


SENDERS = {"slack": slack, "discord": discord, "webhook": webhook, "email": email, "github": github, "jira": jira, "linear": linear, "sentry": sentry, "gdrive": gdrive, "custom": custom}


# ------------------------------------------------------------- copy --------
def _headline(event: str, data: dict, project: Project) -> str:
    if event == "approval.requested":
        return f"approval needed: {data.get('id')} ({project.slug})"
    if event == "ticket.created":
        t = data.get("ticket", {})
        return f"ticket {t.get('id')} created ({t.get('severity')}, {t.get('component')}) in {project.slug}"
    if event == "run.failed":
        return f"run failed: {data.get('run_id')} ({project.slug})"
    if event == "test":
        return f"triage connected to {project.slug}"
    return f"{event} in {project.slug}"


def _details(event: str, data: dict, project: Project) -> str:
    if event == "approval.requested":
        return (f"agent: {data.get('agent_name')}\naction: {data.get('action')}\nreason: {data.get('reason')}\n"
                f"confidence: {data.get('confidence')}\nrun: {data.get('run_id')}\n→ {app_link(project, 'approvals')}")
    if event == "ticket.created":
        t = data.get("ticket", {})
        return f"{t.get('title')}\nseverity {t.get('severity')} · component {t.get('component')} · owner {t.get('owner')}\n→ {app_link(project, 'files')}"
    if event == "run.failed":
        return f"{data.get('error')}\n→ {app_link(project, 'runs/' + str(data.get('run_id')))}"
    if event == "test":
        return "This is a test message from the triage dashboard. If you can read it, the integration works."
    return json.dumps(data, default=str)[:1500]


# ------------------------------------------------------------- dispatch ----
async def run_one(project: Project, provider: str, cfg: dict, event: str, data: dict) -> str:
    fn = SENDERS[provider]
    return await fn(_plain(cfg), event, data, project)


def notify(project_id: str, event: str, data: dict) -> None:
    """Schedule delivery to every connected integration that handles `event`."""
    t = asyncio.create_task(_deliver(project_id, event, data))
    _jobs.add(t)
    t.add_done_callback(_jobs.discard)


async def _deliver(project_id: str, event: str, data: dict) -> None:
    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
        if project is None:
            return
        rows = (await session.execute(select(Integration).where(Integration.project_id == project_id, Integration.status.in_(("connected", "error"))))).scalars().all()
        for row in rows:
            handled = CATALOG.get(row.provider, {}).get("events", [])
            if not handled or (event not in handled and "*" not in handled):
                continue
            try:
                result = await run_one(project, row.provider, row.config or {}, event, data)
                if event == "ticket.created" and data.get("external_url"):
                    await _link_ticket(session, project, data["ticket"]["id"], row.provider, data.pop("external_url"))
                if row.status == "error":
                    row.status = "connected"
                if not result.startswith("skipped"):
                    await activity.log(session, project, "SYSTEM", f"{row.provider.upper()} {result[:160]}", ref_type="integration", ref_id=row.provider)
            except Exception as exc:
                msg = f"{type(exc).__name__}: {str(exc)[:200]}"
                row.status = "error"
                row.config = {**(row.config or {}), "_last_error": msg, "_last_error_at": now().isoformat()}
                await activity.log(session, project, "SYSTEM", f"{row.provider.upper()} delivery failed: {msg}", ref_type="integration", ref_id=row.provider)
                log.warning("integration %s failed: %s", row.provider, msg)
        await session.commit()


async def _link_ticket(session, project: Project, ticket_id: str, provider: str, url: str) -> None:
    """Record the mirrored issue's URL inside the ticket artifact so the tickets page can link to it."""
    from ..models import File
    from ..services import storage

    row = (await session.execute(select(File).where(File.project_id == project.id, File.path == f"/out/tickets/{ticket_id}.json"))).scalar_one_or_none()
    if row is None:
        return
    try:
        data = json.loads((await storage.read_bytes(row)).decode("utf-8"))
    except Exception:
        return
    data.setdefault("external_links", {})[provider] = url
    await storage.write_file(session, project, row.path, json.dumps(data, indent=2, ensure_ascii=False).encode(), "application/json")
