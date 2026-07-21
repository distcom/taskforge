"""TaskForge Canonical Entrypoint — the comprehensive governed runtime.

This module is the single authoritative entry point for launching and resuming
governed TaskForge sessions. It orchestrates the full 6-stage pipeline lifecycle:

    validate → clarify → freeze → strategize → execute → finalize

It provides:
- Canonical launch with proof-artifact generation
- Progressive approval gates with re-entry token support
- Plugin organization freezing and segment assignment
- Execution handoff compilation
- Delivery verification and cleanup receipt generation
- Session lineage and governance capsule emission

Usage (CLI):
    python -m taskforge.entrypoint canonical-entry \\
        --skill-root <path> --workspace <path> --prompt "<task>"

Usage (programmatic):
    from taskforge.entrypoint import CanonicalRuntime
    rt = CanonicalRuntime(skill_root=Path("."), workspace=Path("."))
    result = rt.launch("Build a REST API")
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .engine import GateHeld, PipelineEngine, PipelineViolation
from .models import (
    CheckVerdict,
    Criterion,
    DeliveryReport,
    ExecUnit,
    ExecutionMode,
    ExecutionPlan,
    FrozenRequirement,
    PipelineStage,
    PluginBinding,
    PluginInfo,
    SegmentOutcome,
    StageHop,
    TaskIntent,
    TaskSession,
    UnitOutcome,
    UnitStatus,
    VerifyMethod,
    WorkSegment,
)
from .plugins import PluginIndex, assign_plugins, resolve_plugin_roots, scan_plugins
from .runner import Runner
from .shell import CommandResult, ShellExecutor
from .strategy import build_plan, compile_handoff, extract_intent, seal_requirement, suggest_mode
from .vault import SessionVault
from .verify import Verifier, format_report


# ─── Governance Artifacts ──────────────────────────────────────────────────────


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _governance_capsule(session: TaskSession, skill_root: str) -> dict:
    """Emit the root-authored governance capsule for this session."""
    return {
        "schema_version": "governance_capsule_v1",
        "session_id": session.session_id,
        "authority": "taskforge_canonical",
        "version": __version__,
        "skill_root": skill_root,
        "pipeline_stages": [s.value for s in PipelineStage.sequence()],
        "approval_gates": [s.value for s in PipelineStage.sequence() if s.is_approval_gate],
        "execution_mode": session.mode.value,
        "gate_token": session.gate_token,
        "created_at": _utcnow(),
    }


def _lineage_ledger(session: TaskSession) -> list[dict]:
    """Serialize the stage-transition lineage."""
    return [
        {"origin": hop.origin, "target": hop.target, "at": hop.at, "meta": hop.meta}
        for hop in session.lineage
    ]


def _host_launch_receipt(session: TaskSession, workspace: str, prompt: str) -> dict:
    """Emit the host-facing canonical entry receipt."""
    return {
        "schema_version": "host_launch_receipt_v1",
        "session_id": session.session_id,
        "status": "verified",
        "workspace": workspace,
        "prompt_hash": uuid.uuid5(uuid.NAMESPACE_URL, prompt).hex[:16],
        "launched_at": _utcnow(),
        "version": __version__,
    }


def _runtime_input_packet(session: TaskSession, prompt: str) -> dict:
    """Emit the runtime input packet with plugin organization contract."""
    return {
        "schema_version": "runtime_input_packet_v1",
        "session_id": session.session_id,
        "prompt": prompt,
        "mode": session.mode.value,
        "stage": session.stage.value,
        "plugin_organization_contract": {
            "schema_version": "plugin_organization_v1",
            "derived_by": "agent",
            "execution_mode": session.mode.value,
            "segments": [],
            "selected_plugins": [],
            "uncovered_segments": [],
        },
        "created_at": _utcnow(),
    }


# ─── Canonical Runtime ─────────────────────────────────────────────────────────


class CanonicalRuntime:
    """The single authoritative governed runtime for TaskForge.

    Orchestrates the full pipeline lifecycle from launch through delivery,
    emitting proof artifacts at each stage boundary.
    """

    __slots__ = (
        "_skill_root", "_workspace", "_vault", "_executor",
        "_session", "_engine", "_prompt",
    )

    def __init__(
        self,
        skill_root: Path | str,
        workspace: Path | str,
        *,
        shell: str | None = None,
    ) -> None:
        self._skill_root = Path(skill_root).resolve()
        self._workspace = Path(workspace).resolve()
        self._vault = SessionVault(self._workspace)
        self._executor = ShellExecutor(workspace=self._workspace, shell=shell)
        self._session: TaskSession | None = None
        self._engine: PipelineEngine | None = None
        self._prompt: str = ""

    @property
    def session(self) -> TaskSession | None:
        return self._session

    @property
    def engine(self) -> PipelineEngine | None:
        return self._engine

    @property
    def session_root(self) -> Path:
        """The artifact directory for the current session."""
        if self._session is None:
            raise RuntimeError("No active session.")
        return self._workspace / "output" / "taskforge" / self._session.session_id

    # ─── Launch ────────────────────────────────────────────────────────────

    def launch(self, prompt: str, *, mode: ExecutionMode | None = None) -> dict:
        """Canonical launch — start a new governed session.

        Args:
            prompt: The user's task description (verbatim).
            mode: Optional execution mode override.

        Returns:
            Launch result dict with session_root and proof artifacts.
        """
        self._prompt = prompt
        self._session = TaskSession()
        if mode:
            self._session.mode = mode
        self._engine = PipelineEngine(self._session)

        # Stage 1: VALIDATE
        validation = self._run_validate()

        # Stage 2: CLARIFY
        self._engine.advance()
        self._run_clarify(prompt, mode)

        # Emit proof artifacts
        self._emit_proof_artifacts(prompt)
        self._vault.save(self._session)

        return {
            "status": "launched",
            "session_id": self._session.session_id,
            "session_root": str(self.session_root),
            "stage": self._session.stage.value,
            "mode": self._session.mode.value,
            "gate_token": self._session.gate_token,
            "validation": validation,
            "proof_artifacts": [
                "session.json",
                "summary.json",
                "lineage.json",
                "governance-capsule.json",
                "host-launch-receipt.json",
                "runtime-input-packet.json",
            ],
        }

    # ─── Resume ────────────────────────────────────────────────────────────

    def resume(
        self,
        session_id: str,
        *,
        gate_token: str | None = None,
        host_decision: dict | None = None,
    ) -> dict:
        """Resume an existing session, optionally passing an approval gate.

        Args:
            session_id: The session to resume.
            gate_token: Re-entry token for approval gates.
            host_decision: Structured approval/revision decision JSON.

        Returns:
            Resume result dict.
        """
        loaded = self._vault.load(session_id)
        if loaded is None:
            return {"status": "error", "reason": f"Session '{session_id}' not found."}

        self._session = loaded
        self._engine = PipelineEngine(self._session)

        # Validate gate token if at an approval gate
        if self._session.stage.is_approval_gate:
            if gate_token and gate_token != self._session.gate_token:
                return {"status": "error", "reason": "Invalid gate token."}

            decision_action = (host_decision or {}).get("decision_action", "approve")

            if decision_action == "approve":
                try:
                    self._engine.advance(consent=True)
                except PipelineViolation as exc:
                    return {"status": "error", "reason": str(exc)}
                self._vault.save(self._session)
                return {
                    "status": "advanced",
                    "session_id": session_id,
                    "stage": self._session.stage.value,
                    "gate_token": self._session.gate_token,
                }
            elif decision_action == "revise":
                # Apply revision delta and stay at current stage
                delta = (host_decision or {}).get("revision_delta", [])
                return {
                    "status": "revised",
                    "session_id": session_id,
                    "stage": self._session.stage.value,
                    "revision_applied": delta,
                }

        return {
            "status": "resumed",
            "session_id": session_id,
            "stage": self._session.stage.value,
            "gate_token": self._session.gate_token,
        }

    # ─── Freeze Requirement ────────────────────────────────────────────────

    def freeze_requirement(
        self,
        *,
        title: str = "",
        outputs: list[str] | None = None,
        constraints: list[str] | None = None,
        criteria: list[dict] | None = None,
    ) -> dict:
        """Seal the requirement contract (Stage 3: FREEZE).

        Returns:
            Freeze result with requirement ref_id.
        """
        if self._session is None or self._engine is None:
            return {"status": "error", "reason": "No active session."}

        if self._session.stage != PipelineStage.FREEZE:
            return {"status": "error", "reason": f"Not at FREEZE stage (at {self._session.stage.value})."}

        intent = self._session.intent or extract_intent(self._prompt)
        if outputs:
            intent.expected_outputs = outputs
        if constraints:
            intent.constraints = constraints

        req = seal_requirement(intent, title=title)
        self._session.requirement = req

        # Add criteria to intent
        if criteria:
            for c in criteria:
                intent.success_criteria.append(c.get("description", ""))

        self._session.touch()
        self._vault.save(self._session)

        return {
            "status": "frozen",
            "ref_id": req.ref_id,
            "title": req.title,
            "sealed": req.sealed,
            "locked_at": req.locked_at,
            "gate_token": self._session.gate_token,
            "bounded_return_control": {
                "explicit_user_reentry_required": True,
                "host_decision_contract": {
                    "allowed_actions": ["approve", "revise"],
                    "stage": "freeze",
                },
            },
        }

    # ─── Strategize Plan ───────────────────────────────────────────────────

    def strategize(
        self,
        segments: list[dict] | None = None,
        *,
        mode: ExecutionMode | None = None,
    ) -> dict:
        """Build and seal the execution plan (Stage 4: STRATEGIZE).

        Args:
            segments: List of segment dicts with segment_id, objective, depends_on, criteria.
            mode: Override execution mode.

        Returns:
            Strategize result with plan_ref and handoff packet.
        """
        if self._session is None or self._engine is None:
            return {"status": "error", "reason": "No active session."}

        if self._session.stage != PipelineStage.STRATEGIZE:
            return {"status": "error", "reason": f"Not at STRATEGIZE stage (at {self._session.stage.value})."}

        if self._session.requirement is None:
            return {"status": "error", "reason": "No frozen requirement."}

        # Build segments
        work_segments: list[WorkSegment] = []
        if segments:
            for seg in segments:
                crits = [
                    Criterion(
                        cid=c.get("criterion_id", f"c-{uuid.uuid4().hex[:6]}"),
                        description=c.get("description", ""),
                        method=VerifyMethod(c.get("method", "auto")),
                    )
                    for c in seg.get("criteria", [])
                ]
                work_segments.append(WorkSegment(
                    segment_id=seg.get("segment_id", f"seg-{uuid.uuid4().hex[:6]}"),
                    objective=seg.get("objective", ""),
                    depends_on=seg.get("depends_on", []),
                    write_paths=seg.get("write_paths", []),
                    criteria=crits,
                ))
        else:
            # Default single segment from prompt
            work_segments = [WorkSegment(
                segment_id="seg-primary",
                objective=self._prompt,
                criteria=[Criterion(cid="primary-ok", description="Deliverables meet the sealed requirement.")],
            )]

        # Plugin discovery and assignment
        roots = resolve_plugin_roots(self._workspace)
        plugins = scan_plugins(roots)
        index = PluginIndex(plugins)
        bindings = assign_plugins(index, work_segments)

        exec_mode = mode or self._session.mode
        plan = build_plan(self._session.requirement, work_segments, bindings, mode=exec_mode)
        plan.seal()
        self._session.plan = plan
        self._session.mode = exec_mode
        self._session.touch()

        # Compile handoff
        handoff = compile_handoff(plan)

        self._vault.save(self._session)
        self._write_artifact("handoff.json", handoff)

        return {
            "status": "strategized",
            "plan_ref": plan.plan_ref,
            "mode": exec_mode.value,
            "segments": len(work_segments),
            "units": len(plan.units),
            "waves": len(plan.waves),
            "plugins_found": index.count,
            "plugins_bound": len(bindings),
            "sealed": plan.sealed,
            "handoff": handoff,
            "gate_token": self._session.gate_token,
            "bounded_return_control": {
                "explicit_user_reentry_required": True,
                "host_decision_contract": {
                    "allowed_actions": ["approve", "revise"],
                    "stage": "strategize",
                },
            },
        }

    # ─── Execute ───────────────────────────────────────────────────────────

    def execute_unit(
        self,
        unit_id: str,
        *,
        artifacts: list[str] | None = None,
        note: str = "",
        verdicts: dict[str, str] | None = None,
        verify_commands: list[str] | None = None,
    ) -> dict:
        """Execute a single work unit and record its outcome.

        Args:
            unit_id: The unit to mark as complete.
            artifacts: Output file paths produced.
            note: Completion note.
            verdicts: Criterion verdicts (criterion_id -> pass/fail/skip).
            verify_commands: Commands to run for verification.

        Returns:
            Execution result with progress.
        """
        if self._session is None:
            return {"status": "error", "reason": "No active session."}

        if self._session.plan is None:
            return {"status": "error", "reason": "No sealed plan."}

        # Find the unit
        unit = next((u for u in self._session.plan.units if u.unit_id == unit_id), None)
        if unit is None:
            return {"status": "error", "reason": f"Unit '{unit_id}' not found in plan."}

        # Run verification commands if provided
        verify_results: list[dict] = []
        if verify_commands:
            for cmd in verify_commands:
                result = self._executor.run(cmd)
                verify_results.append(result.to_dict())

        # Parse verdicts
        parsed_verdicts: dict[str, CheckVerdict] = {}
        if verdicts:
            for cid, v in verdicts.items():
                try:
                    parsed_verdicts[cid] = CheckVerdict(v)
                except ValueError:
                    parsed_verdicts[cid] = CheckVerdict.SKIP

        # Record outcome via runner
        runner = Runner(self._session)
        runner.prepare()
        outcome = runner.complete_unit(
            unit,
            artifacts=artifacts or [],
            note=note,
            verdicts=parsed_verdicts,
        )
        runner.commit()
        self._vault.save(self._session)

        progress = runner.progress()
        return {
            "status": "executed",
            "unit_id": unit_id,
            "segment_id": unit.segment_id,
            "outcome_status": outcome.status.value,
            "progress": progress,
            "verify_results": verify_results,
        }

    # ─── Finalize ──────────────────────────────────────────────────────────

    def finalize(self) -> dict:
        """Run delivery verification and produce the acceptance report (Stage 6).

        Returns:
            Finalize result with delivery report.
        """
        if self._session is None or self._engine is None:
            return {"status": "error", "reason": "No active session."}

        # Run verification
        report = Verifier(self._session).run()
        self._session.touch()
        self._vault.save(self._session)

        # Write delivery report artifact
        self._write_artifact("delivery-report.json", {
            "session_id": report.session_id,
            "accepted": report.accepted,
            "emitted_at": report.emitted_at,
            "entries": [
                {"check_id": e.check_id, "label": e.label, "passed": e.passed, "proof": e.proof, "remark": e.remark}
                for e in report.entries
            ],
        })

        # Write cleanup receipt
        cleanup_receipt = {
            "session_id": self._session.session_id,
            "stage": self._session.stage.value,
            "accepted": report.accepted,
            "checks_passed": sum(1 for e in report.entries if e.passed),
            "checks_total": len(report.entries),
            "artifacts_in_session": self._list_artifacts(),
            "cleaned_at": _utcnow(),
        }
        self._write_artifact("cleanup-receipt.json", cleanup_receipt)

        return {
            "status": "finalized",
            "accepted": report.accepted,
            "checks_passed": sum(1 for e in report.entries if e.passed),
            "checks_total": len(report.entries),
            "report": format_report(report),
            "gate_token": self._session.gate_token,
        }

    # ─── Status ────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return current pipeline status."""
        if self._session is None or self._engine is None:
            return {"status": "error", "reason": "No active session."}

        snap = self._engine.snapshot()
        snap["preconditions"] = self._engine.preconditions()
        snap["lineage_length"] = len(self._session.lineage)
        return snap

    # ─── Internal Stage Logic ──────────────────────────────────────────────

    def _run_validate(self) -> dict:
        """Stage 1: Validate workspace prerequisites."""
        issues: list[str] = []

        # Check workspace exists
        if not self._workspace.exists():
            issues.append(f"Workspace does not exist: {self._workspace}")

        # Check for prior sessions
        prior = self._vault.list_all()

        # Check shell availability
        shell_ok = self._executor.shell != ""

        return {
            "workspace": str(self._workspace),
            "workspace_exists": self._workspace.exists(),
            "prior_sessions": len(prior),
            "shell": self._executor.shell,
            "platform": self._executor.platform,
            "shell_available": shell_ok,
            "issues": issues,
        }

    def _run_clarify(self, prompt: str, mode: ExecutionMode | None) -> None:
        """Stage 2: Extract structured intent from raw prompt."""
        exec_mode = mode or suggest_mode(prompt)
        intent = extract_intent(prompt, mode=exec_mode)
        self._session.intent = intent
        self._session.mode = exec_mode
        self._session.touch()

    # ─── Proof Artifacts ───────────────────────────────────────────────────

    def _emit_proof_artifacts(self, prompt: str) -> None:
        """Write all canonical proof artifacts to the session root."""
        if self._session is None:
            return

        root = self.session_root
        root.mkdir(parents=True, exist_ok=True)

        # Governance capsule
        capsule = _governance_capsule(self._session, str(self._skill_root))
        self._write_artifact("governance-capsule.json", capsule)

        # Host launch receipt
        receipt = _host_launch_receipt(self._session, str(self._workspace), prompt)
        self._write_artifact("host-launch-receipt.json", receipt)

        # Runtime input packet
        packet = _runtime_input_packet(self._session, prompt)
        self._write_artifact("runtime-input-packet.json", packet)

        # Lineage ledger
        self._write_artifact("lineage.json", _lineage_ledger(self._session))

        # Summary
        self._write_summary()

    def _write_summary(self) -> None:
        """Write the compact runtime summary."""
        if self._session is None or self._engine is None:
            return
        snap = self._engine.snapshot()
        snap["bounded_return_control"] = {
            "explicit_user_reentry_required": self._session.stage.is_approval_gate,
            "host_decision_contract": {
                "allowed_actions": ["approve", "revise"],
                "stage": self._session.stage.value,
            } if self._session.stage.is_approval_gate else None,
        }
        self._write_artifact("summary.json", snap)

    def _write_artifact(self, filename: str, data: Any) -> None:
        """Write a JSON artifact to the session root."""
        if self._session is None:
            return
        root = self.session_root
        root.mkdir(parents=True, exist_ok=True)
        path = root / filename
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _list_artifacts(self) -> list[str]:
        """List all artifact files in the session root."""
        root = self.session_root
        if not root.exists():
            return []
        return sorted(p.name for p in root.iterdir() if p.is_file())


