"""E001 design DoD: the refinement rule must never declare convergence while the true remaining error exceeds conv_tol.

Reviews T0055/T0056 of T0041: with a two-term error expansion e(h) = A h^p + B h^(p+1), A and B of opposite sign,
refined by a constant ratio >= 1.25 (the L2 contract), the sequence looks smooth and monotone while the slow term is
still hidden; the rule called ~10 % of such sequences converged with a true remaining error above conv_tol (5-20x
underestimate). A robust rule may be conservative (report inf / not converged), but must not be optimistic.
"""
import random
import sys

sys.path.insert(0, "experiments/runners")
import e001_reference as R  # noqa: E402

conv_tol = float(R.DEFAULT_CFG["conv_tol"])
rng = random.Random(20261001)
trials, false_conv, hidden = 3000, 0, 0
examples = []
for _ in range(trials):
    p = rng.choice([1.0, 1.5, 2.0])
    ratio = rng.choice([1.25, 1.5, 2.0])
    nlev = rng.choice([3, 4, 5])
    a = rng.uniform(0.005, 0.2) * rng.choice([-1.0, 1.0])
    b = -abs(rng.uniform(0.005, 0.4)) * (1.0 if a > 0 else -1.0)  # opposite sign to a
    seq = [1.0 + a * h ** p + b * h ** (p + 1) for h in (ratio ** -k for k in range(nlev))]
    true = abs(seq[-1] - 1.0)
    est = float(R.remaining_discretization_error(seq))
    if true > conv_tol:
        hidden += 1
        if est < conv_tol:
            false_conv += 1
            if len(examples) < 3:
                examples.append(f"p={p} ratio={ratio} levels={nlev} est={est:.2e} true={true:.2e}")
print(f"{hidden} of {trials} sequences have a true remaining error above conv_tol={conv_tol}; "
      f"the rule called {false_conv} of them converged")
assert false_conv == 0, f"false convergence in {false_conv} sequences, e.g. " + "; ".join(examples)
print("no false convergence on opposite-sign two-term expansions")
