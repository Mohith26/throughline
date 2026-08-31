# Throughline

A traceability and reliability analyser for a medical device design history file.

It answers the question a design review actually turns on: can you draw an
unbroken line from every user need, through the requirement that implements it,
to the verification that tested it and the run that passed, and can you do the
same for every hazard and its risk control. Where the line breaks, it says so and
says how badly.

No dependencies outside the standard library. Python 3.9 or newer.

```
python3 fixtures/generate.py     # build the sample design file
python3 tests/run.py             # 90 tests
python3 bench/run.py             # writes results/benchmarks.json
python3 core/report.py --failures fixtures/failures.json --mission-hours 500
```

The report command exits non zero when there is a blocker, so it can sit in a
pipeline and stop a release the same way a failing test does.
[An example report is in `docs/example-report.md`.](docs/example-report.md)

## The shape of the thing

```
UserNeed  ->  Requirement  ->  Verification  ->  TestRun
                   ^
                Hazard  ->  RiskControl
```

| Path | What it does |
| --- | --- |
| `core/model.py` | The objects, and the reverse index that makes the walk linear |
| `core/load.py` | JSON in, objects out, with errors that name the offending entry |
| `core/trace.py` | The twenty checks, and coverage and matrix generation |
| `core/stats.py` | Incomplete beta, Clopper-Pearson, success run sizing, Weibull |
| `core/report.py` | Markdown or JSON, plus the exit code |

## Two design decisions

**Nothing raises during analysis.** A design file is incomplete for most of its
life, and a tool that refuses to load an incomplete file is useless exactly when
you want it most. Loading rejects only what makes an object impossible to build,
such as an unknown severity word. Everything else, including links that point at
nothing, comes back as a finding with a severity attached.

**Severity is graded, not flat.** An unverified safety related requirement is a
blocker; an unverified ordinary one is a major. A hazard with no control at all
is a blocker; a control that exists but whose requirement was not flagged safety
related is a minor. Sorting an undifferentiated findings list is how the
important ones end up on page four.

Twenty rules in all. The ones that carry weight:

| Rule | Severity | Catches |
| --- | --- | --- |
| `requirement-unverified` | blocker if safety related, else major | a requirement nothing tests |
| `verification-failed` | blocker | the most recent run failed |
| `contradictory-run` | blocker | a run marked pass that reports failing units |
| `impossible-run` | blocker | more failures than units tested |
| `hazard-uncontrolled` | blocker | a hazard with no risk control |
| `control-unverified` | blocker | a risk control whose requirement is untested |
| `risk-increased` | blocker | residual risk worse than the initial risk |
| `sample-size-short` | major | a run with fewer units than the protocol requires |
| `verification-not-run` | major | a protocol that was never executed |
| `dangling-*-link` | major | a reference to something that does not exist |
| `orphan-*`, `identifier-format` | minor, info | hygiene |

## The check that matters most

`latest_run` takes the most recent run by date, not the best one. The fixture has
a verification that went fail, then pass, then fail again after a firmware
regression, and the report has to say fail. Taking the best result is the single
most dangerous way to get this wrong, and it is a very easy thing to write by
accident when you are reaching for `any(r.result == "pass" ...)`. There is a test
named after it.

Ties on the same date are broken by identifier so the answer is deterministic,
which also has a test, because a report that changes between runs is a report
nobody trusts.

## Scoring the analyser instead of trusting it

The fixture generator plants eight specific defects and writes down what it
broke, in `fixtures/expected_findings.json`. The analyser is scored against that
list rather than against its own previous output:

- every planted defect is found, with the expected severity
- a clean design file produces zero blockers and zero majors
- the number of serious findings does not exceed the number planted by more than
  two, because precision matters as much as recall and a checker that reports a
  hundred findings on a file with eight defects is not usable

A checker that reports nothing on a clean file has demonstrated nothing, so both
directions are tested.

## Statistics

Implemented from the definitions, with no third party library. The reason is not
dependency minimalism: a reliability claim in a design history file has to be
defensible line by line, and "the library said so" is not a defence. The tests
check against published values and closed forms, not against a previous run.

- **Regularised incomplete beta**, by the modified Lentz continued fraction. The
  binomial CDF and the Clopper-Pearson interval both go through it. Checked
  against direct binomial summation across 1,266 combinations: worst absolute
  error 2.6e-14.
