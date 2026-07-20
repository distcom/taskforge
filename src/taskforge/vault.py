"""Session persistence — save, load, list, and resume task sessions.

Stores sessions as JSON under <workspace>/output/taskforge/<session_id>/.
Each session directory contains:
  - session.json   : full resumable state
  - summary.json   : compact status for fast listing
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import (
    CheckEntry,
    CheckVerdict,
    Criterion,
    DeliveryReport,
    ExecUnit,
    ExecutionMode,
    ExecutionPlan,
    FrozenRequirement,
    PipelineStage,
    PluginBinding,
    SegmentOutcome,
    StageHop,
    TaskIntent,
    TaskSession,
    UnitOutcome,
    UnitStatus,
    VerifyMethod,
    WorkSegment,
)

_SESSIONS_DIR = "taskforge"
_SESSION_FILE = "session.json"
_SUMMARY_FILE = "summary.json"


def _sessions_root(workspace: Path) -> Path:
    return workspace / "output" / _SESSIONS_DIR


class SessionVault:
    """Persists and retrieves TaskSession state as JSON artifacts."""

    __slots__ = ("_workspace",)

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)

    @property
    def workspace(self) -> Path:
        return self._workspace

    def save(self, session: TaskSession) -> Path:
        d = _sessions_root(self._workspace) / session.session_id
        d.mkdir(parents=True, exist_ok=True)

        path = d / _SESSION_FILE
        path.write_text(json.dumps(_ser_session(session), indent=2, ensure_ascii=False), encoding="utf-8")

        summary = d / _SUMMARY_FILE
        summary.write_text(json.dumps(_build_summary(session), indent=2), encoding="utf-8")
        return path

    def load(self, session_id: str) -> TaskSession | None:
        path = _sessions_root(self._workspace) / session_id / _SESSION_FILE
        if not path.is_file():
            return None
        try:
            return _deser_session(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def list_all(self) -> list[dict[str, str]]:
        root = _sessions_root(self._workspace)
        if not root.is_dir():
            return []
        items = []
        for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            sf = d / _SUMMARY_FILE
            if not sf.is_file():
                continue
            try:
                items.append(json.loads(sf.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return items

    def remove(self, session_id: str) -> bool:
        import shutil
        d = _sessions_root(self._workspace) / session_id
        if not d.is_dir():
            return False
        shutil.rmtree(d)
        return True


# ─── Serialization ─────────────────────────────────────────────────────────────


def _ser_session(s: TaskSession) -> dict[str, Any]:
    d: dict[str, Any] = {
        "session_id": s.session_id,
        "stage": s.stage.value,
        "mode": s.mode.value,
        "opened_at": s.opened_at,
        "touched_at": s.touched_at,
        "gate_token": s.gate_token,
        "lineage": [{"origin": h.origin, "target": h.target, "at": h.at} for h in s.lineage],
    }
    if s.intent:
        d["intent"] = {**asdict(s.intent), "mode": s.intent.mode.value}
    if s.requirement:
        req = asdict(s.requirement)
        req["intent"]["mode"] = s.requirement.intent.mode.value
        d["requirement"] = req
    if s.plan:
        d["plan"] = _ser_plan(s.plan)
    if s.segment_outcomes:
        d["segment_outcomes"] = [_ser_seg_outcome(o) for o in s.segment_outcomes]
    if s.delivery:
        d["delivery"] = _ser_delivery(s.delivery)
    return d


def _deser_session(d: dict[str, Any]) -> TaskSession:
    s = TaskSession(
        session_id=d["session_id"],
        stage=PipelineStage(d["stage"]),
        mode=ExecutionMode(d.get("mode", "sequential")),
        opened_at=d.get("opened_at", ""),
        touched_at=d.get("touched_at", ""),
        gate_token=d.get("gate_token", ""),
    )
    for h in d.get("lineage", []):
        s.lineage.append(StageHop(**h))
    if d.get("intent"):
        i = dict(d["intent"])
        i["mode"] = ExecutionMode(i.get("mode", "sequential"))
        s.intent = TaskIntent(**i)
    if d.get("requirement"):
        r = dict(d["requirement"])
        ri = dict(r.pop("intent"))
        ri["mode"] = ExecutionMode(ri.get("mode", "sequential"))
        s.requirement = FrozenRequirement(intent=TaskIntent(**ri), **r)
    if d.get("plan"):
        s.plan = _deser_plan(d["plan"])
    for so in d.get("segment_outcomes", []):
        s.segment_outcomes.append(_deser_seg_outcome(so))
    if d.get("delivery"):
        s.delivery = _deser_delivery(d["delivery"])
    return s


def _ser_plan(p: ExecutionPlan) -> dict:
    return {
        "plan_ref": p.plan_ref, "mode": p.mode.value, "locked_at": p.locked_at, "sealed": p.sealed,
        "segments": [_ser_segment(s) for s in p.segments],
        "units": [asdict(u) for u in p.units],
        "bindings": [asdict(b) for b in p.bindings],
        "waves": p.waves,
    }


def _deser_plan(d: dict) -> ExecutionPlan:
    return ExecutionPlan(
        plan_ref=d["plan_ref"], mode=ExecutionMode(d.get("mode", "sequential")),
        segments=[_deser_segment(s) for s in d.get("segments", [])],
        units=[ExecUnit(**u) for u in d.get("units", [])],
        bindings=[PluginBinding(**b) for b in d.get("bindings", [])],
        waves=d.get("waves", []), locked_at=d.get("locked_at", ""), sealed=d.get("sealed", False),
    )


def _ser_segment(s: WorkSegment) -> dict:
    return {
        "segment_id": s.segment_id, "objective": s.objective,
        "plugin_candidates": s.plugin_candidates, "depends_on": s.depends_on,
        "write_paths": s.write_paths,
        "criteria": [{"cid": c.cid, "description": c.description, "method": c.method.value} for c in s.criteria],
    }


def _deser_segment(d: dict) -> WorkSegment:
    return WorkSegment(
        segment_id=d["segment_id"], objective=d["objective"],
        plugin_candidates=d.get("plugin_candidates", []), depends_on=d.get("depends_on", []),
        write_paths=d.get("write_paths", []),
        criteria=[Criterion(cid=c["cid"], description=c["description"], method=VerifyMethod(c.get("method", "auto"))) for c in d.get("criteria", [])],
    )


def _ser_seg_outcome(o: SegmentOutcome) -> dict:
    return {
        "segment_id": o.segment_id, "status": o.status.value, "blocker_reason": o.blocker_reason,
        "outcomes": [{
            "unit_id": u.unit_id, "segment_id": u.segment_id, "status": u.status.value,
            "artifacts": u.artifacts, "note": u.note, "error_msg": u.error_msg,
            "criteria_verdicts": {k: v.value for k, v in u.criteria_verdicts.items()},
            "started": u.started, "finished": u.finished,
        } for u in o.outcomes],
    }


def _deser_seg_outcome(d: dict) -> SegmentOutcome:
    outcomes = [UnitOutcome(
        unit_id=u["unit_id"], segment_id=u["segment_id"], status=UnitStatus(u.get("status", "idle")),
        artifacts=u.get("artifacts", []), note=u.get("note", ""), error_msg=u.get("error_msg", ""),
        criteria_verdicts={k: CheckVerdict(v) for k, v in u.get("criteria_verdicts", {}).items()},
        started=u.get("started", ""), finished=u.get("finished", ""),
    ) for u in d.get("outcomes", [])]
    return SegmentOutcome(
        segment_id=d["segment_id"], status=UnitStatus(d.get("status", "idle")),
        outcomes=outcomes, blocker_reason=d.get("blocker_reason", ""),
    )


def _ser_delivery(r: DeliveryReport) -> dict:
    return {
        "session_id": r.session_id, "accepted": r.accepted, "emitted_at": r.emitted_at, "commentary": r.commentary,
        "entries": [{"check_id": e.check_id, "label": e.label, "passed": e.passed, "proof": e.proof, "remark": e.remark} for e in r.entries],
    }


def _deser_delivery(d: dict) -> DeliveryReport:
    return DeliveryReport(
        session_id=d["session_id"], accepted=d.get("accepted", False),
        emitted_at=d.get("emitted_at", ""), commentary=d.get("commentary", ""),
        entries=[CheckEntry(**e) for e in d.get("entries", [])],
    )


def _build_summary(s: TaskSession) -> dict[str, Any]:
    outcomes = s.segment_outcomes
    return {
        "session_id": s.session_id,
        "stage": s.stage.value,
        "mode": s.mode.value,
        "segments_total": len(outcomes),
        "segments_done": sum(1 for o in outcomes if o.status == UnitStatus.DONE),
        "segments_errored": sum(1 for o in outcomes if o.status == UnitStatus.ERRORED),
        "accepted": s.delivery.accepted if s.delivery else None,
        "touched_at": s.touched_at,
    }
