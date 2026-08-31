"""Benchmarks.

The interesting question for this tool is not raw speed, it is how the analysis
scales, because a real design history file has thousands of requirements rather
than fourteen and several of the checks are naturally quadratic if written
carelessly. So the sweep grows the file and reports the scaling exponent
alongside the timings.
"""

import json
import math
import os
import platform
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import load, model, report, stats, trace

RESULTS = os.path.join(ROOT, "results")
FIXTURES = os.path.join(ROOT, "fixtures")


def clock_resolution():
    """Measured, not assumed. A browser hosted runtime clamps its timers, and a
    benchmark that reports the floor as if it were a measurement is worse than no
    benchmark."""
    gaps = []
    for _ in range(2000):
        a = time.perf_counter()
        b = time.perf_counter()
        while b == a:
            b = time.perf_counter()
        gaps.append(b - a)
    return {"min_gap_ms": round(min(gaps) * 1000.0, 6),
            "median_gap_ms": round(statistics.median(gaps) * 1000.0, 6)}


def percentiles(samples):
    ordered = sorted(samples)
    def at(p):
        return round(ordered[min(len(ordered) - 1, int(p / 100.0 * len(ordered)))] * 1000.0, 4)
    return {"n": len(ordered), "p50_ms": at(50), "p90_ms": at(90), "p99_ms": at(99),
            "mean_ms": round(statistics.fmean(ordered) * 1000.0, 4)}


def timed(fn, repeats):
    out = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
    return out


def synthetic_design(n_requirements, seed=7):
    """A design file of a given size with a realistic link density.

    Roughly one need per four requirements, one verification per requirement,
    1.4 runs per verification, and one hazard per ten requirements, which is the
    shape of the real thing scaled up.
    """
    rng = random.Random(seed)
    d = model.DesignFile()
    n_needs = max(1, n_requirements // 4)
    for i in range(1, n_needs + 1):
        d.add(model.UserNeed("UN-%04d" % i, "need %d" % i))
    for i in range(1, n_requirements + 1):
        d.add(model.Requirement(
            "SRS-%04d" % i, "requirement %d" % i,
            needs=["UN-%04d" % rng.randint(1, n_needs)],
            safety_related=(i % 5 == 0)))
    for i in range(1, n_requirements + 1):
        d.add(model.Verification("VER-%04d" % i, "verification %d" % i,
                                 ["SRS-%04d" % i], "test", 5, "acceptance"))
    run_id = 1
    for i in range(1, n_requirements + 1):
        for _ in range(1 + (1 if rng.random() < 0.4 else 0)):
            d.add(model.TestRun("RUN-%05d" % run_id, "VER-%04d" % i,
                                "pass" if rng.random() < 0.93 else "fail",
                                "2026-%02d-%02d" % (rng.randint(1, 12), rng.randint(1, 28)),
                                units=5, failures=0))
            run_id += 1
    n_hazards = max(1, n_requirements // 10)
    for i in range(1, n_hazards + 1):
        d.add(model.Hazard("HAZ-%04d" % i, "hazard %d" % i, "serious", "remote"))
        d.add(model.RiskControl("RC-%04d" % i, "control %d" % i, "HAZ-%04d" % i,
                                "SRS-%04d" % (((i * 5) % n_requirements) + 1)))
    return d


def bench_scaling():
    sizes = [50, 100, 200, 400, 800]
    points = []
    for size in sizes:
        design = synthetic_design(size)
        samples = timed(lambda d=design: trace.analyse(d), 5)
        median = statistics.median(samples)
        points.append({
            "requirements": size,
            "objects": len(design),
            "analyse_ms": round(median * 1000.0, 3),
            "ms_per_requirement": round(median * 1000.0 / size, 5),
        })
    # Fit an exponent to time = c * n^k on a log log scale. k near 1 is linear,
    # near 2 means a quadratic scan slipped in somewhere.
    xs = [math.log(p["requirements"]) for p in points]
    ys = [math.log(p["analyse_ms"]) for p in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs)))
    exponent = sxy / sxx
    return {"points": points, "scaling_exponent": round(exponent, 3),
            "note": "time = c * n^k fitted on log log; 1.0 is linear, 2.0 is quadratic"}


def bench_operations():
    design = load.load(os.path.join(FIXTURES, "design.json"))
    with open(os.path.join(FIXTURES, "failures.json")) as handle:
        times = json.load(handle)["times"]
    return {
        "load_fixture_ms": percentiles(timed(
            lambda: load.load(os.path.join(FIXTURES, "design.json")), 40)),
        "analyse_fixture_ms": percentiles(timed(lambda: trace.analyse(design), 100)),
        "matrix_ms": percentiles(timed(lambda: trace.matrix(design), 100)),
        "coverage_ms": percentiles(timed(lambda: trace.coverage(design), 100)),
        "markdown_report_ms": percentiles(timed(
            lambda: report.to_markdown(report.build(design)), 40)),
        "weibull_fit_ms": percentiles(timed(lambda: stats.weibull_fit(times), 200)),
        "clopper_pearson_ms": percentiles(timed(
            lambda: stats.clopper_pearson(3, 59, 0.95), 200)),
    }


