"""T0067 spike: numerical-error checks of the prototype kernels (quadrature orders, proxy order P).
Compares port L at level 1-2 with raised quadrature orders and with P + 2; prints relative changes."""
from __future__ import annotations

import functools
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l2proto as P  # noqa: E402

E = P.E


def run(cid, k, **kw):
    cfg = E.checked_config({})
    sig = {E.CU: cfg["sigma_cu"], E.AL: cfg["sigma_al"]}
    c = E.build_cases(cfg, [cid])[0]
    fr = sorted(set(c["cmp_freqs"]) | set(c["info_freqs"]))
    z, _ = P.solve_case(c, fr, k, sig, **kw)
    return z.imag / (2 * math.pi * np.asarray(fr))


if __name__ == "__main__":
    base = P.coax_tables
    for cid, k in (("B1", 2), ("B2", 1)):
        a = run(cid, k)
        P.coax_tables = functools.partial(base, ng=12, nth=256, ngk=18, panels=50)
        b = run(cid, k)
        P.coax_tables = base
        print(cid, k, "quadrature x1.5-2: max rel change %.1e" % np.max(np.abs(b / a - 1)))
    for cid, k, p in (("B2", 1, 5), ("C0", 1, 5)):
        a, b = run(cid, k, P=p), run(cid, k, P=p + 2)
        print(cid, k, f"proxy/harmonic order P={p} -> {p + 2}: max rel change %.1e" % np.max(np.abs(b / a - 1)))
