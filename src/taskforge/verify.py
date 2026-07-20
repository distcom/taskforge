"""Delivery verification — acceptance checks and report generation.

Runs at pipeline stage FINALIZE: compares actual outcomes against the sealed
plan and emits a DeliveryReport with per-check pass/fail evidence.
"""

from __future__ import annotations

from .models import (
    CheckEntry,
    CheckVerdict,
    DeliveryReport,
    TaskSession,
    UnitStatus,
)


class Verifier:
    """Runs structured acceptance checks and produces a DeliveryReport.

    Checks performed:
      1. All planned segments have recorded outcomes.
      2. No segments in ERRORED state.
      3. No segments in STUCK state.
      4. Acceptance criteria verdicts are passing.
      5. Every planned unit has an outcome record.
      6. Completed units produced artifacts.
    """

    __slots__ = ("_session", "_entries")

    def __init__(self, session: TaskSession) -> None:
        self._session = session
        self._entries: list[CheckEntry] = []

    def run(self) -> DeliveryReport:
        """Execute all checks and attach the report to the session."""
        self._entries = []
        self._check_segments_recorded()
        self._check_no_errors()
        self._check_no_stuck()
        self._check_criteria()
        self._check_unit_coverage()
        self._check_artifacts()

        report = DeliveryReport(session_id=self._session.session_id, entries=list(self._entries))
        report.compute_verdict()
        self._session.delivery = report
        self._session.touch()
        return report

    # ─── individual checks ─────────────────────────────────────────────────

    def _check_segments_recorded(self) -> None:
        plan = self._session.plan
        if plan is None:
            self._add("segments-exist", "Execution plan present", False, remark="No plan.")
            return
        planned = {s.segment_id for s in plan.segments}
        recorded = {o.segment_id for o in self._session.segment_outcomes}
        missing = planned - recorded
        self._add(
            "segments-recorded",
            "All planned segments have outcomes",
            not missing,
            proof=f"{len(recorded)}/{len(planned)}",
            remark=f"Missing: {missing}" if missing else "",
        )

    def _check_no_errors(self) -> None:
        errored = [o.segment_id for o in self._session.segment_outcomes if o.status == UnitStatus.ERRORED]
        self._add("no-errors", "No segments errored", not errored,
                  proof=f"{len(errored)} errored", remark=", ".join(errored))

    def _check_no_stuck(self) -> None:
        stuck = [o.segment_id for o in self._session.segment_outcomes if o.status == UnitStatus.STUCK]
        self._add("no-stuck", "No segments stuck", not stuck,
                  proof=f"{len(stuck)} stuck", remark=", ".join(stuck))

    def _check_criteria(self) -> None:
        total = passing = 0
        failures: list[str] = []
        for seg in self._session.segment_outcomes:
            for oc in seg.outcomes:
                for cid, verdict in oc.criteria_verdicts.items():
                    total += 1
                    if verdict == CheckVerdict.PASS:
                        passing += 1
                    else:
                        failures.append(f"{oc.unit_id}/{cid}")
        ok = total > 0 and passing == total
        self._add("criteria-pass", "All acceptance criteria pass", ok,
                  proof=f"{passing}/{total}", remark="; ".join(failures[:8]))

    def _check_unit_coverage(self) -> None:
        plan = self._session.plan
        if plan is None:
            return
        planned_units = {u.unit_id for u in plan.units}
        covered: set[str] = set()
        for seg in self._session.segment_outcomes:
            for oc in seg.outcomes:
                covered.add(oc.unit_id)
        gap = planned_units - covered
        self._add("unit-coverage", "All units have outcomes", not gap,
                  proof=f"{len(covered)}/{len(planned_units)}",
                  remark=f"Uncovered: {gap}" if gap else "")

    def _check_artifacts(self) -> None:
        with_art = without_art = 0
        for seg in self._session.segment_outcomes:
            for oc in seg.outcomes:
                if oc.status == UnitStatus.DONE:
                    if oc.artifacts:
                        with_art += 1
                    else:
                        without_art += 1
        self._add("artifacts-present", "Done units produced artifacts", without_art == 0,
                  proof=f"{with_art} with, {without_art} without")

    def _add(self, cid: str, label: str, passed: bool, *, proof: str = "", remark: str = "") -> None:
        self._entries.append(CheckEntry(check_id=cid, label=label, passed=passed, proof=proof, remark=remark))


# ─── Report Formatting ─────────────────────────────────────────────────────────


def format_report(report: DeliveryReport) -> str:
    """Render a human-readable markdown acceptance report."""
    verdict = "ACCEPTED" if report.accepted else "REJECTED"
    total = len(report.entries)
    passed = sum(1 for e in report.entries if e.passed)
    lines = [
        "# Delivery Report",
        "",
        f"**Session:** {report.session_id}",
        f"**Emitted:** {report.emitted_at}",
        f"**Verdict:** {verdict} ({passed}/{total} checks passed)",
        "",
        "## Checks",
        "",
    ]
    for e in report.entries:
        icon = "PASS" if e.passed else "FAIL"
        lines.append(f"- [{icon}] **{e.check_id}** — {e.label}")
        if e.proof:
            lines.append(f"  - Proof: {e.proof}")
        if e.remark:
            lines.append(f"  - Remark: {e.remark}")
    if report.commentary:
        lines += ["", "## Commentary", "", report.commentary]
    return "\n".join(lines)
