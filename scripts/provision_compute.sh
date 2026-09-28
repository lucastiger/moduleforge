#!/usr/bin/env bash
# Install and self-test the reference solvers ModuleForge experiments need.
# Idempotent. macOS (Apple Silicon, Apple clang) and Ubuntu (gcc). Usage: scripts/provision_compute.sh [--force]
#   ngspice   : Homebrew / apt
#   FastHenry : built from source into ~/.local/bin, then checked against a closed-form inductance.
# FEniCSx is installed only when an objective needs it: see docs/INFRASTRUCTURE.md §5.
set -euo pipefail
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
FORCE="${1:-}"

if ! command -v ngspice > /dev/null; then
  if [ "$(uname)" = "Darwin" ]; then brew install ngspice; else sudo apt-get install -y -qq ngspice; fi
fi

build_fasthenry() {
  local work src real_cc flags name
  work="$(mktemp -d)"
  src="$work/fasthenry"
  echo "building FastHenry (log: $work/build.log)"
  git clone -q --depth 1 https://github.com/hohe/fasthenry-3.0wr "$src"
  # FastHenry is K&R-era C. Modern compilers reject it by default: clang >= 16 (including Apple's) and
  # gcc >= 14 turn implicit declarations, pointer mismatches and `return;` in implicit-int functions
  # into errors, and both default to
  # -fno-common. A wrapper applies the flags to every compile, including the sparse/ sub-build, whose
  # Makefile has its own CFLAGS. The flags come last so -O2 wins over the Makefiles' -O.
  real_cc="$(command -v cc)"
  flags="-O2 -fcommon -w -Wno-error=implicit-function-declaration -Wno-error=implicit-int"
  flags="$flags -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=return-type"
  if "$real_cc" --version 2>&1 | grep -qi clang; then
    flags="$flags -Wno-error=incompatible-function-pointer-types"
  fi
  mkdir -p "$work/cc-wrap"
  for name in cc gcc; do
    printf '#!/bin/sh\nexec "%s" "$@" %s\n' "$real_cc" "$flags" > "$work/cc-wrap/$name"
    chmod +x "$work/cc-wrap/$name"
  done
  if ! (cd "$src" && ./config default > /dev/null && mkdir -p bin \
        && PATH="$work/cc-wrap:$PATH" make fasthenry > "$work/build.log" 2>&1); then
    echo "FastHenry build FAILED. Last lines of $work/build.log:" >&2
    tail -25 "$work/build.log" >&2
    exit 1
  fi
  cp "$src/bin/fasthenry" "$BIN/fasthenry"
}

if [ "$FORCE" = "--force" ] || ! [ -x "$BIN/fasthenry" ]; then
  build_fasthenry
fi

# Self-test: 10 x 1 x 1 mm copper bar in SI units. Closed form (Ruehli/Grover): 5.695 nH.
# (The geometry is in meters on purpose: this FastHenry build mis-scales inductance under `.units mm`.)
t="$(mktemp -d)"
cat > "$t/bar.inp" << 'INP'
.units m
.default sigma=5.8e7
N1 x=0 y=0 z=0
N2 x=0.010 y=0 z=0
E1 N1 N2 w=0.001 h=0.001 nwinc=1 nhinc=1
.external N1 N2
.freq fmin=1e3 fmax=1e3 ndec=1
.end
INP
(cd "$t" && "$BIN/fasthenry" bar.inp > run.log 2>&1) || { echo "FastHenry self-test could not run:" >&2; tail -5 "$t/run.log" >&2; exit 1; }
python3 - "$t/Zc.mat" << 'PY'
import math, sys
v = open(sys.argv[1]).read().splitlines()[2].split()
L = float(v[1].rstrip("j")) / (2 * math.pi * 1e3) * 1e9
ok = abs(L - 5.695) / 5.695 < 0.01
print(f"FastHenry self-test: L = {L:.3f} nH (closed form 5.695 nH) -> {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
PY
echo "ngspice:   $(command -v ngspice)"
echo "fasthenry: $BIN/fasthenry"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "note: add $BIN to your PATH (the launchd plist already does)";; esac
