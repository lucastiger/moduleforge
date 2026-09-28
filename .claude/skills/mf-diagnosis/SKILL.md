---
name: mf-diagnosis
description: Protocol for diagnosing failures and replanning - failure classes, competing explanations, discriminating tests, allowed responses. Use for investigate tasks and whenever a verdict is FAIL, INCONCLUSIVE, or INVALID.
user-invocable: false
---

# Diagnosis protocol

## 1. Confirm the signal
Re-read the failure output and re-run the cheapest check that shows it. Record the exact evidence.

## 2. Consider every class, with evidence for and against
| class | meaning | typical signature |
|---|---|---|
| implementation | code is wrong | exceptions, failing unit tests, error depends on code path, disappears when an independent implementation is used |
| experimental | the experiment cannot answer the question | sanity check failed, reference not converged, unrepresentative sample, metric mismatched to the decision, leakage |
| model | a physical/mathematical assumption is wrong | systematic error that survives verified code and a validated reference, and correlates with a physical variable (loop area, frequency, baseplate distance, current density) |
| planning | we are pursuing the wrong thing | objective not decision-relevant, dependencies wrong, repeated replans without convergence, budget exhausted |
| business | the thesis weakens | customer or market evidence contradicts an assumption in `project/charter.md` |

## 3. At least two competing explanations, each with a discriminating test
A discriminating test is one whose outcome differs sharply between the explanations. Run every
such test that costs under ~15 minutes of compute. Name the result that would prove you wrong.

## 4. Decide and recommend
- Give a class and a calibrated confidence. Low confidence is a legitimate answer.
- implementation → specific repair task(s); experimental → redesign as a NEW experiment id
  (evidence from the broken one is void); model → the model change plus the experiment that will
  test it on fresh sealed data; planning or business → a founder decision memo.
- Never recommend changing acceptance thresholds, the hypothesis, or scope. If you believe they
  are wrong, set `affects_acceptance_criteria: true` and explain; only the founder can change them.
- Evaluations are counted (`max_evaluations`). Do not recommend re-running an evaluation on the
  same data after a model change; fresh sealed seeds only.

## 5. Notes file
`research/diagnoses/<task>.md`: signal · explanations considered · tests run with results ·
conclusion · confidence · recommended actions · what would change the conclusion.
