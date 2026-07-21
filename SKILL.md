---
name: taskforge
description: TaskForge is a governed pipeline runtime that freezes requirements, bounds execution with dependency-aware waves, enforces delivery verification, and preserves resumable session state.
categories: orchestration, pipeline, governance, verification
use_case: Complex multi-step AI agent tasks requiring requirement freeze, approval gates, plugin coordination, and verified delivery
---

# TaskForge Governed Pipeline Entry

This file is the host-facing SOP for entering the TaskForge governed pipeline.
Runtime internals live in `protocols/pipeline.md`; execution discipline lives in
`protocols/execute.md`; host wrapper recipes belong in installer-generated docs.

## Trigger Contract

Enter the TaskForge pipeline before ordinary execution when:

- The user explicitly invokes `$forge`, `/forge`, or the `taskforge` skill
- The host intentionally chooses governed requirement/plan/execution closure for a complex task

Do **not** route every task into TaskForge. Lightweight questions, single-command
checks, or tasks better served by another explicitly requested skill may proceed
outside the pipeline unless the user explicitly invoked this entry.

User instructions remain highest priority. If the user's direct request narrows
or forbids a workflow, follow the user's instruction while preserving pipeline
launch and proof rules.

## Canonical Bootstrap

TaskForge is a host-syntax-neutral skill contract. Before canonical launch, do
only the minimum needed to launch:

- Resolve `skill_root` and `workspace_root`.
- Pass the current user task **verbatim** as the task specification. Do not
  summarize, rewrite, or reduce it to keywords. Preserve exact input paths,
  constraints, output roots, module dependencies, parallel boundaries, and
  acceptance criteria.

Do **not**:

- Search the workspace for canonical proof files before launch
- Inspect the repo, protocol docs, or prior run outputs before launch returns
- Simulate stages or claim canonical entry from reading this file
- Manually create `output/taskforge/<session-id>/`

Canonical entry command:

```bash
REPO_ROOT='<skill_root>'
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$PWD}"
PYTHONPATH="$REPO_ROOT/src" python3 -m taskforge.entrypoint canonical-entry \
  --skill-root "$REPO_ROOT" \
  --workspace "$WORKSPACE_ROOT" \
  --prompt "<current user task, verbatim>"
```

Only validate canonical proof artifacts after `canonical-entry` returns a
`session_root`. Proof of canonical launch requires: `session.json`,
`summary.json`, and `lineage.json` under the returned `session_root`.

If canonical launch fails, report `blocked` with the concrete failure reason
instead of simulating missing stages or proof artifacts.

## Hard Stop And Re-entry

TaskForge uses progressive governed stops at approval gates:

1. **FREEZE** — requirement contract sealed
2. **STRATEGIZE** — execution plan sealed
3. **FINALIZE** — delivery verification complete

When the pipeline halts at an approval gate, stop the current assistant turn.
Do not consume re-entry credentials until a later user message approves or
revises the current boundary.

This is a **hard runtime boundary**, not a suggestion. It overrides ordinary
host autonomy rules such as "continue until done." A detailed original request
is not approval of the frozen requirement or frozen plan.

For re-entry, inspect `summary.json → gate_control`, infer the user's intent,
and write a structured host decision JSON file:

```bash
REPO_ROOT='<skill_root>'
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$PWD}"
DECISION_JSON="$WORKSPACE_ROOT/.taskforge/tmp/host-decision.json"
mkdir -p "$(dirname "$DECISION_JSON")"

cat > "$DECISION_JSON" <<'JSON'
{
  "decision_kind": "approval_response",
  "decision_action": "approve",
  "gate_stage": "freeze",
  "plugin_organization": {
    "schema_version": "plugin_organization_v1",
    "derived_by": "agent",
    "execution_mode": "sequential",
    "segments": [
      {
        "segment_id": "seg-a",
        "goal": "...",
        "candidate_plugin_ids": ["plugin-a"],
        "acceptance_criteria": [
          {"criterion_id": "seg-a-ok", "description": "...", "method": "auto"}
        ]
      }
    ],
    "selected_plugins": [
      {"plugin_id": "plugin-a", "segment_ids": ["seg-a"], "responsibility": "...", "reason": "..."}
    ],
    "uncovered_segments": []
  }
}
JSON

PYTHONPATH="$REPO_ROOT/src" python3 -m taskforge.entrypoint canonical-entry \
  --skill-root "$REPO_ROOT" \
  --workspace "$WORKSPACE_ROOT" \
  --prompt "<current user task, verbatim>" \
  --resume-session "<session_id>" \
  --gate-token "<gate_token>" \
  --host-decision-json "$DECISION_JSON"
```

A structured approval advances to the next progressive stop. A structured
revision must include non-empty `revision_delta` and refreezes the same stage.

## Unified Pipeline Contract

TaskForge owns one runtime authority and one visible requirement/plan surface.
The fixed 6-stage pipeline is:

| # | Stage | Internal Name | Purpose |
|---|-------|---------------|---------|
| 1 | Validate | `validate` | Check prerequisites, discover existing state |
| 2 | Clarify | `clarify` | Extract structured intent from raw task |
| 3 | Freeze | `freeze` | Seal requirement contract (approval gate) |
| 4 | Strategize | `strategize` | Generate execution plan (approval gate) |
| 5 | Execute | `execute` | Carry out approved work units |
| 6 | Finalize | `finalize` | Verify delivery, produce acceptance report (approval gate) |

These stages may be light for simple work, but they are **not silently skipped**.
The full pipeline contract, stage ownership, lineage rules, execution modes,
and output inventory are defined in `protocols/pipeline.md`.

## Plugin Execution

The frozen `plugin_organization` is the only task-plugin truth. Before plan
approval, disclose segments, candidates, selected plugins and reasons, gaps,
and the sequential/parallel difference.

Only selected plugins become segment-bound execution units. The host must not
invent plugins, promote index candidates, or open another requirement/plan
surface. Selection, loading, planning, or dispatch is not contribution proof;
completion requires observable segment outcomes and the acceptance criteria
defined in `protocols/pipeline.md`.

After plan approval, the sealed `ExecutionPlan` is the only dispatch authority.
The Agent still does the real work; required failure, blocking, or missing
evidence blocks task completion.

## Quality Rules

Never claim success without evidence. Minimum invariants:

- Verify before completion
- Do not make silent no-regression claims
- Keep requirement and plan artifacts traceable to the launched session
- Emit cleanup receipts before claiming phase completion
- Expose failures, degraded status, or blocked state explicitly
- Do not add mock success paths, swallowed errors, or template-only pass results
- Do not use fallback behavior to bypass real execution or verification

## Protocol Map

Read these references only after canonical launch or when maintaining the repo:

- `protocols/pipeline.md` — governed pipeline contract and stage ownership
- `protocols/analyze.md` — planning, research, and pre-execution analysis
- `protocols/execute.md` — coding, debugging, and verification
- `protocols/inspect.md` — review and quality gates
- `protocols/coordinate.md` — parallel multi-agent orchestration
- `protocols/reflect.md` — retrospective and evidence-backed corrections

## Maintenance

- Runtime family: governed-pipeline-first
- Version: 1.0.0
- Updated: 2026-07-20
