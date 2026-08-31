"""Builds a synthetic design history file for a fictional surgical instrument.

Everything is invented. The structure follows how a real design control file is
organised, but the device, the requirements and the numbers are made up, and the
generator plants a known set of defects so the analyser can be scored against a
list of answers rather than against its own previous output.

The planted defects are the whole point. A checker that reports nothing on a
clean file has proved nothing.
"""

import json
import os
import random

SEED = 20260831

NEEDS = [
    ("UN-001", "The surgeon can control cutting depth precisely during a procedure"),
    ("UN-002", "The instrument does not overheat tissue outside the cutting site"),
    ("UN-003", "The instrument can be reprocessed between patients"),
    ("UN-004", "The instrument warns the user before the battery is exhausted"),
    ("UN-005", "The console records each procedure for later review"),
    ("UN-006", "The instrument is comfortable to hold for a long procedure"),
]

REQUIREMENTS = [
    ("SRS-001", "Cutting depth is settable from 0.5 mm to 4.0 mm in 0.1 mm steps", ["UN-001"], False),
    ("SRS-002", "Depth setting is held to within 0.05 mm of the commanded value", ["UN-001"], True),
    ("SRS-003", "Tip temperature does not exceed 42 C at the tissue interface", ["UN-002"], True),
    ("SRS-004", "Thermal cutout disables drive within 200 ms of exceeding 45 C", ["UN-002"], True),
    ("SRS-005", "Housing withstands 200 autoclave cycles without loss of seal", ["UN-003"], False),
    ("SRS-006", "All external surfaces are cleanable with the listed agents", ["UN-003"], False),
    ("SRS-007", "A low battery warning is issued with at least 10 minutes remaining", ["UN-004"], True),
    ("SRS-008", "Battery state of charge is estimated to within 5 percent", ["UN-004"], False),
    ("SRS-009", "Each procedure is written to the console log within 2 s of completion", ["UN-005"], False),
    ("SRS-010", "Procedure logs are retained for 90 days", ["UN-005"], False),
    ("SRS-011", "Grip force required for actuation does not exceed 12 N", ["UN-006"], False),
    ("SRS-012", "Drive current is limited to 2.0 A under any single fault", [], True),
    ("SRS-013", "Firmware verifies its own image before enabling the drive", ["UN-002"], True),
    ("SRS-014", "Console rejects a handpiece whose calibration has expired", ["UN-001"], True),
]

HAZARDS = [
    ("HAZ-001", "Thermal injury to tissue adjacent to the cutting site", "serious", "occasional"),
    ("HAZ-002", "Cut deeper than intended", "critical", "remote"),
    ("HAZ-003", "Loss of function part way through a procedure", "serious", "remote"),
    ("HAZ-004", "Cross contamination between patients", "critical", "improbable"),
    ("HAZ-005", "Electrical shock from a single fault condition", "catastrophic", "improbable"),
]

CONTROLS = [
    ("RC-001", "Tip temperature limit enforced in firmware", "HAZ-001", "SRS-003", "minor", "remote"),
    ("RC-002", "Independent thermal cutout", "HAZ-001", "SRS-004", "minor", "improbable"),
    ("RC-003", "Closed loop depth control with tolerance limit", "HAZ-002", "SRS-002", "serious", "improbable"),
    ("RC-004", "Battery warning ahead of exhaustion", "HAZ-003", "SRS-007", "minor", "remote"),
    ("RC-005", "Validated reprocessing instructions", "HAZ-004", "SRS-005", "minor", "improbable"),
    ("RC-006", "Single fault current limit", "HAZ-005", "SRS-012", "serious", "improbable"),
]

VERIFICATIONS = [
    ("VER-001", "Depth range and step verification", ["SRS-001"], "test", 10, "all steps within tolerance"),
    ("VER-002", "Depth accuracy over temperature", ["SRS-002"], "test", 30, "max error <= 0.05 mm"),
    ("VER-003", "Tip temperature mapping", ["SRS-003"], "test", 12, "peak <= 42 C"),
    ("VER-004", "Thermal cutout response time", ["SRS-004"], "test", 29, "cutout <= 200 ms"),
    ("VER-005", "Autoclave endurance", ["SRS-005"], "test", 6, "seal intact after 200 cycles"),
    ("VER-006", "Cleaning agent compatibility", ["SRS-006"], "inspection", 3, "no surface degradation"),
    ("VER-007", "Low battery warning timing", ["SRS-007"], "test", 29, "warning >= 10 min before cutoff"),
    ("VER-008", "State of charge accuracy", ["SRS-008"], "test", 10, "error <= 5 percent"),
    ("VER-009", "Procedure log latency", ["SRS-009"], "test", 20, "latency <= 2 s"),
    ("VER-010", "Log retention", ["SRS-010"], "analysis", None, "retention policy documented"),
    ("VER-011", "Grip force measurement", ["SRS-011"], "test", 15, "force <= 12 N"),
    ("VER-012", "Single fault current limit", ["SRS-012"], "test", 8, "current <= 2.0 A"),
    ("VER-013", "Firmware image verification", ["SRS-013"], "test", 5, "corrupt image refused"),
]

