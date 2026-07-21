# TaskForge Pipeline Protocol

> **What this protocol does — plain language overview**
>
> Every time you invoke `/forge` or `$forge`, the system runs this 6-stage pipeline.
> You do not need to read this document to use TaskForge — it is reference material
> for contributors and advanced users who want to understand the runtime internals.
>
> **The 6 stages in plain terms:**
>
> | Stage | Internal name | What happens |
> |:---:|:---|:---|
> | 1 | `validate` | Check prerequisites and discover existing state |
> | 2 | `clarify` | Clarify what you actually want (ask questions or infer) |
> | 3 | `freeze` | Lock the agreed requirements into a sealed contract |
> | 4 | `strategize` | Write the execution plan with plugin assignments |
> | 5 | `execute` | Hand the approved plan to the current Agent for work |
> | 6 | `finalize` | Verify delivery and produce a final acceptance report |
>
> **Key terms used below:**
> - **Plugin organization**: the Agent splits approved work into segments, searches declared local roots, reads candidate `PLUGIN.md` files, and freezes `plugin_organization` before planning.
> - **Coordinator/Worker lane**: In multi-agent tasks, "coordinator" owns the pipeline; "worker" lanes perform bounded units. Only coordinator makes final completion claims.
> - **Frozen requirement/plan**: Once you approve the requirements or plan, they are locked — the system will not silently change scope.
> - **Proof bundle**: Evidence that a task was actually completed — test results, output logs, verification commands.
> - **Silent fallback**: Quietly switching to a degraded path without telling the user — this is explicitly forbidden.

## Pipeline Identity

`taskforge` is one skill contract across all hosts:

- `/forge`
- `$forge`
- agent-invoked `taskforge`

These are syntax variants for the same governed pipeline, not separate entrypoints.

## Contract Priorities

1. Pipeline authority stays intact — single owner, single truth surface.
2. User-facing pipeline path stays fixed.
3. `SEQUENTIAL` / `PARALLEL` are execution modes, not separate public entry commands.
4. Requirement freezing happens before plan execution.
5. Finalize is mandatory before a phase is considered complete.
6. Silent fallback and silent degradation are forbidden.
7. Fallback success is non-authoritative unless a requirement explicitly approves otherwise.
8. Fake-success behavior is forbidden: the runtime must not swallow errors, emit mock completion, or template a pass result when the primary path failed.
9. New fallback behavior may exist only when the active requirement explicitly approves it, and it must remain explicit, traceable, and easy to disable.
10. `SEQUENTIAL` hands off units serially; `PARALLEL` may group only dependency-ready units with disjoint write scopes.

## Official Runtime Mode

### `interactive_governed`

The only supported mode.

- Ask direct high-value questions when needed
- Freeze a requirement document with user-visible assumptions
- Allow approval boundaries before execution

## Fixed 6-Stage Pipeline

### Stage 1: `validate`

Purpose:

- Verify workspace prerequisites and pipeline readiness
- Discover active requirement or plan artifacts from prior sessions
- Detect conflicting dirty-state conditions

Required outputs:

- Validation receipt
- Workspace-state summary

### Stage 2: `clarify`

Purpose:

- Transform raw task text into a structured intent contract

Required fields:

- objective
- expected_outputs
- constraints
- success_criteria
- exclusions
- assumptions
- questions
- execution_mode

Required user-visible confirmation gates:

- `mode_confirmation`: explain SEQUENTIAL versus PARALLEL in plain language, recommend one mode, and do not ask the user to choose until both options show the task-specific workflow, candidate plugin names, and each candidate's responsibility.
- `plugin_use_confirmation`: after candidate plugins are recommended and before they become approved segment assignments, inform the user and stop for approval, rejection, or revision.

### Stage 3: `freeze` (Approval Gate)

Purpose:

- Freeze the single requirement source for the session

Rules:

- Write under `output/taskforge/<session-id>/requirement.json`
- Execution and review trace back to this document
- Freeze downstream delivery semantics here, including acceptance criteria and verification methods

### Stage 4: `strategize` (Approval Gate)

Purpose:

- Generate the execution plan under `output/taskforge/<session-id>/plan.json`

Required contents:

- Frozen `plugin_organization`
- Task segments and per-segment candidate plugins
- Final selected plugins with responsibilities and reasons
- Uncovered segments
- Approved segment dependencies, execution modes, work units, write scopes, and acceptance criteria
- Every segment freezes at least one acceptance criterion with a unique `criterion_id`, non-empty `description`, and `method` of `auto` or `manual`
- Wave or batch structure (PARALLEL mode)
- Verification commands
- Delivery acceptance plan
- Rollback strategy
- Cleanup expectations

