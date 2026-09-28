"""E000 canary runner: harmonic numbers against their asymptotic expansion.

The reference is validated on this run (sanity check `reference_valid`) before it is used.
"""
import argparse
import math
from fractions import Fraction

from mfos.evidence import ExperimentRun

GAMMA = 0.57721566490153286061  # Euler–Mascheroni constant (OEIS A001620)


def asymptotic(n: int) -> float:
    # H_n = ln n + γ + 1/(2n) − 1/(12 n²) + 1/(120 n⁴) − …  (Graham, Knuth, Patashnik, Concrete Mathematics §9.6)
    return math.log(n) + GAMMA + 1 / (2 * n) - 1 / (12 * n**2) + 1 / (120 * n**4)


def main(smoke: bool) -> None:
    from moduleforge.canary import harmonic

    with ExperimentRun(run_dir="/tmp/e000-smoke" if smoke else None) as run:
        ns = [1000, 10000] if smoke else run.config["ns"]
        run.sanity("exact_small_cases", passed=harmonic(1) == 1.0 and harmonic(2) == 1.5)
        exact10 = float(sum(Fraction(1, k) for k in range(1, 11)))
        ref_err = abs(asymptotic(10) - exact10) / exact10
        run.sanity("reference_valid", passed=ref_err < 1e-8, value=ref_err, threshold=1e-8)
        errs = [abs(harmonic(n) - asymptotic(n)) / asymptotic(n) for n in ns]
        run.metric("max_rel_err", max(errs), n=len(ns))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(ap.parse_args().smoke)
