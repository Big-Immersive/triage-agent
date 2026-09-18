"""Triage agent tools: ownership, release context, and the triage record."""


from pydantic import ValidationError
from workflows import Context

from .. import runtime
from ..schemas import Triage
from ..state import get_state, update_state
from .coerce import StrList, as_list


async def list_components(ctx: Context) -> str:
    """List the valid component names and the team that owns each one."""
    rt = runtime.for_state(await get_state(ctx))
    if not rt.owners:
        return "No component ownership table is connected to this project; use component='general'."
    return "\n".join(f"- {c}: {team} ({chan})" for c, (team, chan) in rt.owners.items())


async def lookup_owner(ctx: Context, component: str) -> str:
    """Return the owning team for a component (see list_components for valid names)."""
    rt = runtime.for_state(await get_state(ctx))
    c = component.strip().lower()
    if c in rt.owners:
        team, chan = rt.owners[c]
        return f"component={c} owner={team} channel={chan}"
    return f"Unknown component '{component}'. Valid: {', '.join(rt.owners)}"


async def release_info(ctx: Context) -> str:
    """Current app version, recent releases, share of users on each version, and the next release date.

    Use this to judge impact (is the affected version current? how many users are on it?)
    and urgency (how close is the next code freeze?).
    """
    rt = runtime.for_state(await get_state(ctx))
    r = rt.releases
    if not r:
        return "No release information is connected to this project."
    lines = [f"Product: {r.get('product', '?')} ({r.get('company', '?')}). Current version: {r.get('current_version', '?')}."]
    lines += [f"- {x['version']} released {x['date']}: {x['notes']}" for x in r.get("releases", [])]
    if r.get("active_users_by_version"):
        lines.append(f"Users by version (%): {r['active_users_by_version']}")
    nr = r.get("next_release")
    if nr:
        lines.append(f"Next release {nr['version']}: code freeze {nr['code_freeze']}, ship {nr['date']}.")
    return "\n".join(lines)


async def record_triage(
    ctx: Context,
    severity: str,
    component: str,
    rationale: str,
    affected_versions: StrList = None,
) -> str:
    """Record severity, component and owner for a NEW bug. Call exactly once.

    Severity guide:
      critical = data loss, security, or money taken wrongly, affecting many users
      high     = crash or data/money problem for a core flow (login, purchase, save), or any billing issue
      medium   = feature broken but there is a workaround / limited users
      low      = cosmetic, minor annoyance, or only on old versions

    Args:
        severity: low, medium, high, or critical.
        component: one of the names from list_components (e.g. shop, billing, cloudsave, auth).
        rationale: 1-2 sentences citing crash counts / user share / flow affected.
        affected_versions: e.g. ["2.4.1"].
    """
    rt = runtime.for_state(await get_state(ctx))
    c = component.strip().lower()
    if rt.owners and c not in rt.owners:
        return f"Unknown component '{component}'. Choose one of: {', '.join(rt.owners)} and call again."
    owner = rt.owners[c][0] if c in rt.owners else "unassigned"
    try:
        tri = Triage(
            severity=severity, component=c, owner=owner,
            rationale=rationale, affected_versions=as_list(affected_versions),
        )
    except ValidationError as exc:
        return f"Invalid triage, fix and call again: {exc.errors()[0]['msg']} (field: {exc.errors()[0]['loc']})"

    await update_state(ctx, triage=tri.model_dump())
    return (
        f"Recorded triage: {tri.model_dump_json()}\n"
        "NOW call handoff(to_agent='writer', reason='triaged: create the ticket')."
    )
