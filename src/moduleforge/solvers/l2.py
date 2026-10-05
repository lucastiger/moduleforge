"""Public L2 API (contract: research/notes/o001-l2-reference.md section 3).

``solve`` runs the exact-kernel round-wire / FFT-plane PEEC of ``l2_core``.  Scope of this build: ``RoundWire`` and
``Plane`` with any number of ports; ``Bar`` and ``Tie`` raise NotImplementedError (added by the next task).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from moduleforge.solvers import l2_core as core

MAX_REFINEMENT: int = core.MAX_REFINEMENT
TOOL_NAME = "moduleforge-l2-exact-kernel"
TOOL_VERSION = "0.1.0"


@dataclass(frozen=True)
class Bar:
    name: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    width: float
    thickness: float
    sigma: float
    width_dir: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class RoundWire:
    name: str
    points: tuple[tuple[float, float, float], ...]
    diameter: float
    sigma: float


@dataclass(frozen=True)
class Plane:
    name: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    z_top: float
    thickness: float
    sigma: float


@dataclass(frozen=True)
class Terminal:
    conductor: str
    vertex: int


@dataclass(frozen=True)
class Port:
    name: str
    plus: Terminal
    minus: Terminal


@dataclass(frozen=True)
class Tie:
    a: Terminal
    b: Terminal


@dataclass
class Result:
    freqs_hz: np.ndarray
    z: np.ndarray
    meta: dict = field(default_factory=dict)


def solve(conductors: Sequence[Bar | RoundWire], planes: Sequence[Plane], ports: Sequence[Port],
          freqs_hz: Sequence[float], refinement: int, ties: Sequence[Tie] = ()) -> Result:
    """Port impedance matrices Z[f, i, j] = V_i / I_j (ohm, all other ports open); L = Im Z / omega.

    The current I_j enters at ``plus_j`` and leaves at ``minus_j``.  One mesh per call (graded to the skin depth at
    max(freqs_hz)).  ``meta`` carries solver_tol, n_filaments, mesh_params, mesh_hash (one equal entry per frequency),
    tool, version, wall_s and the stated bounds."""
    if any(isinstance(c, Bar) for c in conductors):
        raise NotImplementedError("Bar conductors are not implemented yet")
    if ties:
        raise NotImplementedError("Ties are not implemented yet")
    if len(planes) > 1:
        raise NotImplementedError("at most one plane is supported")
    freqs = [float(f) for f in freqs_hz]
    if not freqs or min(freqs) <= 0:
        raise ValueError("freqs_hz must be non-empty and positive")
    names = [c.name for c in conductors]
    if len(set(names)) != len(names):
        raise ValueError("conductor names must be unique")
    specs = [core.WireSpec(c.name, np.asarray(c.points, float), c.diameter, c.sigma) for c in conductors]
    plane = None
    if planes:
        p = planes[0]
        plane = core.PlaneSpec(p.name, p.x_min, p.y_min, p.x_max, p.y_max, p.z_top, p.thickness, p.sigma)

    def term(t: Terminal) -> tuple[int, int]:
        if t.conductor not in names:
            raise ValueError(f"unknown conductor {t.conductor!r}")
        i = names.index(t.conductor)
        if not 0 <= t.vertex < len(specs[i].points):
            raise ValueError(f"vertex {t.vertex} out of range for {t.conductor!r}")
        return i, t.vertex

    pt = [(term(p.plus), term(p.minus)) for p in ports]
    out, meta = core.solve_case(specs, plane, pt, freqs, refinement)
    meta.update(tool=TOOL_NAME, version=TOOL_VERSION)
    return Result(freqs_hz=np.asarray(freqs, float), z=out.z, meta=meta)
