# Design verification report

| | |
| --- | --- |
| User needs | 6 |
| Requirements | 14 |
| Hazards | 5 |
| Verifications | 13 |
| Test runs | 15 |

## Coverage

| Measure | Value |
| --- | --- |
| Needs covered by a requirement | 100.0% |
| Requirements with a verification | 92.86% |
| Requirements passing | 78.57% |
| Safety requirements verified | 85.71% |
| Hazards with a risk control | 100.0% |

## Findings

3 blocker, 3 major, 2 minor, 0 informational.

| Severity | Rule | Subject | Detail |
| --- | --- | --- | --- |
| blocker | contradictory-run | RUN-011 | run is recorded as a pass but reports 2 failing units |
| blocker | requirement-unverified | SRS-014 | requirement has no verification and is safety related |
| blocker | verification-failed | VER-004 | most recent run RUN-006 failed |
| major | dangling-requirement-link | VER-011 | verification covers unknown requirement SRS-099 |
| major | sample-size-short | VER-008 | protocol calls for 10 units, run RUN-010 used 8 |
| major | verification-not-run | VER-013 | verification has never been executed |
| minor | control-requirement-not-flagged | RC-005 | requirement SRS-005 implements a risk control but is not marked safety related |
| minor | orphan-requirement | SRS-012 | requirement does not trace up to any user need |

## Traceability matrix

| Requirement | Needs | Safety | Verifications | Status |
| --- | --- | --- | --- | --- |
| SRS-001 | UN-001 | no | VER-001 (pass) | pass |
| SRS-002 | UN-001 | yes | VER-002 (pass) | pass |
| SRS-003 | UN-002 | yes | VER-003 (pass) | pass |
| SRS-004 | UN-002 | yes | VER-004 (fail) | FAIL |
| SRS-005 | UN-003 | no | VER-005 (pass) | pass |
| SRS-006 | UN-003 | no | VER-006 (pass) | pass |
| SRS-007 | UN-004 | yes | VER-007 (pass) | pass |
| SRS-008 | UN-004 | no | VER-008 (pass) | pass |
| SRS-009 | UN-005 | no | VER-009 (pass) | pass |
| SRS-010 | UN-005 | no | VER-010 (pass) | pass |
| SRS-011 | UN-006 | no | VER-011 (pass) | pass |
| SRS-012 | none | yes | VER-012 (pass) | pass |
| SRS-013 | UN-002 | yes | VER-013 (not-run) | incomplete |
| SRS-014 | UN-001 | yes | none | NOT VERIFIED |

## Reliability

| | |
| --- | --- |
| Units | 40 |
| Weibull shape | 2.0466 |
| Weibull scale | 1369.28 hours |
| Fit r squared | 0.940464 |
| Interpretation | increasing hazard, consistent with wear out |
| B10 life | 456.0 hours |
| Reliability at 500 hours | 0.880539 |
