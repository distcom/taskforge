"""Execution runner — carries out sealed plan units with dependency tracking.

Handles pipeline stage EXECUTE: resolves ready units, records outcomes,
and synchronizes segment-level status back to the session.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    CheckVerdict,
    ExecUnit,
    ExecutionMode,
    ExecutionPlan,
    SegmentOutcome,
    TaskSession,
    UnitOutcome,
    UnitStatus,
)


class ExecutionFault(Exception):
    """Unrecoverable execution error."""


class Runner:
    """Executes plan units respecting dependency order and execution mode.

    SEQUENTIAL mode: one unit at a time.
    PARALLEL mode: all dependency-ready units within a wave.
    """

    __slots__ = ("_session", "_plan", "_outcomes", "_segments")

    def __init__(self, session: TaskSession) -> None:
        self._session = session
        self._plan: ExecutionPlan | None = session.plan
        self._outcomes: dict[str, UnitOutcome] = {}
        self._segments: dict[str, SegmentOutcome] = {}

    def prepare(self) -> None:
        """Initialize execution state from the sealed plan."""
        if self._plan is None:
            raise ExecutionFault("No plan attached to session.")
        if not self._plan.sealed:
            raise ExecutionFault("Plan is not sealed — cannot execute.")

        for seg in self._plan.segments:
            self._segments[seg.segment_id] = SegmentOutcome(segment_id=seg.segment_id)
        for unit in self._plan.units:
            self._outcomes[unit.unit_id] = UnitOutcome(
                unit_id=unit.unit_id, segment_id=unit.segment_id,
            )

    def ready_units(self) -> list[ExecUnit]:
        """Return units whose dependencies are fully satisfied."""
        if self._plan is None:
            return []

        seg_to_unit = {u.segment_id: u.unit_id for u in self._plan.units}
        ready: list[ExecUnit] = []

        for unit in self._plan.units:
            outcome = self._outcomes.get(unit.unit_id)
            if outcome is None or outcome.status != UnitStatus.IDLE:
                continue
            if all(self._dep_ok(d, seg_to_unit) for d in unit.deps):
                ready.append(unit)

        if self._plan.mode == ExecutionMode.SEQUENTIAL:
            return ready[:1]
        return ready

    def complete_unit(
        self,
        unit: ExecUnit,
        *,
        artifacts: list[str] | None = None,
        note: str = "",
        error_msg: str = "",
        status: UnitStatus = UnitStatus.DONE,
        verdicts: dict[str, CheckVerdict] | None = None,
    ) -> UnitOutcome:
        """Record execution outcome for a unit."""
        now = datetime.now(timezone.utc).isoformat()
        oc = self._outcomes.get(unit.unit_id)
        if oc is None:
            oc = UnitOutcome(unit_id=unit.unit_id, segment_id=unit.segment_id)
            self._outcomes[unit.unit_id] = oc

        oc.status = status
        oc.artifacts = artifacts or []
        oc.note = note
        oc.error_msg = error_msg
        oc.criteria_verdicts = verdicts or {}
        oc.finished = now
        if not oc.started:
            oc.started = now

        self._sync_segment(unit.segment_id)
        self._session.touch()
        return oc

    def mark_stuck(self, unit: ExecUnit, reason: str) -> UnitOutcome:
        return self.complete_unit(unit, status=UnitStatus.STUCK, error_msg=reason)

    def commit(self) -> list[SegmentOutcome]:
        """Finalize and write outcomes back to the session."""
        for seg_id, seg_oc in self._segments.items():
            if seg_oc.status == UnitStatus.IDLE:
                seg_oc.status = UnitStatus.STUCK
                seg_oc.blocker_reason = "No units executed."
            seg_oc.outcomes = [
                o for o in self._outcomes.values() if o.segment_id == seg_id
            ]
        self._session.segment_outcomes = list(self._segments.values())
        self._session.touch()
        return self._session.segment_outcomes

    def progress(self) -> dict:
        total = len(self._outcomes)
        done = sum(1 for o in self._outcomes.values() if o.status == UnitStatus.DONE)
        errored = sum(1 for o in self._outcomes.values() if o.status == UnitStatus.ERRORED)
        stuck = sum(1 for o in self._outcomes.values() if o.status == UnitStatus.STUCK)
        return {
            "total": total,
            "done": done,
            "errored": errored,
            "stuck": stuck,
            "idle": total - done - errored - stuck,
            "pct": round(done / total * 100, 1) if total else 0.0,
        }

    # ─── internals ─────────────────────────────────────────────────────────

    def _dep_ok(self, dep: str, seg_to_unit: dict[str, str]) -> bool:
        oc = self._outcomes.get(dep)
        if oc is not None:
            return oc.status == UnitStatus.DONE
        mapped = seg_to_unit.get(dep)
        if mapped:
            oc = self._outcomes.get(mapped)
            return oc.status == UnitStatus.DONE if oc else False
        return False

    def _sync_segment(self, segment_id: str) -> None:
        seg = self._segments.get(segment_id)
        if seg is None:
            return
        statuses = {
            o.status for o in self._outcomes.values() if o.segment_id == segment_id
        }
        if not statuses:
            return
        if statuses == {UnitStatus.DONE}:
            seg.status = UnitStatus.DONE
        elif UnitStatus.ERRORED in statuses:
            seg.status = UnitStatus.ERRORED
        elif UnitStatus.STUCK in statuses:
            seg.status = UnitStatus.STUCK
        elif UnitStatus.ACTIVE in statuses:
            seg.status = UnitStatus.ACTIVE
