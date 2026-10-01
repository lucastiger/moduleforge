"""Layout IR for a wire-bonded half-bridge power-module substrate.

SI units, float64, x-y is the substrate plane, z = 0 at the bottom of the baseplate (see ``stack``).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import Polygon, box

from .conductors import (
    ConductorModel,
    DieShort,
    Plane,
    Port,
    RectCell,
    WireSegment,
    decompose_polygon,
)
from .stack import SIGMA_AL_WIRE, LayerStack, default_dbc_stack

DC_PLUS = "DC+"
DC_MINUS = "DC-"
PHASE = "PHASE"
NETS = (DC_PLUS, DC_MINUS, PHASE)


@dataclass
class Trace:
    """Rectilinear top-Cu polygon with a net label."""

    net: str
    polygon: Polygon


@dataclass
class Die:
    """Switch die: centre (cx, cy), size w x h, switch position 'HS' or 'LS'.

    The die back side (drain/collector) is soldered to a trace (DC+ for HS, PHASE for LS). ``pads`` maps a
    pad name ('source', 'gate') to an absolute rectangle (x0, y0, x1, y1) on the die top.
    """

    cx: float
    cy: float
    w: float
    h: float
    switch: str
    pads: dict[str, tuple[float, float, float, float]]
    thickness: float = 180e-6  # typical SiC/IGBT die thickness
    attach_thickness: float = 50e-6  # typical solder/sinter die attach

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.cx - self.w / 2, self.cy - self.h / 2, self.cx + self.w / 2, self.cy + self.h / 2)

    @property
    def box(self) -> Polygon:
        return box(*self.bounds)


@dataclass
class BondWire:
    """Bond wire as a 3D polyline ``points`` (N, 3); ``net`` is the net it must land on."""

    points: np.ndarray
    diameter: float
    loop_height: float
    net: str

    @property
    def length(self) -> float:
        return float(np.linalg.norm(np.diff(self.points, axis=0), axis=1).sum())


@dataclass
class Terminal:
    """Housing-fixed terminal pad (centre and size), on the top-Cu surface."""

    net: str
    cx: float
    cy: float
    w: float
    h: float


def arc_wire(start_xy, end_xy, z_start, z_end, loop_height, diameter, net, npts: int = 7) -> BondWire:
    """Bond wire whose height above the start-end chord is ``loop_height * sin(pi t)``."""
    t = np.linspace(0.0, 1.0, npts)
    p = np.empty((npts, 3))
    p[:, 0] = start_xy[0] + t * (end_xy[0] - start_xy[0])
    p[:, 1] = start_xy[1] + t * (end_xy[1] - start_xy[1])
    p[:, 2] = z_start + t * (z_end - z_start) + loop_height * np.sin(np.pi * t)
    return BondWire(p, diameter, loop_height, net)


def _ring_ints(poly: Polygon) -> list[list[int]]:
    poly = shapely.normalize(poly)
    return [[int(round(v * 1e9)) for c in r.coords for v in c] for r in (poly.exterior, *poly.interiors)]


@dataclass
class Layout:
    """Half-bridge layout: substrate outline, top-Cu traces, dies, bond wires and housing terminals.

    ``to_conductors()`` returns the solver-neutral ``ConductorModel``.

    **Port definition (commutation loop, per mf-conventions).** The reported quantity is ``L_loop(f)``, the
    inductance of the commutation loop DC+ terminal -> high-side switch -> phase node -> low-side switch ->
    DC- terminal, seen at the port between the DC+ and DC- terminals (positive node on the DC+ terminal
    centre, negative node on the DC- terminal centre, both at the top-Cu surface). The PHASE terminal is
    left *open* (no current leaves through it). Both switches are modelled as *on*: each die is an ideal
    short between its back-side trace footprint and its top source pad, and the bond wires carry the
    current from the pads to the landing traces. Frequency is chosen by the solver/experiment.
    """

    family: str
    dies_per_switch: int
    outline: Polygon
    traces: list[Trace]
    dies: list[Die]
    wires: list[BondWire]
    terminals: dict[str, Terminal]
    baseplate_outline: Polygon
    stack: LayerStack = field(default_factory=default_dbc_stack)
    backside_inset: float = 1.0e-3  # backside Cu is inset from the substrate edge (typical DBC practice)
    wire_sigma: float = SIGMA_AL_WIRE

    def fingerprint(self) -> str:
        """Stable SHA-256 hex digest of the layout IR: every IR field but the two listed last.

        That includes every input of ``to_conductors()``, which returns the whole ``LayerStack`` (``kind``
        label included).

        Covered: ``family`` and ``dies_per_switch``; the whole ``LayerStack`` (its ``kind`` label and, for
        every layer, name, material, thickness, sigma and k); ``backside_inset`` and ``wire_sigma``; the
        substrate ``outline`` and ``baseplate_outline`` (shapely-normalized rings); every ``Trace`` (net,
        polygon rings); every ``Die`` (switch, cx, cy, w, h, thickness, attach_thickness, and each pad's name
        and rectangle); every ``BondWire`` (net, 3D points, diameter); every ``Terminal`` (dict key, cx, cy,
        w, h). Each value is hashed in place, together with its field and its element, so exchanging two different
        values between two elements or two fields changes the digest. Traces, dies and wires are hashed in list
        order; pads and terminals sorted by name (dict insertion order does not matter).

        Quantization: lengths are quantized to 1 nm per field: each coordinate, size and thickness is rounded
        on its own to the nearest integer number of nanometres (polygon rings after ``shapely.normalize``),
        so changing one of them by more than 1 nm changes the digest. Conductivities (sigma, k) are rounded
        to 12 significant digits. The rounding makes the digest insensitive to most float round-off, but it
        does not guarantee that a smaller change is absorbed: a change of any size that carries a value across a
        rounding boundary (half a nanometre, or half a unit in the 12th digit) changes the digest, and so can
        moving a polygon vertex by less than 1 nm if that changes the vertex ``shapely.normalize`` starts the
        ring at.

        Not covered (exactly these two IR fields): ``BondWire.loop_height`` (a generator parameter that is
        redundant with the hashed wire points) and ``Terminal.net`` (redundant with the hashed dict key).
        """
        h = hashlib.sha256()

        def put(*items):
            h.update(repr(items).encode())

        def nm(v):
            return int(round(v * 1e9))

        def sig(v):
            return f"{float(v):.12g}"

        put("family", self.family, self.dies_per_switch)
        put("stack", self.stack.kind, [(la.name, la.material, nm(la.thickness), sig(la.sigma), sig(la.k))
                      for la in self.stack.layers])
        put("backside_inset", nm(self.backside_inset), "wire_sigma", sig(self.wire_sigma))
        put("outline", _ring_ints(self.outline), _ring_ints(self.baseplate_outline))
        for t in self.traces:
            put("trace", t.net, _ring_ints(t.polygon))
        for d in self.dies:
            put("die", d.switch, [nm(v) for v in (d.cx, d.cy, d.w, d.h, d.thickness, d.attach_thickness)],
                sorted((k, [nm(v) for v in r]) for k, r in d.pads.items()))
        for w in self.wires:
            put("wire", w.net, np.round(w.points * 1e9).astype(np.int64).tolist(), nm(w.diameter))
        for n in sorted(self.terminals):
            t = self.terminals[n]
            put("term", n, [nm(v) for v in (t.cx, t.cy, t.w, t.h)])
        return h.hexdigest()

    def top_cu_z(self) -> tuple[float, float]:
        return self.stack.z_bottom("top_cu"), self.stack.z_top("top_cu")

    def die_z_range(self, die: Die) -> tuple[float, float]:
        zb = self.top_cu_z()[1] + die.attach_thickness
        return zb, zb + die.thickness

    def to_conductors(self) -> ConductorModel:
        """Solver-neutral conductor model (see class docstring for the port definition)."""
        z0, z1 = self.top_cu_z()
        st = self.stack
        sigma_cu = st.layer("top_cu").sigma
        rects = tuple(
            RectCell(t.net, x0, y0, x1, y1, z0, z1 - z0, sigma_cu)
            for t in self.traces
            for (x0, y0, x1, y1) in decompose_polygon(t.polygon)
        )
        segs = []
        for i, w in enumerate(self.wires):
            for a, b in zip(w.points[:-1], w.points[1:], strict=True):
                segs.append(WireSegment(i, w.net, tuple(map(float, a)), tuple(map(float, b)), w.diameter,
                                        self.wire_sigma))
        planes = []
        back = self.outline.buffer(-self.backside_inset, join_style="mitre")
        for name, poly in (("backside_cu", back), ("baseplate", self.baseplate_outline)):
            la = st.layer(name)
            planes.append(Plane(name, np.array(shapely.geometry.polygon.orient(poly).exterior.coords)[:-1],
                                st.z_bottom(name), la.thickness, la.sigma))
        net_of_switch = {"HS": DC_PLUS, "LS": PHASE}
        shorts = []
        for i, d in enumerate(self.dies):
            zt = self.die_z_range(d)[1]
            shorts.append(DieShort(i, d.switch, d.cx, d.cy, d.w, d.h, z1, zt, net_of_switch[d.switch],
                                   d.pads["source"]))
        tp, tn = self.terminals[DC_PLUS], self.terminals[DC_MINUS]
        port = Port((tp.cx, tp.cy, z1), (tn.cx, tn.cy, z1), phase_open=True)
        return ConductorModel(st, rects, tuple(segs), tuple(planes), tuple(shorts), port)
