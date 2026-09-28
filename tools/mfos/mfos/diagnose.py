"""Failure classification and response policy.

The deterministic layer classifies *signals*; an independent scientist run (fresh
context) then confirms or overturns the class with evidence and a discriminating
test. The response depends on the class, not on how the failure felt:

  implementation  code is wrong                 -> repair (fresh builder), then escalate model, then diagnose
  experimental    experiment/reference invalid  -> fix the experiment; hypothesis untouched; evidence voided
  model           physics/math assumption wrong -> diagnose + critic audit -> planner replans within objective
  planning        wrong objective/decomposition -> founder decision memo
  business        thesis weakening              -> founder decision memo (never auto-acted on)
"""
from __future__ import annotations

from dataclasses import dataclass

SIGNAL_CLASS = {
    "dod_failed": "implementation",
    "gate_failed": "implementation",
    "scope_violation": "implementation",
    "agent_error": "implementation",
    "review_rejected": "implementation",
    "experiment_error": "implementation",
    "evidence_invalid": "experimental",
    "sanity_failed": "experimental",
    "verdict_inconclusive": "experimental",
    "verdict_fail": "model",
    "claim_conflict": "model",
    "attempts_exhausted": "planning",
    "replans_exhausted": "planning",
    "budget_exhausted": "planning",
    "evaluations_exhausted": "planning",
    "thesis_signal": "business",
}


@dataclass
class Response:
    failure_class: str
    action: str  # repair | diagnose | fix_experiment | replan | founder
    needs_review: bool
    note: str


def respond(signal: str, attempts: int = 0, max_attempts: int = 3) -> Response:
    cls = SIGNAL_CLASS.get(signal, "planning")
    if cls == "implementation":
        if attempts < max_attempts:
            return Response(cls, "repair", False, "retry in a fresh session with the failure output")
        return Response(cls, "diagnose", False, "repairs exhausted; scientist diagnoses before replanning")
    if cls == "experimental":
        return Response(cls, "fix_experiment", True,
                        "evidence voided; scientist repairs the experiment design; critic reviews the new design")
    if cls == "model":
        return Response(cls, "diagnose", True,
                        "independent diagnosis with alternatives and a discriminating test, plus critic audit")
    return Response(cls, "founder", False, "requires a founder decision")
