"""Domain models for the TaskForge orchestration engine.

All shared types live here — enums, dataclasses, and value objects used across
every pipeline stage. Zero external dependencies; pure stdlib.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_session_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"tf-{ts}-{uuid.uuid4().hex[:6]}"


# ─── Pipeline Stage ────────────────────────────────────────────────────────────


class PipelineStage(enum.Enum):
    """Immutable 6-stage pipeline enforced by the orchestration engine."""

    VALIDATE = "validate"
    CLARIFY = "clarify"
    FREEZE = "freeze"
    STRATEGIZE = "strategize"
    EXECUTE = "execute"
    FINALIZE = "finalize"

    @classmethod
    def sequence(cls) -> list[PipelineStage]:
        return [
            cls.VALIDATE,
            cls.CLARIFY,
            cls.FREEZE,
            cls.STRATEGIZE,
            cls.EXECUTE,
            cls.FINALIZE,
        ]

    def successor(self) -> PipelineStage | None:
        seq = self.sequence()
        idx = seq.index(self)
        return seq[idx + 1] if idx < len(seq) - 1 else None

    @property
    def is_approval_gate(self) -> bool:
        """Stages that halt the pipeline until explicit user consent."""
        return self in _APPROVAL_GATES


_APPROVAL_GATES: frozenset[PipelineStage] = frozenset({
    PipelineStage.FREEZE,
    PipelineStage.STRATEGIZE,
    PipelineStage.FINALIZE,
})


# ─── Execution Mode ────────────────────────────────────────────────────────────


class ExecutionMode(enum.Enum):
    """Determines execution topology.

    SEQUENTIAL — units run one-by-one in dependency order (lower overhead).
    PARALLEL   — independent units within a wave run concurrently.
    """

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


# ─── Status Tracking ───────────────────────────────────────────────────────────


class UnitStatus(enum.Enum):
    IDLE = "idle"
    ACTIVE = "active"
    DONE = "done"
    ERRORED = "errored"
    STUCK = "stuck"


class CheckVerdict(enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class VerifyMethod(enum.Enum):
    AUTO = "auto"
    MANUAL = "manual"


# ─── Plugin Models ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class PluginInfo:
    """Lightweight descriptor parsed from a plugin manifest (PLUGIN.md)."""

    plugin_id: str
    display_name: str
    summary: str
    manifest_path: str
    categories: list[str] = field(default_factory=list)
    use_case: str = ""
    limits: str = ""


@dataclass(slots=True)
class PluginBinding:
    """Associates a plugin with specific work segments."""

    plugin_id: str
    segment_ids: list[str]
    duty: str
    rationale: str
    entrypoint: str = ""


# ─── Task Decomposition ────────────────────────────────────────────────────────


@dataclass(slots=True)
class Criterion:
    """A single verifiable acceptance condition."""

    cid: str
    description: str
    method: VerifyMethod = VerifyMethod.AUTO


@dataclass(slots=True)
class WorkSegment:
    """An independent slice of decomposed work."""

    segment_id: str
    objective: str
    plugin_candidates: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    criteria: list[Criterion] = field(default_factory=list)


# ─── Intent & Requirements ─────────────────────────────────────────────────────


@dataclass(slots=True)
class TaskIntent:
    """Structured intent extracted during the CLARIFY stage."""

    objective: str
    expected_outputs: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL


@dataclass(slots=True)
class FrozenRequirement:
    """Immutable requirement contract — the single source of truth."""

    ref_id: str
    title: str
    intent: TaskIntent
    locked_at: str = ""
    sealed: bool = False

    def seal(self) -> None:
        self.locked_at = _utcnow()
        self.sealed = True


# ─── Execution Plan ────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ExecUnit:
    """Atomic executable unit derived from a work segment."""

    unit_id: str
    segment_id: str
    label: str
    plugin_id: str = ""
    plugin_entry: str = ""
    deps: list[str] = field(default_factory=list)
    write_scope: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    verify_cmd: str = ""


@dataclass(slots=True)
class ExecutionPlan:
    """Approved plan binding segments, plugins, and units into waves."""

    plan_ref: str
    mode: ExecutionMode
    segments: list[WorkSegment] = field(default_factory=list)
    units: list[ExecUnit] = field(default_factory=list)
    bindings: list[PluginBinding] = field(default_factory=list)
    waves: list[list[str]] = field(default_factory=list)
    locked_at: str = ""
    sealed: bool = False

    def seal(self) -> None:
        self.locked_at = _utcnow()
        self.sealed = True


# ─── Execution Results ─────────────────────────────────────────────────────────


@dataclass(slots=True)
class UnitOutcome:
    """Recorded result of a single executed unit."""

    unit_id: str
    segment_id: str
    status: UnitStatus = UnitStatus.IDLE
    artifacts: list[str] = field(default_factory=list)
    note: str = ""
    error_msg: str = ""
    criteria_verdicts: dict[str, CheckVerdict] = field(default_factory=dict)
    started: str = ""
    finished: str = ""


@dataclass(slots=True)
class SegmentOutcome:
    """Aggregated outcome for a work segment."""

    segment_id: str
    status: UnitStatus = UnitStatus.IDLE
    outcomes: list[UnitOutcome] = field(default_factory=list)
    blocker_reason: str = ""


# ─── Verification ──────────────────────────────────────────────────────────────


@dataclass(slots=True)
class CheckEntry:
    """One verification check result."""

    check_id: str
    label: str
    passed: bool
    proof: str = ""
    remark: str = ""


@dataclass(slots=True)
class DeliveryReport:
    """Final acceptance report emitted at FINALIZE."""

    session_id: str
    entries: list[CheckEntry] = field(default_factory=list)
    accepted: bool = False
    emitted_at: str = ""
    commentary: str = ""

    def compute_verdict(self) -> bool:
        self.accepted = all(e.passed for e in self.entries) if self.entries else False
        self.emitted_at = _utcnow()
        return self.accepted


# ─── Session State ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class StageHop:
    """Lineage record of a stage transition."""

    origin: str
    target: str
    at: str = field(default_factory=_utcnow)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TaskSession:
    """Top-level orchestrator state — fully serializable and resumable."""

    session_id: str = field(default_factory=_make_session_id)
    stage: PipelineStage = PipelineStage.VALIDATE
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    intent: TaskIntent | None = None
    requirement: FrozenRequirement | None = None
    plan: ExecutionPlan | None = None
    segment_outcomes: list[SegmentOutcome] = field(default_factory=list)
    delivery: DeliveryReport | None = None
    lineage: list[StageHop] = field(default_factory=list)
    opened_at: str = field(default_factory=_utcnow)
    touched_at: str = field(default_factory=_utcnow)
    gate_token: str = field(default_factory=lambda: uuid.uuid4().hex[:16])

    def touch(self) -> None:
        self.touched_at = _utcnow()

