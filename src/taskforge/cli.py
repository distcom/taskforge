"""TaskForge CLI — command-line interface for the orchestration engine.

Commands:
  run       Start or resume a task pipeline
  status    Show pipeline status for a session
  sessions  List all stored sessions
  verify    Run delivery acceptance checks
  plugins   Discover available local plugins
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .engine import PipelineEngine
from .models import (
    CheckVerdict,
    Criterion,
    ExecutionMode,
    TaskSession,
    UnitStatus,
    VerifyMethod,
    WorkSegment,
)
from .plugins import PluginIndex, assign_plugins, resolve_plugin_roots, scan_plugins
from .runner import Runner
from .strategy import build_plan, extract_intent, seal_requirement, suggest_mode
from .vault import SessionVault
from .verify import Verifier, format_report


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="taskforge", description="TaskForge — AI agent task orchestration engine.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root (default: cwd).")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Start or resume a task pipeline.")
    r.add_argument("--prompt", required=True, help="Task description.")
    r.add_argument("--session", help="Resume existing session by ID.")
    r.add_argument("--mode", choices=["sequential", "parallel"], help="Override execution mode.")
    r.add_argument("--json", action="store_true")
    r.set_defaults(fn=_cmd_run)

    s = sub.add_parser("status", help="Show session status.")
    s.add_argument("--session", required=True)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_status)

    ls = sub.add_parser("sessions", help="List stored sessions.")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(fn=_cmd_sessions)

    v = sub.add_parser("verify", help="Run delivery acceptance checks.")
    v.add_argument("--session", required=True)
    v.add_argument("--json", action="store_true")
    v.set_defaults(fn=_cmd_verify)

    d = sub.add_parser("plugins", help="Discover local plugins.")
    d.add_argument("--json", action="store_true")
    d.set_defaults(fn=_cmd_plugins)

    return p


# ─── Commands ──────────────────────────────────────────────────────────────────


def _cmd_run(a: argparse.Namespace) -> int:
    vault = SessionVault(a.workspace)
    session = vault.load(a.session) if a.session else TaskSession()
    if a.session and session is None:
        _err(f"Session '{a.session}' not found.")
        return 1

    engine = PipelineEngine(session)
    mode = ExecutionMode(a.mode) if a.mode else suggest_mode(a.prompt)
    session.mode = mode

    if session.intent is None:
        session.intent = extract_intent(a.prompt, mode=mode)

    roots = resolve_plugin_roots(a.workspace)
    plugins = scan_plugins(roots)
    index = PluginIndex(plugins)

    segments = [WorkSegment(
        segment_id="seg-primary",
        objective=a.prompt,
        criteria=[Criterion(cid="primary-ok", description="Deliverables meet the sealed requirement.")],
    )]
    bindings = assign_plugins(index, segments)

    if session.requirement is None:
        session.requirement = seal_requirement(session.intent)
    if session.plan is None:
        session.plan = build_plan(session.requirement, segments, bindings)
        session.plan.seal()

    vault.save(session)
    snap = engine.snapshot()
    snap["plugins_found"] = index.count
    snap["plugins_bound"] = len(bindings)

    if a.json:
        _json(snap)
    else:
        print(f"Session: {session.session_id}")
        print(f"  Stage:   {session.stage.value}")
        print(f"  Mode:    {mode.value}")
        print(f"  Plugins: {index.count} found, {len(bindings)} bound")
        print(f"  Token:   {session.gate_token}")
    return 0


def _cmd_status(a: argparse.Namespace) -> int:
    vault = SessionVault(a.workspace)
    session = vault.load(a.session)
    if session is None:
        _err(f"Session '{a.session}' not found.")
        return 1
    snap = PipelineEngine(session).snapshot()
    if a.json:
        _json(snap)
    else:
        print(f"Session: {session.session_id}")
        print(f"  Stage:    {snap['stage']}")
        print(f"  Mode:     {snap['mode']}")
        print(f"  Segments: {snap['segments_done']}/{snap['segments_total']} done")
        print(f"  Finished: {snap['finished']}")
    return 0


def _cmd_sessions(a: argparse.Namespace) -> int:
    vault = SessionVault(a.workspace)
    items = vault.list_all()
    if a.json:
        _json(items)
    else:
        if not items:
            print("No sessions.")
        else:
            print(f"{'Session ID':<28} {'Stage':<12} {'Mode':<12} {'Touched'}")
            print("-" * 76)
            for i in items:
                print(f"{i.get('session_id','?'):<28} {i.get('stage','?'):<12} {i.get('mode','?'):<12} {i.get('touched_at','')}")
    return 0


def _cmd_verify(a: argparse.Namespace) -> int:
    vault = SessionVault(a.workspace)
    session = vault.load(a.session)
    if session is None:
        _err(f"Session '{a.session}' not found.")
        return 1
    report = Verifier(session).run()
    vault.save(session)
    if a.json:
        _json({"session_id": report.session_id, "accepted": report.accepted,
               "passed": sum(1 for e in report.entries if e.passed), "total": len(report.entries)})
    else:
        print(format_report(report))
    return 0 if report.accepted else 1


def _cmd_plugins(a: argparse.Namespace) -> int:
    roots = resolve_plugin_roots(a.workspace)
    plugins = scan_plugins(roots)
    if a.json:
        _json([{"plugin_id": p.plugin_id, "name": p.display_name, "summary": p.summary, "path": p.manifest_path} for p in plugins])
    else:
        if not roots:
            print("No plugin roots configured.")
            print(f"  Global:    ~/.taskforge/roots.json")
            print(f"  Workspace: {a.workspace}/.taskforge/roots.json")
        elif not plugins:
            print(f"Searched {len(roots)} root(s), found 0 plugins.")
        else:
            print(f"Found {len(plugins)} plugin(s) from {len(roots)} root(s):\n")
            for p in plugins:
                print(f"  {p.display_name}")
                if p.summary:
                    print(f"    {p.summary[:100]}")
                print()
    return 0


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _err(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


def _json(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        _err(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
