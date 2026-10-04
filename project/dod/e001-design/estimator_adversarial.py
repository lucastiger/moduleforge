"""E001 design DoD: the refinement rule, on the registered path, must neither converge falsely nor refuse accurate solvers.

Registered path: remaining_discretization_error(values, h=<relative mesh sizes>, order_range=(order_min, order_max),
steady_tol=steady_tol), as the runner calls it (reviews T0058/T0059 of T0057: the earlier check exercised only the
values-only fallback, which the runner never uses). Error model e(h) = A h^p + B h^(p+1), constant ratio q >= 1.25.
  1. Safety (reviews T0055/T0056 of T0041): with A, B of opposite sign the slow term can hide; the rule must never
     report an estimate below conv_tol while the true remaining error is above conv_tol.
  2. Power (review T0058 of T0057): with A, B of the same sign there is no cancellation, but the observed order exceeds
     p; capping it at order_max rejected 265 of 265 accurate sequences at p = 2. Sequences whose true remaining error is
     below conv_tol / 10 must be declared converged in >= 90 % of cases for each leading order p in {1, 1.5, 2}.
  3. Both hold with worst-case compliant solver noise (+-solver_err_budget per value, floor 2 x budget).
"""
import random
import sys

sys.path.insert(0, "experiments/runners")
import e001_reference as R  # noqa: E402

cfg = R.DEFAULT_CFG
conv_tol = float(cfg["conv_tol"])
order_range = (float(cfg["order_min"]), float(cfg["order_max"]))
steady_tol = float(cfg["steady_tol"])
rng = random.Random(20261003)


def sample(sign):
    p, q, n = rng.choice([1.0, 1.5, 2.0]), rng.choice([1.25, 1.5, 2.0]), rng.choice([4, 5])
    a = rng.uniform(0.005, 0.2) * rng.choice([-1.0, 1.0])
    b = abs(rng.uniform(0.005, 0.4)) * (1.0 if a > 0 else -1.0) * sign
    h = [q ** -k for k in range(n)]
    v = [1.0 + a * x ** p + b * x ** (p + 1) for x in h]
    est = float(R.remaining_discretization_error(v, h=h, order_range=order_range, steady_tol=steady_tol))
    return p, abs(v[-1] - 1.0), est


problems = []
false_conv = hidden = 0
for _ in range(4000):
    _, true, est = sample(-1.0)
    if true > conv_tol:
        hidden += 1
        false_conv += est < conv_tol
print(f"safety: {false_conv} false convergences among {hidden} opposite-sign sequences with true error > conv_tol")
if false_conv:
    problems.append(f"{false_conv} false convergences on opposite-sign sequences")
accepted = {}
while min((t for _, t in accepted.values()), default=0) < 100 or len(accepted) < 3:
    p, true, est = sample(+1.0)
    if true < conv_tol / 10:
        a, t = accepted.get(p, (0, 0))
        accepted[p] = (a + (est < conv_tol), t + 1)
for p, (a, t) in sorted(accepted.items()):
    print(f"power: p={p}: {a}/{t} accurate same-sign sequences declared converged ({a / t:.0%})")
    if a < 0.9 * t:
        problems.append(f"p={p}: only {a}/{t} accurate sequences declared converged (need >= 90 %)")
# 3. Noise (reviews T0061/T0062 of T0060): the runner's noise floor is 2 x min(solver_err_budget, solver_tol x amp).
#    A compliant solver may err by up to solver_err_budget per value, so test that worst case: values perturbed by
#    +-budget (relative), floor 2 x budget. At budget 1e-4 power fell to 17-32 %; the design must keep >= 90 %.
budget = float(cfg["solver_err_budget"])
false_noisy, hidden_noisy, noisy = 0, 0, {}
nrng = random.Random(20261004)
for i in range(16000):
    sign = 1.0 if i % 2 == 0 else -1.0
    p, q, n = nrng.choice([1.0, 1.5, 2.0]), nrng.choice([1.25, 1.5, 2.0]), nrng.choice([4, 5])
    a = nrng.uniform(0.005, 0.2) * nrng.choice([-1.0, 1.0])
    b = abs(nrng.uniform(0.005, 0.4)) * (1.0 if a > 0 else -1.0) * sign
    h = [q ** -k for k in range(n)]
    exact = [1.0 + a * x ** p + b * x ** (p + 1) for x in h]
    v = [e * (1 + nrng.uniform(-budget, budget)) for e in exact]
    true = abs(exact[-1] - 1.0)
    est = float(R.remaining_discretization_error(v, noise=2 * budget * abs(v[-1]), h=h, order_range=order_range,
                                                 steady_tol=steady_tol))
    if sign > 0 and true < conv_tol / 10:
        acc_, tot_ = noisy.get(p, (0, 0))
        noisy[p] = (acc_ + (est < conv_tol), tot_ + 1)
    if sign < 0 and true > conv_tol:
        hidden_noisy += 1
        false_noisy += est < conv_tol
print(f"noisy (solver_err_budget {budget:.0e}): {false_noisy} false convergences among {hidden_noisy}; power "
      + ", ".join(f"p={p}: {a_}/{t_}" for p, (a_, t_) in sorted(noisy.items())))
if false_noisy:
    problems.append(f"noisy: {false_noisy} false convergences at solver_err_budget {budget:.0e}")
for p, (a_, t_) in sorted(noisy.items()):
    if a_ < 0.9 * t_:
        problems.append(f"noisy p={p}: only {a_}/{t_} accurate sequences declared converged at solver_err_budget "
                        f"{budget:.0e} (need >= 90 %)")
assert not problems, "; ".join(problems)
print("refinement rule: no false convergence and >= 90 % acceptance of accurate solvers, noise-free and at the "
      "solver budget, on the registered path")
