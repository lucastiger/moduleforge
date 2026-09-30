# O001 — L2 reference selection (F6 license + capability audit) and E001 design

Task T0020 · scientist · 2026-09-29 · status: proposal (E001 is a draft awaiting founder registration)

Labels: **[F]** fact checked first-hand (source + access date given) · **[I]** inference · **[S]** speculation.
All web sources were accessed on 2026-09-29.

## 0. Summary
- **Recommendation:** use the Whiteley Research FastHenry (`fasthenry-3.0wr-031424`) as L2, pinned below. Of the three
  candidates, its sources are the only ones that carry a **permissive** license: MIT's 2003 relicensing text.
  Call it as a separate executable with the bundled Sparse solver. Do **not** enable the optional KLU or MKL solvers.
- **Do not use** FastHenry2 (FastFieldSolvers) or, as far as can be told, the original MIT 1996 tarball. Their
  sources carry MIT's 1996 notice, which allows only *"internal, noncommercial purposes"*. ModuleForge is a
  commercial company.
- **Founder decision needed (F6 response = decision record):** the 2003 license has a clause requiring the
  LICENSEE to **indemnify** MIT. That clause is not standard MIT/BSD wording and needs founder/legal acceptance
  before an ADR records the tool.
- **Not verified:** building from source. My attempt to build it locally was blocked by the session's
  permission policy, so this note makes no first-hand claim about either platform. Third-party packaging evidence
  is given in §1.3. The builder task must build it on both platforms and record the result.
- E001 is designed to be solver-agnostic: it calls `moduleforge.solvers.l2`, specified in §3. The same
  experiment therefore validates FastHenry or the in-house fallback (§2).

## 1. Candidate audit

### 1.1 Licenses (quoted)
| Candidate | Source inspected | License text found |
|---|---|---|
| MIT FastHenry 3.0 (`fasthenry-3.0-12Nov96`) | Not downloaded. Distributed from https://www.rle.mit.edu/cpg/research_codes.htm (page reachable, HTTP 200) [F]. pkgsrc `cad/fasthenry` 3.0.19961112 names master site http://www.rle.mit.edu/cpg/codes/ (https://pkgsrc.se/cad/fasthenry) [F] | **Unverified.** [I] It very likely carries the 1996 notice below, for three reasons: FastHenry2 is derived from it and carries that notice; the wr README calls itself "the fasthenry-3.0-12Nov96 distribution with the following changes"; and the wr tree still ships `doc/old_ps/license_.tex`, the only file in it containing the word "noncommercial". |
| FastFieldSolvers FastHenry2 | https://github.com/ediloren/FastHenry2 master @ `363e43ed57ad3b9affa11cba5a86624fad0edaa9` (2015-09-08, "Linux/Unix version 3.0.1"). GitHub API reports `license: null`. codeload tarball sha256 `b9d1fdb48a958940ad6f28cd9f8ecb32df301ab0eb1c6d50bec5b23b9575ef03` [F] | `src/fasthenry/mulGlobal.h` [F]: *"Permission to use, copy and modify for internal, noncommercial purposes is hereby granted. Any distribution of this program or any part thereof is strictly prohibited without prior written consent of M.I.T. … LICENSEE agrees not to make any copies except for LICENSEE'S internal noncommercial use, or to use separately any portion of this software without prior written consent of M.I.T."* The FastFieldSolvers license page (https://www.fastfieldsolvers.com/license.htm) returned no terms to my fetch. |
| Whiteley Research fasthenry (wrcad/xictools) | https://github.com/wrcad/xictools, file `fasthenry/fasthenry-3.0wr-031424.tar.gz` at commit `d28932afd22acf116c8bcd22e56a57faf3fb6d07` (latest commit touching `fasthenry/`, 2024-11-23) [F] | Header of `src/fasthenry/*.c,h` (e.g. `mulGlobal.h`) [F]: *"Copyright (C) 2003 by the Board of Trustees of Massachusetts Institute of Technology … License to use, copy, modify, sell and/or distribute this software and its documentation for any purpose is hereby granted without royalty, subject to the following terms and conditions: 1. The above copyright notice and this permission notice must appear in all copies … 2. The names of the Copyright Owners may not be used in advertising or publicity … 3. THE SOFTWARE IS PROVIDED "AS-IS" … LICENSEE shall indemnify, hold harmless and defend the Copyright Owners … against any and all claims arising out of the exercise of any rights under this Agreement …"* The xictools `license/README` says the distribution is released under Apache-2.0, "In some cases, not all provisions of the Apache license are available due to constraints imposed by the licensing of earlier work … the file will contain a sub-header" [F]. FreeBSD port `science/fasthenry` declares MIT for this tarball (https://www.freshports.org/science/fasthenry/) [F]. |

