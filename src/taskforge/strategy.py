"""Strategic planning — intent extraction, requirement sealing, plan generation.

Pure-function module: transforms models without side effects.
Covers pipeline stages CLARIFY → FREEZE → STRATEGIZE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .models import (
    Criterion,
    ExecUnit,
    ExecutionMode,
    ExecutionPlan,
    FrozenRequirement,
    PluginBinding,
    TaskIntent,
    VerifyMethod,
    WorkSegment,
)


# ─── Intent Extraction (CLARIFY) ──────────────────────────────────────────────


def extract_intent(
    raw_task: str,
    *,
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
    outputs: list[str] | None = None,
    constraints: list[str] | None = None,
    exclusions: list[str] | None = None,
) -> TaskIntent:
    """Build a structured TaskIntent from raw task text."""
    return TaskIntent(
        objective=raw_task,
        expected_outputs=outputs or [],
        constraints=constraints or [],
        exclusions=exclusions or [],
        mode=mode,
    )


def suggest_mode(
    task_text: str,
    *,
    segment_count: int = 1,
    parallelizable: bool = False,
    chain_depth: int = 1,
) -> ExecutionMode:
    """Heuristic: recommend SEQUENTIAL vs PARALLEL execution topology."""
    if segment_count > 4 and parallelizable:
        return ExecutionMode.PARALLEL
    if chain_depth > 3 and segment_count > 3:
        return ExecutionMode.PARALLEL
    return ExecutionMode.SEQUENTIAL


# ─── Requirement Sealing (FREEZE) ─────────────────────────────────────────────


def seal_requirement(intent: TaskIntent, *, title: str = "") -> FrozenRequirement:
    """Create and seal an immutable requirement contract."""
    req = FrozenRequirement(
        ref_id=f"req-{uuid.uuid4().hex[:10]}",
        title=title or intent.objective[:80],
        intent=intent,
    )
    req.seal()
    return req


# ─── Plan Generation (STRATEGIZE) ─────────────────────────────────────────────


def build_plan(
    requirement: FrozenRequirement,
    segments: list[WorkSegment],
    bindings: list[PluginBinding],
    *,
    mode: ExecutionMode | None = None,
) -> ExecutionPlan:
    """Generate an execution plan from sealed requirement + plugin bindings.

    Produces ExecUnits per segment, organizes into dependency-ordered waves
    (PARALLEL mode) or a single serial wave (SEQUENTIAL mode).
    """
    exec_mode = mode or requirement.intent.mode
    plan_ref = f"plan-{uuid.uuid4().hex[:10]}"

    units: list[ExecUnit] = []
    for seg in segments:
        bound_plugin = ""
        entry = ""
        for b in bindings:
            if seg.segment_id in b.segment_ids:
                bound_plugin = b.plugin_id
                entry = b.entrypoint
                break

        units.append(ExecUnit(
            unit_id=f"u-{seg.segment_id}",
            segment_id=seg.segment_id,
            label=seg.objective,
            plugin_id=bound_plugin,
            plugin_entry=entry,
            deps=seg.depends_on,
            write_scope=seg.write_paths,
            artifacts=[c.description for c in seg.criteria],
        ))

    waves = _order_waves(units) if exec_mode == ExecutionMode.PARALLEL else [[u.unit_id for u in units]]

    return ExecutionPlan(
        plan_ref=plan_ref,
        mode=exec_mode,
        segments=segments,
        units=units,
        bindings=bindings,
        waves=waves,
    )


def _order_waves(units: list[ExecUnit]) -> list[list[str]]:
    """Topological wave decomposition: units with satisfied deps share a wave."""
    by_id = {u.unit_id: u for u in units}
    # Also map segment_id -> unit_id for dep resolution
    seg_to_unit = {u.segment_id: u.unit_id for u in units}
    done: set[str] = set()
    waves: list[list[str]] = []
    remaining = set(by_id.keys())

    while remaining:
        ready = []
        for uid in remaining:
            unit = by_id[uid]
            if all(_dep_satisfied(d, done, seg_to_unit) for d in unit.deps):
                ready.append(uid)
        if not ready:
            ready = list(remaining)  # break cycles
        waves.append(sorted(ready))
        done.update(ready)
        remaining -= set(ready)
    return waves


def _dep_satisfied(dep: str, done: set[str], seg_to_unit: dict[str, str]) -> bool:
    if dep in done:
        return True
    mapped = seg_to_unit.get(dep)
    return mapped in done if mapped else False


# ─── Handoff Packet ───────────────────────────────────────────────────────────


def compile_handoff(plan: ExecutionPlan) -> dict:
    """Compile a sealed plan into an agent-consumable handoff packet."""
    if not plan.sealed:
        raise ValueError("Plan must be sealed before handoff compilation.")

    return {
        "handoff_ref": f"ho-{uuid.uuid4().hex[:10]}",
        "plan_ref": plan.plan_ref,
        "mode": plan.mode.value,
        "waves": plan.waves,
        "units": [
            {
                "unit_id": u.unit_id,
                "segment_id": u.segment_id,
                "label": u.label,
                "plugin_id": u.plugin_id,
                "plugin_entry": u.plugin_entry,
                "deps": u.deps,
                "write_scope": u.write_scope,
                "artifacts": u.artifacts,
                "verify_cmd": u.verify_cmd,
            }
            for u in plan.units
        ],
        "action_required": True,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
    }
