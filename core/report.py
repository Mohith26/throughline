"""Turns a design file into the two artefacts a design review actually wants:
a traceability matrix and a findings list, plus the coverage numbers that go on
the front page.

Output is JSON or Markdown. Markdown because the matrix ends up pasted into a
design history document and nobody wants to reformat a table by hand, JSON
because the same numbers get consumed by whatever dashboard exists this quarter.

The exit code is the part that matters for automation: a blocker means non zero,
so this can sit in a pipeline and stop a release the same way a failing test does.
"""

import json

from core import stats, trace

STATUS_MARK = {
    "passed": "pass", "failed": "FAIL", "blocked": "blocked",
    "incomplete": "incomplete", "unverified": "NOT VERIFIED",
}


def build(design, reliability=None):
    findings = trace.analyse(design)
    payload = {
        "counts": design.counts(),
        "coverage": trace.coverage(design),
        "findings": [f.as_dict() for f in findings],
        "findings_by_severity": _by_severity(findings),
        "matrix": trace.matrix(design),
    }
    if reliability:
        payload["reliability"] = reliability
    return payload


def _by_severity(findings):
    out = {trace.BLOCKER: 0, trace.MAJOR: 0, trace.MINOR: 0, trace.INFO: 0}
    for f in findings:
        out[f.severity] += 1
    return out


def reliability_summary(times, confidence=0.95, mission_hours=None):
    """A Weibull fit plus the statements that go alongside it.

    The r squared is reported next to the parameters rather than buried, because
    a Weibull fitted to data that is not Weibull will still return two confident
    looking numbers.
    """
    shape, scale, r2 = stats.weibull_fit(times)
    out = {
        "units": len(times),
        "shape": round(shape, 4),
        "scale_hours": round(scale, 2),
        "r_squared": round(r2, 6),
        "interpretation": stats.interpret_shape(shape),
        "b10_hours": round(stats.weibull_bx_life(0.10, shape, scale), 2),
        "b50_hours": round(stats.weibull_bx_life(0.50, shape, scale), 2),
        "confidence": confidence,
    }
    if mission_hours:
        out["mission_hours"] = mission_hours
        out["reliability_at_mission"] = round(
            stats.weibull_reliability(mission_hours, shape, scale), 6)
    return out


def sampling_plan(reliability, confidence=0.95):
    n = stats.zero_failure_sample_size(reliability, confidence)
    return {
        "target_reliability": reliability,
        "confidence": confidence,
        "zero_failure_sample_size": n,
        "demonstrated_if_clean": round(stats.demonstrated_reliability(n, confidence), 6),
        "note": "a single failure invalidates the plan; the exact bound must then be used",
    }


def to_markdown(payload):
    lines = []
    counts = payload["counts"]
    cov = payload["coverage"]
    sev = payload["findings_by_severity"]

    lines.append("# Design verification report")
    lines.append("")
    lines.append("| | |")
    lines.append("| --- | --- |")
    lines.append("| User needs | %d |" % counts["needs"])
    lines.append("| Requirements | %d |" % counts["requirements"])
    lines.append("| Hazards | %d |" % counts["hazards"])
    lines.append("| Verifications | %d |" % counts["verifications"])
    lines.append("| Test runs | %d |" % counts["runs"])
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append("| Measure | Value |")
    lines.append("| --- | --- |")
    lines.append("| Needs covered by a requirement | %s%% |" % cov["needs_covered_pct"])
    lines.append("| Requirements with a verification | %s%% |" % cov["requirements_verified_pct"])
    lines.append("| Requirements passing | %s%% |" % cov["requirements_passing_pct"])
    lines.append("| Safety requirements verified | %s%% |" % cov["safety_requirements_verified_pct"])
    lines.append("| Hazards with a risk control | %s%% |" % cov["hazards_controlled_pct"])
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append("%d blocker, %d major, %d minor, %d informational."
                 % (sev["blocker"], sev["major"], sev["minor"], sev["info"]))
    lines.append("")
    if payload["findings"]:
        lines.append("| Severity | Rule | Subject | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for f in payload["findings"]:
            lines.append("| %s | %s | %s | %s |"
                         % (f["severity"], f["rule"], f["subject"], f["message"]))
    else:
        lines.append("No findings.")
    lines.append("")
    lines.append("## Traceability matrix")
    lines.append("")
    lines.append("| Requirement | Needs | Safety | Verifications | Status |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in payload["matrix"]:
        vers = ", ".join("%s (%s)" % (v["verification"], v["result"]) for v in row["verifications"])
        lines.append("| %s | %s | %s | %s | %s |" % (
            row["requirement"], ", ".join(row["needs"]) or "none",
            "yes" if row["safety_related"] else "no",
            vers or "none", STATUS_MARK[row["status"]]))

    if "reliability" in payload:
        rel = payload["reliability"]
        lines.append("")
        lines.append("## Reliability")
        lines.append("")
        lines.append("| | |")
        lines.append("| --- | --- |")
        lines.append("| Units | %d |" % rel["units"])
        lines.append("| Weibull shape | %s |" % rel["shape"])
        lines.append("| Weibull scale | %s hours |" % rel["scale_hours"])
        lines.append("| Fit r squared | %s |" % rel["r_squared"])
        lines.append("| Interpretation | %s |" % rel["interpretation"])
        lines.append("| B10 life | %s hours |" % rel["b10_hours"])
        if "reliability_at_mission" in rel:
            lines.append("| Reliability at %s hours | %s |"
                         % (rel["mission_hours"], rel["reliability_at_mission"]))
    return "\n".join(lines) + "\n"


def exit_code(payload):
    return 1 if payload["findings_by_severity"][trace.BLOCKER] else 0


def main():
    import argparse
    import os
    import sys

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description="Design verification traceability report")
    parser.add_argument("design", nargs="?",
                        default=os.path.join(here, "fixtures", "design.json"))
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--failures", help="JSON file of failure times for a reliability fit")
    parser.add_argument("--mission-hours", type=float, default=None)
    args = parser.parse_args()

    from core import load
    design = load.load(args.design)

    reliability = None
    if args.failures:
        with open(args.failures) as handle:
            times = json.load(handle)["times"]
        reliability = reliability_summary(times, mission_hours=args.mission_hours)

    payload = build(design, reliability)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(to_markdown(payload))
    return exit_code(payload)


if __name__ == "__main__":
    import sys
    sys.exit(main())
