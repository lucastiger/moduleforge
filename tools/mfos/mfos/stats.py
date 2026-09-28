"""Small, dependency-light statistics used by experiment runners.

Every metric that feeds an acceptance criterion should carry an uncertainty
interval; these helpers make that the path of least resistance.
"""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np


def _rank(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(len(a), dtype=float)
    # average ties
    vals, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    if np.any(counts > 1):
        sums = np.zeros(len(vals))
        np.add.at(sums, inv, ranks)
        ranks = sums[inv] / counts[inv]
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) != len(y) or len(x) < 3:
        raise ValueError("spearman needs two equal-length samples of size >= 3")
    rx, ry = _rank(x), _rank(y)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx**2).sum() * (ry**2).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else 0.0


def mape(pred: Sequence[float], ref: Sequence[float]) -> float:
    p, r = np.asarray(pred, float), np.asarray(ref, float)
    if np.any(r == 0):
        raise ValueError("mape undefined for zero reference values")
    return float(np.mean(np.abs(p - r) / np.abs(r)))


def topk_recall(pred: Sequence[float], ref: Sequence[float], k_frac: float = 0.1, within_frac: float = 0.2,
                lower_is_better: bool = True) -> float:
    """Fraction of the predicted top k_frac that lie inside the reference top within_frac."""
    p, r = np.asarray(pred, float), np.asarray(ref, float)
    sgn = 1.0 if lower_is_better else -1.0
    k = max(1, int(round(k_frac * len(p))))
    w = max(1, int(round(within_frac * len(r))))
    top_pred = set(np.argsort(sgn * p)[:k].tolist())
    top_ref = set(np.argsort(sgn * r)[:w].tolist())
    return len(top_pred & top_ref) / k


def bootstrap_ci(stat: Callable[..., float], *samples: Sequence[float], n_boot: int = 2000,
                 level: float = 0.95, seed: int = 0) -> tuple[float, tuple[float, float]]:
    """Paired percentile bootstrap. Returns (point_estimate, (lo, hi))."""
    arrays = [np.asarray(s, float) for s in samples]
    n = len(arrays[0])
    if any(len(a) != n for a in arrays):
        raise ValueError("paired bootstrap needs equal-length samples")
    rng = np.random.default_rng(seed)
    point = float(stat(*arrays))
    boots = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        boots[i] = stat(*[a[idx] for a in arrays])
    alpha = (1.0 - level) / 2.0
    lo, hi = np.quantile(boots, [alpha, 1.0 - alpha])
    return point, (float(lo), float(hi))
