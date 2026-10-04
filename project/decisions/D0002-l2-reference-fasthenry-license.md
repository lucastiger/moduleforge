# D0002 — L2 inductance reference: FastHenry 3.0wr under MIT's 2003 license, indemnity clause accepted
Date: 2026-09-30 · Status: accepted · Decider: founder

## Context
O001 needs an L2 reference solver (FastHenry-class PEEC) against which L1 is judged. mf-conventions allows
external reference tools only as separate executables for internal research, with their status recorded in a
decision record. The F6 audit (T0020, `research/notes/o001-l2-reference.md` §1) found exactly one candidate
whose sources carry terms that permit commercial use: Whiteley Research's FastHenry 3.0wr, under MIT's 2003
license. That license adds an indemnity clause, which is not standard MIT/BSD wording (audit §0, §7 item 1).

## Decision
- **Tool and pin.** `fasthenry-3.0wr-031424` from `https://raw.githubusercontent.com/wrcad/xictools/d28932afd22acf116c8bcd22e56a57faf3fb6d07/fasthenry/fasthenry-3.0wr-031424.tar.gz`,
  sha256 `6da40d0e31425bca85be46434b33ecc194205d705b47f4459d91568c9f4301ef` (5 211 870 bytes), built with
  `make all` and the bundled Sparse solver. KLU and MKL stay off.
- **License accepted, including the indemnity clause**, for internal research use of the unmodified tool as a
  separate executable: never vendored into this repository, never linked or imported, never redistributed.
- **Provisioning** (founder decision I0003, option b). `scripts/provision_compute.sh` downloads the pinned
  tarball, verifies its sha256 and builds it into `~/.local/bin` on this Mac and on burst VMs. The L2 adapter
  only resolves the provisioned binary (`MF_FASTHENRY_BIN`, then `PATH`) and records its path and sha256. It
  never downloads or builds anything; this supersedes the audit's "the adapter fetches it" rule (§1.4).

The clause, verbatim from `src/fasthenry/mulGlobal.h` of the pinned tarball:

> LICENSEE shall indemnify, hold harmless and defend the Copyright Owners and their trustees, officers,
> employees, students and agents against any and all claims arising out of the exercise of any rights under
> this Agreement, including, without limiting the generality of the foregoing, against any damages, losses or
> liabilities whatsoever with respect to death or injury to person or damage to property arising from or out of
> the possession, use, or operation of Software or Licensed Program(s) by LICENSEE or its customers.

## Verified first-hand (2026-09-30, founder session)
- Tarball sha256 and size match the audit.
- Licenses in the tarball: 73 of 95 `.c`/`.h` files carry the MIT 2003 notice (grant: "use, copy, modify, sell
  and/or distribute … for any purpose … without royalty"). The bundled Sparse package (`src/sparse`, © 1985–88
  Kenneth S. Kundert and the University of California) is permissive with attribution. Whiteley Research's
  solver files (© 2018) are "provided under the terms and conditions of the MIT license as it applies the the
  FastHenry computer software". The only noncommercial text is `doc/old_ps/license_.tex`, a historical document,
  not the license of the distributed sources.
- Build: Apple clang 21.0.0, macOS arm64, via the script's compatibility flags. Binary sha256
  `15bfbcd129afeb29e1b37258e43f41a714af482964aba261731c0d9bd0d37365`. Self-test (10 × 1 × 1 mm Cu bar):
  5.704 nH against the 5.695 nH closed form (+0.16 %).
- Bundled examples against `examples/results/linux_sparse`: 22 of 23 reproduce (all matrix entries; worst
  relative difference 2.9e-5, on ground-plane examples; most identical to the printed digits).

## Known issues
- **Intermittent crash.** `pin-con7` (1680 filaments, multipole) segfaults (exit 139) in about 1 run in 8 run
  alone and more often with other inputs in the directory. A crashed run leaves an empty `Zc.mat`. Completed
  runs reproduce the reference exactly (637 entries). The L2 adapter must treat any non-zero exit or signal as
  a failed solve and never parse `Zc.mat` from it. The root cause is not known; until it is, a completed run
  is trusted only through E001's analytic validation.
- **`.units mm`** scales the reported impedance by 1000 (5704 nH for the self-test bar), as in the build this
  replaces. Decks are written in metres (T0022).
- Linux x86-64 build: verified 2026-10-04 on a GCP e2-standard-4 VM (Ubuntu 24.04) via scripts/burst_gcp.sh;
  the pinned tarball's sha256 checked and the self-test passed (5.704 nH vs 5.695 nH).

## Alternatives considered
- FastHenry2 (FastFieldSolvers) — rejected: its sources carry MIT's earlier notice, "internal, noncommercial
  purposes" only.
- MIT FastHenry 3.0 (1996 tarball) — rejected: [inferred, audit] same noncommercial notice, no advantage.
- In-house FastHenry-class solver (audit §2) — kept as the fallback if E001 fails for tool reasons; less
  independent of L1.

## Consequences
We carry the indemnity exposure the clause describes for our use of the tool. Revisit this record before the
binary, its source, or its raw output is ever provided to a customer or bundled into a product. Any change of
pin, build or solver package is a new decision. The unpinned binary built on 2026-09-28 from
`github.com/hohe/fasthenry-3.0wr` (sha256 `ff598ac63d79aa570adf07db9e85b5a8d85d7c2bc1b5e769b75f91ef0bbb0a29`)
is replaced; no evidence was produced with it.