### Stage 5: `execute`

Purpose:

- Compile the frozen plan into work the current Agent can perform
- Stop with Agent control until the complete segment result returns through canonical re-entry

Rules:

- The sealed `ExecutionPlan` controls topology and is the only work authority after plan approval
- `execute` compiles the plan into a handoff packet, marks it `action_required`, and gives control to the current Agent
- Every handoff unit names its unit, segment, assigned plugin, `plugin_entry`, responsibility, expected outputs, verification, dependencies, and write scope
- The current Agent performs `SEQUENTIAL` units serially; for `PARALLEL`, it may group only dependency-ready units with disjoint write scopes
- The handoff may contain only work units from the sealed plan
- TaskForge does not execute plugins or create completion results on the Agent's behalf
- The Agent reads every assigned `PLUGIN.md`, follows that plugin's instructions, does the real work, writes the complete result, and returns it through canonical re-entry for acceptance
- Canonical re-entry validates the source session, sealed plan, complete work-unit bindings, and criterion results before `finalize`
- Incomplete, failed, or blocked required segments cannot enter successful finalize or support a completion claim
- Dangerous bulk deletion and blind recursive wipe commands against managed roots are forbidden during governed execution

### Stage 6: `finalize` (Approval Gate)

Purpose:

- Close the phase in a clean, auditable way

Minimum actions:

- Accept the complete, plan-matched execution results before successful finalize
- Temp artifact cleanup
- Workspace hygiene pass
- Cleanup receipt write
- Delivery-acceptance report write with 6 structured checks

## Protocol Delegation

The runtime may delegate stage internals to existing protocols:

- `analyze.md` for analysis, planning, and research
- `execute.md` for execution, debugging, and verification
- `inspect.md` for quality review
- `coordinate.md` for PARALLEL orchestration
- `reflect.md` for retrospective learning after work closure

Delegation must not bypass the fixed stage order.

## Plugin Candidate Audit Rules

- Candidate audit runs inside canonical TaskForge; it may expose candidates for inspection, but it does not choose task plugins, bind execution, or control stage progression
- Candidate scores and rankings are audit metadata only
- Candidate audit must not populate `plugin_organization`, add approved work, or block stage progression
- Fallback or degraded paths must emit an explicit hazard alert rather than a silent warning

## Authority Boundary Contract

Layer ownership:

- TaskForge governed pipeline: public entry, stage order, requirement freeze, plan traceability, Agent handoff, segment-result acceptance, cleanup receipts
- Plugin candidate audit: compatibility evidence inside the governed pipeline
- Host bridge: hidden governance context attachment only
- Process-method layers: workflow discipline only, never a second runtime surface

Explicitly forbidden:

- A second visible runtime entry ritual
- A second routing authority layer
- A second requirement truth surface
- A second plan truth surface

## Coordinator/Worker Hierarchy Contract

During PARALLEL Agent work, delegation is hierarchical:

- `coordinator` lane:
  - Owns canonical requirement freeze
  - Owns canonical plan freeze
  - Owns the frozen `plugin_organization` and its Agent handoff projection
  - Owns final completion claim for the full task
- `worker` lane:
  - Inherits coordinator-frozen requirement and plan context
  - Performs bounded delegated units
  - Returns bounded segment results and escalation requests only

Worker lanes are forbidden from:

- Writing a second canonical requirement document
- Writing a second canonical execution plan
- Issuing final completion claims for the coordinator task
- Changing the frozen `plugin_organization` without coordinator approval

## Artifact Contract

Expected runtime artifacts under `output/taskforge/<session-id>/`:

- `session.json` — full session state
- `summary.json` — compact status summary with gate control
- `lineage.json` — ordered stage-transition ledger
- `requirement.json` — frozen requirement contract
- `plan.json` — sealed execution plan
- `handoff.json` — agent-execution handoff packet
- `execution-results.json` — terminal segment results from Agent
- `delivery-report.json` — acceptance verification report
- `cleanup-receipt.json` — finalize cleanup evidence

## Success Criteria

The governed pipeline is considered healthy only when:

- The 6-stage sequence is preserved
- Requirement and plan artifacts exist
- Accepted Agent segment results trace back to the approved plan and handoff
- Cleanup is recorded
- No success claim is made without verification evidence
- No fallback or degraded path is presented as equivalent success
- Any fallback or degraded path emits a standalone hazard alert
