# TaskForge Coordinate Protocol

> **What this protocol does — plain language overview**
>
> This is the multi-agent orchestration protocol. It governs how TaskForge
> coordinates multiple AI agents working on large (PARALLEL-mode) tasks.
>
> You do not need to read this to use TaskForge. It is reference material for
> contributors and advanced users building on TaskForge or investigating how
> large tasks are coordinated internally.
>
> **Key terms used below:**
> - **Coordinator/Worker lane**: One coordinator and multiple workers. Only coordinator makes the final completion claim for the whole task.
> - **Wave-sequential execution**: Large tasks are split into sequential "waves." Within a wave, independent sub-tasks may run in parallel.
> - **Scatter-gather**: Fan-out (assign task variants to multiple agents in parallel) then fan-in (collect all results and synthesize one output).
> - **Plugin work**: The current Agent follows an assigned plugin while completing one bounded segment. TaskForge assigns and validates the work; it does not run the plugin itself.
> - **Dialectic mode**: A structured design analysis where two groups of agents argue different perspectives, then a coordinator synthesizes the best ideas from both.

## Governed Pipeline Position

This protocol describes how the current Agent may coordinate PARALLEL work after
pipeline stage 5 `execute` emits the handoff packet.
It is not a separate user entrypoint.

The fixed user-facing pipeline path remains:

1. `validate`
2. `clarify`
3. `freeze`
4. `strategize`
5. `execute`
6. `finalize`

This protocol only activates after the requirement and plan are already frozen.
The active work contract is: sealed plan → handoff packet → execution results.

## Scope

Activated for PARALLEL-mode tasks that require:

- Multi-agent coordination with dependency-aware waves
- Step-level bounded parallelism for independent units
- Workflow-based execution with phases
- Long-running iterative tasks

## Coordinator/Worker Authority Model

PARALLEL delegation uses two governance scopes:

- `coordinator`: one lane per user task; owns canonical requirement/plan truth and final completion claims
- `worker`: delegated lane; inherits frozen context and emits local execution evidence

Worker lanes keep pipeline discipline but are not new top-level governors.

Runtime enforcement for worker lanes:

- Coordinator emits a delegation envelope before delegated worker execution
- Worker startup validates inherited requirement/plan truth against that envelope
- Worker records delegation validation before starting the bounded unit

Worker lanes must not:

- Create a second canonical requirement surface
- Create a second canonical execution-plan surface
- Emit final completion claims for the full coordinator task
- Change the coordinator-frozen `plugin_organization`

## Agent Work Coordination Truth

- `SEQUENTIAL` work is completed serially by the current Agent; this protocol covers the PARALLEL case
- PARALLEL execution is wave-sequential by dependency
- Parallel work is step-scoped and bounded to independent units only
- The Agent-confirmed `plugin_organization` is frozen before planning
- Segment plugin work is phase-bound: `pre_execution`, `in_execution`, `post_execution`, `verification`
- Work-unit lanes may join bounded parallel windows only when their write scopes are disjoint

### Role Division

| Concern | Provider |
|---------|----------|
| Agent spawning | Host-native agent API |
| Task assignment & follow-up | Host-native messaging |
| Agent synchronization | Barrier/wait primitives |
| Agent shutdown | Host-native lifecycle |
| Workflow definition (optional) | External orchestration layer |
| Session persistence (optional) | Session vault |

## Anti-Drift Handoff Contract

Every PARALLEL subtask handoff should preserve:

- The primary objective
- The declared scope
- The current completion-state target
- Any report-only anti-drift warnings already known
- Whether the work is a bounded specialization or a generalized capability claim

Coordinator rules:

- Workers may surface report-only warnings, but must not invent a new hard gate
- If an existing approved policy or failed gate truly blocks progress, cite that exact surface
- Aggregation must not flatten bounded-specialization outputs into generalized completion claims
- When a plugin is assigned, preserve the relevant instructions from its `PLUGIN.md`
- Only coordinator aggregation may publish final completion claims for the full task

## Plugin Work

A selected plugin guides a bounded segment. TaskForge organizes the work and checks the
returned result; it does not directly run the plugin.

Rules:

- TaskForge keeps final control of stage order, plan authority, and completion claims
- Index candidates may be surfaced as audit evidence, but they never auto-promote into approved work units
- When segment plugin work exists, `execute` must emit one handoff packet naming each segment, work-unit role, assigned plugin, and `plugin_entry`
- The current Agent reads each assigned `PLUGIN.md` and completes its bounded work under the frozen requirement context
- The Agent returns expected outputs, result summaries, failures, blocking reasons, and segment states
- Each work unit carries phase binding, lane policy, write scope, and review mode
- A new plugin can enter execution only through a user-approved plan revision

