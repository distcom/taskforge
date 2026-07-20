"""Tests for the pipeline engine and stage transitions."""

import pytest

from taskforge.engine import GateHeld, PipelineEngine, PipelineViolation
from taskforge.models import PipelineStage, TaskSession


class TestPipelineStage:
    def test_sequence_length(self):
        assert len(PipelineStage.sequence()) == 6

    def test_successor_chain(self):
        assert PipelineStage.VALIDATE.successor() == PipelineStage.CLARIFY
        assert PipelineStage.CLARIFY.successor() == PipelineStage.FREEZE
        assert PipelineStage.FREEZE.successor() == PipelineStage.STRATEGIZE
        assert PipelineStage.STRATEGIZE.successor() == PipelineStage.EXECUTE
        assert PipelineStage.EXECUTE.successor() == PipelineStage.FINALIZE
        assert PipelineStage.FINALIZE.successor() is None

    def test_approval_gates(self):
        assert PipelineStage.FREEZE.is_approval_gate
        assert PipelineStage.STRATEGIZE.is_approval_gate
        assert PipelineStage.FINALIZE.is_approval_gate
        assert not PipelineStage.VALIDATE.is_approval_gate
        assert not PipelineStage.CLARIFY.is_approval_gate
        assert not PipelineStage.EXECUTE.is_approval_gate


class TestPipelineEngine:
    def _engine(self) -> PipelineEngine:
        return PipelineEngine(TaskSession())

    def test_starts_at_validate(self):
        assert self._engine().stage == PipelineStage.VALIDATE

    def test_advance_non_gate(self):
        e = self._engine()
        assert e.advance() == PipelineStage.CLARIFY
        assert e.advance() == PipelineStage.FREEZE

    def test_gate_blocks_without_consent(self):
        e = self._engine()
        e.advance()  # CLARIFY
        e.advance()  # FREEZE
        with pytest.raises(GateHeld) as exc:
            e.advance()
        assert exc.value.stage == PipelineStage.FREEZE

    def test_gate_passes_with_consent(self):
        e = self._engine()
        e.advance()  # CLARIFY
        e.advance()  # FREEZE
        assert e.advance(consent=True) == PipelineStage.STRATEGIZE

    def test_cannot_pass_terminal(self):
        s = TaskSession(stage=PipelineStage.FINALIZE)
        e = PipelineEngine(s)
        with pytest.raises(PipelineViolation):
            e.advance(consent=True)

    def test_lineage_recorded(self):
        e = self._engine()
        e.advance()
        assert len(e.session.lineage) == 1
        assert e.session.lineage[0].origin == "validate"
        assert e.session.lineage[0].target == "clarify"

    def test_finished_requires_delivery(self):
        s = TaskSession(stage=PipelineStage.FINALIZE)
        assert not PipelineEngine(s).finished

    def test_snapshot(self):
        snap = self._engine().snapshot()
        assert snap["stage"] == "validate"
        assert snap["mode"] == "sequential"
        assert snap["finished"] is False

    def test_preconditions_strategize(self):
        s = TaskSession(stage=PipelineStage.STRATEGIZE)
        issues = PipelineEngine(s).preconditions()
        assert any("requirement" in i.lower() for i in issues)

    def test_preconditions_execute(self):
        s = TaskSession(stage=PipelineStage.EXECUTE)
        issues = PipelineEngine(s).preconditions()
        assert any("plan" in i.lower() for i in issues)
