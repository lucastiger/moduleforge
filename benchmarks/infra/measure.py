"""Run a command; print wall seconds and the child's peak RSS. Usage: python measure.py -- cmd args..."""
import resource
import subprocess
import sys
import time

cmd = sys.argv[sys.argv.index("--") + 1:]
t = time.time()
r = subprocess.run(cmd, capture_output=True, text=True)
wall = time.time() - t
rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
rss_mb = rss / 2**20 if sys.platform == "darwin" else rss / 2**10   # macOS reports bytes, Linux KB
print(f"wall_s={wall:.2f} peak_rss_MB={rss_mb:.0f} rc={r.returncode}")
sys.stderr.write(r.stdout[-3000:] + r.stderr[-2000:])