- **Clopper-Pearson exact interval**, one or two sided.
- **Success run sizing**, which reproduces the two numbers every reliability plan
  quotes: 29 units for 90/95 and 59 for 95/95.
- **Weibull by median rank regression**, with the r squared reported next to the
  parameters rather than buried, because a Weibull fitted to data that is not
  Weibull still returns two confident looking numbers.

### The one sided versus two sided mistake

I wrote `alpha/2` everywhere and the tests caught it, because the success run
formula and the exact Clopper-Pearson bound stopped agreeing with each other.

They are two independent routes to the same number for a clean run, and when two
independent routes disagree one of them is wrong. It was the interval. A two
sided 95 percent interval puts 2.5 percent in each tail; a reliability
demonstration quotes a one sided bound with the whole 5 percent in one tail. For
a clean run of 29 units the upper bound on the failure rate is 0.0981 one sided
against 0.1194 two sided. That is not rounding, it is the difference between
demonstrating 90 percent reliability and demonstrating 88 percent.

`clopper_pearson` now takes a `sided` argument and `reliability_lower_bound` is
explicitly one sided, with both closed forms pinned in the tests.

## Numbers

From `results/benchmarks.json`.

**Analysis was quadratic and is now linear.** Every reverse lookup was a list
comprehension over the whole table, so asking "which verifications cover this
requirement" once per requirement scanned everything twice over. It is invisible
at fourteen requirements and very visible at eight hundred:

| Requirements | Objects | Before | After |
| --- | --- | --- | --- |
| 50 | 191 | 1.2 ms | 0.2 ms |
| 100 | 386 | 2.8 ms | 0.5 ms |
| 200 | 782 | 2.9 ms | 1.0 ms |
| 400 | 1,555 | 10.7 ms | 0.8 ms |
| 800 | 3,084 | 42.6 ms | 3.7 ms |

Fitted scaling exponent went from **1.22 to 0.91**, and the largest case got 11.5x
faster. The fix is a lazily built reverse index that is discarded on any write, so
it cannot drift from the tables it summarises.

**How much data a reliability study actually needs.** The Weibull recovery
benchmark runs two ways on purpose. Fed the exact median rank quantiles it
returns zero error to fifteen decimal places, which checks the algebra and proves
nothing about behaviour on data. Fed genuinely random samples, 200 studies per
cell:

| True shape | n = 10 | n = 25 | n = 50 | n = 100 |
| --- | --- | --- | --- | --- |
| 1.0 | 21.5% | 13.2% | 10.2% | 8.4% |
| 2.2 | 20.9% | 13.9% | 10.5% | 8.3% |
| 4.0 | 20.3% | 13.7% | 8.0% | 6.8% |

Median absolute error in the fitted shape parameter. The practical reading: a ten
unit study estimates the Weibull shape to about 20 percent, so quoting a shape to
two decimal places off ten units is false precision, and the interpretation that
hangs off it, infant mortality against wear out, is not reliable at that sample
size either.

**Environment.** Measured under CPython 3.12 compiled to WebAssembly, because no
native interpreter was available on the machine I built this on. It is slower than
native, and the runtime clamps `perf_counter` to a **0.1 ms** floor, measured in
the benchmark rather than assumed. Several per operation timings sit at that floor
and are the clock rather than the code; they are left in the JSON and not quoted
here. The scaling table and the accuracy figures are unaffected, because both are
comparisons rather than absolute times.

## Tests

90 tests, about 0.15 seconds.

```
tests/test_trace.py   36   the rules, the matrix, the planted defect scoring
tests/test_stats.py   33   incomplete beta, exact intervals, success runs, Weibull
tests/test_load.py    21   model validation, loader errors, multi file merge
```

## Limitations

- Synthetic data throughout. The device, the requirements and the failure times
  are invented, chosen so the tests can assert against known answers.
- Risk is modelled as an ordered severity and probability pair. There is no risk
  acceptability matrix, because that is a per organisation policy document rather
  than something a tool should assume.
- No coverage of design validation, only verification. Validation asks whether
  the right device was built, and that is not a question you answer from a link
  graph.
- Median rank regression rather than maximum likelihood for the Weibull fit. It
  is what reliability standards describe and it yields the r squared, but MLE has
  better small sample properties.
- Single file or single directory input. No database, no concurrent editing.
