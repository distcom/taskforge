"""Cross-platform command executor — the shell bridge for TaskForge.

Provides a unified interface for running verification commands, build steps,
and plugin entrypoints across POSIX and Windows environments. Replaces the
need for platform-specific bridges by detecting the runtime OS and choosing
the appropriate shell automatically.

Zero external dependencies; pure stdlib (subprocess, shutil, platform).
"""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


# ─── Result Model ──────────────────────────────────────────────────────────────


@dataclass(slots=True)
class CommandResult:
    """Outcome of a shell command execution."""

    command: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    shell_used: str = ""

    @property
    def ok(self) -> bool:
        """True when the command exited successfully (code 0)."""
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Combined stdout + stderr for quick inspection."""
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.strip())
        if self.stderr.strip():
            parts.append(self.stderr.strip())
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout[:4096],
            "stderr": self.stderr[:4096],
            "timed_out": self.timed_out,
            "ok": self.ok,
            "shell_used": self.shell_used,
        }


# ─── Shell Detection ───────────────────────────────────────────────────────────


def detect_platform() -> str:
    """Return normalized platform identifier: 'windows', 'macos', or 'linux'."""
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    return "linux"


def find_shell() -> str:
    """Locate the best available shell for the current platform."""
    plat = detect_platform()

    if plat == "windows":
        # Prefer pwsh (PowerShell 7+), fall back to powershell, then cmd
        for candidate in ("pwsh", "powershell", "cmd"):
            if shutil.which(candidate):
                return candidate
        return "cmd"

    # POSIX: prefer user's SHELL, then bash, then sh
    user_shell = os.environ.get("SHELL", "")
    if user_shell and Path(user_shell).exists():
        return user_shell
    for candidate in ("/bin/bash", "/usr/bin/bash", "/bin/sh"):
        if Path(candidate).exists():
            return candidate
    return "/bin/sh"


def _build_shell_args(shell: str, command: str) -> list[str]:
    """Build the argument list for subprocess based on shell type."""
    basename = Path(shell).stem.lower()

    if basename in ("pwsh", "powershell"):
        return [shell, "-NoProfile", "-NonInteractive", "-Command", command]
    if basename == "cmd":
        return [shell, "/c", command]
    # POSIX shells
    return [shell, "-c", command]


# ─── Executor ──────────────────────────────────────────────────────────────────


class ShellExecutor:
    """Runs commands in the detected platform shell with timeout and env control.

    Usage:
        executor = ShellExecutor(workspace=Path("."))
        result = executor.run("pytest -q")
        if result.ok:
            print(result.stdout)
    """

    __slots__ = ("_workspace", "_shell", "_env_overrides", "_default_timeout")

    def __init__(
        self,
        workspace: Path | str = ".",
        *,
        shell: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> None:
        self._workspace = Path(workspace).resolve()
        self._shell = shell or find_shell()
        self._env_overrides = env or {}
        self._default_timeout = timeout

    @property
    def shell(self) -> str:
        return self._shell

    @property
    def platform(self) -> str:
        return detect_platform()

    def run(
        self,
        command: str,
        *,
        cwd: Path | str | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
        stdin_data: str | None = None,
    ) -> CommandResult:
        """Execute a command and return structured results.

        Args:
            command: Shell command string to execute.
            cwd: Working directory (defaults to workspace).
            timeout: Seconds before killing the process (defaults to instance timeout).
            env: Extra environment variables merged over os.environ.
            stdin_data: Optional string piped to stdin.

        Returns:
            CommandResult with stdout, stderr, returncode, and metadata.
        """
        work_dir = Path(cwd).resolve() if cwd else self._workspace
        effective_timeout = timeout or self._default_timeout

        # Build environment
        run_env = dict(os.environ)
        run_env.update(self._env_overrides)
        if env:
            run_env.update(env)

        args = _build_shell_args(self._shell, command)
        timed_out = False

        try:
            proc = subprocess.run(
                args,
                cwd=str(work_dir),
                env=run_env,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            return CommandResult(
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timed_out=False,
                shell_used=self._shell,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=command,
                returncode=-1,
                stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
                stderr=f"Command timed out after {effective_timeout}s",
                timed_out=True,
                shell_used=self._shell,
            )
        except OSError as exc:
            return CommandResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=f"Shell execution failed: {exc}",
                timed_out=False,
                shell_used=self._shell,
            )

    def run_sequence(
        self,
        commands: Sequence[str],
        *,
        stop_on_failure: bool = True,
        cwd: Path | str | None = None,
        timeout: int | None = None,
    ) -> list[CommandResult]:
        """Run multiple commands in order.

        Args:
            commands: Ordered list of shell commands.
            stop_on_failure: If True, halt on first non-zero exit.
            cwd: Working directory for all commands.
            timeout: Per-command timeout.

        Returns:
            List of CommandResult for each executed command.
        """
        results: list[CommandResult] = []
        for cmd in commands:
            result = self.run(cmd, cwd=cwd, timeout=timeout)
            results.append(result)
            if stop_on_failure and not result.ok:
                break
        return results

    def verify(self, command: str, *, cwd: Path | str | None = None) -> bool:
        """Quick pass/fail check — returns True if command exits 0."""
        return self.run(command, cwd=cwd).ok

    def which(self, tool: str) -> str | None:
        """Locate a tool on PATH (cross-platform shutil.which wrapper)."""
        return shutil.which(tool)
