"""TaskForge — High-performance task orchestration engine for AI agents.

Decomposes complex requests into structured pipelines, coordinates local plugins,
enforces delivery verification, and preserves resumable state across sessions.

Pipeline stages:
    1. VALIDATE  — Check workspace integrity and preconditions
    2. CLARIFY   — Extract structured intent from raw task description
    3. FREEZE    — Lock requirements into an immutable contract
    4. STRATEGIZE — Build execution plan with plugin assignments
    5. EXECUTE   — Run approved work units with dependency tracking
    6. FINALIZE  — Verify delivery and emit acceptance report
"""

__version__ = "1.0.0"
__author__ = "TaskForge Contributors"
