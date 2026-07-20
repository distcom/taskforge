"""Tests for strategy, runner, verification, and vault."""

from pathlib import Path

import pytest

from taskforge.models import (
    CheckVerdict,
    Criterion,
    ExecutionMode,
    PipelineStage,
    TaskSession,
    UnitStatus,
    WorkSegment,
)
from taskforge.runner import ExecutionFault, Runner
from taskforge.strategy import (
    build_plan,
    compile_handoff,
    extract_intent,
    seal_requirement,
    suggest_mode,
)
from taskforge.vault import SessionVault
from taskforge.verify import Verifier, format_report


# ─── Strategy ──────────────────────────────────────────────────────────────────


class TestStrategy:
    def test_extract_intent(self):
        intent = extract_intent("Build API", outputs=["api.py"], constraints=["py3.10+"])
        assert intent.objective == "Build API"
        assert "api.py" in intent.expected_outputs
        assert intent.mode == ExecutionMode.SEQUENTIAL

    def test_suggest_mode_simple(self):
        assert suggest_mode("x", segment_count=2) == ExecutionMode.SEQUENTIAL

    def test_suggest_mode_complex(self):
        assert suggest_mode("x", segment_count=6, parallelizable=True) == ExecutionMode.PARALLEL

    def test_seal_requirement(self):
        req = seal_requirement(extract_intent("Task"), title="My Req")
        assert req.sealed
        assert req.locked_at != ""
        assert req.title == "My Req"

    def test_build_plan(self):
        req = seal_requirement(extract_intent("Task"))
        segs = [WorkSegment(segment_id="s1", objective="Work"), WorkSegment(segment_id="s2", objective="More", depends_on=["s1"])]
        plan = build_plan(req, segs, [])
        assert len(plan.units) == 2
        assert plan.mode == ExecutionMode.SEQUENTIAL

    def test_parallel_waves(self):
        req = seal_requirement(extract_intent("Task", mode=ExecutionMode.PARALLEL))
        segs = [
            WorkSegment(segment_id="a", objective="A"),
            WorkSegment(segment_id="b", objective="B"),
            WorkSegment(segment_id="c", objective="C", depends_on=["a", "b"]),
        ]
        plan = build_plan(req, segs, [], mode=ExecutionMode.PARALLEL)
        assert len(plan.waves) == 2
        assert set(plan.waves[0]) == {"u-a", "u-b"}
        assert plan.waves[1] == ["u-c"]

    def test_handoff_requires_sealed(self):
        req = seal_requirement(extract_intent("T"))
        plan = build_plan(req, [WorkSegment(segment_id="s", objective="W")], [])
        with pytest.raises(ValueError):
            compile_handoff(plan)

    def test_handoff_sealed(self):
        req = seal_requirement(extract_intent("T"))
        plan = build_plan(req, [WorkSegment(segment_id="s", objective="W")], [])
        plan.seal()
        ho = compile_handoff(plan)
        assert ho["action_required"] is True


# ─── Runner ────────────────────────────────────────────────────────────────────


class TestRunner:
    def _session(self) -> TaskSession:
        req = seal_requirement(extract_intent("Task"))
        segs = [WorkSegment(segment_id="s1", objective="A"), WorkSegment(segment_id="s2", objective="B", depends_on=["s1"])]
        plan = build_plan(req, segs, [])
        plan.seal()
        s = TaskSession(stage=PipelineStage.EXECUTE)
        s.requirement = req
        s.plan = plan
        return s

    def test_prepare(self):
        r = Runner(self._session())
        r.prepare()
        assert r.progress()["total"] == 2

    def test_no_plan_raises(self):
        with pytest.raises(ExecutionFault):
            Runner(TaskSession()).prepare()

    def test_sequential_respects_deps(self):
        r = Runner(self._session())
        r.prepare()
        ready = r.ready_units()
        assert len(ready) == 1
        assert ready[0].segment_id == "s1"

    def test_complete_unlocks_next(self):
        r = Runner(self._session())
        r.prepare()
        unit = r.ready_units()[0]
        r.complete_unit(unit, artifacts=["out.txt"], note="done")
        ready2 = r.ready_units()
        assert len(ready2) == 1
        assert ready2[0].segment_id == "s2"

    def test_commit(self):
        s = self._session()
        r = Runner(s)
        r.prepare()
        for u in s.plan.units:
            r.complete_unit(u, artifacts=["x"], note="ok")
        results = r.commit()
        assert all(o.status == UnitStatus.DONE for o in results)


# ─── Verifier ──────────────────────────────────────────────────────────────────


class TestVerifier:
    def _done_session(self) -> TaskSession:
        req = seal_requirement(extract_intent("Task"))
        segs = [WorkSegment(segment_id="s1", objective="Work")]
        plan = build_plan(req, segs, [])
        plan.seal()
        s = TaskSession(stage=PipelineStage.FINALIZE)
        s.requirement = req
        s.plan = plan
        r = Runner(s)
        r.prepare()
        for u in plan.units:
            r.complete_unit(u, artifacts=["f.txt"], note="ok", verdicts={"c": CheckVerdict.PASS})
        r.commit()
        return s

    def test_all_pass(self):
        report = Verifier(self._done_session()).run()
        assert report.accepted
        assert all(e.passed for e in report.entries)

    def test_errored_fails(self):
        s = self._done_session()
        s.segment_outcomes[0].status = UnitStatus.ERRORED
        report = Verifier(s).run()
        assert not report.accepted

    def test_format(self):
        report = Verifier(self._done_session()).run()
        text = format_report(report)
        assert "ACCEPTED" in text
        assert "# Delivery Report" in text


# ─── Vault ─────────────────────────────────────────────────────────────────────


class TestVault:
    def test_save_load(self, tmp_path: Path):
        s = TaskSession()
        s.intent = extract_intent("Test")
        s.requirement = seal_requirement(s.intent)
        v = SessionVault(tmp_path)
        v.save(s)
        loaded = v.load(s.session_id)
        assert loaded is not None
        assert loaded.session_id == s.session_id
        assert loaded.requirement.sealed

    def test_load_missing(self, tmp_path: Path):
        assert SessionVault(tmp_path).load("nope") is None

    def test_list(self, tmp_path: Path):
        v = SessionVault(tmp_path)
        v.save(TaskSession())
        v.save(TaskSession())
        assert len(v.list_all()) == 2

    def test_remove(self, tmp_path: Path):
        v = SessionVault(tmp_path)
        s = TaskSession()
        v.save(s)
        assert v.remove(s.session_id)
        assert v.load(s.session_id) is None

    def test_plan_roundtrip(self, tmp_path: Path):
        req = seal_requirement(extract_intent("T"))
        plan = build_plan(req, [WorkSegment(segment_id="s", objective="W")], [])
        plan.seal()
        s = TaskSession()
        s.requirement = req
        s.plan = plan
        v = SessionVault(tmp_path)
        v.save(s)
        loaded = v.load(s.session_id)
        assert loaded.plan.sealed
        assert len(loaded.plan.units) == 1
