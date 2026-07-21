# TaskForge Analyze Protocol

> **What this protocol does — plain language overview**
>
> This is the planning and analysis protocol. It governs how TaskForge clarifies
> requirements, designs architecture, and writes execution plans — primarily during
> Stages 2–4 of the pipeline.
>
> You do not need to read this to use TaskForge. It is reference material for those
> who want to understand how the system thinks before it acts.
>
> **Key terms used below:**
> - **Phase A / Phase B**: Internal protocol phases. Phase A = pre-execution analysis (classify the task); Phase B = planning and design execution (write the plan).
> - **Proxy-goal drift**: When the system optimizes a visible metric instead of the actual goal. Planning is the cheapest place to prevent this.
> - **Brownfield context**: An existing codebase that already has its own architecture and conventions — as opposed to a blank-slate new project.
> - **Dialectic mode**: A structured multi-perspective design analysis: two groups of agents argue different viewpoints, then a coordinator synthesizes the best ideas from both.

## Governed Pipeline Position

This protocol is not a standalone user entrypoint.
It is the planning and analysis surface used inside the governed pipeline defined by `protocols/pipeline.md`.

The user-facing pipeline path remains fixed:

1. `validate`
2. `clarify`
3. `freeze`
4. `strategize`
5. `execute`
6. `finalize`

`analyze.md` primarily owns stages 2 through 4:

- `clarify`: clarify intent or infer assumptions
- `freeze`: freeze the requirement contract
- `strategize`: generate the executable plan

## Anti-Drift Planning Guardrails

Planning is the first place where proxy-goal drift can be prevented cheaply.

- Freeze the primary objective before discussing implementation convenience
- Name non-objective proxy signals explicitly
- Keep validation material in a validation role
- Declare the intended scope and completion state honestly
- Preserve bounded specialization as a valid outcome when generalization is not yet proven

## Closure-First Preflight (2 Probes + 1 Verify)

Even in planning/research, the primary failure mode is stalling.
Run a minimal closed loop early: probe context → locate evidence → verify assumptions.

### Contract (No Code Writing)

Within the first 3 actions:

1. **Probe #1 (fast):** inspect workspace shape / available docs
2. **Probe #2 (targeted):** search for the most relevant keyword(s) and existing plans/specs
3. **Verify #1:** validate at least 1 key assumption against an artifact (repo evidence or 2 independent external sources)

## Scope

### Phase A: Pre-Execution Analysis

Activated when a task needs structured analysis before execution:

- Task could be classified as multiple types → clarify via analysis
- User explicitly asks to "analyze", "think through", or "evaluate"
- Compound task requiring decomposition into phases

### Phase B: Planning & Design Execution

Activated for planning, design, and research tasks:

- Requirements analysis and discovery
- Architecture and system design
- Research and investigation
- Option evaluation and comparison

## Phase A: Pre-Execution Analysis

### A1: Problem Framing

- What exactly is being asked? What are the constraints?
- Is this a single task or compound task?

### A2: Structured Analysis (by estimated complexity)

| Complexity | Method | Stage |
|-----------|--------|-------|
| Simple | Concise risk and objective check | `clarify` |
| Multi-step | Structured options, constraints, and acceptance criteria | `clarify` → `freeze` |
| Complex | Socratic clarification plus explicit tradeoff comparison | `clarify` → `strategize` |
| Code-heavy | Repository evidence probe before plan text | `validate` → `strategize` |

### A3: Classification Decision

Based on analysis output, determine:

- Final complexity (may differ from initial estimate)
- Task type (plan/code/review/debug/research)
- Compound task? → decompose
- Execution mode: SEQUENTIAL vs PARALLEL

### Compound Task Decomposition

| Complexity | Method | Stage |
|-----------|--------|-------|
| Simple | Short serial checklist | `strategize` |
| Multi-step | Phase plan with owners, verification, and rollback notes | `strategize` |
| Complex | Wave-sequential plan with bounded parallel windows | `strategize` → `execute` |

Output: ordered phases, each with protocol, quality gate, and handoff context.

## Phase B: Planning & Design Execution

### B1: Requirements Discovery

- Ask one high-value clarification when ambiguity blocks requirement quality
- Compare options before choosing an implementation direction
- For complex work, first explain SEQUENTIAL versus PARALLEL and stop for the user's mode choice
- After specialist plugins are recommended, ask for confirmation before those plugins become execution obligations
- Output clarified requirements, assumptions, acceptance criteria, and user-visible tradeoffs

Governed pipeline requirement:

- Persist an intent contract that can be turned into a frozen requirement
- Do not merge mode confirmation, plugin-use confirmation, and requirement approval into one prompt

### B2: Architecture Design (if needed)

- Cognitive personas (architect, security, frontend, backend)
- Output: Architecture diagrams, component design, data flow

### B2 Self-Check (All Design Tasks)

After generating initial design:

1. List 3 ways this design could fail in production
2. If any failure mode suggests a fundamentally different approach → generate alternative
3. If alternative is equally viable → present both to user with trade-off comparison
4. If no viable alternative → proceed with original + document failure modes as risks

### B3: Plan Documentation

Generates plan at `output/taskforge/<session-id>/plan.json`

Minimum governed-pipeline contents:

- Confirmed execution mode
- Approved selected plugins, clearly separated from final material-use evidence
- Wave or batch structure
- Verification commands
- Rollback rules
- Phase cleanup expectations

### B4: Deep Research (if needed)

- Multi-agent parallel research workflow
- Output: Research findings with sources

### B5: Brownfield Context Hook (Optional, Complex Planning Only)

Run this hook only when:

1. Current task type is `planning`
2. Current complexity is multi-step or complex
3. An existing codebase is involved

Hook steps:

1. **Brownfield context snapshot** — build a light snapshot of stack, architecture, conventions, concerns
2. **Assumption preflight** — produce a concise assumptions list before writing the final plan
3. **Handoff** — carry assumptions + brownfield context into B3 output

## Research Mode

When task is purely research (no implementation):

1. Skip B1 unless scope is unclear
2. Go directly to B4 (deep research)
3. Store findings in session state

## Conflict Avoidance

- Do NOT write code during this protocol (respect HARD-GATE)
- Do not create a second requirement or plan surface outside the active session
- Analysis (Phase A) completes BEFORE implementation begins, not in parallel with execution
- Any planning aid must feed the canonical requirement and plan surfaces rather than invent parallel artifacts

## Transition to Implementation

After design is approved:

1. SEQUENTIAL: Switch to execute.md serial native execution
2. PARALLEL: Switch to coordinate.md protocol (wave-sequential execution with bounded parallel units)
3. Always carry the plan document forward as context
4. Execution must hand off into pipeline stage 5 `execute`, not bypass directly into ad-hoc coding
