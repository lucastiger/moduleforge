"""E001 design DoD: on the registered path the remaining-error estimate must bound single-term convergence tightly.

Registered path (as the runner calls it): remaining_discretization_error(values, h=<relative mesh sizes>,
order_range=(order_min, order_max), steady_tol=steady_tol). For an exact single-term error e(h) = A h^p with p in
[order_min, order_max] and a constant ratio q >= 1.25 (the L2 contract) the estimate must lie in [true, 3 x true];
exactly constant values must give ~0. (Earlier versions of this check called the values-only fallback, which the
runner never uses: reviews T0058/T0059 of T0057.) Two-term and adversarial sequences: estimator_adversarial.py.
"""
import sys

sys.path.insert(0, "experiments/runners")
import e001_reference as R  # noqa: E402

cfg = R.DEFAULT_CFG
order_range = (float(cfg["order_min"]), float(cfg["order_max"]))
steady_tol = float(cfg["steady_tol"])
assert hasattr(R, "remaining_discretization_error"), "runner does not expose remaining_discretization_error"
problems = []
for p in (1.0, 1.5, 2.0):
    for q in (1.25, 1.5, 2.0):
        h = [q ** -k for k in range(5)]
        v = [1.0 + 0.05 * x ** p for x in h]
        true = abs(v[-1] - 1.0)
        est = float(R.remaining_discretization_error(v, h=h, order_range=order_range, steady_tol=steady_tol))
        print(f"p={p} q={q}: estimate {est:.3e}, true remaining error {true:.3e}")
        if not 0.999 * true <= est <= 3 * true:
            problems.append(f"p={p} q={q}: estimate {est:.3e} not within [true, 3 x true] = [{true:.3e}, {3 * true:.3e}]")
flat = float(R.remaining_discretization_error([1.0] * 5, h=[2.0 ** -k for k in range(5)], order_range=order_range,
                                              steady_tol=steady_tol))
if flat > 1e-12:
    problems.append(f"a converged sequence gives {flat:.3e}, expected ~0")
assert not problems, "; ".join(problems)
print("remaining-error estimator bounds single-term convergence on the registered path")
