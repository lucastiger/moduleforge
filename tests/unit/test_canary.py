import math
from fractions import Fraction

import pytest

from moduleforge.canary import harmonic

# Euler-Mascheroni constant, OEIS A001620.
GAMMA = 0.57721566490153286061


def test_exact_small():
    assert harmonic(1) == 1.0
    assert harmonic(2) == 1.5


def test_matches_exact_rational():
    exact = float(sum(Fraction(1, k) for k in range(1, 11)))
    assert abs(harmonic(10) - exact) / exact <= 1e-15


@pytest.mark.parametrize("n", [1000, 10000, 100000, 1000000])
def test_asymptotic_expansion(n):
    # H_n ~ ln n + gamma + 1/(2n) - 1/(12 n^2) + 1/(120 n^4)
    # (Concrete Mathematics, §9.6).
    ref = math.log(n) + GAMMA + 1 / (2 * n) - 1 / (12 * n**2) + 1 / (120 * n**4)
    assert abs(harmonic(n) - ref) / ref <= 1e-12


def test_type_and_monotone():
    vals = [harmonic(n) for n in (1, 2, 3, 10, 100, 1000)]
    assert all(type(v) is float for v in vals)
    assert all(a < b for a, b in zip(vals, vals[1:], strict=False))


@pytest.mark.parametrize("n", [0, -1])
def test_value_error(n):
    with pytest.raises(ValueError):
        harmonic(n)


@pytest.mark.parametrize("n", [2.5, True])
def test_type_error(n):
    with pytest.raises(TypeError):
        harmonic(n)