Additional facts about the wr tree [F]:
- It bundles the Sparse package by default.
- `make SOLVER=KLU_SOLVER` links SuiteSparse KLU; `BUILD` says "MKL is not currently supported due to a licensing
  issue".
- [I] KLU is LGPL-2.1. That is irrelevant for a separate executable, but keep the default solver to avoid the
  question entirely.

### 1.2 Capabilities
Checked in the wr source (`src/fasthenry/readGeom.c`, `examples/input/*.inp`) [F].

**Features.** FastHenry2 3.0.1 is derived from the same MIT 3.0 code and shows the same example set [F]. [I] It has
the same feature set.
- **Finite meshed conductive planes:** `g` cards with corner points, `thick=`, `seg1=`/`seg2=` mesh counts, and
  `nhinc`/`rh` thickness layering (`readGeom.c` ≈l.1048–1142). Holes and nonuniform planes are supported
  (`hole.inp`, `holey_gp.inp`, `doc/nonuniform_manual.pdf`).
- **Cross-section filament subdivision:** `nwinc=`, `nhinc=`, `rw=`, `rh=` per segment or as `.default`
  (≈l.486–503, 737–774). This is what captures skin and proximity effects.
- **Frequency sweep:** `.freq fmin= fmax= ndec=` (`choosefreqs`, ≈l.313).
- **Ports and ties:** `.external n1 n2` defines a port; `.equiv` merges nodes (e.g. `onebargp.inp`).
- **Output:** a port impedance matrix per frequency in `Zc.mat` (text). Example outputs such as
  `examples/Zc_3d_examp2.mat` ship in FastHenry2.

**Round wires:** [I] segments are rectangular (`w`, `h`), and I found no round cross-section in the parser. The
adapter must therefore approximate a round wire. E001 cases B1–B4 test that approximation (§4).

**wr-specific changes** (README) [F]: superconductor support, a defined exit status, binary-mode output files, and
`sigma` defaulting to copper.

