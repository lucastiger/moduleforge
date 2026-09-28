import numpy as np

from mfos.stats import bootstrap_ci, mape, spearman, topk_recall


def test_spearman_known_values():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert abs(spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) - 0.8) < 1e-12  # 1 - 6*4/(5*24)


def test_bootstrap_is_reproducible_and_brackets_point():
    rng = np.random.default_rng(0)
    x = rng.normal(size=60)
    y = x + 0.3 * rng.normal(size=60)
    p1, ci1 = bootstrap_ci(spearman, x, y, n_boot=500, seed=3)
    p2, ci2 = bootstrap_ci(spearman, x, y, n_boot=500, seed=3)
    assert (p1, ci1) == (p2, ci2)
    assert ci1[0] <= p1 <= ci1[1]


def test_mape_and_topk():
    assert abs(mape([1.1, 0.9], [1.0, 1.0]) - 0.1) < 1e-12
    ref = np.arange(100.0)
    assert topk_recall(ref, ref) == 1.0
