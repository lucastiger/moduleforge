#!/usr/bin/env bash
# Install and self-test the reference solvers ModuleForge experiments need.
# Idempotent. macOS (Apple Silicon, Apple clang) and Ubuntu (gcc). Usage: scripts/provision_compute.sh [--force]
#   ngspice   : Homebrew / apt
#   FastHenry : built from the pinned wr tarball (project/decisions/D0002) into ~/.local/bin, then checked
#               against a closed-form inductance. --force rebuilds it.
# FEniCSx is installed only when an objective needs it: see docs/INFRASTRUCTURE.md §5.
set -euo pipefail
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
FORCE="${1:-}"

if ! command -v ngspice > /dev/null; then
  if [ "$(uname)" = "Darwin" ]; then brew install ngspice; else sudo apt-get install -y -qq ngspice; fi
fi

# L2 reference pinned by project/decisions/D0002 (MIT 2003 license, indemnity clause accepted by the founder).
FH_URL="https://raw.githubusercontent.com/wrcad/xictools/d28932afd22acf116c8bcd22e56a57faf3fb6d07/fasthenry/fasthenry-3.0wr-031424.tar.gz"
FH_SHA256="6da40d0e31425bca85be46434b33ecc194205d705b47f4459d91568c9f4301ef"

build_fasthenry() {
  local work src real_cc flags name got
  work="$(mktemp -d)"
  src="$work/fasthenry-3.0wr"
  echo "building FastHenry 3.0wr-031424 (log: $work/build.log)"
  curl -fsSL -o "$work/fasthenry.tar.gz" "$FH_URL"
  got="$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
         "$work/fasthenry.tar.gz")"
  if [ "$got" != "$FH_SHA256" ]; then
    echo "FastHenry tarball sha256 mismatch: got $got, pinned $FH_SHA256 (D0002)" >&2
    exit 1
  fi
  tar -xzf "$work/fasthenry.tar.gz" -C "$work"
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
  # The wr BUILD file: `make all` from the top directory with the bundled Sparse solver; the old `config`
  # step is for MinGW only. KLU/MKL stay off (D0002).
  if ! (cd "$src" && mkdir -p bin && PATH="$work/cc-wrap:$PATH" make all > "$work/build.log" 2>&1); then
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
# (The geometry is in meters on purpose: this FastHenry build scales the impedance by 1000 under `.units mm`;
# checked on the pinned build, D0002.)
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