### 1.3 Build status (macOS arm64, Linux x86-64, system C compiler)
- **Not verified first-hand** [F]. I did not attempt to work around the permission denial on the local build.
- The wr `BUILD` file [F]: "The present source files and default Makefiles will work on any known reasonably
  modern system that is vaguely Unix-like, including OS X, Cygwin, and of course Linux/*BSD"; build with
  `make all`.
- Packaging evidence [F]:
  - FreeBSD packages this tarball for aarch64 and amd64 (freshports, above).
  - MacPorts lists `fasthenry-wr` arm64 binaries for darwin 22–25 at https://mirrors.mit.edu/macports/packages/fasthenry-wr
    (an older wr version, 3.0wr-010114, per the search snippet; not opened).
- [I] It will very likely build on both targets. **Action for the L2 builder task:** build from the pinned tarball
  on both platforms, run the bundled `examples/` and diff against `examples/results`, and record compiler
  versions and warnings.

### 1.4 Recommendation and pin
- **Tool:** fasthenry-3.0wr-031424.
- **Source:** `https://raw.githubusercontent.com/wrcad/xictools/d28932afd22acf116c8bcd22e56a57faf3fb6d07/fasthenry/fasthenry-3.0wr-031424.tar.gz`
- **sha256:** `6da40d0e31425bca85be46434b33ecc194205d705b47f4459d91568c9f4301ef` (5 211 870 bytes, downloaded
  2026-09-29) [F].
- **Build:** `make all` with the default Sparse solver.
- **Use rules (mf-conventions):** never vendored into the repo. The adapter fetches it, checks the sha256 and
  builds it into a tool cache. It runs as a subprocess for internal research only. The binary's sha256 is recorded
  in `ExperimentRun(tools=…)` provenance.

**Rejected:**
- FastHenry2: noncommercial-only notice.
- MIT 1996 tarball: [I] same notice, and no advantage over wr.

## 2. In-house FastHenry-class fallback

**What it is:**
- A Python/numpy PEEC (permissive, no external binary).
- Conductors are split into straight segments, and segments into `nw×nh` rectangular filaments with uniform
  current.
- Filament partial inductances come from the Hoer–Love closed form (near pairs) and the filament Neumann formula
  (far pairs); resistances are `l/(σA)`.
- It uses a mesh/nodal formulation (MNA with `Z = R + jωL`), with ties as node merges and ports as current
  injections, solved densely up to ~10⁴ filaments (≈1.6 GB complex128 at 10⁴; [I] adequate for E001/E002 sizes
  with graded meshes).
- Planes are 2-D grids of x- and y-directed filament bars with graded thickness layers (FastHenry's plane model).
- The closed forms it needs are already implemented and self-checked in `experiments/runners/e001_reference.py`.

**When it would be needed** (any one of these):
1. The founder does not accept the 2003 license's indemnity clause.
2. The pinned wr build fails on either platform, or its examples do not reproduce.
3. FastHenry fails E001 for a reason inside the tool (not the adapter), e.g. plane accuracy.
4. E002 needs throughput FastHenry cannot give.

It must pass the identical E001, since E001 only sees `moduleforge.solvers.l2`.

**Caveat:** an in-house L2 built from the same closed forms as L1 is less independent. [I] E001's comparison
against exact field solutions (Bessel internal impedance, image theory) partly compensates; the closed forms alone
would not.

## 3. Contract: `moduleforge.solvers.l2` (to be implemented by a later builder task)
SI units and float64 throughout; complex128 impedances. All types are frozen dataclasses. Everything E001 calls:

```python
from moduleforge.solvers import l2

l2.MAX_REFINEMENT: int                      # highest supported refinement level (>= 5)

l2.Bar(name: str, start: tuple[float, float, float], end: tuple[float, float, float],
       width: float, thickness: float, sigma: float,
       width_dir: tuple[float, float, float] | None = None)
    # straight rectangular conductor; start/end = centroids of the end faces (m).
    # width_dir defaults to z x axis (horizontal bars: width in-plane, thickness along z).
l2.RoundWire(name: str, points: tuple[tuple[float, float, float], ...], diameter: float, sigma: float)
    # polyline of straight round segments, vertex to vertex along the centre line (no corner extension).
l2.Plane(name: str, x_min: float, y_min: float, x_max: float, y_max: float,
         z_top: float, thickness: float, sigma: float)
    # finite rectangular conductive plane occupying [x_min,x_max]x[y_min,y_max]x[z_top-thickness, z_top].
    # In E001 planes are floating (no terminals).
l2.Terminal(conductor: str, vertex: int)    # Bar: 0 = start, 1 = end; RoundWire: polyline vertex index
l2.Port(name: str, plus: Terminal, minus: Terminal)
l2.Tie(a: Terminal, b: Terminal)            # ideal zero-impedance connection (FastHenry .equiv)

res = l2.solve(conductors: Sequence[Bar | RoundWire], planes: Sequence[Plane], ports: Sequence[Port],
               freqs_hz: Sequence[float], refinement: int, ties: Sequence[Tie] = ()) -> l2.Result
res.freqs_hz: np.ndarray         # (nf,)
res.z: np.ndarray                # (nf, np, np) complex128, ohm; Z[i, j] = V_i / I_j with all other ports open
res.meta: dict                   # tool name, version, binary sha256, n_filaments, wall_s, per-level mesh params
```

**Port convention:** the current `I_j` enters the structure at `plus_j` and leaves at `minus_j`, so `L = Im Z / ω`.
Two parallel conductors whose ports point the same way have `Im Z12 > 0` (E001 A3/A4/B3 test the sign).

**Refinement contract:**
- Level `k+1` must refine every discretization the adapter controls:
  - segment subdivision along the length;
  - cross-section filaments (`nwinc`, `nhinc`) with geometric grading so the outer filament is ≤ δ/2 by the finest
    levels;
  - plane `seg1`/`seg2` and plane thickness layers.
- The mesh must be defined relative to geometry and δ, not in absolute metres, so that the exact similarity
  (lengths × s, f / s²) yields identical meshes. The `length_scaling` check relies on this.

**Solver accuracy:** iterative tolerance ≤ 1e-6 relative, or a direct solve. `reciprocity` requires
|Z12 − Z21|/|Z12| ≤ 1e-3.

**Round wires:** the adapter chooses the representation, e.g. a staircase or ring of rectangular filaments
approximating the disk. It must converge to the round-wire solution under refinement; E001 B1–B4 would detect it
if not.

**Implementability on FastHenry** [I]:
- bars → segments with `w`, `h`, `wx/wy/wz`;
- wires → one segment per polyline edge (or a filament bundle);
- planes → `g` cards with nodes at the corners;
- terminals → named nodes; ports → `.external`; ties → `.equiv`;
- frequencies → one `.freq` per value (`fmin=fmax`);
- `Zc.mat` parsed into `res.z`.

One adapter subtlety: FastHenry plane nodes sit at the plane mid-thickness. Planes are floating in E001, so this
matters only for galvanic plane contacts (future E002 work, outside this contract).

## 4. E001 design (draft `experiments/drafts/E001.yaml`, runner `experiments/runners/e001_reference.py`)

**Principle:**
- Each closed form is exact for the *modeled* geometry: the same partial-inductance topology, segments running
  vertex-to-vertex, and mutual inductance exactly 0 between orthogonal segments. Any error left over is a stated
  residual.
- LF bar cases use 100 Hz (δ_Cu = 6.6 mm ≫ bar dimensions), so the DC closed forms apply.
- The ≥ 5 MHz cases use round wires, because only for them is the frequency dependence exact (Bessel).

**Materials:** Cu σ = 5.8e7 S/m, Al σ = 3.77e7 S/m, identical in L2 and the closed forms.

| Case | Class | Geometry (mm) | Closed form | f | Residual model error (stated) |
|---|---|---|---|---|---|
| A1 | bar_self | Cu bar 20×3×0.3 | Hoer–Love self [HL] | 100 Hz | ≤1e-4 (LF skin, bounded by `regime_valid` at 2.8e-5) |
| A2 | bar_self | Cu bar 10×1×1 | Hoer–Love self | 100 Hz | ≤1e-4 |
| A3 | bar_mutual | two 20×3×0.3 side by side, 4 mm centres, two ports | L11, M12 Hoer–Love | 100 Hz | ≤1e-4 |
| A4 | bar_mutual | 15×3×0.3 at z=0; 10×2×0.3 at x∈[5,15], y=0.5, z=0.8 | L11, M12, L22 Hoer–Love (general offsets) | 100 Hz | ≤1e-4 |
| B1 | wire_chain | Al Ø0.3 straight, 10 | tube partial L [R][G] + exact Bessel internal Z [RWV] | 100 Hz, 5, 20, 80 MHz | O((r/l)²) ≈ 1e-4 |
| B2 | wire_chain | staple (0,0,0)→(0,0,1.5)→(8,0,1.5)→(8,0,0) | Σ self − 2M(legs); orthogonal pairs 0 | same | 0.5(r/l_min)² = 5e-3 (conservative) |
| B3 | wire_mutual | two staples at y=0 and y=1.5, two ports | L11, M12 | same | + (r/p)²/ln(p/r) proximity ≈ 9e-3 |
| B4 | wire_parallel_tied | B3 with ends tied, one port | 1/(1ᵀZ⁻¹1) of exact branch Z | 5, 20, 80 MHz | ≈ 9e-3 |
| C0 | loop_free | horizontal rectangle loop 10×5 at z=1, Al Ø0.3 | partial sum (cross-checked with Grover's rectangle formula) | 5, 20, 80 MHz | ≈ 5e-4 |
| C1 | loop_over_plane | C0 over a floating Cu plane, t=0.3, top z=0, margin 15 (40×35) | image theory about the plane recessed by δ/2 (Wheeler) [W] | 5, 20, 80 MHz | (δ/2h)² + (r/2h)² + 1e-3 truncation ≈ 7e-3 |

Closed-form values (nH), from the runner:
- A1 12.171 · A2 5.704 · A3 M 6.179 · A4 M 4.670
- B1 8.316 / 8.057 / 7.937 / 7.877 (100 Hz / 5 / 20 / 80 MHz)
- C0 19.02 / 18.66 / 18.48 · C1 14.78 / 14.39 / 14.19 (5 / 20 / 80 MHz)

These show why a DC-only or plane-less L2 fails A1:
- B1 at 80 MHz vs DC differs by 5.6%.
- C1 vs C0 differs by 23%.

**Metric:**
- `max_rel_err_vs_analytic` = max over 32 compared values of |L2 − closed form|/|closed form|, where L2 is at the
  finest level of the pre-registered refinement rule. The rule starts at level 1 and advances until one refinement
  changes every compared value by < 1%, stopping at `refinement_max` = 5.
- The attached interval is a deterministic bound: ± (last-refinement change + stated residual). The cases are
  deterministic, so this is not a sampling CI. A1 uses the point value.

**Diversity statistics:**
- `analytic_value_span`: max/min of the compared values, ≈ 7.
- `n_geometry_classes`: 7.

**Sanity checks** (each can fail; each separates "the experiment is broken" from "L2 is wrong"):
1. `closed_forms_published_values`:
   - Kelvin ber/bei at 1, 2, 5 vs the exact rational series. My first recalled table value for bei(5) was wrong, and
     this check caught it; the reference now comes from exact arithmetic.
   - Grover's square GMD 0.44705a and thin-strip e^-1.5 w.
   - Internal-impedance DC and HF limits.
2. `closed_forms_independent_check`:
   - Hoer–Love vs 6-D Gauss–Legendre: 9e-15.
   - Filament formula vs quadrature: 2e-15.
   - Bessel series vs Hankel asymptotics: 4e-13.
   - Hoer–Love → GMD formula for long bars and → filament in the thin limit.
   - Partial-sum rectangle vs Grover's rectangle formula at r = 1 µm: 5e-5.
3. `analytic_length_scaling`: every case at (2×, f/4) gives exactly 2×.
4. `regime_valid`: LF skin deficit, δ/t_plane ≤ 0.2, (δ/2h)² ≤ 1e-3.
5. `plane_truncation_bound`: a 2-D floating-PEC-strip BEM.
   - It reproduces the infinite image to 2e-8 at W = 400h.
   - C1's margin gives a 2-D truncation of 1.4e-5. [I] 3-D truncation is smaller, since fields fall faster.
6. `l2_converged`: < 1% under one refinement.
7. `reciprocity`: ≤ 1e-3.
8. `l_monotone_in_frequency`: driving-point Im Z/ω is non-increasing in ω, a theorem for RL one-ports (Foster form
   [GU]); the PEEC discretization is exactly such a network. Bars are also solved at 5/20/80 MHz for this check
   only, which covers bar HF behaviour where no closed form exists.
9. `length_scaling`: A1, B2 and C1 at (2×, f/4), within 1%.

**What would prove L2 wrong:**
- an error > 2% on any case;
- non-convergence;
- a reciprocity or scaling violation;
- L increasing with f.

**Runner verification done here:**
- `--analytic-only` passes (exit 0).
- `--smoke` currently ends with status `error`, because `moduleforge.solvers` does not exist yet.
- A /tmp-only stand-in solver (closed form × (1 + bias + 0.02/2^k)) exercised the whole L2 path: at bias 0 all
  checks pass with metric 0.005; at bias 0.03 the metric is 0.035, so A1 would fail. This checks plumbing only; it
  is not evidence.

**Coverage gaps** [I], so that E002 readers do not over-read a pass:
- **Rectangular bars at HF:** no exact closed form exists. They are covered only by convergence, monotonicity and
  the shared filament machinery that B-cases validate.
- **Inclined bond-wire legs:** closed forms for thick non-orthogonal segments carry O(r/l) joint errors, so they are
  covered by convergence only.
- **Galvanic plane contacts, and bar–wire junctions:** not tested.

**Ambiguity in the packet, and how I resolved it:** "--smoke runs at least one case of every geometry class at
20 MHz". Bar closed forms are DC-only (a 2–3% HF deviation is expected [I]). So smoke solves bar classes at 20 MHz
*and* at 100 Hz, and compares only at 100 Hz. The founder should confirm.

## 5. Closed forms used (citations)
- **Hoer & Love 1965 [HL]:** C. Hoer, C. Love, J. Res. NBS 69C(2):127–137. Exact 6-fold integral for parallel
  rectangular bars. The same function appears in A. E. Ruehli, IBM J. Res. Dev. 16(5):470–481 (1972), and in
  FastHenry `joelself.c:eval_eq`; I compared term by term [F].
- **Grover 1946 [G]:** *Inductance Calculations*, Van Nostrand (Dover 2004). Parallel filaments with offset (Ch. 7),
  rectangle GMD (Ch. 3), rectangle loop (Ch. 14).
- **Rosa 1908 [R]:** Bull. Bur. Stand. 4:301–344. Straight-wire and tube self-inductance.
- **Image theory with Wheeler's incremental-inductance rule [W]:** H. A. Wheeler, Proc. IRE 30(9):412–424 (1942). A
  thick good conductor behaves as a perfect conductor recessed by δ/2.
- **Exact round-wire internal impedance [RWV]:** Ramo, Whinnery & Van Duzer, *Fields and Waves in Communication
  Electronics*, 3rd ed. §5.6: Z′ = k J0(ka)/(2πaσ J1(ka)), k = (1−j)/δ.
- **Bessel functions [AS]:** Abramowitz & Stegun 9.1.10, 9.2.5–9.2.10, 9.9.10.
- **RL driving-point monotonicity [GU]:** Guillemin, *Synthesis of Passive Networks* (1957).
- **μ0:** CODATA 2018.

[I] Bibliographic details are from memory of the standard references and were not re-fetched. Every formula is
verified numerically by the self-checks above, independently of the citation.

## 6. Published half-bridge anchors (for E002 plausibility)
- **PowerSynth, TPEL 2019:** T. Evans et al., "PowerSynth: A Power Module Layout Generation Tool", IEEE TPEL 2019.
  Author PDF: https://e3da.csce.uark.edu/pub/doc/2019/T.Evans-IEEE.TPEL-2019.pdf [F: search result]. The abstract
  reports that parasitic models were compared with FastHenry and with measurements on a half-bridge prototype. **The
  loop-inductance numbers were not extracted** (budget); this is a follow-up for the E002 design task.
- **Q3D vs double-pulse (~4% agreement):** not located in this task. Open.

## 7. Open items for the founder / planner
1. Accept or reject the 2003 MIT license with its indemnity clause, as an ADR. If rejected: fallback (§2).
2. The L2 builder task builds the pinned wr tarball on macOS arm64 and Linux x86-64 and reproduces `examples/`.
3. Confirm the smoke-mode interpretation for bar classes (§4).
4. Extract the PowerSynth and Q3D anchor numbers during E002 design.