## Orchestration Pattern

### Scatter-Gather Fan-out/Fan-in

- **Fan-out**: assign one subtask per role/agent
- **Fan-in**: one barrier per milestone
- **Gather**: coordinator updates shared memory once per milestone

Rule of thumb: **one milestone == one scatter-gather round**.

### Dispatch Envelope (Recommended)

When assigning subtasks, wrap each in a small envelope:

```yaml
session_id: "{session_id}"
phase: "plan|investigate|implement|verify"
owner: "{role_name}"
deadline_minutes: 15
retry_budget: 1
deliverable:
  format: "markdown"
  sections: ["summary", "evidence", "risks", "next_steps"]
```

### Task Contract (Subtask Interface / DoD)

Before fan-out, each subtask SHOULD include:

```yaml
task_id: "T-1"
goal: "One-sentence, testable outcome"
scope:
  in: ["Allowed modules/files/APIs"]
  out: ["Explicit non-goals"]
inputs:
  - "Facts, constraints, and required context"
outputs:
  - "Artifacts (file paths) or result shape"
definition_of_done:
  - "Acceptance criteria (verifiable)"
verification:
  - "Commands/tests/checks to run"
status: "todo|doing|blocked|done"
```

Contract rules:

- Prefer `verification` that is command-shaped (copy/paste runnable)
- If required info is missing, return `status=blocked` (do not guess)
- If the subtask has an assigned plugin, keep the contract narrow enough that the worker can follow that `PLUGIN.md`

## Shared Memory Contract (3-Tier)

1. **User ↔ Coordinator memory**: the main conversation (source of truth for user intent + decisions)
2. **Coordinator ↔ Worker private memory**: per-worker working notes (NOT broadcast)
3. **Shared agents memory**: a bounded, refreshed "what we know so far" block owned by coordinator

Rules:

- Update only at milestone boundaries, not on every message
- Prefer facts + artifacts over prose
- Hard cap: summarize and overwrite when it grows too large

## Reliability & Failure Handling

1. **Timeout**: If a worker misses its deadline, send one reminder. If still no response: proceed with partial results and record the missing deliverable.
2. **Retry**: Respect `retry_budget`. A retry must change something (prompt, scope, context, or role). If exhausted: degrade scope with explicit hazard alert.
3. **Contradiction**: When two workers disagree, coordinator demands concrete evidence before choosing.
4. **Degraded Mode**: If multiple workers fail, do not silently fall back. Emit a standalone hazard alert, reduce parallelism, and mark the result non-authoritative.

## Staged Confirmation

Always confirm with user at these points:

1. After workflow definition (before spawning agents)
2. After each major phase completion
3. Before final integration of results
4. Before committing changes

## Wave Contract (PARALLEL Mode)

When PARALLEL mode is active, generate wave structure:

- `wave_id`
- `units` (task ids / owners)
- `depends_on`
- `entry_criteria`
- `exit_criteria`
- `verify_commands`

Execution semantics:

1. Independent units may run in bounded parallel within a wave
2. Waves run sequentially by dependency
3. Verification gates must pass before advancing to next wave

## Dialectic Mode

Structured multi-perspective design analysis. Activated only when user explicitly requests it.

### When to Use

- Multiple viable architectural approaches with unclear trade-offs
- High-stakes design decisions where blind spots are costly
- User explicitly requests dialectic analysis

### Not For

- Implementation tasks (use standard coding flow)
- Single correct answer questions
- Trivial design choices (use analyze.md B2 Self-Check instead)
- Debugging

### Execution Steps

1. **Prepare context** — coordinator reads relevant code/docs, formulates the design question
2. **Create team** — spawn 4 agents (2 per perspective group)
3. **Send role prompts** — each agent receives perspective + 6-phase workflow
4. **Context isolation** — Group A and Group B receive different context slices
5. **Execute** — agents run 6-phase workflow (propose → reflect → synthesize → compare → reflect → final)
6. **Collect** — coordinator waits for all final outputs
7. **Timeout handling** — proceed with minimum 2 outputs from different groups
8. **Output processing** — extract consensus, divergence, blind spots, synthesize
9. **User decision** — present synthesis; user accepts, chooses, or requests deeper analysis
10. **Shutdown** — close all agents

## Conflict Avoidance

- Do NOT use multi-agent fan-out for SEQUENTIAL tasks
- Only one team active per project at a time
- Do NOT bypass canonical re-entry; PARALLEL work must return complete results before `finalize`
- Worker file write scopes must be pre-partitioned to avoid overwrites
