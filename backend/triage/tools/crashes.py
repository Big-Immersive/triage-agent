"""Crash-log tool: aggregate the project's crash telemetry (stand-in for Crashlytics/Sentry)."""


from collections import Counter, defaultdict

from workflows import Context

from .. import runtime
from ..state import get_state


def aggregate(rows: list[dict], keyword: str = "", app_version: str = "") -> str:
    """Pure aggregation over crash rows; `query_crashes` is the tool wrapper."""
    kw = keyword.strip().lower()
    ver = app_version.strip()
    rows = [
        r for r in rows
        if (not kw or kw in r["signature"].lower() or kw in r["stack_top"].lower())
        and (not ver or r["app_version"] == ver)
    ]
    if not rows:
        return f"No crashes match keyword={keyword!r} version={app_version!r}."

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["signature"]].append(r)

    out = [f"{len(rows)} crash events in {len(groups)} signature(s):"]
    for sig, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        versions = Counter(r["app_version"] for r in rs)
        devices = Counter(r["device"] for r in rs)
        platforms = Counter("iOS" if r["os"].startswith("iOS") else "Android" for r in rs)
        first = min(r["timestamp"] for r in rs)[:10]
        last = max(r["timestamp"] for r in rs)[:10]
        out.append(
            f"- signature={sig} events={len(rs)} users={len({r['user_id'] for r in rs})} "
            f"versions={dict(versions)} platforms={dict(platforms)} first_seen={first} last_seen={last}\n"
            f"    top devices: {', '.join(f'{d} ({n})' for d, n in devices.most_common(3))}\n"
            f"    stack: {rs[0]['stack_top']}"
        )
    return "\n".join(out)


async def query_crashes(ctx: Context, keyword: str = "", app_version: str = "") -> str:
    """Search the crash log and group results by crash signature.

    Use this to confirm a reported crash actually appears in telemetry and how
    widespread it is. Search by a keyword from the symptom (e.g. "shop",
    "signin", "cloudsave", "billing") and/or an app version (e.g. "2.4.1").
    Leave keyword empty to see the top signatures for a version.

    Args:
        keyword: matched case-insensitively against the crash signature and stack trace.
        app_version: exact version filter, e.g. "2.4.1". Empty = all versions.
    """
    rt = runtime.for_state(await get_state(ctx))
    if not rt.crash_rows:
        return "No crash log is connected to this project."
    return aggregate(rt.crash_rows, keyword, app_version)
