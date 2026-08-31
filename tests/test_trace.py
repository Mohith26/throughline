"""Traceability analysis tests.

The important one is `test_finds_every_planted_defect`. The fixture generator
writes down what it deliberately broke, and the analyser is scored against that
list rather than against its own previous output. A checker that reports nothing
on a clean file has demonstrated nothing, so both directions are tested: every
planted defect is found, and a clean file produces no blockers or majors.
"""

import json
import os
import unittest

from core import load, model, report, trace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "fixtures")


def clean_design():
    """A small design file with nothing wrong with it."""
    d = model.DesignFile()
    d.add(model.UserNeed("UN-001", "a need"))
    d.add(model.Requirement("SRS-001", "a requirement", needs=["UN-001"], safety_related=True))
    d.add(model.Hazard("HAZ-001", "a hazard", "serious", "remote"))
    d.add(model.RiskControl("RC-001", "a control", "HAZ-001", "SRS-001",
                            residual_severity="minor", residual_probability="improbable"))
    d.add(model.Verification("VER-001", "a verification", ["SRS-001"], "test", 5, "all pass"))
    d.add(model.TestRun("RUN-001", "VER-001", "pass", "2026-05-01", units=5, failures=0))
    return d


class CleanFileTests(unittest.TestCase):
    def test_a_clean_file_has_no_blockers_or_majors(self):
        findings = trace.analyse(clean_design())
        serious = [f for f in findings if f.severity in (trace.BLOCKER, trace.MAJOR)]
        self.assertEqual(serious, [], [f.as_dict() for f in serious])

    def test_a_clean_file_reports_full_coverage(self):
        cov = trace.coverage(clean_design())
        self.assertEqual(cov["needs_covered_pct"], 100.0)
        self.assertEqual(cov["requirements_verified_pct"], 100.0)
        self.assertEqual(cov["requirements_passing_pct"], 100.0)
        self.assertEqual(cov["safety_requirements_verified_pct"], 100.0)
        self.assertEqual(cov["hazards_controlled_pct"], 100.0)

    def test_clean_file_exits_zero(self):
        self.assertEqual(report.exit_code(report.build(clean_design())), 0)


