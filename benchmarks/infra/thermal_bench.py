"""3D steady conduction in a power-module stack: 7-point finite differences, harmonic-mean conductivity,
convective (cold-plate) bottom boundary, 400 W in four dies. Solved with smoothed-aggregation AMG + CG.
Cost proxy for an FEniCSx P1 thermal solve of similar size. Prints the energy balance as a correctness check.

Usage: python thermal_bench.py
"""
import resource
import sys
import time

import numpy as np
import pyamg
import scipy.sparse as sp

# layer stack bottom-up: (thickness m, conductivity W/mK)
LAYERS = [(3e-3, 180.0), (0.1e-3, 50.0), (0.3e-3, 390.0), (0.32e-3, 90.0), (0.3e-3, 390.0), (0.05e-3, 200.0),
          (0.2e-3, 370.0)]
H_COLD = 5000.0  # W/m2K


def assemble(nx: int, ny: int, nz: int):
    lx, ly = 60e-3, 50e-3
    zb = np.cumsum([0.0] + [layer[0] for layer in LAYERS])
    height = zb[-1]
    zc = (np.arange(nz) + 0.5) * height / nz
    kz = np.array([LAYERS[np.searchsorted(zb, z) - 1][1] for z in zc])
    dx, dy, dz = lx / nx, ly / ny, height / nz
    n = nx * ny * nz
    idx = np.arange(n).reshape(nz, ny, nx)
    k = np.broadcast_to(kz[:, None, None], (nz, ny, nx)).copy()
    rows, cols, vals = [], [], []
    diag = np.zeros(n)

    def couple(a, b, ka, kb, area, dist):
        g = area / dist * 2 * ka * kb / (ka + kb)
        rows.extend([a, b])
        cols.extend([b, a])
        vals.extend([-g, -g])
        np.add.at(diag, a, g)
        np.add.at(diag, b, g)

    couple(idx[:, :, :-1].ravel(), idx[:, :, 1:].ravel(), k[:, :, :-1].ravel(), k[:, :, 1:].ravel(), dy * dz, dx)
    couple(idx[:, :-1, :].ravel(), idx[:, 1:, :].ravel(), k[:, :-1, :].ravel(), k[:, 1:, :].ravel(), dx * dz, dy)
    couple(idx[:-1].ravel(), idx[1:].ravel(), k[:-1].ravel(), k[1:].ravel(), dx * dy, dz)
    np.add.at(diag, idx[0].ravel(), H_COLD * dx * dy)
    data = np.concatenate([np.concatenate(vals), diag])
    r = np.concatenate([np.concatenate(rows), np.arange(n)])
    c = np.concatenate([np.concatenate(cols), np.arange(n)])
    A = sp.csr_matrix((data, (r, c)), shape=(n, n))
    xg, yg = np.meshgrid((np.arange(nx) + 0.5) * dx, (np.arange(ny) + 0.5) * dy)
    q = np.zeros((ny, nx))
    for cx, cy in [(15e-3, 15e-3), (15e-3, 35e-3), (45e-3, 15e-3), (45e-3, 35e-3)]:
        q[(abs(xg - cx) < 2.5e-3) & (abs(yg - cy) < 2.5e-3)] = 1.0
    q *= 400.0 / q.sum()
    b = np.zeros(n)
    b[idx[-1].ravel()] = q.ravel()
    return A, b, idx, dx * dy


def solve(nx: int, ny: int, nz: int):
    A, b, idx, cell_area = assemble(nx, ny, nz)
    t0 = time.perf_counter()
    ml = pyamg.smoothed_aggregation_solver(A, symmetry="symmetric", max_coarse=500)
    residuals = []
    T = ml.solve(b, tol=1e-8, accel="cg", residuals=residuals)
    elapsed = time.perf_counter() - t0
    balance = H_COLD * cell_area * T[idx[0].ravel()].sum() / 400.0  # heat out / heat in
    return A.shape[0], elapsed, T.max(), balance, len(residuals)


if __name__ == "__main__":
    print(f"{'DOFs':>9} {'solve s':>8} {'Tmax-Tcool K':>12} {'Qout/Qin':>9} {'iters':>6}")
    for dims in [(120, 100, 24), (240, 200, 30), (300, 250, 40)]:
        n, t, tmax, bal, iters = solve(*dims)
        print(f"{n:9d} {t:8.1f} {tmax:12.2f} {bal:9.4f} {iters:6d}", flush=True)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(f"peak RSS: {rss / (2**20 if sys.platform == 'darwin' else 2**10):.0f} MB")