def bench_numerics():
    """Accuracy, not speed. A reliability number that is fast and wrong is worse
    than useless, so the incomplete beta is checked against direct binomial
    summation and the worst error is recorded."""
    worst = 0.0
    checks = 0
    for n in [5, 12, 30, 59, 100]:
        for p in [0.01, 0.05, 0.2, 0.5, 0.8, 0.99]:
            for k in range(0, n + 1):
                direct = sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))
                mine = stats.binomial_cdf(k, n, p)
                worst = max(worst, abs(direct - mine))
                checks += 1
    return {"comparisons": checks, "worst_absolute_error": worst}


def bench_recovery():
    """How well the Weibull fit recovers parameters it was built from.

    Two modes, and the difference between them is the point.

    The noiseless mode feeds the exact median rank quantiles back in. It returns
    zero error to fifteen decimal places, which proves the algebra is right and
    proves nothing whatsoever about behaviour on data. A benchmark that scores
    perfectly is telling you the benchmark is too easy.

    The sampled mode draws actual random failures from the same distribution,
    which is what a real reliability study has, and reports the spread across
    repeated studies. Those are the numbers worth quoting.
    """
    rows = []
    for shape, scale in [(0.8, 500.0), (1.0, 1000.0), (2.2, 1450.0), (4.0, 800.0)]:
        for n in [10, 25, 50]:
            times = [scale * (-math.log(1.0 - f)) ** (1.0 / shape)
                     for f in stats.median_ranks(n)]
            got_shape, got_scale, r2 = stats.weibull_fit(times)
            rows.append({
                "true_shape": shape, "true_scale": scale, "n": n,
                "shape_error_pct": round(abs(got_shape - shape) / shape * 100.0, 9),
                "scale_error_pct": round(abs(got_scale - scale) / scale * 100.0, 9),
                "r_squared": round(r2, 9),
            })

    sampled = []
    rng = random.Random(4242)
    for shape, scale in [(1.0, 1000.0), (2.2, 1450.0), (4.0, 800.0)]:
        for n in [10, 25, 50, 100]:
            shape_errors = []
            scale_errors = []
            r2s = []
            for _ in range(200):
                times = sorted(scale * (-math.log(1.0 - rng.random())) ** (1.0 / shape)
                               for _ in range(n))
                got_shape, got_scale, r2 = stats.weibull_fit(times)
                shape_errors.append(abs(got_shape - shape) / shape * 100.0)
                scale_errors.append(abs(got_scale - scale) / scale * 100.0)
                r2s.append(r2)
            sampled.append({
                "true_shape": shape, "true_scale": scale, "n": n, "studies": 200,
                "median_shape_error_pct": round(statistics.median(shape_errors), 3),
                "p90_shape_error_pct": round(sorted(shape_errors)[179], 3),
                "median_scale_error_pct": round(statistics.median(scale_errors), 3),
                "median_r_squared": round(statistics.median(r2s), 4),
            })

    return {
        "noiseless": rows,
        "noiseless_worst_shape_error_pct": max(r["shape_error_pct"] for r in rows),
        "noiseless_note": "exact quantiles in, so zero error here only checks the algebra",
        "sampled": sampled,
        "sampled_worst_median_shape_error_pct": max(s["median_shape_error_pct"] for s in sampled),
    }


def main():
    os.makedirs(RESULTS, exist_ok=True)
    started = time.time()
    payload = {
        "environment": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "clock": clock_resolution(),
        },
        "scaling": bench_scaling(),
        "operations": bench_operations(),
        "numerics": bench_numerics(),
        "weibull_recovery": bench_recovery(),
    }
    payload["wall_seconds"] = round(time.time() - started, 2)

    path = os.path.join(RESULTS, "benchmarks.json")
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)

    sc = payload["scaling"]
    print("scaling exponent %.3f (1.0 would be linear)" % sc["scaling_exponent"])
    for p in sc["points"]:
        print("  %4d requirements, %5d objects -> %8.3f ms  (%.5f ms each)"
              % (p["requirements"], p["objects"], p["analyse_ms"], p["ms_per_requirement"]))
    ops = payload["operations"]
    for name in sorted(ops):
        print("  %-22s p50 %8.4f ms" % (name, ops[name]["p50_ms"]))
    print("binomial cdf worst absolute error vs direct summation: %.3e"
          % payload["numerics"]["worst_absolute_error"])
    rec = payload["weibull_recovery"]
    print("weibull noiseless worst shape error %.2e%% (algebra check only)"
          % rec["noiseless_worst_shape_error_pct"])
    print("weibull sampled median shape error by study size:")
    for s in rec["sampled"]:
        print("  shape %.1f n=%3d -> median %5.2f%%  p90 %5.2f%%  r2 %.4f"
              % (s["true_shape"], s["n"], s["median_shape_error_pct"],
                 s["p90_shape_error_pct"], s["median_r_squared"]))
    print("clock floor %.4f ms" % payload["environment"]["clock"]["median_gap_ms"])
    print("wrote %s in %.1fs" % (path, payload["wall_seconds"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
