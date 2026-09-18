"""Inbound (push) integrations: external systems call
POST /api/inbound/{provider}/{project_id}; we verify the request the way that
provider signs it, normalize the payload into intake items, and hand them to
the task service. Each provider has: verify(request, cfg) and parse(payload, cfg).

Providers without request signing (Jira Cloud) are protected by the
integration's inbound token passed as ?token=.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request


class InboundError(HTTPException):
    def __init__(self, msg: str, status: int = 401):
        super().__init__(status, msg)


def _hmac_ok(secret: str, msg: bytes, expected: str) -> bool:
    return bool(secret) and hmac.compare_digest(hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest(), expected.strip().lower())


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()


# ------------------------------------------------------------------ slack ----
async def slack_verify(request: Request, body: bytes, cfg: dict, token_ok: bool) -> None:
    ts = request.headers.get("x-slack-request-timestamp", "")
    sig = request.headers.get("x-slack-signature", "")
    if not ts or not sig or abs(time.time() - float(ts or 0)) > 300:
        raise InboundError("slack: missing or stale signature")
    base = f"v0:{ts}:".encode() + body
    if not hmac.compare_digest("v0=" + hmac.new(str(cfg.get("signing_secret", "")).encode(), base, hashlib.sha256).hexdigest(), sig):
        raise InboundError("slack: bad signature")


def slack_parse(payload: dict, cfg: dict) -> tuple[list[dict], Any]:
    """Returns (items, immediate_response). Handles url_verification and message events."""
    if payload.get("type") == "url_verification":
        return [], {"challenge": payload.get("challenge")}
    ev = payload.get("event") or {}
    if payload.get("type") != "event_callback" or ev.get("type") != "message":
        return [], {"ok": True}
    if ev.get("bot_id") or ev.get("subtype") in ("bot_message", "message_changed", "message_deleted", "channel_join"):
        return [], {"ok": True}
    want = str(cfg.get("intake_channel") or "").strip()
    if want and ev.get("channel") != want and ev.get("channel_name") != want.lstrip("#"):
        return [], {"ok": True}
    if ev.get("thread_ts") and ev.get("thread_ts") != ev.get("ts") and not cfg.get("include_threads"):
        return [], {"ok": True}
    ts = str(ev.get("ts", "")).replace(".", "")
    meta = {"channel": ev.get("channel"), "ts": ev.get("ts"), "team": payload.get("team_id")}
    if cfg.get("workspace_domain"):
        meta["permalink"] = f"https://{cfg['workspace_domain']}.slack.com/archives/{ev.get('channel')}/p{ts}"
    return [{"id": f"SL-{ts[-10:]}", "source": "slack", "author": ev.get("user", ""), "text": ev.get("text", ""),
             "received_at": datetime.fromtimestamp(float(ev.get("ts", time.time())), tz=timezone.utc).isoformat(), "metadata": meta}], {"ok": True}


# ----------------------------------------------------------------- github ----
async def github_verify(request: Request, body: bytes, cfg: dict, token_ok: bool) -> None:
    sig = request.headers.get("x-hub-signature-256", "")
    if not sig.startswith("sha256=") or not _hmac_ok(str(cfg.get("webhook_secret", "")), body, sig[7:]):
        raise InboundError("github: bad signature")


def github_parse(payload: dict, cfg: dict) -> tuple[list[dict], Any]:
    action = payload.get("action")
    issue = payload.get("issue")
    if not issue or action not in ("opened", "reopened"):
        if payload.get("comment") and action == "created" and issue and cfg.get("include_comments"):
            c = payload["comment"]
            return [{"id": f"GH-{issue['number']}-C{c['id']}", "source": "github", "author": c.get("user", {}).get("login", ""),
                     "text": f"Comment on #{issue['number']} {issue.get('title', '')}:\n{c.get('body', '')}", "received_at": c.get("created_at"),
                     "metadata": {"url": c.get("html_url"), "issue": issue["number"]}}], {"ok": True}
        return [], {"ok": True}
    labels = [l.get("name") for l in issue.get("labels", [])]
    want = [x.strip() for x in str(cfg.get("intake_label") or "").split(",") if x.strip()]
    if want and not (set(want) & set(labels)):
        return [], {"ok": True}
    return [{"id": f"GH-{issue['number']}", "source": "github", "author": issue.get("user", {}).get("login", ""),
             "text": f"{issue.get('title', '')}\n\n{issue.get('body') or ''}", "received_at": issue.get("created_at"),
             "metadata": {"url": issue.get("html_url"), "labels": labels, "repository": payload.get("repository", {}).get("full_name")}}], {"ok": True}


# ------------------------------------------------------------------- jira ----
async def jira_verify(request: Request, body: bytes, cfg: dict, token_ok: bool) -> None:
    if not token_ok:   # Jira Cloud webhooks carry no signature: the URL includes ?token=
        raise InboundError("jira: missing or bad token")


def jira_parse(payload: dict, cfg: dict) -> tuple[list[dict], Any]:
    if payload.get("webhookEvent") not in ("jira:issue_created",):
        return [], {"ok": True}
    issue = payload.get("issue") or {}
    f = issue.get("fields") or {}
    want = str(cfg.get("intake_issue_type") or "").strip().lower()
    if want and str((f.get("issuetype") or {}).get("name", "")).lower() != want:
        return [], {"ok": True}
    desc = f.get("description")
    if isinstance(desc, dict):   # ADF
        desc = " ".join(_adf_text(desc))
    site = str(cfg.get("site_url") or "").rstrip("/")
    return [{"id": issue.get("key", ""), "source": "jira", "author": (f.get("reporter") or {}).get("displayName", ""),
             "text": f"{f.get('summary', '')}\n\n{desc or ''}", "received_at": f.get("created"),
             "metadata": {"url": f"{site}/browse/{issue.get('key')}" if site else None, "priority": (f.get("priority") or {}).get("name")}}], {"ok": True}


def _adf_text(node: dict) -> list[str]:
    out = []
    if node.get("type") == "text":
        out.append(node.get("text", ""))
    for c in node.get("content", []) or []:
        out += _adf_text(c)
    return out


# ----------------------------------------------------------------- linear ----
async def linear_verify(request: Request, body: bytes, cfg: dict, token_ok: bool) -> None:
    if not _hmac_ok(str(cfg.get("webhook_secret", "")), body, request.headers.get("linear-signature", "")):
        raise InboundError("linear: bad signature")


def linear_parse(payload: dict, cfg: dict) -> tuple[list[dict], Any]:
    if payload.get("type") != "Issue" or payload.get("action") != "create":
        return [], {"ok": True}
    d = payload.get("data") or {}
    return [{"id": d.get("identifier", ""), "source": "linear", "author": (d.get("creator") or {}).get("name", "") if isinstance(d.get("creator"), dict) else "",
             "text": f"{d.get('title', '')}\n\n{d.get('description') or ''}", "received_at": d.get("createdAt"),
             "metadata": {"url": d.get("url"), "team": (d.get("team") or {}).get("key")}}], {"ok": True}


# ----------------------------------------------------------------- sentry ----
async def sentry_verify(request: Request, body: bytes, cfg: dict, token_ok: bool) -> None:
    sig = request.headers.get("sentry-hook-signature", "")
    if sig:
        if not _hmac_ok(str(cfg.get("client_secret", "")), body, sig):
            raise InboundError("sentry: bad signature")
    elif not token_ok:
        raise InboundError("sentry: missing signature or token")


def sentry_parse(payload: dict, cfg: dict) -> tuple[list[dict], Any]:
    data = payload.get("data") or payload
    issue = data.get("issue") or data.get("event") or {}
    if not issue:
        return [], {"ok": True}
    title = issue.get("title") or issue.get("message") or "Sentry issue"
    culprit = issue.get("culprit") or ""
    count = issue.get("count") or issue.get("userCount")
    tags = {t[0]: t[1] for t in issue.get("tags", []) if isinstance(t, list) and len(t) == 2}
    meta = {"url": issue.get("permalink") or issue.get("web_url"), "count": count, "level": issue.get("level"), **{k: tags[k] for k in ("release", "device", "os") if k in tags}}
    if tags.get("release"):
        meta["app_version"] = tags["release"]
    return [{"id": f"SEN-{issue.get('id') or issue.get('shortId') or int(time.time())}", "source": "sentry", "author": "sentry",
             "text": f"{title}\n{culprit}\nevents: {count}", "received_at": issue.get("firstSeen") or issue.get("datetime"), "metadata": meta}], {"ok": True}


# ------------------------------------------------------------------ email ----
async def email_verify(request: Request, body: bytes, cfg: dict, token_ok: bool) -> None:
    if not token_ok:   # Postmark / SendGrid / Mailgun inbound: protect the URL with the token
        raise InboundError("email: missing or bad token")


def email_parse(payload: dict, cfg: dict) -> tuple[list[dict], Any]:
    # Postmark JSON (From, Subject, TextBody, HtmlBody, MessageID), SendGrid inbound parse (from, subject, text, html), Mailgun (sender, subject, body-plain)
    sender = payload.get("From") or payload.get("from") or payload.get("sender") or ""
    subject = payload.get("Subject") or payload.get("subject") or ""
    text = payload.get("TextBody") or payload.get("text") or payload.get("body-plain") or payload.get("stripped-text") or ""
    if not text and (payload.get("HtmlBody") or payload.get("html")):
        text = _strip_html(payload.get("HtmlBody") or payload.get("html"))
    mid = payload.get("MessageID") or payload.get("Message-Id") or payload.get("message-id") or hashlib.sha1(f"{sender}{subject}{text[:200]}".encode()).hexdigest()[:10]
    return [{"id": f"EM-{re.sub(r'[^A-Za-z0-9]', '', str(mid))[-12:].upper()}", "source": "email", "author": sender,
             "text": f"{subject}\n\n{text}".strip(), "received_at": payload.get("Date") or payload.get("date"), "metadata": {"subject": subject}}], {"ok": True}


# ---------------------------------------------------------------- discord ----
async def discord_verify(request: Request, body: bytes, cfg: dict, token_ok: bool) -> None:
    if not token_ok:   # Discord channels are polled; this push path is for relay bots / automations
        raise InboundError("discord: missing or bad token")


def discord_parse(payload: dict, cfg: dict) -> tuple[list[dict], Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else [payload]
    out = []
    for m in items:
        text = m.get("content") or m.get("text") or ""
        if not text:
            continue
        author = m.get("author") if isinstance(m.get("author"), str) else (m.get("author") or {}).get("username", "")
        out.append({"id": f"DC-{m.get('id', hashlib.sha1(text.encode()).hexdigest()[:10])}", "source": "discord", "author": author, "text": text,
                    "received_at": m.get("timestamp"), "metadata": {"channel": m.get("channel_id")}})
    return out, {"ok": True}


# ---------------------------------------------------------- generic / custom ----
async def webhook_verify(request: Request, body: bytes, cfg: dict, token_ok: bool) -> None:
    sig = request.headers.get("x-triage-signature", "")
    secret = str(cfg.get("inbound_secret") or cfg.get("secret") or "")
    if sig.startswith("sha256=") and secret:
        if not _hmac_ok(secret, body, sig[7:]):
            raise InboundError("webhook: bad signature")
    elif not token_ok:
        raise InboundError("webhook: missing signature or token")


def webhook_parse(payload: dict, cfg: dict) -> tuple[list[dict], Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else [payload]
    return [i for i in items if isinstance(i, dict)], {"ok": True}


PUSH = {
    "slack": (slack_verify, slack_parse),
    "github": (github_verify, github_parse),
    "jira": (jira_verify, jira_parse),
    "linear": (linear_verify, linear_parse),
    "sentry": (sentry_verify, sentry_parse),
    "email": (email_verify, email_parse),
    "discord": (discord_verify, discord_parse),
    "webhook": (webhook_verify, webhook_parse),
    "custom": (webhook_verify, webhook_parse),
}


async def handle(provider: str, request: Request, body: bytes, cfg: dict, token_ok: bool) -> tuple[list[dict], Any]:
    if provider not in PUSH:
        raise InboundError(f"{provider}: no inbound push support", 404)
    verify, parse = PUSH[provider]
    await verify(request, body, cfg, token_ok)
    ctype = request.headers.get("content-type", "")
    if "json" in ctype or body.lstrip().startswith(b"{"):
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            raise InboundError("invalid JSON", 400)
    else:
        form = await request.form()
        payload = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
        if provider == "slack" and "payload" in payload:   # interactive payloads
            payload = json.loads(payload["payload"])
    return parse(payload, cfg)
