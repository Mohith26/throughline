"""Traceability analysis: the part an auditor actually asks about.

Four questions, and this module answers all four with evidence rather than a
yes or a no:

  1. Is every user need covered by at least one requirement?
  2. Is every requirement verified by at least one verification?
  3. Has every verification actually been run, and did it pass?
  4. Does every hazard have a risk control, and is that control itself verified?

The output is a list of findings. Each one names the object, the rule it broke,
and a severity, so the report can be sorted by what matters instead of by what
happens to be first in the file. Nothing here raises: an incomplete design file
is the normal state of a design file, and the tool has to be usable while the
work is in progress.

The severity ladder is deliberate. An unverified safety related requirement is
worse than an unverified ordinary one, and a hazard with no control at all is
worse than a hazard whose control exists but has not been tested yet. Sorting a
findings list by an undifferentiated severity is how the important ones end up
on page four.
"""

from core import model

BLOCKER = "blocker"
MAJOR = "major"
MINOR = "minor"
INFO = "info"

ORDER = {BLOCKER: 0, MAJOR: 1, MINOR: 2, INFO: 3}


class Finding(object):
    def __init__(self, severity, rule, subject, message, evidence=None):
        self.severity = severity
        self.rule = rule
        self.subject = subject
        self.message = message
        self.evidence = evidence or {}

    def __repr__(self):
        return "<%s %s %s>" % (self.severity, self.rule, self.subject)

    def as_dict(self):
        return {
            "severity": self.severity, "rule": self.rule, "subject": self.subject,
            "message": self.message, "evidence": self.evidence,
        }


def _sort(findings):
    return sorted(findings, key=lambda f: (ORDER[f.severity], f.rule, f.subject))


def check_needs(design):
    out = []
    for need in design.needs.values():
        covered = design.requirements_for_need(need.id)
        if not covered:
            out.append(Finding(
                MAJOR, "need-uncovered", need.id,
                "user need has no requirement tracing to it"))
    return out


def check_requirements(design):
    out = []
    for req in design.requirements.values():
        for need_id in req.needs:
            if need_id not in design.needs:
                out.append(Finding(
                    MAJOR, "dangling-need-link", req.id,
                    "requirement traces to unknown user need %s" % need_id,
                    {"need": need_id}))
        if not req.needs:
            out.append(Finding(
                MINOR, "orphan-requirement", req.id,
                "requirement does not trace up to any user need"))

        verifications = design.verifications_for_requirement(req.id)
        if not verifications:
            out.append(Finding(
                BLOCKER if req.safety_related else MAJOR, "requirement-unverified", req.id,
                "requirement has no verification"
                + (" and is safety related" if req.safety_related else ""),
                {"safety_related": req.safety_related}))
    return out


def check_verifications(design):
    out = []
    for ver in design.verifications.values():
        for req_id in ver.requirements:
            if req_id not in design.requirements:
                out.append(Finding(
                    MAJOR, "dangling-requirement-link", ver.id,
                    "verification covers unknown requirement %s" % req_id,
                    {"requirement": req_id}))
        if not ver.requirements:
            out.append(Finding(
                MINOR, "orphan-verification", ver.id,
                "verification does not cover any requirement"))

        latest = design.latest_run(ver.id)
        if latest is None:
            out.append(Finding(
                MAJOR, "verification-not-run", ver.id,
                "verification has never been executed"))
            continue
        if latest.result == "fail":
            out.append(Finding(
                BLOCKER, "verification-failed", ver.id,
                "most recent run %s failed" % latest.id,
                {"run": latest.id, "date": latest.executed_on,
                 "failures": latest.failures, "units": latest.units}))
        elif latest.result == "blocked":
            out.append(Finding(
                MAJOR, "verification-blocked", ver.id,
                "most recent run %s is blocked" % latest.id, {"run": latest.id}))
        elif latest.result == "not-run":
            out.append(Finding(
                MAJOR, "verification-not-run", ver.id,
                "most recent run %s has not been executed" % latest.id, {"run": latest.id}))

        if ver.sample_size is not None and latest.units is not None:
            if latest.units < ver.sample_size:
                out.append(Finding(
                    MAJOR, "sample-size-short", ver.id,
                    "protocol calls for %d units, run %s used %d"
                    % (ver.sample_size, latest.id, latest.units),
                    {"required": ver.sample_size, "actual": latest.units, "run": latest.id}))
    return out


def check_runs(design):
    out = []
    for run in design.runs.values():
        if run.verification not in design.verifications:
            out.append(Finding(
                MAJOR, "dangling-verification-link", run.id,
                "run references unknown verification %s" % run.verification,
                {"verification": run.verification}))
        if run.result == "pass" and run.failures:
            # A passing run that recorded failing units is a contradiction, and
            # it is exactly the kind of thing that gets copied forward from a
            # previous report without anyone re-reading it.
            out.append(Finding(
                BLOCKER, "contradictory-run", run.id,
                "run is recorded as a pass but reports %d failing units" % run.failures,
                {"failures": run.failures, "units": run.units}))
        if run.units is not None and run.failures is not None and run.failures > run.units:
            out.append(Finding(
                BLOCKER, "impossible-run", run.id,
                "run reports more failures (%d) than units tested (%d)"
                % (run.failures, run.units),
                {"failures": run.failures, "units": run.units}))
    return out


