"""E001 design DoD: the refinement rule must estimate the remaining discretization error, not the last step.

Review T0030 of T0020: for geometric convergence with ratio rho the remaining error is change * rho / (1 - rho),
4x the last change at rho = 0.8 and 9x at rho = 0.9. The runner must expose
`remaining_discretization_error(values)` (L at successive refinement levels, finest last) and use it for both
the l2_converged decision and disc_unc.
"""
import sys

sys.path.insert(0, "experiments/runners")
import e001_reference as R  # noqa: E402

assert hasattr(R, "remaining_discretization_error"), "runner does not expose remaining_discretization_error(values)"
problems = []
for rho in (0.5, 0.8, 0.9):
    seq = [1.0 + 0.02 * rho ** k for k in range(4)]
    true = abs(seq[-1] - 1.0)
    est = float(R.remaining_discretization_error(seq))
    print(f"rho={rho}: estimate {est:.3e}, true remaining error {true:.3e}")
    if not 0.999 * true <= est <= 3 * true:
        problems.append(f"rho={rho}: estimate {est:.3e} not within [true, 3 x true] = [{true:.3e}, {3 * true:.3e}]")
flat = float(R.remaining_discretization_error([1.0, 1.0, 1.0]))
if flat > 1e-12:
    problems.append(f"a converged sequence gives {flat:.3e}, expected ~0")
assert not problems, "; ".join(problems)
print("remaining-error estimator bounds geometric convergence")
