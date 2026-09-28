#!/usr/bin/env bash
# Infrastructure benchmarks B2-B5 (B1 is cc_concurrency.sh). Run from the repository root:
#   uv run --group physics bash benchmarks/infra/run_all.sh
# Compare with the reference numbers in docs/INFRASTRUCTURE.md §13.
set -euo pipefail
cd "$(dirname "$0")"
echo "== B2 L1 PEEC (fill + complex solve, float64)";  python l1_bench.py 200 400 800 1600 2>&1 | grep -v WARNING
echo "== B3 L2 FastHenry half-bridge loop (needs scripts/provision_compute.sh)"
for cfg in "8 3 30" "16 5 60" "24 7 80"; do
  set -- $cfg; python fh_gen.py "$1" "$2" "$3" > /tmp/mf_fh.inp
  (cd /tmp && python "$OLDPWD/measure.py" -- fasthenry /tmp/mf_fh.inp 2> /dev/null | sed "s/^/nw=$1 nh=$2 plane=$3  /")
done
echo "== B4 3D thermal (AMG-CG; FEniCSx cost proxy)"; python thermal_bench.py
echo "== B5 ngspice double-pulse"; python measure.py -- ngspice -b dpt.cir 2> /dev/null
echo "== B6 sustained throughput (throttling): 4 workers x 10 min"; python l1_throughput.py 4 10