def check_risk(design):
    out = []
    for hazard in design.hazards.values():
        controls = design.controls_for_hazard(hazard.id)
        if not controls:
            out.append(Finding(
                BLOCKER, "hazard-uncontrolled", hazard.id,
                "hazard has no risk control",
                {"severity": hazard.severity, "probability": hazard.probability}))
            continue
        for control in controls:
            if control.requirement is None:
                out.append(Finding(
                    MAJOR, "control-not-a-requirement", control.id,
                    "risk control is not implemented by any requirement",
                    {"hazard": hazard.id}))
                continue
            if control.requirement not in design.requirements:
                out.append(Finding(
                    MAJOR, "dangling-control-link", control.id,
                    "risk control points at unknown requirement %s" % control.requirement,
                    {"requirement": control.requirement}))
                continue
            req = design.requirements[control.requirement]
            if not req.safety_related:
                out.append(Finding(
                    MINOR, "control-requirement-not-flagged", control.id,
                    "requirement %s implements a risk control but is not marked safety related"
                    % req.id, {"requirement": req.id}))
            if not design.verifications_for_requirement(req.id):
                out.append(Finding(
                    BLOCKER, "control-unverified", control.id,
                    "risk control is implemented by %s, which has no verification" % req.id,
                    {"requirement": req.id, "hazard": hazard.id}))

            if control.residual_severity is not None:
                before = hazard.severity_index()
                after = model.SEVERITIES.index(control.residual_severity)
                if after > before:
                    out.append(Finding(
                        BLOCKER, "risk-increased", control.id,
                        "residual severity %s is worse than the initial %s"
                        % (control.residual_severity, hazard.severity),
                        {"initial": hazard.severity, "residual": control.residual_severity}))
    return out


def check_ids(design):
    out = []
    for table in (design.needs, design.requirements, design.hazards,
                  design.controls, design.verifications):
        for item in table.values():
            if not item.well_formed_id():
                out.append(Finding(
                    INFO, "identifier-format", item.id,
                    "identifier does not match the PREFIX-123 convention"))
    return out


ALL_CHECKS = (check_needs, check_requirements, check_verifications,
              check_runs, check_risk, check_ids)


def analyse(design):
    findings = []
    for check in ALL_CHECKS:
        findings.extend(check(design))
    return _sort(findings)


def coverage(design):
    """The percentages that go at the top of a report.

    Safety related coverage is reported separately because it is the number that
    decides whether a design review can proceed, and averaging it into the
    overall figure hides exactly the thing you need to see.
    """
    reqs = list(design.requirements.values())
    verified = [r for r in reqs if design.verifications_for_requirement(r.id)]
    safety = [r for r in reqs if r.safety_related]
    safety_verified = [r for r in safety if design.verifications_for_requirement(r.id)]

    def passing(req):
        vers = design.verifications_for_requirement(req.id)
        if not vers:
            return False
        for ver in vers:
            latest = design.latest_run(ver.id)
            if latest is None or latest.result != "pass":
                return False
        return True

    passed = [r for r in reqs if passing(r)]
    needs = list(design.needs.values())
    needs_covered = [n for n in needs if design.requirements_for_need(n.id)]
    hazards = list(design.hazards.values())
    hazards_controlled = [h for h in hazards if design.controls_for_hazard(h.id)]

    def pct(part, whole):
        return round(100.0 * len(part) / len(whole), 2) if whole else None

    return {
        "requirements": len(reqs),
        "requirements_verified": len(verified),
        "requirements_verified_pct": pct(verified, reqs),
        "requirements_passing": len(passed),
        "requirements_passing_pct": pct(passed, reqs),
        "safety_requirements": len(safety),
        "safety_requirements_verified": len(safety_verified),
        "safety_requirements_verified_pct": pct(safety_verified, safety),
        "needs": len(needs),
        "needs_covered_pct": pct(needs_covered, needs),
        "hazards": len(hazards),
        "hazards_controlled_pct": pct(hazards_controlled, hazards),
    }


def matrix(design):
    """The traceability matrix itself: one row per requirement, walked in both
    directions, which is the artefact that goes into the design history file."""
    rows = []
    for req in sorted(design.requirements.values(), key=lambda r: r.id):
        vers = sorted(design.verifications_for_requirement(req.id), key=lambda v: v.id)
        statuses = []
        for ver in vers:
            latest = design.latest_run(ver.id)
            statuses.append({
                "verification": ver.id, "method": ver.method,
                "result": latest.result if latest else "not-run",
                "run": latest.id if latest else None,
                "date": latest.executed_on if latest else None,
            })
        controls = [c.id for c in design.controls.values() if c.requirement == req.id]
        rows.append({
            "requirement": req.id, "title": req.title,
            "safety_related": req.safety_related,
            "needs": sorted(req.needs),
            "verifications": statuses,
            "risk_controls": sorted(controls),
            "status": _row_status(statuses),
        })
    return rows


def _row_status(statuses):
    if not statuses:
        return "unverified"
    results = [s["result"] for s in statuses]
    if "fail" in results:
        return "failed"
    if "blocked" in results:
        return "blocked"
    if all(r == "pass" for r in results):
        return "passed"
    return "incomplete"
