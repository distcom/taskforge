"""Tests for shell executor and canonical entrypoint."""

from pathlib import Path

import pytest

from taskforge.shell import CommandResult, ShellExecutor, detect_platform, find_shell
from taskforge.entrypoint import CanonicalRuntime


# ─── Shell ─────────────────────────────────────────────────────────────────────


class TestShellDetection:
    def test_detect_platform_returns_string(self):
        plat = detect_platform()
        assert plat in ("windows", "macos", "linux")

    def test_find_shell_returns_path(self):
        shell = find_shell()
        assert len(shell) > 0


class TestCommandResult:
    def test_ok_true(self):
        r = CommandResult(command="echo hi", returncode=0, stdout="hi\n", stderr="")
        assert r.ok is True

    def test_ok_false_on_nonzero(self):
        r = CommandResult(command="false", returncode=1, stdout="", stderr="err")
        assert r.ok is False

    def test_ok_false_on_timeout(self):
        r = CommandResult(command="sleep 99", returncode=0, stdout="", stderr="", timed_out=True)
        assert r.ok is False

    def test_output_combines(self):
        r = CommandResult(command="x", returncode=0, stdout="out\n", stderr="warn\n")
        assert "out" in r.output
        assert "warn" in r.output

    def test_to_dict(self):
        r = CommandResult(command="ls", returncode=0, stdout="files", stderr="")
        d = r.to_dict()
        assert d["ok"] is True
        assert d["command"] == "ls"


class TestShellExecutor:
    def test_run_echo(self, tmp_path: Path):
        ex = ShellExecutor(workspace=tmp_path)
        result = ex.run("echo hello")
        assert result.ok
        assert "hello" in result.stdout

    def test_run_failure(self, tmp_path: Path):
        ex = ShellExecutor(workspace=tmp_path)
        result = ex.run("exit 1")
        assert not result.ok
        assert result.returncode == 1

    def test_run_cwd(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        ex = ShellExecutor(workspace=tmp_path)
        result = ex.run("pwd", cwd=sub)
        assert "sub" in result.stdout

    def test_run_timeout(self, tmp_path: Path):
        ex = ShellExecutor(workspace=tmp_path)
        result = ex.run("sleep 10", timeout=1)
        assert result.timed_out
        assert not result.ok

    def test_run_sequence(self, tmp_path: Path):
        ex = ShellExecutor(workspace=tmp_path)
        results = ex.run_sequence(["echo a", "echo b", "echo c"])
        assert len(results) == 3
        assert all(r.ok for r in results)

    def test_run_sequence_stops_on_failure(self, tmp_path: Path):
        ex = ShellExecutor(workspace=tmp_path)
        results = ex.run_sequence(["echo a", "exit 1", "echo c"], stop_on_failure=True)
        assert len(results) == 2

    def test_verify(self, tmp_path: Path):
        ex = ShellExecutor(workspace=tmp_path)
        assert ex.verify("true") is True
        assert ex.verify("false") is False

    def test_which(self, tmp_path: Path):
        ex = ShellExecutor(workspace=tmp_path)
        # python3 should exist on any test system
        assert ex.which("python3") is not None or ex.which("python") is not None

    def test_env_override(self, tmp_path: Path):
        ex = ShellExecutor(workspace=tmp_path, env={"MY_TEST_VAR": "forge123"})
        result = ex.run("echo $MY_TEST_VAR")
        assert "forge123" in result.stdout


# ─── Canonical Entrypoint ──────────────────────────────────────────────────────


class TestCanonicalRuntime:
    def test_launch(self, tmp_path: Path):
        rt = CanonicalRuntime(skill_root=tmp_path, workspace=tmp_path)
        result = rt.launch("Build a REST API")
        assert result["status"] == "launched"
        assert result["session_id"].startswith("tf-")
        assert result["stage"] == "clarify"
        assert "governance-capsule.json" in result["proof_artifacts"]

    def test_launch_creates_artifacts(self, tmp_path: Path):
        rt = CanonicalRuntime(skill_root=tmp_path, workspace=tmp_path)
        result = rt.launch("Test task")
        session_root = Path(result["session_root"])
        assert (session_root / "governance-capsule.json").exists()
        assert (session_root / "host-launch-receipt.json").exists()
        assert (session_root / "runtime-input-packet.json").exists()
        assert (session_root / "lineage.json").exists()

    def test_freeze_requirement(self, tmp_path: Path):
        rt = CanonicalRuntime(skill_root=tmp_path, workspace=tmp_path)
        rt.launch("Build API")
        # Advance to FREEZE
        rt.engine.advance()  # clarify -> freeze
        result = rt.freeze_requirement(title="API Req")
        assert result["status"] == "frozen"
        assert result["sealed"] is True

    def test_strategize(self, tmp_path: Path):
        rt = CanonicalRuntime(skill_root=tmp_path, workspace=tmp_path)
        rt.launch("Build API")
        rt.engine.advance()  # -> freeze
        rt.freeze_requirement()
        rt.engine.advance(consent=True)  # -> strategize
        result = rt.strategize(segments=[
            {"segment_id": "s1", "objective": "Build endpoints"},
            {"segment_id": "s2", "objective": "Write tests", "depends_on": ["s1"]},
        ])
        assert result["status"] == "strategized"
        assert result["units"] == 2
        assert result["sealed"] is True

    def test_full_pipeline(self, tmp_path: Path):
        rt = CanonicalRuntime(skill_root=tmp_path, workspace=tmp_path)
        rt.launch("Task")
        rt.engine.advance()  # -> freeze
        rt.freeze_requirement()
        rt.engine.advance(consent=True)  # -> strategize
        rt.strategize()
        rt.engine.advance(consent=True)  # -> execute

        # Execute the unit
        plan = rt.session.plan
        unit = plan.units[0]
        result = rt.execute_unit(unit.unit_id, artifacts=["out.txt"], note="done",
                                 verdicts={"primary-ok": "pass"})
        assert result["status"] == "executed"

    def test_resume_missing_session(self, tmp_path: Path):
        rt = CanonicalRuntime(skill_root=tmp_path, workspace=tmp_path)
        result = rt.resume("nonexistent")
        assert result["status"] == "error"

    def test_resume_with_approval(self, tmp_path: Path):
        rt = CanonicalRuntime(skill_root=tmp_path, workspace=tmp_path)
        launch = rt.launch("Task")
        session_id = launch["session_id"]

        # Advance to freeze gate
        rt.engine.advance()  # -> freeze
        rt.freeze_requirement()
        rt._vault.save(rt.session)

        # Resume with approval
        rt2 = CanonicalRuntime(skill_root=tmp_path, workspace=tmp_path)
        result = rt2.resume(session_id, gate_token=launch["gate_token"],
                           host_decision={"decision_action": "approve"})
        # Session was at freeze (approval gate), so it should advance
        assert result["status"] in ("advanced", "resumed")

    def test_status(self, tmp_path: Path):
        rt = CanonicalRuntime(skill_root=tmp_path, workspace=tmp_path)
        rt.launch("Task")
        snap = rt.status()
        assert snap["stage"] == "clarify"
        assert "preconditions" in snap
