"""L1 PEEC cost proxy: dense partial-inductance fill (exact Neumann formula for parallel filaments,
GMD self terms) plus a complex solve at 20 MHz. Same computational shape as the planned L1 model.

Usage: python l1_bench.py [N ...]      (default sizes 200 400 800 1600)
"""
import resource
import sys
import time

import numpy as np

MU = 1e-7  # mu0 / 4pi
OMEGA = 2 * np.pi * 2e7


def f_kernel(u, d):
    return u * np.arcsinh(u / d) - np.sqrt(u * u + d * d)


def make_problem(n: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    a1 = rng.uniform(0, 30e-3, n)
    a2 = a1 + rng.uniform(0.5e-3, 3e-3, n)
    y = rng.uniform(0, 30e-3, n)
    z = rng.choice([0.77e-3, 1.5e-3, 3e-3], n)
    w = rng.uniform(0.3e-3, 5e-3, n)
    t = np.full(n, 0.3e-3)
    return a1, a2, y, z, w, t


def _distances(y, z, w, t, xp):
    d = xp.hypot(y[:, None] - y[None, :], z[:, None] - z[None, :])
    gmd = 0.2235 * (w + t)
    return xp.where(d < 1e-12, gmd[:, None], xp.maximum(d, 0.5 * (gmd[:, None] + gmd[None, :])))


def fill_np(a1, a2, y, z, w, t):
    d = _distances(y, z, w, t, np)
    A1, A2, B1, B2 = a1[:, None], a2[:, None], a1[None, :], a2[None, :]
    return MU * (f_kernel(A2 - B1, d) + f_kernel(A1 - B2, d) - f_kernel(A1 - B1, d) - f_kernel(A2 - B2, d))


def solve_np(L, R, omega=OMEGA, nports: int = 4):
    Z = np.diag(R) + 1j * omega * L
    rhs = np.zeros((L.shape[0], nports), complex)
    rhs[:nports, :nports] = np.eye(nports)
    return np.linalg.solve(Z, rhs)


def make_jax_eval():
    import jax
    import jax.numpy as jnp
    jax.config.update("jax_enable_x64", True)

    def jax_eval(a1, a2, y, z, w, t, R, omega):
        d = _distances(y, z, w, t, jnp)

        def fk(u):
            return u * jnp.arcsinh(u / d) - jnp.sqrt(u * u + d * d)

        A1, A2, B1, B2 = a1[:, None], a2[:, None], a1[None, :], a2[None, :]
        L = MU * (fk(A2 - B1) + fk(A1 - B2) - fk(A1 - B1) - fk(A2 - B2))
        Z = jnp.diag(R).astype(jnp.complex128) + 1j * omega * L
        rhs = jnp.zeros((L.shape[0], 4), jnp.complex128).at[:4, :4].set(jnp.eye(4))
        return jnp.linalg.solve(Z, rhs)

    return jax.jit(jax_eval), jnp


def main(sizes: list[int]) -> None:
    jax_eval, jnp = make_jax_eval()
    print(f"{'N':>5} {'numpy ms':>9} {'jax ms':>8} {'jit compile s':>13} {'sym err':>8}")
    for n in sizes:
        p = make_problem(n)
        R = np.full(n, 1e-4)
        L = fill_np(*p)
        sym = np.abs(L - L.T).max() / np.abs(L).max()
        reps = max(3, int(2000 / n))
        t0 = time.perf_counter()
        for _ in range(reps):
            solve_np(fill_np(*p), R)
        t_np = (time.perf_counter() - t0) / reps * 1e3
        args = [jnp.asarray(v) for v in p] + [jnp.asarray(R), OMEGA]
        t0 = time.perf_counter()
        jax_eval(*args).block_until_ready()
        t_compile = time.perf_counter() - t0
        t0 = time.perf_counter()
        for _ in range(reps):
            jax_eval(*args).block_until_ready()
        t_jax = (time.perf_counter() - t0) / reps * 1e3
        print(f"{n:5d} {t_np:9.1f} {t_jax:8.1f} {t_compile:13.2f} {sym:8.1e}", flush=True)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(f"peak RSS: {rss / (2**20 if sys.platform == 'darwin' else 2**10):.0f} MB")


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or [200, 400, 800, 1600])
