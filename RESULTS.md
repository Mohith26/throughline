# Results

Working notes. Every number in the README appears here with the command that
produced it. If it is not in `results/benchmarks.json` or in the test output it
does not belong in either file.

```
python3 fixtures/generate.py     # deterministic from SEED
python3 tests/run.py             # full suite
python3 tests/count_tests.py     # per file counts
python3 bench/run.py             # results/benchmarks.json
python3 core/report.py --failures fixtures/failures.json --mission-hours 500
```

## Environment

```
CPython 3.12.1
Emscripten-3.1.58-wasm32-32bit
perf_counter resolution floor: 0.1 ms (measured, not assumed)
```

Python compiled to WebAssembly, because no native interpreter was available where
I built this. It is slower than native, and the runtime clamps its high resolution
timer as a side channel defence. The benchmark measures that floor by spinning on
`perf_counter` until the value changes, and reports it alongside everything else.

Consequence: several per operation timings sit at 0.1 ms and are the clock, not
the code. I have left them in the JSON and I do not quote them. The two headline
results are unaffected, because both are comparisons rather than absolute times:
the scaling exponent is a ratio, and the accuracy figures have no clock in them.

## Test suite

```
tests run 90, failures 0, errors 0      about 0.15 s
```

| File | Tests |
| --- | --- |
| tests/test_trace.py | 36 |
| tests/test_stats.py | 33 |
| tests/test_load.py | 21 |

Tests worth naming:

- `test_an_earlier_pass_does_not_clear_a_later_failure` is the one that matters
  most. Taking the best run rather than the latest is the easiest way to write
  this wrong and the most dangerous.
- `test_same_day_runs_are_broken_by_identifier_deterministically` runs the lookup
  five times and requires the same answer, because a report that changes between
  runs is a report nobody trusts.
- `test_agrees_with_the_exact_binomial_bound` cross checks the success run
  formula against the exact Clopper-Pearson bound across three confidence levels
  and four sample sizes. This is the test that caught the one sided mistake.
- `test_one_and_two_sided_bounds_differ_as_the_definitions_require` pins both
  closed forms so the distinction can never quietly collapse again.
- `test_finds_every_planted_defect` and `test_does_not_flood_the_report_with_extras`
  score recall and precision against the generator's own written down answer key.
- `test_a_clean_file_has_no_blockers_or_majors` is the negative control.

## Scoring against the planted defects

`fixtures/generate.py` plants eight defects and records them in
`fixtures/expected_findings.json`. The analyser finds all eight with the expected
severity, and produces 8 findings in total on that file: 3 blocker, 3 major, 2
minor, 0 informational. Recall 8/8, no extras.

| Rule | Subject | Severity |
| --- | --- | --- |
| contradictory-run | RUN-011 | blocker |
| requirement-unverified | SRS-014 | blocker |
| verification-failed | VER-004 | blocker |
| dangling-requirement-link | VER-011 | major |
| sample-size-short | VER-008 | major |
| verification-not-run | VER-013 | major |
| control-requirement-not-flagged | RC-005 | minor |
| orphan-requirement | SRS-012 | minor |

One correction along the way: the answer key originally named RUN-021 for the
contradictory run and the real identifier was RUN-011. The analyser was right and
the key was wrong. Worth recording because the obvious reflex on a failing test is
to look at the code first, and here the code was fine.

## Scaling

Analysis time against design file size, five sizes, median of five runs each.

| Requirements | Objects | Before | After | Speedup |
| --- | --- | --- | --- | --- |
| 50 | 191 | 1.2 ms | 0.2 ms | 6.0x |
| 100 | 386 | 2.8 ms | 0.5 ms | 5.6x |
| 200 | 782 | 2.9 ms | 1.0 ms | 2.9x |
| 400 | 1,555 | 10.7 ms | 0.8 ms | 13.4x |
| 800 | 3,084 | 42.6 ms | 3.7 ms | 11.5x |

