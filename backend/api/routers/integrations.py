from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..core.deps import ProjectDep, Session
from ..integrations.catalog import CATALOG, SECRET_FIELDS
from ..models import Integration, now
from ..schemas import IntegrationIn, IntegrationOut
from ..core.security import decrypt, encrypt, mask
from ..core.config import settings
from ..services import activity
from ..services.sync import schedule_first_sync
import secrets
from ..integrations import adapters as svc

router = APIRouter(prefix="/api/projects/{project_id}/integrations", tags=["integrations"])


def _masked(config: dict) -> dict:
    out = {}
    for k, v in (config or {}).items():
        if k.startswith("_"):
            out[k] = v
        elif k in SECRET_FIELDS and v:
            try:
                out[k] = mask(decrypt(str(v)[4:])) if str(v).startswith("enc:") else mask(str(v))
            except Exception:
                out[k] = "••••"
        else:
            out[k] = v
    return out


@router.get("")
async def list_integrations(project: ProjectDep, session: Session):
    rows = {r.provider: r for r in (await session.execute(select(Integration).where(Integration.project_id == project.id))).scalars()}
    out = []
    for key, c in CATALOG.items():
        r = rows.get(key)
        ib = c["inbound"]
        api_base = settings.API_PUBLIC_URL.rstrip("/") if settings.API_PUBLIC_URL else ""
        url = f"{api_base}/api/inbound/{key}/{project.id}" if r and r.inbound_token else None
        out.append({
            "inbound": {
                "mode": ib["mode"], "summary": ib["summary"], "steps": ib["steps"], "fields": list(ib["fields"]), "field_meta": ib["fields"], "events": ib["events"],
                "url": (url + ("" if key in ("slack", "github", "linear") else f"?token={r.inbound_token}")) if url else None,
                "verified": bool((r.config or {}).get("_inbound_verified")) if r else False,
                "count": r.inbound_count if r else 0, "last_sync_at": r.last_sync_at if r else None, "last_sync_result": r.last_sync_result if r else None,
                "next_sync_at": r.next_sync_at if r else None,
            },
            "provider": key, "label": c["label"], "category": c["category"], "adapter": c["status"], "functional": c["status"] == "live",
            "summary": c["summary"], "how_it_works": c["how_it_works"], "steps": c["steps"], "fields": list(c["fields"]), "field_meta": c["fields"],
            "secret_fields": [f for f in list(c["fields"]) + list(ib["fields"]) if f in SECRET_FIELDS], "permissions": c["permissions"], "test": c["test"], "events": c["events"],
            "note": c["summary"], "status": r.status if r else "not_connected", "config": _masked(r.config) if r else {}, "connected_at": r.connected_at if r else None,
        })
    return out


def _merge(existing: dict, incoming: dict) -> dict:
    merged = {k: v for k, v in (existing or {}).items() if not k.startswith("_")}
    for k, v in incoming.items():
        if k in SECRET_FIELDS:
            if not isinstance(v, str) or not v.strip() or v.startswith("••") or "…" in v:
                continue   # blank / masked echo => keep the stored secret
            merged[k] = "enc:" + encrypt(v.strip())
        else:
            merged[k] = v
    return merged


@router.put("/{provider}", response_model=IntegrationOut)
async def upsert(provider: str, body: IntegrationIn, project: ProjectDep, session: Session):
    if provider not in CATALOG:
        raise HTTPException(404, "Unknown provider")
    row = (await session.execute(select(Integration).where(Integration.project_id == project.id, Integration.provider == provider))).scalar_one_or_none()
    if row is None:
        row = Integration(project_id=project.id, provider=provider)
        session.add(row)
    row.config = _merge(row.config or {}, body.config)
    row.status = body.status
    row.connected_at = now() if body.status == "connected" else None
    if body.status == "connected":
        if not row.inbound_token:
            row.inbound_token = secrets.token_urlsafe(24)
        schedule_first_sync(row)
    else:
        row.next_sync_at = None
    await activity.log(session, project, "SYSTEM", f"integration {provider} {body.status}", ref_type="integration", ref_id=provider)
    await session.commit()
    return IntegrationOut(provider=row.provider, status=row.status, config=_masked(row.config), connected_at=row.connected_at)


@router.post("/{provider}/test")
async def test(provider: str, body: IntegrationIn, project: ProjectDep, session: Session):
    """Try the credentials as given (merged with stored secrets) without saving them."""
    if provider not in CATALOG:
        raise HTTPException(404, "Unknown provider")
    row = (await session.execute(select(Integration).where(Integration.project_id == project.id, Integration.provider == provider))).scalar_one_or_none()
    cfg = _merge(row.config if row else {}, body.config)
    missing = [f for f in CATALOG[provider]["fields"] if not cfg.get(f) and "optional" not in CATALOG[provider]["fields"][f]["label"]]
    if missing:
        return {"ok": False, "message": f"missing: {', '.join(missing)}"}
    try:
        msg = await svc.run_one(project, provider, cfg, "test", {})
        return {"ok": True, "message": msg}
    except Exception as exc:
        return {"ok": False, "message": f"{type(exc).__name__}: {str(exc)[:300]}"}
