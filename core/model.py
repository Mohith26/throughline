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

    # ---- construction ----------------------------------------------------

    def add(self, item):
        table = {
            "need": self.needs, "requirement": self.requirements, "hazard": self.hazards,
            "control": self.controls, "verification": self.verifications, "run": self.runs,
        }[item.kind]
        if item.id in table:
            raise ModelError("duplicate %s id %s" % (item.kind, item.id))
        table[item.id] = item
        return item

    # ---- reverse indexes -------------------------------------------------

    def requirements_for_need(self, need_id):
        return [r for r in self.requirements.values() if need_id in r.needs]

    def verifications_for_requirement(self, req_id):
        return [v for v in self.verifications.values() if req_id in v.requirements]

    def runs_for_verification(self, ver_id):
        return [r for r in self.runs.values() if r.verification == ver_id]

    def controls_for_hazard(self, hazard_id):
        return [c for c in self.controls.values() if c.hazard == hazard_id]

    def latest_run(self, ver_id):
        """Most recent run by execution date, ties broken by identifier so the
        answer is deterministic when two runs share a date."""
        runs = self.runs_for_verification(ver_id)
        if not runs:
            return None
        return sorted(runs, key=lambda r: (r.executed_on, r.id))[-1]