Fitted exponent on `time = c * n^k`: **1.223 before, 0.910 after.**

The cause was that every reverse lookup was a list comprehension over the whole
table, so asking "which verifications cover this requirement" once per requirement
scanned all verifications for each one. At fourteen requirements that is free. The
400 to 800 step made it obvious: doubling the input quadrupled the time.

The fix is a reverse index built lazily and discarded on any write, so it cannot
drift from the tables it summarises. The exponent below 1.0 is measurement noise
at these sizes, not a sublinear algorithm; the honest reading is "linear".

## Numerical accuracy

The incomplete beta implementation checked against direct binomial summation over
every k for n in {5, 12, 30, 59, 100} and p in {0.01, 0.05, 0.2, 0.5, 0.8, 0.99}:

```
1,266 comparisons, worst absolute error 2.55e-14
```

Published values reproduced by the exact interval:

| Case | Expected | Source |
| --- | --- | --- |
| 0 failures in 29, one sided 95% | upper bound 0.09814 | closed form, 1 - 0.05^(1/29) |
| 0 failures in 29, two sided 95% | upper bound 0.11944 | closed form, 1 - 0.025^(1/29) |
| 2 failures in 20, two sided 95% | (0.01235, 0.31698) | standard table |
| 90% reliability at 95% confidence | 29 units | success run theorem |
| 95% reliability at 95% confidence | 59 units | success run theorem |

## Weibull recovery

Run two ways deliberately.

**Noiseless.** Exact median rank quantiles in, so the fit should invert them
exactly. Worst shape error 0.0 to fifteen decimal places across shapes 0.8, 1.0,
2.2 and 4.0 at n of 10, 25 and 50. This checks the algebra and says nothing about
data.

**Sampled.** Genuinely random draws from the same distribution, 200 independent
studies per cell. Median absolute error in the fitted shape:

| True shape | n=10 | n=25 | n=50 | n=100 |
| --- | --- | --- | --- | --- |
| 1.0 | 21.5% | 13.2% | 10.2% | 8.4% |
| 2.2 | 20.9% | 13.9% | 10.5% | 8.3% |
| 4.0 | 20.3% | 13.7% | 8.0% | 6.8% |

p90 error at n=10 runs 45 to 48 percent. Median r squared at n=10 is about 0.93,
which is high enough that the fit looks convincing while being that far out.

The practical reading, and the reason this benchmark exists in two forms: a ten
unit reliability study pins the Weibull shape to roughly 20 percent. Quoting a
shape to two decimals from ten units is false precision, and the qualitative call
that hangs off it, infant mortality against random against wear out, is not safe
at that sample size either. The noiseless run would have told me none of this.

## Example report

`docs/example-report.md`, generated from the fixture. Coverage on that file:

| Measure | Value |
| --- | --- |
| Needs covered by a requirement | 100% |
| Requirements with a verification | 92.86% |
| Requirements passing | 78.57% |
| Safety requirements verified | 85.71% |
| Hazards with a risk control | 100% |

Reliability section from the 40 synthetic failure times, which were drawn from a
Weibull with shape 2.2 and scale 1450: the fit returns shape 2.0466 and scale
1369.28, r squared 0.94. That is a 7 percent shape error on 40 samples, which sits
right where the sampled recovery table says it should. The fit not landing exactly
on 2.2 is the expected behaviour, not a defect.

Exit code 1, because there are blockers.

## Things that went wrong, in order

1. **One sided against two sided confidence bounds.** Caught by two independent
   routes to the same number disagreeing. The fix was a `sided` argument and an
   explicitly one sided reliability bound.
2. **The answer key was wrong, not the analyser.** RUN-021 against RUN-011.
3. **Analysis was quadratic.** Invisible on the fixture, obvious on a synthetic
   file eight hundred requirements wide.
4. **A benchmark that scored perfectly.** Zero error on Weibull recovery meant the
   benchmark was feeding the fit its own answer. Adding real sampling turned it
   into a result that says something useful.
