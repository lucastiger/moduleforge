"""Public L2 API (contract: research/notes/o001-l2-reference.md section 3).

``solve`` runs the exact-kernel PEEC of ``l2_core``: round wires (annuli x azimuthal harmonics), axis-parallel rectangular
``Bar`` conductors (Hoer-Love boxes, exact), one finite ``Plane`` (FFT-applied tables), any number of ports and ideal
``Tie`` connections.  Not implemented (raise NotImplementedError): bars together with wires or a plane, inclined bars.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from moduleforge.solvers import l2_core as core

MAX_REFINEMENT: int = core.MAX_REFINEMENT
TOOL_NAME = "moduleforge-l2-exact-kernel"
TOOL_VERSION = "0.2.0"


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


def _prepare(conductors: Sequence[Bar | RoundWire], planes: Sequence[Plane]):
    if len(planes) > 1:
        raise NotImplementedError("at most one plane is supported")
    names = [c.name for c in conductors]
    if len(set(names)) != len(names):
        raise ValueError("conductor names must be unique")
    specs = []
    for c in conductors:
        if isinstance(c, Bar):
            specs.append(core.BarSpec(c.name, np.asarray(c.start, float), np.asarray(c.end, float), c.width, c.thickness,
                                      c.sigma, None if c.width_dir is None else np.asarray(c.width_dir, float)))
        else:
            specs.append(core.WireSpec(c.name, np.asarray(c.points, float), c.diameter, c.sigma))
    plane = None
    if planes:
        p = planes[0]
        plane = core.PlaneSpec(p.name, p.x_min, p.y_min, p.x_max, p.y_max, p.z_top, p.thickness, p.sigma)
    return names, specs, plane


def _term(names, specs, t: Terminal) -> tuple[int, int]:
    if t.conductor not in names:
        raise ValueError(f"unknown conductor {t.conductor!r}")
    i = names.index(t.conductor)
    nv = 2 if isinstance(specs[i], core.BarSpec) else len(specs[i].points)
    if not 0 <= t.vertex < nv:
        raise ValueError(f"vertex {t.vertex} out of range for {t.conductor!r}")
    return i, t.vertex


def solve(conductors: Sequence[Bar | RoundWire], planes: Sequence[Plane], ports: Sequence[Port],
          freqs_hz: Sequence[float], refinement: int, ties: Sequence[Tie] = ()) -> Result:
    """Port impedance matrices Z[f, i, j] = V_i / I_j (ohm, all other ports open); L = Im Z / omega.

    The current I_j enters at ``plus_j`` and leaves at ``minus_j``.  A ``Tie`` joins two terminals by an ideal
    zero-impedance connection (the nodes are merged).  One mesh per call (graded to the skin depth at max(freqs_hz)).
    ``meta`` carries solver_tol, n_filaments, mesh_params, mesh_hash (one equal entry per frequency), tool, version, wall_s,
    gmres_info (scipy flag per frequency and port; 0 = converged), peak_rss_mb and the stated bounds."""
    names, specs, plane = _prepare(conductors, planes)
    freqs = [float(f) for f in freqs_hz]
    pt = [(_term(names, specs, p.plus), _term(names, specs, p.minus)) for p in ports]
    tt = [(_term(names, specs, t.a), _term(names, specs, t.b)) for t in ties]
    out, meta = core.solve_case(specs, plane, pt, freqs, refinement, ties=tt)
    meta.update(tool=TOOL_NAME, version=TOOL_VERSION)
    return Result(freqs_hz=np.asarray(freqs, float), z=out.z, meta=meta)


def mesh_meta(conductors: Sequence[Bar | RoundWire], planes: Sequence[Plane], ports: Sequence[Port],
              freqs_hz: Sequence[float], refinement: int, ties: Sequence[Tie] = ()) -> dict:
    """``mesh_params``, ``n_filaments`` and ``mesh_hash`` exactly as ``solve`` reports them in ``meta`` for the same
    arguments, built through the same code path (``core.build_meshes``) but without assembling or solving anything."""
    names, specs, plane = _prepare(conductors, planes)
    for p in ports:
        _term(names, specs, p.plus), _term(names, specs, p.minus)
    for t in ties:
        _term(names, specs, t.a), _term(names, specs, t.b)
    return core.mesh_summary(specs, plane, [float(f) for f in freqs_hz], refinement)
