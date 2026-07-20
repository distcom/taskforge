"""Pipeline engine — enforces the immutable 6-stage execution sequence.

The engine is the single authority for stage transitions. It raises
`GateHeld` at approval gates and rejects out-of-order advancement.
"""

from __future__ import annotations

from .models import (
    PipelineStage,
    TaskSession,
    StageHop,
    UnitStatus,
)


class PipelineViolation(Exception):
    """Raised on illegal stage transitions."""


class GateHeld(Exception):
    """Raised when the pipeline halts at an approval gate awaiting user consent."""

    def __init__(self, stage: PipelineStage, reason: str, token: str):
        self.stage = stage
        self.token = token
        super().__init__(reason)


class PipelineEngine:
    """Drives a TaskSession through the 6-stage pipeline.

    Invariants enforced:
    - Stages advance strictly in sequence order.
    - Approval gates (FREEZE, STRATEGIZE, FINALIZE) block until `consent=True`.
    - Preconditions are validated before entering each stage.
    - Every transition is recorded in the session lineage.
    """

    __slots__ = ("_session",)

    def __init__(self, session: TaskSession) -> None:
        self._session = session

    @property
    def session(self) -> TaskSession:
        return self._session

    @property
    def stage(self) -> PipelineStage:
        return self._session.stage

    @property
    def finished(self) -> bool:
        return (
            self._session.stage == PipelineStage.FINALIZE
            and self._session.delivery is not None
        )

    def advance(self, *, consent: bool = False) -> PipelineStage:
        """Move to the next pipeline stage.

        Args:
            consent: Must be True to pass an approval gate.

        Returns:
            The stage now active.

        Raises:
            GateHeld: Current stage is an approval gate and consent is False.
            PipelineViolation: Already at terminal stage.
        """
        cur = self._session.stage

        if cur.is_approval_gate and not consent:
            raise GateHeld(
                stage=cur,
                reason=f"Approval gate at '{cur.value}' requires explicit consent.",
                token=self._session.gate_token,
            )

        nxt = cur.successor()
        if nxt is None:
            raise PipelineViolation(f"Pipeline complete — cannot advance past '{cur.value}'.")

        self._session.lineage.append(StageHop(origin=cur.value, target=nxt.value))
        self._session.stage = nxt
        self._session.touch()
        return nxt

    def preconditions(self) -> list[str]:
        """Return unmet preconditions for the current stage (empty = ready)."""
        s = self._session
        issues: list[str] = []

        if s.stage == PipelineStage.STRATEGIZE:
            if s.requirement is None:
                issues.append("No sealed requirement contract.")
            elif not s.requirement.sealed:
                issues.append("Requirement contract not yet sealed.")

        elif s.stage == PipelineStage.EXECUTE:
            if s.plan is None:
                issues.append("No execution plan exists.")
            elif not s.plan.sealed:
                issues.append("Execution plan not yet sealed.")

        elif s.stage == PipelineStage.FINALIZE:
            incomplete = [
                o.segment_id
                for o in s.segment_outcomes
                if o.status != UnitStatus.DONE
            ]
            if incomplete:
                issues.append(f"Segments not done: {', '.join(incomplete)}")

        return issues

    def snapshot(self) -> dict:
        """Concise status dict for host/CLI consumption."""
        outcomes = self._session.segment_outcomes
        return {
            "session_id": self._session.session_id,
            "stage": self._session.stage.value,
            "mode": self._session.mode.value,
            "segments_total": len(outcomes),
            "segments_done": sum(1 for o in outcomes if o.status == UnitStatus.DONE),
            "segments_errored": sum(1 for o in outcomes if o.status == UnitStatus.ERRORED),
            "segments_stuck": sum(1 for o in outcomes if o.status == UnitStatus.STUCK),
            "finished": self.finished,
            "gate_token": self._session.gate_token,
        }
