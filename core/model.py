"""The objects a design history file is made of, and the links between them.

The shape here follows how a medical device design control file is actually
structured, because the whole point of the tool is to answer the question an
auditor asks: show me that every user need was translated into a requirement,
that every requirement was verified, and that every hazard has a control which
was itself verified.

    UserNeed  ->  Requirement  ->  Verification  ->  TestRun
                       ^
                    Hazard -> RiskControl

Two design decisions worth stating.

First, nothing here validates by throwing. A design file is usually incomplete
while it is being written, and a tool that refuses to load an incomplete file is
useless during the period you most want it. Structural problems are reported as
findings, with a severity, and the caller decides what to do about them.

Second, identifiers are strings chosen by the author, not generated. Real
requirements have names like SRS-014 that appear in documents the tool does not
own, and renumbering them would be actively harmful.
"""

import re

ID_PATTERN = re.compile(r"^[A-Z]{2,6}-\d{1,4}$")

SEVERITIES = ("negligible", "minor", "serious", "critical", "catastrophic")
PROBABILITIES = ("improbable", "remote", "occasional", "probable", "frequent")

RESULTS = ("pass", "fail", "blocked", "not-run")


class ModelError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ModelError(message)


class Node(object):
    kind = "node"

    def __init__(self, identifier, title, **extra):
        _require(isinstance(identifier, str) and identifier, "identifier must be a non empty string")
        _require(isinstance(title, str) and title, "%s: title must be a non empty string" % identifier)
        self.id = identifier
        self.title = title
        self.extra = extra

    def __repr__(self):
        return "<%s %s>" % (self.kind, self.id)

    def well_formed_id(self):
        return bool(ID_PATTERN.match(self.id))


class UserNeed(Node):
    kind = "need"


class Requirement(Node):
    kind = "requirement"

    def __init__(self, identifier, title, needs=(), safety_related=False, **extra):
        Node.__init__(self, identifier, title, **extra)
        self.needs = list(needs)
        self.safety_related = bool(safety_related)


class Hazard(Node):
    kind = "hazard"

    def __init__(self, identifier, title, severity, probability, controls=(), **extra):
        Node.__init__(self, identifier, title, **extra)
        _require(severity in SEVERITIES, "%s: unknown severity %r" % (identifier, severity))
        _require(probability in PROBABILITIES,
                 "%s: unknown probability %r" % (identifier, probability))
        self.severity = severity
        self.probability = probability
        self.controls = list(controls)

    def severity_index(self):
        return SEVERITIES.index(self.severity)

    def probability_index(self):
        return PROBABILITIES.index(self.probability)


class RiskControl(Node):
    kind = "control"

    def __init__(self, identifier, title, hazard, requirement=None,
                 residual_severity=None, residual_probability=None, **extra):
        Node.__init__(self, identifier, title, **extra)
        self.hazard = hazard
        self.requirement = requirement
        if residual_severity is not None:
            _require(residual_severity in SEVERITIES,
                     "%s: unknown residual severity %r" % (identifier, residual_severity))
        if residual_probability is not None:
            _require(residual_probability in PROBABILITIES,
                     "%s: unknown residual probability %r" % (identifier, residual_probability))
        self.residual_severity = residual_severity
        self.residual_probability = residual_probability


class Verification(Node):
    kind = "verification"

    def __init__(self, identifier, title, requirements=(), method="test",
                 sample_size=None, acceptance=None, **extra):
        Node.__init__(self, identifier, title, **extra)
        self.requirements = list(requirements)
        self.method = method
        self.sample_size = sample_size
        self.acceptance = acceptance


class TestRun(object):
    kind = "run"

    def __init__(self, identifier, verification, result, executed_on,
                 units=None, failures=None, notes=None, **extra):
        _require(isinstance(identifier, str) and identifier, "run identifier must be a non empty string")
        _require(result in RESULTS, "%s: unknown result %r" % (identifier, result))
        self.id = identifier
        self.verification = verification
        self.result = result
        self.executed_on = executed_on
        self.units = units
        self.failures = failures
        self.notes = notes
        self.extra = extra

    def __repr__(self):
        return "<run %s %s>" % (self.id, self.result)


class DesignFile(object):
    """Everything, plus the indexes needed to walk it in either direction."""

    def __init__(self):
        self.needs = {}
        self.requirements = {}
        self.hazards = {}
        self.controls = {}
        self.verifications = {}
        self.runs = {}
        self._index = None

    # ---- construction ----------------------------------------------------

    def add(self, item):
        table = {
            "need": self.needs, "requirement": self.requirements, "hazard": self.hazards,
            "control": self.controls, "verification": self.verifications, "run": self.runs,
        }[item.kind]
        if item.id in table:
            raise ModelError("duplicate %s id %s" % (item.kind, item.id))
        table[item.id] = item
        self._index = None
        return item

    # ---- reverse index ---------------------------------------------------

    def _build_index(self):
        """Bucket every link once instead of scanning for it every time.

        The first version answered each lookup with a list comprehension over the
        whole table, so an analysis that asks "which verifications cover this
        requirement" once per requirement was quadratic. It did not show at
        fourteen requirements and it very much showed at eight hundred: doubling
        the file size quadrupled the analysis time.

        The index is built lazily and thrown away on any add, so it can never
        drift from the tables it summarises.
        """
        reqs_by_need = {}
        for req in self.requirements.values():
            for need_id in req.needs:
                reqs_by_need.setdefault(need_id, []).append(req)
        vers_by_req = {}
        for ver in self.verifications.values():
            for req_id in ver.requirements:
                vers_by_req.setdefault(req_id, []).append(ver)
        runs_by_ver = {}
        for run in self.runs.values():
            runs_by_ver.setdefault(run.verification, []).append(run)
        controls_by_hazard = {}
        for control in self.controls.values():
            controls_by_hazard.setdefault(control.hazard, []).append(control)
        latest = {}
        for ver_id, runs in runs_by_ver.items():
            latest[ver_id] = sorted(runs, key=lambda r: (r.executed_on, r.id))[-1]
        self._index = {
            "reqs_by_need": reqs_by_need,
            "vers_by_req": vers_by_req,
            "runs_by_ver": runs_by_ver,
            "controls_by_hazard": controls_by_hazard,
            "latest_run": latest,
        }
        return self._index

    def index(self):
        return self._index if self._index is not None else self._build_index()

    def __len__(self):
        return sum(len(t) for t in
                   (self.needs, self.requirements, self.hazards,
                    self.controls, self.verifications, self.runs))

    def counts(self):
        return {
            "needs": len(self.needs), "requirements": len(self.requirements),
            "hazards": len(self.hazards), "controls": len(self.controls),
            "verifications": len(self.verifications), "runs": len(self.runs),
        }

    # ---- reverse indexes -------------------------------------------------

    def requirements_for_need(self, need_id):
        return list(self.index()["reqs_by_need"].get(need_id, ()))

    def verifications_for_requirement(self, req_id):
        return list(self.index()["vers_by_req"].get(req_id, ()))

    def runs_for_verification(self, ver_id):
        return list(self.index()["runs_by_ver"].get(ver_id, ()))

    def controls_for_hazard(self, hazard_id):
        return list(self.index()["controls_by_hazard"].get(hazard_id, ()))

    def latest_run(self, ver_id):
        """Most recent run by execution date, ties broken by identifier so the
        answer is deterministic when two runs share a date."""
        return self.index()["latest_run"].get(ver_id)