# ---- the planted defects, and what the analyser must say about each --------
#
# SRS-014  no verification at all, and it is safety related  -> blocker
# HAZ-003  is controlled, but by RC-004 -> SRS-007 which is fine, so no finding
# VER-004  latest run fails                                   -> blocker
# VER-008  run used 8 units against a protocol calling for 10  -> major
# RUN-011  on VER-009 is recorded as a pass while reporting 2 failing units -> blocker
# UN-006   is covered, so clean; UN-003 covered twice, clean
# SRS-012  has no user need                                    -> minor orphan
# VER-011  points at SRS-011 and also at a requirement that does not exist -> major
# RC-005   implements SRS-005 which is not marked safety related -> minor
# VER-013  has never been run                                    -> major

EXPECTED_FINDINGS = [
    ("requirement-unverified", "SRS-014", "blocker"),
    ("verification-failed", "VER-004", "blocker"),
    ("contradictory-run", "RUN-011", "blocker"),
    ("sample-size-short", "VER-008", "major"),
    ("dangling-requirement-link", "VER-011", "major"),
    ("verification-not-run", "VER-013", "major"),
    ("orphan-requirement", "SRS-012", "minor"),
    ("control-requirement-not-flagged", "RC-005", "minor"),
]


def build_runs(rng):
    runs = []
    counter = 1

    def add(ver, result, day, units=None, failures=None, notes=None):
        nonlocal counter
        runs.append({
            "id": "RUN-%03d" % counter,
            "verification": ver,
            "result": result,
            "executed_on": "2026-%02d-%02d" % (3 + day // 28, 1 + day % 28),
            "units": units,
            "failures": failures,
            "notes": notes,
        })
        counter += 1

    add("VER-001", "pass", 1, 10, 0)
    add("VER-002", "pass", 3, 30, 0)
    add("VER-003", "pass", 5, 12, 0)

    # VER-004 failed the first time, was fixed, then failed again. The analyser
    # must report the most recent result, not the best one.
    add("VER-004", "fail", 7, 29, 3, "cutout measured at 240 ms on three units")
    add("VER-004", "pass", 20, 29, 0, "after firmware change 1.4.2")
    add("VER-004", "fail", 41, 29, 1, "regression after thermal model rework")

    add("VER-005", "pass", 9, 6, 0)
    add("VER-006", "pass", 11, 3, 0)
    add("VER-007", "pass", 13, 29, 0)
    add("VER-008", "pass", 15, 8, 0, "two units unavailable at time of test")
    add("VER-009", "pass", 17, 20, 2, "two units logged late but within margin")
    add("VER-010", "pass", 19, None, None)
    add("VER-011", "pass", 21, 15, 0)
    add("VER-012", "pass", 23, 8, 0)
    add("VER-002", "pass", 30, 30, 0, "repeat after tooling change")
    return runs


def build():
    rng = random.Random(SEED)
    needs = [{"id": i, "title": t} for i, t in NEEDS]
    requirements = [
        {"id": i, "title": t, "needs": n, "safety_related": s}
        for i, t, n, s in REQUIREMENTS
    ]
    hazards = [
        {"id": i, "title": t, "severity": s, "probability": p}
        for i, t, s, p in HAZARDS
    ]
    controls = [
        {"id": i, "title": t, "hazard": h, "requirement": r,
         "residual_severity": rs, "residual_probability": rp}
        for i, t, h, r, rs, rp in CONTROLS
    ]
    verifications = [
        {"id": i, "title": t, "requirements": r, "method": m,
         "sample_size": ss, "acceptance": a}
        for i, t, r, m, ss, a in VERIFICATIONS
    ]
    # Planted: VER-011 also claims a requirement that does not exist.
    for ver in verifications:
        if ver["id"] == "VER-011":
            ver["requirements"] = ["SRS-011", "SRS-099"]

    runs = build_runs(rng)
    return {
        "needs": needs, "requirements": requirements, "hazards": hazards,
        "controls": controls, "verifications": verifications, "runs": runs,
    }


def failure_times():
    """Synthetic times to failure for the reliability example.

    Drawn from a Weibull with shape 2.2 and scale 1450 hours by inverse transform
    on a fixed seed, so the fit has a known right answer to be checked against.
    """
    rng = random.Random(SEED + 1)
    shape, scale = 2.2, 1450.0
    out = []
    for _ in range(40):
        u = rng.random()
        out.append(round(scale * (-__import__("math").log(1.0 - u)) ** (1.0 / shape), 2))
    return sorted(out)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    payload = build()
    with open(os.path.join(here, "design.json"), "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    with open(os.path.join(here, "failures.json"), "w") as handle:
        json.dump({"shape": 2.2, "scale": 1450.0, "times": failure_times()},
                  handle, indent=2)
    with open(os.path.join(here, "expected_findings.json"), "w") as handle:
        json.dump([{"rule": r, "subject": s, "severity": v}
                   for r, s, v in EXPECTED_FINDINGS], handle, indent=2)
    for key, value in payload.items():
        print("%-14s %d" % (key, len(value)))
    print("planted defects %d" % len(EXPECTED_FINDINGS))


if __name__ == "__main__":
    main()
