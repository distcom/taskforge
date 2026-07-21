# TaskForge Reflect Protocol

> **What this protocol does — plain language overview**
>
> This is the retrospective protocol. It defines how TaskForge reviews completed
> work, identifies recurring problems, and proposes improvements to your workflow.
>
> You do not need to read this to use TaskForge. It activates after `finalize`
> when you want to reflect on what happened and improve for next time.
>
> **Key terms used below:**
> - **CER (Context Evidence Report)**: A structured output format for what went wrong and how to prevent it. Structure: Pattern → Evidence → Root Cause → Intervention → Guardrail → Confidence.
> - **CF-1 to CF-6 (Context Failure classes)**:
>   CF-1 = attention dilution (AI lost track of early context in a long session);
>   CF-2 = context poisoning (stale or contradictory state);
>   CF-3 = observation bloat (tool outputs dominating useful context tokens);
>   CF-4 = memory mismatch (wrong content retrieved);
>   CF-5 = tool contract ambiguity (mismatched tool input/output expectations);
>   CF-6 = evaluation blind spot (no rubric or weak verification).
> - **Proxy-goal drift**: When the system optimizes a visible metric instead of the actual goal.
> - **report_only**: A warning recorded for review purposes that does not automatically block any action.

## Scope

Activated when the user wants to:

- Review and reflect on recent project work
- Identify workflow optimization opportunities
- Detect recurring error patterns and design preventive hooks
- Diagnose context quality failures in long-running tasks
- Discover reusable patterns for future projects
- Decide whether to create new plugins, agents, or hooks
- Conduct a collaborative improvement discussion

## Governed Pipeline Position

This protocol is a retrospective and learning surface, not the primary user entrypoint.
It can be invoked after governed execution completes, or used as part of a cleanup
and learning pass after pipeline stage 6 `finalize`.

The fixed pipeline path remains:

1. `validate`
2. `clarify`
3. `freeze`
4. `strategize`
5. `execute`
6. `finalize`

`reflect.md` never replaces those stages.
It consumes their receipts and artifacts to improve future runs.

## Anti-Proxy-Goal-Drift Retro Lens

Retro treats proxy-goal drift as a first-class learning failure mode.

Core retro questions:

1. What objective did the work claim to serve?
2. Which proxy signals were optimized instead?
3. Did validation material stay outside implementation truth?
4. Was the repair made at the intended abstraction layer?
5. Was the final completion state honest for the actual scope and evidence?
6. Was a bounded specialization preserved honestly?

## 5-Phase Architecture

Phase 1: GATHER → Phase 2: ANALYZE → Phase 3: DISCUSS → Phase 4: DECIDE → Phase 5: ACT

---

## Phase 1: GATHER (Data Collection)

### 1.1 Session History Retrieval

- Read recent session files from `output/taskforge/`
- Extract: tasks performed, files modified, tools used

### 1.2 Session Activity Review

- Read recent session vault entries
- Extract stage transitions, outcomes, timing

### 1.3 Error Log Collection

- `git log --oneline -20` (recent commits, especially fix/revert)
- Search session traces for error, fix, bug, revert patterns

### 1.4 Context Signal Collection

- Count retries, fallback frequency, and compaction events
- Measure large-output tool calls and repeated low-value observations
- Detect route instability (same intent, different outcomes)

#### Default Trigger Thresholds

| Signal | Metric | Default Threshold | Trigger Meaning |
|--------|--------|-------------------|-----------------|
| Retry spike | `retry_count_10m` | `>= 3` | Execution stuck in retry loop |
| Fallback frequency | `fallback_rate` | `>= 0.20` | Primary path reliability degraded |
| Context pressure | `context_pressure` | `>= 0.75` | Context budget at risk |
| Route instability | `route_stability` | `< 0.80` | Same intent routes differently |

Present structured data collection report before proceeding.

---

## Phase 2: ANALYZE (Structured Analysis)

### 2.1 Session Reflection

- Analyze recent sessions for problems solved, patterns established

### 2.2 Problem Pattern Detection

- Scan for user frustration signals, repeated errors, tool misuse
- Severity categorization (high/medium/low)

### 2.3 Workflow Frequency Analysis

- Most frequently used tool combinations
- Repeated multi-step workflows (automation candidates)

### 2.4 Cross-Session Trend Analysis

- Synthesize data from 2.1–2.3
- Error trends, activity domains, time sinks

### 2.5 Context Failure Typing

Classify failures into one or more classes:

- CF-1: Attention dilution / lost-in-middle
- CF-2: Context poisoning (stale or contradictory state)
- CF-3: Observation bloat (tool outputs dominate useful tokens)
- CF-4: Memory mismatch (retrieval irrelevant/missing)
- CF-5: Tool contract ambiguity (tool schema/intent mismatch)
- CF-6: Evaluation blind spot (no rubric, weak verification)

### 2.6 Intervention Design

Map each failure class to interventions:

- Compaction strategy update (what to compress, when)
- Observation masking rules (what to retain vs reference)
- Context partitioning for PARALLEL tasks
- Memory indexing/persistence policy adjustments
- Evaluation rubric and verification gate hardening

### 2.7 Anti-Drift Classification

For governed retros, classify whether the run showed:

- Objective / proxy substitution
- Validation-material contamination
- Abstraction-layer mismatch
- Completion-state overclaim
- Specialization erasure

Each classification ends in one of:

- `aligned`
- `report_only_warning`
- `completion_language_corrected`
- `specialization_confirmed`
- `escalate_via_existing_policy`

---

## Phase 3: DISCUSS (Interactive Discussion)

### Interaction Style: Pedagogical Advisory

**Proactive Engagement:**

- Actively identify improvement opportunities
- Use guiding questions to surface insights
- For each finding, provide concrete improvement path

**Data-Grounded Suggestions:**

- Every suggestion references specific evidence from Phase 2
- When uncertain, acknowledge uncertainty explicitly

**Discussion Topics:**

- Workflow review: automation candidates, efficiency improvements
- Error prevention: hooks, pre-commit checks
- Context quality: compression policy, masking policy
- Tool effectiveness: routing accuracy, fallback frequency
- Future planning: templates, plugins, new tools
- Completion honesty: whether the reported end-state matched objective and proof

**Respectful Autonomy:**

- User makes all final decisions
- Explicitly ask for confirmation before Phase 4

---

## Phase 4: DECIDE (Decisions)

### Decision Categories

| Category | Action Type |
|----------|------------|
| Recurring workflow | Create plugin |
| Error prevention | Create hook or pre-commit check |
| Behavioral pattern | Create/update learning note |
| Context quality | Update retro policy/playbook |
| Completion honesty correction | Update review/closure wording |
| Knowledge capture | Persist memory |
| Complex automation | Create agent or orchestration template |

### User Confirmation Gate

Present all decisions as prioritized list.
User approves, modifies, or rejects each before Phase 5.

---

## Phase 5: ACT (Execute Improvements)

### 5.1 Create Hooks

- Define trigger, matcher, action
- Create rule file or pre-commit hook

### 5.2 Create Plugins

- Define plugin name, description, trigger
- Write PLUGIN.md with proper frontmatter

### 5.3 Update Configuration

- Direct file edits to pipeline config, roots.json, protocol docs

### 5.4 Persist Knowledge

- Persist explicit project decisions
- Persist long-term entities/relations for cross-session retrieval

### 5.5 Generate CER Report

Generate structured report:

- `output/retro/YYYY-MM-DD-<topic>-cer.md`
- `output/retro/YYYY-MM-DD-<topic>-cer.json`

### 5.6 Compare CER Across Iterations (Optional)

- Compare baseline and current CER reports
- Output delta summaries
- Track trend fields: pattern delta, fallback_rate delta, stability delta

---

## Context Evidence Report (CER) Output Contract

Every analysis MUST output this schema:

1. **Pattern**: failure class tags (CF-1..CF-6)
2. **Evidence**: concrete observations (commands, outputs, events)
3. **Root Cause**: why the pattern occurred
4. **Intervention**: concrete change proposal
5. **Guardrail**: validation check preventing recurrence
6. **Confidence**: high/medium/low with scope limits

No recommendation should be emitted without Evidence.

---

## Complexity Adaptation

| Complexity | Scope | Phases Used | Depth |
|-----------|-------|-------------|-------|
| Simple | Single session retro | 1 + 2 + 3 + 4 | Full analysis, selective action |
| Multi-step | Multi-session retro | All 5 phases | Full analysis + implementation |
| Complex | System-wide retro | All 5 + parallel agents | Deep analysis + major changes |

## Conflict Avoidance

- Phase 2 analysis runs sequentially to avoid mutual exclusion
- Exception: Complex grade uses PARALLEL team for parallel analysis
- Phase 5 actions are sequential: hooks first, then plugins, then config
- Pipeline or threshold changes require explicit user confirmation
