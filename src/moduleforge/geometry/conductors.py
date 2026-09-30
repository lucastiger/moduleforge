"""Solver-neutral conductor model produced by ``Layout.to_conductors()``.

All quantities SI, float64, z = 0 at the bottom of the baseplate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import Polygon, box

from .stack import LayerStack


@dataclass(frozen=True)
class RectCell:
    """Axis-aligned top-Cu rectangle: spans x0..x1, y0..y1, z..z+thickness, conductivity sigma."""

    net: str
    x0: float
    y0: float
    x1: float
    y1: float
    z: float
    thickness: float
    sigma: float

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


@dataclass(frozen=True)
class WireSegment:
    """Straight round-wire segment p0 -> p1 (3-vectors) of a bond wire; ``net`` is the landing net."""

    wire_index: int
    net: str
    p0: tuple[float, float, float]
    p1: tuple[float, float, float]
    diameter: float
    sigma: float


@dataclass(frozen=True)
class Plane:
    """Conductive plane (backside Cu or baseplate) with its true extent (polygon exterior, CCW)."""

    name: str
    outline: np.ndarray = field(compare=False)
    z_bottom: float = 0.0
    thickness: float = 0.0
    sigma: float = 0.0

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (*self.outline.min(axis=0), *self.outline.max(axis=0))


@dataclass(frozen=True)
class DieShort:
    """Die with the switch on: ideal short between the die footprint on the trace of ``bottom_net``
    (z_bottom) and the source pad at the die top (z_top), where the wires start."""

    die_index: int
    switch: str
    x: float
    y: float
    w: float
    h: float
    z_bottom: float
    z_top: float
    bottom_net: str
    pad: tuple[float, float, float, float]


@dataclass(frozen=True)
class Port:
    """Commutation-loop port: positive node at the DC+ terminal, negative node at the DC- terminal
    (both on the top-Cu surface), PHASE terminal left open."""

    p_pos: tuple[float, float, float]
    p_neg: tuple[float, float, float]
    phase_open: bool = True


@dataclass(frozen=True)
class ConductorModel:
    """Everything an L1/L2 solver needs, with no solver-specific choices."""

    stack: LayerStack
    rects: tuple[RectCell, ...]
    wires: tuple[WireSegment, ...]
    planes: tuple[Plane, ...]
    shorts: tuple[DieShort, ...]
    port: Port

    def copper_area(self, net: str | None = None) -> float:
        return sum(r.area for r in self.rects if net is None or r.net == net)


def decompose_polygon(poly: Polygon, tol: float = 1e-12) -> list[tuple[float, float, float, float]]:
    """Decompose a rectilinear polygon (holes allowed) into disjoint rectangles (x0, y0, x1, y1).

    Horizontal-slab decomposition between consecutive distinct vertex y values, then vertical merging of
    slabs with identical x extent. The rectangle areas sum to ``poly.area`` exactly (up to round-off).
    """
    rings = [poly.exterior, *poly.interiors]
    ys: list[float] = []
    for y in sorted(c[1] for r in rings for c in r.coords):
        if not ys or y - ys[-1] > tol:
            ys.append(y)
    minx, _, maxx, _ = poly.bounds
    open_rects: dict[tuple[float, float], list[float]] = {}
    out: list[tuple[float, float, float, float]] = []
    for ya, yb in zip(ys[:-1], ys[1:], strict=True):
        cells = []
        piece = poly.intersection(box(minx - 1.0, ya, maxx + 1.0, yb))
        for g in getattr(piece, "geoms", [piece]):
            if g.is_empty or g.geom_type != "Polygon":
                continue
            x0, _, x1, _ = g.bounds
            if abs(g.area - (x1 - x0) * (yb - ya)) > 1e-9 * max(g.area, tol):
                raise ValueError("polygon is not rectilinear")
            cells.append((x0, x1))
        still_open = {}
        for key in cells:
            hit = next((k for k in open_rects if abs(k[0] - key[0]) < tol and abs(k[1] - key[1]) < tol), None)
            if hit is not None:
                still_open[hit] = open_rects.pop(hit)
                still_open[hit][1] = yb
            else:
                still_open[key] = [ya, yb]
        out.extend((x0, y0, x1, y1) for (x0, x1), (y0, y1) in open_rects.items())
        open_rects = still_open
    out.extend((x0, y0, x1, y1) for (x0, x1), (y0, y1) in open_rects.items())
    return out
