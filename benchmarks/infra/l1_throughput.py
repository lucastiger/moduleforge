"""Sustained L1 throughput with W worker processes for M minutes; prints evaluations/minute each minute.
Reveals thermal throttling on a fanless MacBook Air. Usage: python l1_throughput.py WORKERS MINUTES [N]"""
import multiprocessing as mp
import os
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")   # Accelerate: one thread per worker


def worker(n, stop_at, q):
    import numpy as np
    sys.path.insert(0, os.path.dirname(__file__))
    from l1_bench import fill_np, make_problem, solve_np
    p = make_problem(n)
    R = np.full(n, 1e-4)
    while time.time() < stop_at:
        solve_np(fill_np(*p), R, 2 * np.pi * 2e7)
        q.put(time.time())


if __name__ == "__main__":
    W, M = int(sys.argv[1]), float(sys.argv[2])
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    q = mp.Queue()
    t0 = time.time()
    stop = t0 + 60 * M
    ps = [mp.Process(target=worker, args=(n, stop, q)) for _ in range(W)]
    for p in ps:
        p.start()
    counts = {}
    while any(p.is_alive() for p in ps) or not q.empty():
        try:
            t = q.get(timeout=1)
            counts[int((t - t0) // 60)] = counts.get(int((t - t0) // 60), 0) + 1
        except Exception:
            pass
    for minute in sorted(counts):
        print(f"minute {minute + 1}: {counts[minute]} evaluations (N={n}, {W} workers)")
