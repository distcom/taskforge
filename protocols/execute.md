# TaskForge Execute Protocol

> **What this protocol does — plain language overview**
>
> This is the execution protocol. It governs how TaskForge writes code, fixes bugs,
> and runs tests — specifically during Stage 5 (`execute`) of the pipeline.
>
> You do not need to read this to use TaskForge. It is reference material for advanced
> users and contributors who want to understand how execution decisions are made.
>
> **Key terms used below:**
> - **SEQUENTIAL / PARALLEL**: Execution topology. SEQUENTIAL = one unit at a time; PARALLEL = dependency-ready units within a wave run concurrently.
> - **Closure-First Contract**: The principle of reaching a working state quickly before expanding scope. Two probe steps + one verification step early in any task.
> - **Proxy-goal drift**: When the system optimizes a visible metric instead of the actual goal.
> - **Evidence-Based Communication**: Never say "should work"; always show [Command] → [Output] → [Claim].
> - **Completion Gate**: Identify what to verify → run it → read output → confirm correctness → mark complete.

## Governed Pipeline Position

This protocol is the execution surface for pipeline stage 5 `execute`.
It does not replace the governed pipeline entry or skip the earlier planning stages.

The governed pipeline path remains:

1. `validate`
2. `clarify`
3. `freeze`
4. `strategize`
5. `execute`
6. `finalize`

`execute.md` assumes stages 1 through 4 have already produced:

- A frozen requirement document
- A sealed execution plan
- A confirmed execution mode
- Approved selected plugins when bounded plugin help will be used
- A frozen downstream delivery-acceptance contract

The job here is to execute, verify, and hand off cleanly to `finalize`.

## Anti-Drift Execution Guardrails

During execution:

- Do not optimize a visible proxy signal while quietly abandoning the frozen objective
- Do not absorb validation material into product truth without explicit approval
- Do not relabel a bounded fix as generalized completion unless the proof bundle supports that claim
- Do preserve valid specialization when the requirement or plan intentionally scoped the work that way

## Scope

Activated when the task requires writing or modifying code:

- Feature implementation
- Bug fixing and debugging
- Code refactoring
- Test writing

## Closure-First Contract (2 Probes + 1 Verify)

Primary objective: **avoid dead-air** and reach a **minimal closed loop** quickly.

### Contract

Within the first 3 actions of an execution task:

1. **Probe #1 (fast):** establish workspace shape and likely entry points
2. **Probe #2 (targeted):** search the most relevant keyword(s) from the user prompt
3. **Verify #1 (smallest relevant):** pick 1 verification command that can falsify your change
   - Coding: run the narrowest test (`pytest -q`, `npm test`, etc.)
   - Debug: reproduce the bug / run the failing test / run the minimal build step

## Execution by Complexity

### Simple Tasks

1. Pre-implementation: write tests first (RED → GREEN → REFACTOR)
2. Implementation: native tools
3. Post-implementation: auto-review triggers
4. If security-relevant: security review

### Multi-Step Tasks (SEQUENTIAL)

1. Ensure design exists (from analyze.md protocol)
2. Execute planned units in native serial order
   - Sequence-first execution from the sealed plan
   - No blanket multi-agent fan-out
3. Optional delegated units must remain bounded and explicitly planned
4. Track progress across units
5. Final review with verification-before-completion

### Complex Tasks (PARALLEL)

Defer to coordinate.md protocol (wave-sequential orchestration with bounded parallel units).

## Debug Mode

| Complexity | Approach |
|-----------|----------|
| Simple | Structured 4-phase root cause debugging |
| Multi-step | Parallel investigation with systematic debugging |
| Any | Build-specific errors use root-cause flow |

## Quality Patterns: Core Tier

### Always-On Patterns

- **Evidence-Based Communication**: NEVER say "should work", "probably fine". ALWAYS use [Command] → [Output] → [Claim] format.
- **Completion Gate**: IDENTIFY what to verify → RUN verification → READ output → VERIFY correctness → MARK COMPLETE.
- **Learning Capture**: Record routing decision + injection effectiveness + improvements.

### Task-Type-Specific Patterns

| Task Type | Additional Patterns | Reason |
|-----------|-------------------|--------|
| Debug | Root Cause Discipline + Scientific Method | Prevents blind fix attempts |
| Coding | 6-Phase Quality Pipeline | Ensures code quality gates |
| Research | Evidence Chain | Ensures cited sources |
| Planning | Structured Analysis | Systematic decomposition |

### 6-Phase Quality Pipeline (Coding Tasks)

Build → Types → Lint → Tests → Security → Diff → [READY / NOT READY]

### Root Cause Discipline (Debug Tasks)

Iron Law: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.
Complete Phase 1 (root cause investigation) before proposing fixes.
If 3+ fix attempts fail, STOP and question the architecture.

### Scientific Method (Debug Tasks)

Form SINGLE hypothesis. State clearly: I think X because Y.
Make SMALLEST possible change to test. One variable at a time.

### Behavioral Tone (All Complexity Levels)

- **Conclusion-First Output**: Deliver the result first, then provide the evidence chain.
- **Exploration Budget**: Consecutive exploratory tool calls capped at 8. Beyond that: summarize known info → request user direction.
- **No Self-Commentary**: Do not explain difficulty. Deliver engineering results directly.

## Quality Gates

Before marking code task complete:

1. All tests pass
2. Code review completed
3. No security vulnerabilities (for user-facing code)
4. No debug statements left in production code
5. Delivery-acceptance evidence is sufficient for the claimed completion wording
6. A handoff bundle exists for pipeline stage 6 `finalize`

## Required Handoff To `finalize`

Execution is not complete at the last passing test.
Before leaving this protocol, write or preserve the evidence needed for finalize:

- Verification commands and results
- Changed artifact list
- Temp artifact list
- Process cleanup notes when relevant
- Manual spot-check status when the frozen requirement declared them
- Completion-language downgrade notes when delivery truth is not fully passing
- Open risks or deferred follow-ups

`finalize` is mandatory and owns the final closure receipt.

## Conflict Avoidance

- Do NOT use multi-agent fan-out for simple/multi-step coding tasks
- Do not self-introduce new fallback logic during implementation unless the active requirement explicitly approves
- Do not convert primary-path failure into fake success by swallowing exceptions
- Prefer explicit failure exposure over convenience recovery
- If a requirement explicitly permits fallback behavior, keep it explicit, document the trigger, and make the path easy to disable
