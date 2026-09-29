"""Framework canary: harmonic numbers with a known asymptotic answer."""

from __future__ import annotations

import math


def harmonic(n: int) -> float:
    """Return the n-th harmonic number H_n = sum_{k=1}^{n} 1/k as float64.

    Definition: Graham, Knuth, Patashnik, *Concrete Mathematics*, 2nd ed., §6.3.
    Terms are summed with ``math.fsum`` (correctly rounded summation).

    Raises:
        TypeError: if ``n`` is not an int (bool is rejected).
        ValueError: if ``n < 1``.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"n must be an int, got {type(n).__name__}")
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    return math.fsum(1.0 / k for k in range(1, n + 1))
