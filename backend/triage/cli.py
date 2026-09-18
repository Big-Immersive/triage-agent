"""`triage` command-line entry point.

    triage inbox                      list the raw feedback items
    triage run [IDS...] [-v] [--auto-approve]
                                      run the agents on the inbox (or specific ids)
    triage eval                       run everything with auto-approve and score against eval/expected.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import settings

console = Console()
SEV_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _fmt_kwargs(kwargs: dict) -> str:
    parts = []
    for k, v in kwargs.items():
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        parts.append(f"{k}={s[:80]}{'…' if len(s) > 80 else ''}")
    return ", ".join(parts)


def _make_on_event(verbose: bool):
    def on_event(kind: str, payload) -> None:
        if kind == "agent":
            console.print(f"\n  [bold magenta]▶ {payload}[/]")
        elif kind == "tool_call":
            console.print(f"    [yellow]⚙ {payload.tool_name}[/]({_fmt_kwargs(payload.tool_kwargs)})")
        elif kind == "tool_result":
            out = str(payload.tool_output).strip().replace("\n", "\n        ")
            if getattr(payload.tool_output, "is_error", False):
                console.print(f"        [red]↳ {out[:300]}[/]")
            elif verbose:
                console.print(f"        [dim]↳ {out[:900]}{'…' if len(out) > 900 else ''}[/]")
        elif kind == "final" and payload:
            console.print(f"    [green]💬 {payload[:300]}[/]")
        elif kind == "error":
            console.print(f"    [red]✖ {payload}[/]")
    return on_event


def _ask_human(prompt: str) -> str:
    console.print()
    console.print(Panel(prompt, title="human gate", border_style="red"))
    try:
        return console.input("[bold red]reviewer ›[/] ").strip() or "y"
    except (EOFError, KeyboardInterrupt):
        return "n"


def _auto_human(prompt: str) -> str:
    console.print(f"    [red]⏸ human gate[/] [dim](auto-approved)[/]")
    return "y"


def _build_runner(auto_approve: bool, verbose: bool):
    """CLI runtime: the demo dataset from fixtures/, artifacts to out/, no database."""
    from llama_index.core import Settings

    from . import runtime
    from .agents import build_workflow
    from .runner import Runner

    settings.configure()
    rt = runtime.register(runtime.ProjectRuntime.from_fixtures("cli", settings.FIXTURES_DIR, Settings.embed_model, out_dir=settings.OUT_DIR))
    return Runner(
        build_workflow(), rt, auto_approve=auto_approve,
        on_event=_make_on_event(verbose), ask_human=_auto_human if auto_approve else _ask_human,
    )


def cmd_inbox(_: argparse.Namespace) -> None:
    from .runner import load_inbox

    table = Table(title="inbox", expand=True)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("source", no_wrap=True)
    table.add_column("version", no_wrap=True)
    table.add_column("text", style="dim")
    for fb in load_inbox():
        table.add_row(fb.id, fb.source, fb.metadata.get("app_version") or "-", fb.text[:90].replace("\n", " ") + ("…" if len(fb.text) > 90 else ""))
    console.print(table)


async def _run(ids: list[str], auto_approve: bool, verbose: bool) -> list:
    from .runner import load_inbox

    items = load_inbox(ids or None)
    if not items:
        raise SystemExit("No matching inbox items.")
    with console.status(f"loading {settings.LLM_MODEL} + indexes…"):
        runner = _build_runner(auto_approve, verbose)

    results = []
    for i, fb in enumerate(items, 1):
        console.rule(f"[bold]{fb.id}[/] ({i}/{len(items)}) · {fb.source}")
        console.print(f"[dim]{fb.text[:200].replace(chr(10), ' ')}{'…' if len(fb.text) > 200 else ''}[/]")
        result, log = await runner.run_one(fb)
        results.append((result, log))
        colour = {"new_ticket": "green", "duplicate": "blue", "needs_info": "yellow", "dropped": "dim", "unresolved": "red"}[result.outcome]
        extra = result.ticket_id or result.duplicate_of or ""
        console.print(
            f"\n  [{colour}]● {result.outcome}[/] {extra} "
            f"[dim]category={result.category} severity={result.severity or '-'} "
            f"agents={'→'.join(log.agents_visited)} tools={len(log.tool_calls)} {log.seconds:.0f}s[/]"
        )
        if result.artifact:
            console.print(f"  [dim]→ {result.artifact}[/]")
    return results


def cmd_run(args: argparse.Namespace) -> None:
    results = asyncio.run(_run(args.ids, args.auto_approve, args.verbose))
    _summary(results)


def _summary(results: list) -> None:
    table = Table(title="batch summary", expand=True)
    for col in ("id", "category", "outcome", "ref", "severity", "agents", "time"):
        table.add_column(col, no_wrap=True)
    for r, log in results:
        table.add_row(r.feedback_id, r.category, r.outcome, r.ticket_id or r.duplicate_of or "-", r.severity or "-", "→".join(log.agents_visited), f"{log.seconds:.0f}s" + (" ✖" if log.error else ""))
    console.print()
    console.print(table)
    settings.OUT_DIR.mkdir(exist_ok=True)
    (settings.OUT_DIR / "results.json").write_text(json.dumps([r.model_dump() for r, _ in results], indent=2))


def cmd_eval(args: argparse.Namespace) -> None:
    expected = json.loads(settings.EVAL_FILE.read_text())
    results = asyncio.run(_run(list(expected), auto_approve=True, verbose=args.verbose))
    by_id = {r.feedback_id: r for r, _ in results}

    table = Table(title="eval", expand=True)
    for col in ("id", "category", "outcome", "duplicate_of", "component", "severity", "pass"):
        table.add_column(col, no_wrap=True)
    passed = 0
    for fid, exp in expected.items():
        r = by_id.get(fid)
        checks = []
        checks.append(("category", r.category == exp["category"]))
        checks.append(("outcome", r.outcome == exp["outcome"]))
        dup_ok = None
        if exp.get("duplicate_of"):
            want = exp["duplicate_of"]
            if want.startswith("batch:"):
                want = by_id[want.split(":")[1]].ticket_id
            dup_ok = r.duplicate_of == want and want is not None
            checks.append(("duplicate_of", dup_ok))
        comp_ok = None
        if exp.get("component"):
            comp_ok = r.component == exp["component"]
            checks.append(("component", comp_ok))
        sev_ok = None
        if exp.get("min_severity"):
            sev_ok = r.severity is not None and SEV_ORDER[r.severity] >= SEV_ORDER[exp["min_severity"]]
            checks.append(("min_severity", sev_ok))
        ok = all(v for _, v in checks)
        passed += ok

        def mark(v):
            return "-" if v is None else ("[green]✓[/]" if v else "[red]✗[/]")

        table.add_row(
            fid,
            f"{r.category} {mark(checks[0][1])}",
            f"{r.outcome} {mark(checks[1][1])}",
            f"{r.duplicate_of or '-'} {mark(dup_ok)}",
            f"{r.component or '-'} {mark(comp_ok)}",
            f"{r.severity or '-'} {mark(sev_ok)}",
            "[green]PASS[/]" if ok else "[red]FAIL[/]",
        )
    console.print()
    console.print(table)
    console.print(f"\n[bold]{passed}/{len(expected)} items fully correct[/] with {settings.LLM_MODEL}")
    _summary(results)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="triage", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inbox", help="list raw feedback items").set_defaults(func=cmd_inbox)

    p_run = sub.add_parser("run", help="run the agents over the inbox")
    p_run.add_argument("ids", nargs="*", help="feedback ids to process (default: all)")
    p_run.add_argument("--auto-approve", action="store_true", help="skip the human gate")
    p_run.add_argument("-v", "--verbose", action="store_true", help="show tool outputs")
    p_run.set_defaults(func=cmd_run)

    p_eval = sub.add_parser("eval", help="run all items (auto-approve) and score against eval/expected.json")
    p_eval.add_argument("-v", "--verbose", action="store_true")
    p_eval.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