# ─── CLI Entry ─────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="taskforge.entrypoint",
        description="TaskForge Canonical Runtime Entrypoint",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = p.add_subparsers(dest="command", required=True)

    ce = sub.add_parser("canonical-entry", help="Launch or resume a governed session.")
    ce.add_argument("--skill-root", type=Path, required=True, help="TaskForge installation root.")
    ce.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root.")
    ce.add_argument("--prompt", required=True, help="Task description (verbatim).")
    ce.add_argument("--resume-session", help="Resume existing session by ID.")
    ce.add_argument("--gate-token", help="Re-entry token for approval gates.")
    ce.add_argument("--host-decision-json", type=Path, help="Path to host decision JSON file.")
    ce.add_argument("--mode", choices=["sequential", "parallel"], help="Override execution mode.")
    ce.add_argument("--json", action="store_true", help="Output as JSON.")

    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for canonical-entry command."""
    args = _build_parser().parse_args(argv)

    if args.command == "canonical-entry":
        rt = CanonicalRuntime(skill_root=args.skill_root, workspace=args.workspace)

        # Load host decision if provided
        host_decision: dict | None = None
        if args.host_decision_json and args.host_decision_json.exists():
            try:
                host_decision = json.loads(args.host_decision_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        if args.resume_session:
            result = rt.resume(
                args.resume_session,
                gate_token=args.gate_token,
                host_decision=host_decision,
            )
        else:
            mode = ExecutionMode(args.mode) if args.mode else None
            result = rt.launch(args.prompt, mode=mode)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Status:  {result.get('status')}")
            print(f"Session: {result.get('session_id', 'N/A')}")
            print(f"Stage:   {result.get('stage', 'N/A')}")
            if result.get("session_root"):
                print(f"Root:    {result['session_root']}")
            if result.get("gate_token"):
                print(f"Token:   {result['gate_token']}")

        return 0 if result.get("status") != "error" else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
