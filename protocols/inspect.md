# TaskForge Inspect Protocol

> **What this protocol does — plain language overview**
>
> This is the quality review protocol. It governs how TaskForge reviews code,
> runs security checks, and validates work before marking it complete.
>
> You do not need to read this to use TaskForge. It is reference material for
> contributors and advanced users who want to understand quality gates.
>
> **Key terms used below:**
> - **Simple / Multi-step / Complex**: Review depth scales with task complexity.
> - **Anti-proxy-goal-drift lens**: A review checklist ensuring the change actually achieved its stated goal, not just visible metrics.
> - **report_only_warning**: A finding that must be recorded but does not by itself block a merge.
> - **specialization_confirmed**: The change is correctly scoped as a specific solution.
> - **completion_language_corrected**: The code may be fine, but the claim of completion needs to be reduced to match the actual evidence.

## Scope

Activated when the task requires evaluating existing code:

- Code review (style, correctness, maintainability)
- Security audit (OWASP Top 10, secrets, injection)
- Quality assurance (test coverage, performance)
- Pre-merge validation (comprehensive check before merge)

## Review Depth by Complexity

### Simple (Quick Review)

1. Single-agent lightweight review: bugs, style, correctness
2. Auto-triggered after code changes

### Multi-Step (Thorough Review)

1. Stage 1 — Spec reviewer: Does code match the approved design?
2. Stage 2 — Quality reviewer: Is code clean, tested, secure?

### Complex (Multi-Agent Review)

1. Spawn reviewer agents (role prompt per perspective)
2. Coordinate review rounds
3. Parallel perspectives: security, performance, architecture, style
4. Aggregate findings via lead synthesis

## Security Review (Any Complexity)

Always available as an independent check:

1. Checks: OWASP Top 10, hardcoded secrets, injection, XSS, CSRF
2. Can run alongside any complexity-specific review without conflict

## Anti-Proxy-Goal-Drift Review Lens

Every governed review should also answer:

1. What is the primary objective the change claims to serve?
2. Which proxy signals could be mistaken for true success?
3. Was validation material kept in a validation role, or did it leak into product logic?
4. Is the claimed completion state supported by evidence, or is the wording ahead of the proof?
5. Was the fix applied at the correct abstraction layer?
6. Is a bounded specialization being described honestly?

Report-only boundary:

- Anti-drift findings are review evidence and completion-language corrections
- They do not by themselves create a new hard gate or automatic merge block
- If another approved policy or gate is violated, cite that surface explicitly

## Review Checklist

Before approving code:

1. Code is readable and well-named
2. Functions are small (<50 lines)
3. Proper error handling at system boundaries
4. No hardcoded values (use constants or config)
5. Tests exist and pass (80%+ coverage)
6. No security vulnerabilities
7. No debug statements in production code
8. Immutable patterns used (no mutation)
9. No new fallback or degraded-path logic unless the active requirement explicitly approves it
10. Any fallback path is labeled as a hazard, not presented as equivalent success
11. No mock-success, template-success, swallowed-error, or simulation-only path
12. Any allowed fallback is explicit, traceable, documented, and easy to disable
13. The reviewed change states its primary objective, not only its local success signal
14. Validation material is not absorbed into product logic
15. The claimed completion state matches the evidence bundle and scope
16. Bounded specialization is preserved or explicitly marked as not-yet-generalized
17. Product acceptance criteria are frozen in the requirement doc
18. Manual spot checks are either not needed or honestly left as pending
19. Delivery-truth wording does not collapse process success into project acceptance

## Output Format

Review findings categorized by severity:

- **CRITICAL**: Must fix before merge (security vulnerabilities, data loss risks)
- **HIGH**: Should fix before merge (bugs, logic errors)
- **MEDIUM**: Fix when possible (code smells, minor style issues)
- **LOW**: Optional improvement (naming suggestions, minor refactors)

Fallback-specific review rule:

- Treat silent fallback or self-introduced fallback logic as HIGH at minimum and CRITICAL when it can hide capability loss
- Treat swallowed errors, mock-success branches, or template-only pass results as HIGH at minimum

Objective-protection disposition:

- `aligned`: objective, scope, and completion wording match the evidence
- `report_only_warning`: drift risk exists, must be recorded, does not block merge
- `specialization_confirmed`: valid as bounded specialization, must not be relabeled
- `completion_language_corrected`: code may stand, but completion wording must be reduced
- `escalate_via_existing_policy`: another approved policy or gate is independently violated

## Conflict Avoidance

- Simple review: single-agent only
- Multi-step review: two-stage only
- Complex review: multi-agent team only
- Security review: available at any complexity (exempt from mutual exclusion)

## Transition After Review

- CRITICAL/HIGH issues found: route to execute.md protocol for fixes
- `report_only_warning` or `completion_language_corrected`: update requirement/plan/closure wording
- `specialization_confirmed`: preserve specialization wording
- `escalate_via_existing_policy`: cite the specific approved policy or gate
- All clean: proceed to commit/merge
- Architectural issues found: route to analyze.md protocol for redesign
