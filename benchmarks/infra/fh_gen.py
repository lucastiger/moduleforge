"""Representative half-bridge commutation loop for FastHenry (SI units: FastHenry's `.units mm` mode
reported inductance 1000x too high in our build, so geometry is written in meters).

DC+ trace -> 2 high-side dies -> 16 bond wires -> phase trace -> 2 low-side dies -> 16 bond wires -> DC- trace.
The DBC backside copper is a floating ground plane (eddy currents). Resolution knobs: nw, nh (filaments across
each trace cross-section) and plane_seg (plane mesh). Environment PNH sets filaments through the plane thickness.

Usage: python fh_gen.py NW NH PLANE_SEG > loop.inp
"""
import os
import sys

MM = 1e-3


def gen(nw: int, nh: int, plane_seg: int, wires_per_die: int = 8, f: float = 2e7) -> str:
    lines = [".units m", ".default sigma=5.8e7", f".default nwinc={nw} nhinc={nh}"]
    zt = 0.77  # top-copper centerline, mm (0.3 Cu over 0.32 ceramic over 0.3 Cu)
    xs = [2 + 26 * i / (2 * wires_per_die) for i in range(2 * wires_per_die + 1)]

    def trace(name: str, y: float) -> None:
        for i, x in enumerate(xs):
            lines.append(f"N{name}{i} x={x * MM:.6g} y={y * MM:.6g} z={zt * MM:.6g}")
        for i in range(len(xs) - 1):
            lines.append(f"E{name}{i} N{name}{i} N{name}{i + 1} w={10 * MM:g} h={0.3 * MM:g}")

    trace("P", 0)   # DC+
    trace("O", 15)  # phase (output)
    trace("M", 30)  # DC-
    for side, (y0, y1, src, dst) in {"H": (3, 12, "P", "O"), "L": (18, 27, "O", "M")}.items():
        for k in range(2 * wires_per_die):
            x = xs[k] + 0.8
            pts = {"a": (y0, zt + 0.35), "b": ((y0 + y1) / 2, zt + 3.5), "c": (y1, zt + 0.15)}
            for tag, (y, z) in pts.items():
                lines.append(f"N{side}w{k}{tag} x={x * MM:.6g} y={y * MM:.6g} z={z * MM:.6g}")
            wire = f"w={0.35 * MM:g} h={0.35 * MM:g} nwinc=2 nhinc=2"
            lines.append(f"E{side}w{k}s1 N{side}w{k}a N{side}w{k}b {wire}")
            lines.append(f"E{side}w{k}s2 N{side}w{k}b N{side}w{k}c {wire}")
            lines.append(f"E{side}d{k} N{src}{k} N{side}w{k}a w={2 * MM:g} h={0.2 * MM:g} nwinc=1 nhinc=1")
            lines.append(f".equiv N{side}w{k}c N{dst}{k}")
    if plane_seg:
        a, b, zp = -8 * MM, 38 * MM, 0.15 * MM
        pnh = int(os.environ.get("PNH", "1"))
        lines.append(f"gplane x1={a:g} y1={a:g} z1={zp:g} x2={b:g} y2={a:g} z2={zp:g} x3={b:g} y3={b:g} z3={zp:g} "
                     f"thick={0.3 * MM:g} seg1={plane_seg} seg2={plane_seg} nhinc={pnh}")
        lines.append(f"+ nfloat ({15 * MM:g},{15 * MM:g},{zp:g})")
    lines.append(".external NP0 NM0")
    lines.append(f".freq fmin={f} fmax={f} ndec=1")
    lines.append(".end")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    nw, nh, seg = (int(a) for a in sys.argv[1:4])
    sys.stdout.write(gen(nw, nh, seg))