class IndividualRuleTests(unittest.TestCase):
    def setUp(self):
        self.d = clean_design()

    def _rules(self):
        return {f.rule for f in trace.analyse(self.d)}

    def test_uncovered_need(self):
        self.d.add(model.UserNeed("UN-002", "lonely need"))
        self.assertIn("need-uncovered", self._rules())

    def test_unverified_safety_requirement_is_a_blocker(self):
        self.d.add(model.Requirement("SRS-002", "unverified", needs=["UN-001"], safety_related=True))
        found = [f for f in trace.analyse(self.d) if f.rule == "requirement-unverified"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, trace.BLOCKER)

    def test_unverified_ordinary_requirement_is_only_major(self):
        self.d.add(model.Requirement("SRS-003", "unverified", needs=["UN-001"]))
        found = [f for f in trace.analyse(self.d) if f.rule == "requirement-unverified"]
        self.assertEqual(found[0].severity, trace.MAJOR)

    def test_dangling_need_link(self):
        self.d.add(model.Requirement("SRS-004", "points nowhere", needs=["UN-999"]))
        self.assertIn("dangling-need-link", self._rules())

    def test_orphan_requirement(self):
        self.d.add(model.Requirement("SRS-005", "no need", needs=[]))
        self.assertIn("orphan-requirement", self._rules())

    def test_failed_run_is_a_blocker(self):
        self.d.add(model.TestRun("RUN-002", "VER-001", "fail", "2026-06-01", units=5, failures=1))
        found = [f for f in trace.analyse(self.d) if f.rule == "verification-failed"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, trace.BLOCKER)

    def test_a_later_pass_clears_an_earlier_failure(self):
        self.d.add(model.TestRun("RUN-002", "VER-001", "fail", "2026-06-01", units=5, failures=1))
        self.d.add(model.TestRun("RUN-003", "VER-001", "pass", "2026-07-01", units=5, failures=0))
        self.assertNotIn("verification-failed", self._rules())

    def test_an_earlier_pass_does_not_clear_a_later_failure(self):
        # The ordering trap: taking the best result rather than the latest one is
        # the single most dangerous way to get this wrong.
        self.d.add(model.TestRun("RUN-002", "VER-001", "fail", "2026-08-01", units=5, failures=2))
        self.assertIn("verification-failed", self._rules())

    def test_same_day_runs_are_broken_by_identifier_deterministically(self):
        self.d.add(model.TestRun("RUN-002", "VER-001", "fail", "2026-05-01", units=5, failures=1))
        latest = self.d.latest_run("VER-001")
        self.assertEqual(latest.id, "RUN-002")
        for _ in range(5):
            self.assertEqual(self.d.latest_run("VER-001").id, "RUN-002")

    def test_short_sample_size(self):
        self.d.add(model.TestRun("RUN-002", "VER-001", "pass", "2026-06-01", units=3, failures=0))
        found = [f for f in trace.analyse(self.d) if f.rule == "sample-size-short"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].evidence["required"], 5)
        self.assertEqual(found[0].evidence["actual"], 3)

    def test_contradictory_run(self):
        self.d.add(model.TestRun("RUN-002", "VER-001", "pass", "2026-06-01", units=5, failures=2))
        found = [f for f in trace.analyse(self.d) if f.rule == "contradictory-run"]
        self.assertEqual(found[0].severity, trace.BLOCKER)

    def test_impossible_run(self):
        self.d.add(model.TestRun("RUN-002", "VER-001", "fail", "2026-06-01", units=2, failures=5))
        self.assertIn("impossible-run", self._rules())

    def test_uncontrolled_hazard_is_a_blocker(self):
        self.d.add(model.Hazard("HAZ-002", "no control", "critical", "occasional"))
        found = [f for f in trace.analyse(self.d) if f.rule == "hazard-uncontrolled"]
        self.assertEqual(found[0].severity, trace.BLOCKER)

    def test_control_pointing_at_an_unverified_requirement_is_a_blocker(self):
        self.d.add(model.Requirement("SRS-006", "unverified control", needs=["UN-001"],
                                     safety_related=True))
        self.d.add(model.Hazard("HAZ-003", "another", "serious", "remote"))
        self.d.add(model.RiskControl("RC-002", "control", "HAZ-003", "SRS-006"))
        rules = self._rules()
        self.assertIn("control-unverified", rules)

    def test_control_requirement_not_flagged_safety_related(self):
        self.d.add(model.Requirement("SRS-007", "not flagged", needs=["UN-001"]))
        self.d.add(model.Verification("VER-002", "v", ["SRS-007"]))
        self.d.add(model.TestRun("RUN-002", "VER-002", "pass", "2026-06-01"))
        self.d.add(model.Hazard("HAZ-004", "h", "minor", "remote"))
        self.d.add(model.RiskControl("RC-003", "c", "HAZ-004", "SRS-007"))
        self.assertIn("control-requirement-not-flagged", self._rules())

    def test_residual_risk_worse_than_initial_is_a_blocker(self):
        self.d.add(model.Hazard("HAZ-005", "h", "minor", "remote"))
        self.d.add(model.RiskControl("RC-004", "c", "HAZ-005", "SRS-001",
                                     residual_severity="critical"))
        found = [f for f in trace.analyse(self.d) if f.rule == "risk-increased"]
        self.assertEqual(found[0].severity, trace.BLOCKER)

    def test_identifier_format_is_only_informational(self):
        self.d.add(model.UserNeed("not_an_id", "badly named"))
        found = [f for f in trace.analyse(self.d) if f.rule == "identifier-format"]
        self.assertEqual(found[0].severity, trace.INFO)

    def test_findings_are_sorted_by_severity(self):
        self.d.add(model.UserNeed("bad_id", "x"))
        self.d.add(model.Hazard("HAZ-009", "no control", "serious", "remote"))
        findings = trace.analyse(self.d)
        order = [trace.ORDER[f.severity] for f in findings]
        self.assertEqual(order, sorted(order))


class PlantedDefectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load.load(os.path.join(FIXTURES, "design.json"))
        with open(os.path.join(FIXTURES, "expected_findings.json")) as handle:
            cls.expected = json.load(handle)
        cls.findings = trace.analyse(cls.design)

    def test_finds_every_planted_defect(self):
        actual = {(f.rule, f.subject) for f in self.findings}
        missing = [e for e in self.expected if (e["rule"], e["subject"]) not in actual]
        self.assertEqual(missing, [], "analyser missed %d planted defects" % len(missing))

    def test_assigns_the_expected_severity_to_each(self):
        by_key = {(f.rule, f.subject): f.severity for f in self.findings}
        wrong = []
        for e in self.expected:
            got = by_key.get((e["rule"], e["subject"]))
            if got != e["severity"]:
                wrong.append({"rule": e["rule"], "subject": e["subject"],
                              "expected": e["severity"], "got": got})
        self.assertEqual(wrong, [])

    def test_does_not_flood_the_report_with_extras(self):
        # Precision matters as much as recall. A checker that reports a hundred
        # findings on a file with eight defects is not usable.
        serious = [f for f in self.findings if f.severity in (trace.BLOCKER, trace.MAJOR)]
        expected_serious = [e for e in self.expected
                            if e["severity"] in (trace.BLOCKER, trace.MAJOR)]
        self.assertLessEqual(len(serious), len(expected_serious) + 2,
                             [f.as_dict() for f in serious])

    def test_reports_the_latest_result_for_the_retested_verification(self):
        # VER-004 went fail, pass, fail. The report must say fail.
        latest = self.design.latest_run("VER-004")
        self.assertEqual(latest.result, "fail")
        self.assertEqual(latest.executed_on, "2026-04-14")

    def test_exit_code_is_non_zero_when_blockers_exist(self):
        payload = report.build(self.design)
        self.assertGreater(payload["findings_by_severity"]["blocker"], 0)
        self.assertEqual(report.exit_code(payload), 1)


class MatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load.load(os.path.join(FIXTURES, "design.json"))
        cls.rows = trace.matrix(cls.design)

    def test_one_row_per_requirement_sorted(self):
        self.assertEqual(len(self.rows), len(self.design.requirements))
        ids = [r["requirement"] for r in self.rows]
        self.assertEqual(ids, sorted(ids))

    def test_unverified_requirement_is_marked(self):
        row = next(r for r in self.rows if r["requirement"] == "SRS-014")
        self.assertEqual(row["status"], "unverified")
        self.assertEqual(row["verifications"], [])

    def test_failed_requirement_is_marked(self):
        row = next(r for r in self.rows if r["requirement"] == "SRS-004")
        self.assertEqual(row["status"], "failed")

    def test_passing_requirement_is_marked(self):
        row = next(r for r in self.rows if r["requirement"] == "SRS-001")
        self.assertEqual(row["status"], "passed")

    def test_rows_carry_their_risk_controls(self):
        row = next(r for r in self.rows if r["requirement"] == "SRS-003")
        self.assertIn("RC-001", row["risk_controls"])

    def test_coverage_matches_the_matrix(self):
        cov = trace.coverage(self.design)
        verified = len([r for r in self.rows if r["verifications"]])
        self.assertEqual(cov["requirements_verified"], verified)


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load.load(os.path.join(FIXTURES, "design.json"))
        cls.payload = report.build(cls.design)

    def test_markdown_contains_every_section(self):
        text = report.to_markdown(self.payload)
        for heading in ["# Design verification report", "## Coverage",
                        "## Findings", "## Traceability matrix"]:
            self.assertIn(heading, text)

    def test_markdown_lists_every_requirement(self):
        text = report.to_markdown(self.payload)
        for req_id in self.design.requirements:
            self.assertIn(req_id, text)

    def test_json_payload_is_serialisable(self):
        json.dumps(self.payload)

    def test_reliability_section_appears_when_supplied(self):
        with open(os.path.join(FIXTURES, "failures.json")) as handle:
            times = json.load(handle)["times"]
        payload = report.build(self.design, report.reliability_summary(times, mission_hours=500))
        text = report.to_markdown(payload)
        self.assertIn("## Reliability", text)
        self.assertIn("B10 life", text)


if __name__ == "__main__":
    unittest.main()
