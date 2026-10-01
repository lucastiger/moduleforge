# O001 — L2 reference selection (F6 license + capability audit) and E001 design

Task T0020 · scientist · 2026-09-29 · status: proposal (E001 is a draft awaiting founder registration)
Revised by T0041 · 2026-09-30 · design fixes from reviews T0029/T0030 (§3, §4, license date in §0/§1.1). The tool
decision is recorded in project/decisions/D0002; E001 stays solver-agnostic. T0041 attempt 2 re-audited the attempt-1
work and added: the YAML number-literal fix (§4.5, would have crashed the registered run), the exact 1-D form of the
Bessel/reaction self-check (§4.1), the small-step guard of the refinement rule (§4.4), and the mutation record (§4.5).
T0041 attempt 3 (2026-10-01) answers reviews T0051/T0052 of attempt 2: finite cross-section of wire–wire and
wire–image mutuals with a rigorous remainder bound (§4.2a, §4.3 term (d)); a refinement rule that does not
underestimate decelerating (algebraic) convergence, with ≥ 4 levels and a solver noise floor (§4.4); a constant
refinement ratio, `meta['mesh_h']`, and a forward-error `solver_tol` that includes conditioning (§3); the metric
interval recorded at level 0.95 as an estimated error band (§4.4); the stale B1 DoD text and B3's resistance fixed.

Labels: **[F]** fact checked first-hand (source + access date given) · **[I]** inference · **[S]** speculation.
All web sources were accessed on 2026-09-29.

## 0. Summary
- **Recommendation:** use the Whiteley Research FastHenry (`fasthenry-3.0wr-031424`) as L2, pinned below. Of the three
  candidates, its sources are the only ones that carry a **permissive** license: MIT's 2003 relicensing text.
  Call it as a separate executable with the bundled Sparse solver. Do **not** enable the optional KLU or MKL solvers.
- **Do not use** FastHenry2 (FastFieldSolvers) or, as far as can be told, the original MIT 1996 tarball. Their
  sources carry MIT's earlier notice (FastHenry2 `mulGlobal.h`: "Copyright (c) 1992 Massachusetts Institute of
  Technology, Cambridge, MA."; date corrected by T0041 after review T0030 and re-fetched first-hand 2026-09-30 from
  raw.githubusercontent.com/ediloren/FastHenry2/master/src/fasthenry/mulGlobal.h [F]), which allows only
  *"internal, noncommercial purposes"*. ModuleForge is a commercial company.
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
| MIT FastHenry 3.0 (`fasthenry-3.0-12Nov96`) | Not downloaded. Distributed from https://www.rle.mit.edu/cpg/research_codes.htm (page reachable, HTTP 200) [F]. pkgsrc `cad/fasthenry` 3.0.19961112 names master site http://www.rle.mit.edu/cpg/codes/ (https://pkgsrc.se/cad/fasthenry) [F] | **Unverified.** [I] It very likely carries the noncommercial notice below (dated 1992 in FastHenry2's `mulGlobal.h` header), for three reasons: FastHenry2 is derived from it and carries that notice; the wr README calls itself "the fasthenry-3.0-12Nov96 distribution with the following changes"; and the wr tree still ships `doc/old_ps/license_.tex`, the only file in it containing the word "noncommercial". |
| FastFieldSolvers FastHenry2 (notice © 1992 MIT) | https://github.com/ediloren/FastHenry2 master @ `363e43ed57ad3b9affa11cba5a86624fad0edaa9` (2015-09-08, "Linux/Unix version 3.0.1"). GitHub API reports `license: null`. codeload tarball sha256 `b9d1fdb48a958940ad6f28cd9f8ecb32df301ab0eb1c6d50bec5b23b9575ef03` [F] | `src/fasthenry/mulGlobal.h` [F]: *"Permission to use, copy and modify for internal, noncommercial purposes is hereby granted. Any distribution of this program or any part thereof is strictly prohibited without prior written consent of M.I.T. … LICENSEE agrees not to make any copies except for LICENSEE'S internal noncommercial use, or to use separately any portion of this software without prior written consent of M.I.T."* The FastFieldSolvers license page (https://www.fastfieldsolvers.com/license.htm) returned no terms to my fetch. |
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
res.meta: dict                   # required: 'solver_tol' (float, see below), 'n_filaments' (int, the one mesh
                                 # of this call); also tool name, version, binary sha256, wall_s, mesh params
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

**One mesh per refinement level (T0041).** `l2.solve(..., freqs_hz, refinement=k)` must build exactly one mesh
for the call and use that same mesh at every frequency of the call: graded to the skin depth at `max(freqs_hz)`
(the finest need), never re-meshed per frequency. Reason: `l_monotone_in_frequency` relies on the RL
driving-point theorem, which holds for one fixed network only; with a mesh per frequency, mesh-to-mesh
differences up to `conv_tol` (1 %) could exceed `monotone_tol` (0.1 %) and invalidate a correct run. Deck
writers that emit one `.freq` card per value must emit them in one deck against one geometry, not one deck per
frequency. `res.meta['n_filaments']` must be a single integer (the one mesh); the runner's
`l2_one_mesh_per_solve` check fails otherwise.

**Constant refinement ratio (T0041 attempt 3, review T0052).** Every discretization parameter the adapter controls
(segment length, filament width and height, the first graded cell at the surface, plane cells, plane thickness
layers) is refined by the **same fixed ratio** r ≥ 1.25 between consecutive levels, h_{k+1} = h_k / r. Integer
counts are rounded up. Additive schemes (n = k, n = 2k + 1) are not allowed: they make the error algebraic in k,
and then the geometric model of the refinement rule (§4.4) underestimates. `res.meta['mesh_h']` (float > 0) is
required: the characteristic relative cell size of the call, i.e. the largest refined cell size divided by its
reference size. The runner's `l2_constant_refinement_ratio` check requires every realized ratio
h_k/h_{k+1} ≥ `refinement_ratio_min` = 1.25 and max/min of the ratios ≤ `refinement_ratio_spread` = 1.1.
[F] With a stand-in adapter that reports h = 1/k, the check fails (value 1.36).

**Solver accuracy (T0041): `res.meta['solver_tol']` is required.** It is a float upper bound on the relative
**forward error** of every returned port impedance due to the linear algebra and the output format (review T0052:
a residual tolerance is not a forward error). Its parts:
- iterative solves: κ_est × the relative-residual tolerance, plus the error of any matrix compression (multipole),
  with κ_est an estimate of the condition number of the solved system (e.g. a LAPACK-style 1-norm estimate);
- direct factorization of the uncompressed system: κ_est × 1.1e-16 (unit roundoff);
- in both cases, plus the rounding of the written impedances (Zc.mat digits).

[I] PEEC systems with graded filaments can have κ ≫ 1, so for the 100 Hz cases this effectively requires a direct
LU of the uncompressed matrix. FastHenry exposes direct and iterative solution options (`-s`) and direct or
multipole matrix products (`-m`) per its documentation as I recall it, not re-checked; T0022 must confirm the
options and report κ_est. The runner checks every solve against what its comparisons need:
- A relative error ε in Z becomes ε·|Z|max/(ω|L|min) in L. At 100 Hz the resistance dominates. For the bars
  (A1–A4) that ratio is 48–99, and for the Al wire chains compared at 100 Hz (B1–B3) it is 720–2 400. The wire
  chains, not the bars, are the worst case: B3 needs M12 = 2.70 nH beside R = 4.13 mΩ (11 mm of Ø0.3 mm Al;
  corrected from 3.8 mΩ after review T0051; the code was right).
- Required: `meta['solver_tol']` ≤ `solver_err_budget` / amplification, with `solver_err_budget` = 1e-4 of L.
  Computed per case from the closed form (`solver_tol_required`): A1/A2 ≤ 2.0e-6, A3/A4 ≤ 1.0e-6,
  B1 ≤ 1.4e-7, B2 ≤ 1.2e-7, B3 ≤ 4.1e-8, and ≤ 1e-4 for the HF-only cases B4, C0, C1.
- **Decision: tighten the requirement; keep f_lf = 100 Hz.** Raising f_lf would cut the amplification ∝ 1/f,
  but it would break the DC closed forms of the bars. The internal-inductance skin deficit grows ∝ f²: for A1 it is
  2.8e-5 at 100 Hz and would be 2.8e-3 at 1 kHz, above the 1e-3 regime limit. The earlier "≤ 1e-6" was
  insufficient for B1–B3.
- [I] On FastHenry this means a direct LU of the full (non-multipole) matrix, or a GMRES tolerance ≤ 1e-8 with
  multipole error included. I did not verify first-hand which FastHenry 3.0wr options provide this; T0022 must
  confirm and report it in `meta['solver_tol']`.
- `reciprocity` requires |Z12 − Z21|/|Z12| ≤ 1e-3.
- The same budget sets the refinement rule's noise floor: two levels can differ by up to 2 × `solver_err_budget`
  × |L| from the solver alone (§4.4).

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

**Principle.**
- Each closed form is exact for the *modeled* geometry (same partial-inductance topology, segments running vertex
  to vertex, zero mutual between orthogonal segments) up to a **stated residual model error**. The residuals are
  derived in §4.3 and checked against independent references.
- LF bar cases use 100 Hz (δ_Cu = 6.6 mm ≫ bar dimensions), so the DC closed forms apply.
- ≥ 5 MHz cases use round wires, whose frequency dependence has an exact treatment (Bessel).
- Materials: Cu σ = 5.8e7 S/m and Al σ = 3.77e7 S/m, identical in L2 and in the closed forms.

| Case | Class | Geometry (mm) | Closed form | f | Stated residual (§4.3) |
|---|---|---|---|---|---|
| A1 | bar_self | Cu bar 20×3×0.3 | Hoer–Love self [HL] | 100 Hz | 1e-4 |
| A2 | bar_self | Cu bar 10×1×1 | Hoer–Love self | 100 Hz | 1e-4 |
| A3 | bar_mutual | two 20×3×0.3, 4 mm centres, two ports | L11, M12 Hoer–Love | 100 Hz | 1e-4 |
| A4 | bar_mutual | 15×3×0.3 at z=0; 10×2×0.3 at x∈[5,15], y=0.5, z=0.8 | L11, M12, L22 | 100 Hz | 1e-4 |
| B1 | wire_chain | Al Ø0.3 straight, 10 | wire self (§4.1) | 100 Hz, 5, 20, 80 MHz | 5.4–5.7e-5 |
| B2 | wire_chain | staple (0,0,0)→(0,0,1.5)→(8,0,1.5)→(8,0,0) | Σ self − 2M(legs) (+§4.2) | same | 8.6–9.1e-4 |
| B3 | wire_mutual | two staples at y=0 and y=1.5, two ports | L11, M12 (+§4.2, §4.2a) | same | L11 8.6e-4 (100 Hz)–1.3e-3; M12 2.0e-6 (100 Hz)–1.2e-5 |
| B4 | wire_parallel_tied | B3 with ends tied, one port | 1/(1ᵀZ⁻¹1) of the branch Z | 5, 20, 80 MHz | 8.7–9.4e-4 |
| C0 | loop_free | rectangle loop 10×5 at z=1, Al Ø0.3 | partial sum (+§4.2, §4.2a) | 5, 20, 80 MHz | 1.5e-4 |
| C1 | loop_over_plane | C0 over a floating Cu plane, t=0.3, top z=0, margin 15 (40×35) | image about the plane recessed by δ/2 [W] (+§4.2, §4.2a) | 5, 20, 80 MHz | 1.4–1.6e-3 |

All stated residuals are ≤ 1.6e-3, below the 2e-3 target and far below the 2 % criterion.

**Closed-form values (nH), from the runner (T0041):**
- A1 12.171 · A2 5.704 · A3 M 6.179 · A4 M 4.670.
- B1 8.3128 / 8.0602 / 7.9432 / 7.8836 (100 Hz / 5 / 20 / 80 MHz). The T0020 values were 8.316 / 8.057 / 7.937 /
  7.877.
- B3 M12 2.6996 / 2.7001 / 2.7004 / 2.7005 (100 Hz / 5 / 20 / 80 MHz; attempt 2: 2.6986, without §4.2a).
- B4 5.0337 / 4.9707 / 4.9385 · C0 19.033 / 18.684 / 18.506 · C1 14.774 / 14.392 / 14.197 (5 / 20 / 80 MHz).

These show why a DC-only or plane-less L2 fails A1: B1 changes by 5.2 % between 100 Hz and 80 MHz, and C1 is
23 % below C0.

### 4.1 Round-wire self term: mean distance instead of r (reviews T0029/T0030, finding 1)
- **[F] Error in T0020.** T0020 modeled the external self-inductance as the filament mutual at distance r. The
  filament mutual (Grover [G] ch. 7) is M(l,d) = μ0/2π [l asinh(l/d) − √(l²+d²) + d]. Expanded:
  μ0/2π [l ln(2l/d) − l + d − d²/(4l) + d⁴/(32l³) − d⁶/(96l⁵) …].
- **Exact form.** Averaging over the current distribution J gives, for the ln-part, the infinite-wire internal
  impedance, which is already carried by the exact Bessel Z_int [RWV]. The linear term, however, averages to the
  *mean* distance ⟨d⟩, not r. So the O(r/l) residual was first order.
  - Uniform current: ⟨d⟩ = 128r/(45π) = 0.905r [MW].
  - Surface current: ⟨d⟩ = 4r/π.
- **Correction (derived here; `wire_self_correction`).** Add
  μ0/2π [(⟨d⟩ − r) − (⟨d²⟩ − r²)/(4l) + (⟨d⁴⟩ − r⁴)/(32l³)].
  - Moments are taken over the exact infinite-wire profile J(ρ)/I = k J0(kρ)/(2πr J1(kr)), k = (1−j)/δ [RWV].
    They use the **unconjugated reaction weights** J(p)J(q)/I², for which the functional is stationary [RU]. This
    covers the whole uniform→surface transition continuously.
  - ⟨d⟩ uses the angular mean of |p − q| between coaxial circles, (2/π)(ρ+ρ′)E(4ρρ′/(ρ+ρ′)²) (substitute
    φ = π − 2θ). Also ⟨d²⟩ = 2⟨ρ²⟩ and ⟨d⁴⟩ = 2⟨ρ⁴⟩ + 4⟨ρ²⟩².
  - Limits checked (`closed_forms_published_values`): 128/(45π) to 4.9e-7; r² and 5r⁴/3 to 1e-15; → 4r/π at
    r/δ = 386 within δ/r.
- **[F] Independent verification** (`closed_forms_independent_check`, "tube PEEC"). A finite straight segment is
  split into 80 coaxial annuli with uniform current each. It uses the exact finite-length kernel, **solves** for
  the current distribution, and uses no Bessel functions or moments. Closed form vs tube PEEC:

  | Length | 100 Hz | 5–80 MHz | T0020's filament-at-r (100 Hz / 80 MHz) |
  |---|---|---|---|
  | 1.5 mm | 7.8e-9 | 2.7–3.0e-4 | +4.0e-3 / −9.6e-3 |
  | 5 mm | 3.8e-9 | 1.4–1.7e-5 | +8.2e-4 / −2.1e-3 |
  | 10 mm | 1.6e-9 | 0.5–1.7e-6 | +3.4e-4 / −8.8e-4 |

  - The tube PEEC converges: 40→80 annuli changes it by ≤ 1.6e-5.
  - The old model fails this check; mutation "old_wire_model" is caught.
  - The residual scales as (r/l)², as expected of a stationary functional.
- The Bessel Z_int also equals the reaction integral with the log kernel, which checks the complex (unconjugated)
  weighting. [F] Agreement 4.7e-12 (5 MHz) and 1.0e-12 (80 MHz), tolerance `tol_independent` = 1e-6. The integral
  is evaluated in 1-D form, ⟨ln d⟩ = 2∫ j(ρ) ln ρ C(ρ) dρ with C(ρ) = ρJ1(kρ)/(rJ1(kr)) [AS 9.1.30], because the
  angular mean of ln|p − q| over coaxial circles is ln max(ρ, ρ′). Attempt 1 used the 2-D tensor form, whose kink at
  ρ = ρ′ stalled Gauss quadrature at 7.5e-5 against a 1e-4 tolerance. That was a quadrature artifact; the identity
  holds. Mutation "conjugated weights" now fails the check.

### 4.2 Proximity: leading-order line-dipole correction (derived here; `_prox_terms`, `prox_factor`)
- **Why it is needed.** At HF a wire in the transverse field of parallel currents (other wires, its own image)
  carries a line dipole that lowers L. T0020 bounded this without including it, and that bound (≈ 7–9e-3 for
  B3/B4/C1) did not meet 2e-3. The runner now includes the correction.
- **Size of the correction** (difference with it on/off; C0 is 6–7e-5):

  | Case | 5 MHz | 80 MHz |
  |---|---|---|
  | B3 L11 | 1.26e-3 | 1.61e-3 |
  | B4 | 0.92e-3 | 1.17e-3 |
  | C1 | 0.87e-3 | 1.16e-3 |

- **Derivation.**
  - Inside the wire, A_z = C J1(kρ)cos θ. Outside, (Gρ + D/ρ)cos θ. Continuity of A_z and ∂A_z/∂ρ at ρ = a gives
    D/(Ga²) = J2(ka)/J0(ka).
  - So the dipole relative to a perfect conductor is χ = −J2(ka)/J0(ka), with χ → j(a/δ)²/4 at DC and → 1 for
    a ≫ δ (both checked).
  - For a perfect conductor, the energy change per length in a transverse gradient |∇A| is
    ΔL′ = −(2πr²/μ0)|∇A/I|². Against a line current at distance p this gives −μ0/2π (r/p)², which agrees with the
    expansion of the exact two-wire line (μ0/π)arccosh(p/2r) [RWV] and of the wire over a plane.
- **In the PEEC model, only parallel segments couple.** The drive is therefore the transverse gradient of the
  axial vector potential of all *parallel* segments and of all images:
  ΔZ_seg[t,u] = −jωχ_s(2πr_s²/μ0)∫_s g_t·g_u dz.
- **[F] Check.** Against the exact PEC two-wire line (p = 1.5 mm, r = 0.15 mm) the dipole term agrees to 1.8e-2 of
  itself, inside the next-multipole estimate 1.5(r/p)² = 1.5e-2 plus end effects.

### 4.2a Finite cross-section of mutual terms (T0041 attempt 3; reviews T0051/T0052, finding 1)
- **[F] Error in attempt 2.** Every wire–wire and wire–image mutual used the filament formula at the centre
  distance. The kernel's end terms are not harmonic in the transverse plane, so averaging over two finite cross-
  sections shifts it. This is the same mechanism as the ⟨d⟩ correction of §4.1, but it had been applied to self
  terms only. B3's M12 was 3.9e-4 (DC) and 7.8e-4 (thin skin) too low, against a stated bound of ≤ 1e-6.
  C1's image terms (≈ 2e-4 of L) and B4 (≈ 2e-4) were covered only by unused slack. Reproduced first-hand by the
  founder check `b3_mutual_exact.py` before the fix (error 3.89e-4 / 7.80e-4, bound 8.9e-11 / 1.05e-6).
- **Derivation (here).**
  - Each fil_mutual term g(u, d) = u asinh(u/d) − √(u² + d²) has the 2-D transverse Laplacian
    g'' + g'/d = −1/√(u² + d²). From g' = −√(u²+d²)/d and g'' = u²/(d²√(u²+d²)). For equal aligned segments
    this gives μ0/2π(1/d − 1/√(l²+d²)), as both reviewers found.
  - The current distributions are axisymmetric. The relative position w = v − u of a source point and a receiver
    point (unconjugated reaction weights) therefore has an isotropic distribution, and the average is a weighted
    circle mean of M about the centre offset D.
  - Circle means obey Darboux's equation, (1/t)(t m')' = mean of ΔM over the circle. Integrating twice gives
    m(t) = M(D) + (t²/4)ΔM(D) + R(t), with |R(t)| ≤ (t⁴/64)·sup|Δ²M| over the disk of radius t (the kernel of
    each integration is positive).
  - Hence ⟨M⟩ = M(D) + (⟨|w|²⟩/4)ΔM(D) + R. Here ⟨|w|²⟩ = s2_a + s2_b with s2 = ∫Jρ²dA/I (complex Bessel profile;
    r²/2 uniform, → r² surface). The bound is |R| ≤ (⟨|w|⁴⟩_abs/64)·sup_{|x| ≥ D − r_a − r_b}|Δ²M|.
  - ⟨|w|⁴⟩_abs ≤ a4_a a0_b + a0_a a4_b + 4 a2_a a2_b, with a_n = ∫|J|ρⁿdA/|I|.
  - Δ²g = (2u² − ρ²)/(u²+ρ²)^{5/2}, bounded termwise by max(2u²/(u²+ρ_lo²)^{5/2}, 1/(u²+ρ_lo²)^{3/2}).
  - The runner adds the first-order term to every parallel wire–wire pair and every wire–image pair
    (`_pair_cross_section`). The bound is the stated term (d) of §4.3. It is **rigorous** given the modeled
    profiles: no [I] factor and no free constant.
- **[F] Independent check** (`closed_forms_independent_check`, through the assembly with proximity off). The brute-
  force average of the filament kernel over both Bessel-profile cross-sections uses Gauss panels (8 nodes, not the
  moments' 12) and the trapezoid rule in both angles (20 × 20). It uses no moments and no Laplacians.

  | Quantity | Shift being corrected | Closed form − brute force | Stated (d) |
  |---|---|---|---|
  | B3 M12 @ 100 Hz | 3.9e-4 | 2.6e-15 H | 5.5e-15 H |
  | B3 M12 @ 80 MHz | 7.3e-4 | 8.4e-15 H | 3.0e-14 H |
  | C1 image term @ 20 MHz | 5.6e-4 (of the image term) | 3.7e-15 H | 1.0e-14 H |

  Mutations caught (all by this check): no cross-section term; sign flipped; one wire's moment only; uniform-current
  moment at every frequency; image pairs without the term in the assembly. The last one was missed by a first
  version that checked the pair function directly; the check now runs through `_assemble`.
- **Truncation order: first-order term only.** [F] Adding the second-order term (⟨|w|⁴⟩/64)Δ²M would reduce B3 M12's
  DC error to < 1e-8. But E001's 2 % criterion does not need it, and the bound of the remaining error would drop to
  ~3e-7. **Disclosure:** at 10 GHz the founder's `b3_mutual_exact.py` reference is the δ → 0, proximity-free limit.
  The runner uses the finite-δ profile (δ/r = 5.5e-3) and includes the proximity dipole. These two physical terms
  account for 5.6e-6 of the runner-vs-reference difference of 9.0e-6: 1.3e-6 dipole (computed) and 4.3e-6
  finite δ (by subtraction; predicted (δ/r)·shift = 4.2e-6). The second-order mean-value term is 3.5e-6. A second-order closed form with its tighter rigorous bound would therefore
  fail that check without being wrong. I kept the first-order form for simplicity. Its rigorous bound (1.5e-5)
  holds against the finite-δ truth and also covers the reference's simplifications. The margin is 1.7×.

### 4.3 Stated residual model error per class (`residual_model_error`, per compared quantity)
Every term is weighted through the case's excitation vectors (segment currents per unit port current; for ties,
the actual branch split), then divided by |L| of the compared quantity.
- **(a) Wire self term, every wire segment** (B1–B4, C0, C1): ≤ μ0/2π [r²/l + (2r)⁶/(48l⁵)] per segment.
  - The first term is the second-order redistribution error of the stationary reaction [RU]. [I] The perturbation
    potential varies by ≤ r/2 across the section, and the stiffness of a zero-net-current radial mode is
    ≥ l/4 in μ0/2π units, so the error is ≤ (r/2)²/(l/4).
  - The second term is twice the first omitted series term at d = 2r.
  - [F] The tube PEEC shows the true residual is 15× (l = 1.5 mm), 20× (5 mm) and 35–120× (10 mm) smaller than
    this. It vanishes in both limits: at DC the resistance fixes a uniform current, and at thin skin the current is
    pinned to the surface.
  - B1 is the only term for its case: 5.4–5.7e-5. The B2 legs (l = 1.5 mm) dominate B2, B3 L11 and B4 (≈ 8.6e-4).
- **(b) Proximity, every wire segment receiving a dipole:** ≤ (2.5(r/p)² + 8r/l) × |dipole correction| per
  receiving segment.
  - 1.5(r/p)² is the next multipole (from the exact arccosh, ratio 3/(8x²)), and (r/p)² is axial non-locality.
  - 8r/l is the end regions: 2r at each end, doubled [I] for a non-uniform density.
  - Adds ≈ 1e-5 (C0), 3e-4 (B3 L11) and 2e-4 (C1).
  - M12 of B3 has no self terms and a dipole cross term of ≤ 1.2e-6 relative; its (b) allowance is ≤ 1e-6.
- **(c) Plane (C1):** (δ/2h)² + tol_truncation.
  - Wheeler's recession is the real part of the first-order complex image. [F] Against Carson's exact half-space
    integral [C] (`wheeler_recession_independent`) the per-length error is 0.50 (δ/2h)²·μ0/2π at
    0.5/5/20/80 MHz, as the expansion predicts (−½(δ/2h)² from ln(1 + δ/2h)).
  - L per length of C1 is 2.4·μ0/2π, so the relative error is < (δ/2h)² ≤ 2.2e-4.
  - The truncation allowance is 1e-3: `plane_truncation_bound` certifies a 2-D estimate of 1.4e-5, and [I] 3-D
    truncation is smaller.
- **(d) Finite cross-section of mutuals (§4.2a), every parallel wire–wire and wire–image pair:** the rigorous
  Taylor remainder of the first-order mean-value term, weighted by |u_i[k]|·|u_j[l]|. Sizes: 2.0e-6 to 1.2e-5 (B3
  M12), 1.6–3.1e-6 (B4), 0.4–0.9e-6 (C1), ≤ 2e-8 elsewhere.
- **Bars (A1–A4):** 1e-4. Hoer–Love is exact for uniform current, and `regime_valid` bounds the 100 Hz skin
  deficit at 2.8e-5 of the internal part.

**Per-class bound, term by term ([F] printed from `residual_model_error` and its terms; relative to |L|).**
"prox" is the size of the proximity correction itself, shown to give a sense of term (b).

| Case, quantity | (a) self | (b) proximity [prox] | (c) plane | (d) cross-section [shift corrected] | stated total | evidence for the dominant term |
|---|---|---|---|---|---|---|
| B1 L11, 100 Hz–80 MHz | 5.4–5.7e-5 | 0 [0] | — | 0 [0] | 5.4–5.7e-5 | tube PEEC, ≥ 35× margin |
| B2 L11 | 8.6–9.1e-4 | ≤ 1.9e-7 | — | ≤ 1.7e-8 [0.6–1.3e-6] | 8.6–9.1e-4 | tube PEEC at l = 1.5 mm, 15× margin |
| B3 L11 (100 Hz / 5–80 MHz) | 8.6–9.1e-4 | 3.1e-8 / 3.0–3.7e-4 [1.3–1.6e-3] | — | ≤ 1.7e-8 [0.6–1.3e-6] | 8.6e-4 / 1.2–1.3e-3 | (a) tube PEEC; (b) two-wire line [I] |
| B3 M12 | 0 | ≤ 1e-6 [≤ 1.2e-6] | — | 2.0e-6–1.1e-5 [3.9–7.3e-4] | 2.0e-6–1.2e-5 | (d) rigorous; brute-force average |
| B4 L11 (tied) | 6.5–6.6e-4 | 2.2–2.7e-4 [0.96–1.17e-3] | — | 1.6–3.1e-6 [1.6–2.0e-4] | 8.7–9.4e-4 | as B3; tie formula exact (tied_branch_independent) |
| C0 L11 | 1.4–1.5e-4 | 7–9e-6 [5.9–7.2e-5] | — | ≤ 2e-8 [2.2–2.8e-5] | 1.5e-4 | tube PEEC |
| C1 L11 | 1.8–1.9e-4 | 1.5–2.0e-4 [0.90–1.16e-3] | 1.0–1.2e-3 | 0.4–0.9e-6 [1.7–2.2e-4] | 1.4–1.6e-3 | (c) Carson check + truncation allowance |

- **Why B3 M12's proximity term is so small.** With port 1 open, the dipole that wire 2's field induces in wire 1
  has zero average over wire 1. So it adds no EMF to wire 1, and by reciprocity the same holds the other way. What
  remains are third-body cross terms (the far leg of the same staple), whose fields are nearly orthogonal at the
  receiving leg. The n = 0 cross-section shift is a different mechanism and is not small (§4.2a). Attempt 2's
  paragraph here argued from the dipole alone; that was the error.
- **Robustness of "≤ 2e-3" to its weakest link, the [I] proximity-accuracy factor of term (b).** [F] By arithmetic
  on the table: the 2e-3 conclusion survives a dipole correction wrong by up to 67 % (B3 L11 at 80 MHz), 66 % (C1
  at 5 MHz) or 114 % (B4). The stated (b) allowance is 17–23 % of the correction.
- **B1 vs exact references.** [F] `b1_exact_limits.py` on main (fixed by the founder with epsabs = 0, commit
  b0cafdb) passes: error 1.1e-9 at 100 Hz and 1.32e-5 at 10 GHz, against bounds of 5.4e-5 and 5.75e-5. The 10 GHz
  residual is the finite-δ physics the δ → 0 reference omits: predicted Re Δ⟨d⟩ = −(2/π)δ·μ0/2π = −0.104 pH;
  observed −0.103 pH.
- **B3 M12 vs exact references.** [F] `b3_mutual_exact.py` passes: 9.8e-7 at 100 Hz (bound 2.0e-6) and 9.0e-6 at
  10 GHz (bound 1.5e-5); see §4.2a for the decomposition of the 10 GHz difference.

### 4.4 Refinement rule and discretization uncertainty (reviews T0030, T0052; `remaining_discretization_error`)
- **Rule.** Levels k0 = 1, 2, … are solved, at least `refinement_min_levels` = 4 and at most `refinement_max` = 5.
  For every L (all solved frequencies and compared entries) the remaining error is estimated from the sequence of
  changes d_k = |L_k − L_{k−1}|. The contract fixes a constant refinement ratio (§3), so in the asymptotic range
  the changes contract geometrically with a constant observed ratio ρ = d_k/d_{k−1}.
  - **Steady ratio (≥ 4 levels).** If the last observed ratio does not exceed the previous one beyond what the
    noise floor can produce, use the geometric tail 1.25·base·ρ/(1−ρ). Here ρ = max(last two ratios, 0.5),
    base = max(d_last, 0.5·d_prev) (the small-step guard from attempt 2), and 1.25 is Roache's three-grid factor
    [ROA].
  - **Decelerating ratio (review T0052).** If the ratio grows, the geometric asymptotic range is not established.
    Additive refinement (error ∝ k^−p) and a slower mode emerging both look like this. Then the estimate is the
    larger of two tails, both with Roache's factor 3 for an unverified range:
    - the geometric tail;
    - the additive-refinement tail, from L_k = L∞ + C k^−p fitted exactly to the last three levels (k = 1-based
      position; ∞ if the data imply p ≤ 0).
  - **3 levels:** geometric tail with factor 3, because one ratio cannot be checked. **2 levels:** ρ = 0.9 and
    factor 3 (27× the change). **1 level:** ∞. **ρ ≥ 1:** ∞. The rule never decides convergence on fewer than
    4 levels.
  - **Noise floor.** A change ≤ 2·`solver_err_budget`·|L| is what two levels can differ by from the solver alone
    (§3). It gives no evidence of slow contraction, and the deceleration test allows for it.
- **Stopping.** The rule stops when every remaining error is < conv_tol = 1 %, or at refinement_max.
  `disc_unc` = that estimate (relative).
- **[F] Checks.**
  - DoD `convergence_estimator.py` passes. Geometric ρ = 0.5/0.8/0.9: 1.25× the true remaining error. Algebraic
    p = 1: 3.0×; p = 2: 3.3×. Attempt 2 gave 0.42× for p = 1.
  - Scratch sweep, not tuned on the DoD. Algebraic (k + c)^−p with p ∈ {0.5, 1, 1.5, 2, 3},
    c ∈ {−0.5, 0, 0.5, 2} and 4 or 5 levels: the lowest estimate/true ratio is 2.06. Geometric ρ = 0.25: 7.5×
    (the ρ ≥ 0.5 floor). Two modes (0.3^k + 0.7^k): 3.4–4.0×.
  - Noise: 2 000 geometric sequences (ρ = 0.5) with ±1e-4 solver noise; none was falsely held unconverged at 1 %.
  - [I] Limits: no finite-sample rule bounds arbitrarily slow convergence. With p < 0.5 and an unlucky offset it
    can still underestimate. The constant-ratio contract and the `l2_constant_refinement_ratio` check are the
    primary defence; the deceleration test is the second.
  - Scratch plumbing test (T0041 attempt 3). A stand-in `moduleforge.solvers.l2` returns the closed form with
    Im Z × (1 + bias + 0.03·0.6^k), solver_tol 0, mesh_h = 2^−k. Run through `--smoke` and through full mode with
    the draft's config (32 compared values, 7 classes, all 15 sanity checks reported, status complete):
    - bias 0: converged at 4 levels, value 3.9e-3, interval [0, 0.0103];
    - bias 3 %: interval [0.029, 0.040], so A1 fails as it should;
    - solver_tol 1e-3 or missing: `l2_solver_tolerance` fails;
    - mesh_h = 1/k (additive): `l2_constant_refinement_ratio` fails.
- **Metric interval (review T0052).** `max_rel_err_vs_analytic` is recorded with **level 0.95** as an *estimated
  error band*: [max_i(err_i − u_i)⁺, max_i(err_i + u_i)], with u_i = remaining discretization estimate + stated
  residual model error.
  - Attempt 2 called it a deterministic bound at level 1.0. That overstated it: the discretization part is a
    GCI-type estimate, and Roache presents the 1.25-factor GCI as roughly a 95 % band ([ROA]; [I] from memory of
    Roache's 1998 book, not re-fetched). Some model terms ((a), (b)) are [I].
  - The level is nominal. It is not a sampling CI, because the cases are deterministic.
  - Acceptance A1 reads the point value.

### 4.5 Sanity checks (each can fail; each separates "experiment broken" from "L2 wrong")
Analytic checks, run on every mode including `--analytic-only`:
1. `closed_forms_published_values`: Kelvin functions, Grover GMDs, Z_int limits, mean-distance limits,
   normalisation, and the χ limits.
2. `closed_forms_independent_check`: Hoer–Love vs 6-D Gauss–Legendre (9e-15, tolerance `tol_independent` = 1e-6);
   filament vs quadrature; Bessel vs Hankel; Grover limits; Bessel Z_int vs reaction integral; wire self vs tube
   PEEC (§4.1); dipole vs two-wire line (§4.2).
3. `image_plane_independent` (new): the runner's 3-D image term vs a generic Neumann quadrature over the explicitly
   mirrored polyline. It covers the C1 loop at 5/20/80 MHz and an open U path at 20 MHz. Agreement 4e-16,
   tolerance 1e-6. Mutations "image sign" and "recess δ instead of δ/2" are caught.
4. `wheeler_recession_independent` (new): vs Carson (§4.3c), tolerance (δ/2h)². The worst ratio is 0.50. Both
   mutations above are caught.
5. `tied_branch_independent` (new): tie assembly vs the explicit parallel formula
   (Z11Z22 − Z12Z21)/(Z11 + Z22 − Z12 − Z21) for B4 and for an asymmetric pair (Ø0.25, span 7, height 1.2).
   Agreement 4e-16, tolerance 1e-10. Mutation "ignore branch mutual" is caught.
6. `analytic_length_scaling`.
7. `regime_valid`.
8. `plane_truncation_bound`.

`closed_forms_independent_check` also contains the cross-section brute-force comparison (§4.2a), and
`image_plane_independent` and `wheeler_recession_independent` now compare filament-axis terms (`xsec=False`), so
they keep testing the image geometry and the recession only.

**[F] Mutation record (T0041 attempts 2 and 3, scratch script; each mutation applied to a copy of the runner source).**
The unmutated runner passes all 8 analytic checks.

| Mutation | Checks that fail |
|---|---|
| horizontal image current not reversed | image_plane_independent, wheeler_recession_independent |
| recess δ instead of δ/2 | image_plane_independent, wheeler_recession_independent |
| no recession (PEC at the surface) | image_plane_independent, wheeler_recession_independent |
| tie assembly ignores the branch mutual | tied_branch_independent |
| T0020 filament-at-r self term (no mean-distance correction) | closed_forms_independent_check (tube PEEC) |
| moments from the uniform profile at every f | closed_forms_published_values, closed_forms_independent_check |
| conjugated reaction weights | closed_forms_independent_check |
| proximity correction sign flipped | closed_forms_independent_check (two-wire line) |
| no cross-section term in mutuals (attempt 2's model) | closed_forms_independent_check (cross-section average) |
| cross-section term sign flipped / one wire's moment only | closed_forms_independent_check (cross-section average) |
| uniform-current moment at every frequency | closed_forms_independent_check (cross-section average, 80/20 MHz) |
| image pairs without the cross-section term | closed_forms_independent_check (C1 image term) |
| attempt-2 refinement estimator | DoD convergence_estimator.py (algebraic p = 1: 0.42× true) |

L2 checks:
9. `l2_converged` (§4.4).
10. `l2_solver_tolerance` (new, §3).
11. `l2_constant_refinement_ratio` (new in attempt 3, §3).
12. `l2_one_mesh_per_solve` (new, §3).
13. `reciprocity`.
14. `l_monotone_in_frequency`.
15. `length_scaling`.

**Coverage.** `--smoke` runs A1, A3, B2, B3, B4, C0 and C1, which covers all 7 geometry classes. It uses 20 MHz
(bars compared at 100 Hz and also solved at 20 MHz) and the rule's minimum of 4 levels.

**Hygiene.**
- Every config key is read by the runner, and the draft's keys equal `DEFAULT_CFG`'s.
- `cases` filters `build_cases`.
- `tol_independent` (now 1e-6; it was unused, so no check is weakened) governs the numerical-quadrature
  comparisons.
- `solver_err_budget` is new. Attempt 3 adds `refinement_min_levels`, `refinement_ratio_min` and
  `refinement_ratio_spread`, all read by the runner.
- **[F] Number literals (T0041 attempt 2; neither review caught this).** mfos reads specs with PyYAML
  (`store.read_yaml` → `yaml.safe_load`), which follows YAML 1.1 and parses `5.0e6`, `2.0e7`, `8.0e7`, `5.8e7` and
  `3.77e7` (no exponent sign) as **strings**. Through `MFOS_SPEC_JSON` the registered run would have received
  `freqs_hf_hz = ['5.0e6', '2.0e7', '8.0e7']`. Reproduced with a stand-in L2: the full run ended with
  status `error` (`TypeError` at the first ω = 2πf). `mfos register` would have frozen the strings into the spec.
  - Fix: the draft writes `5.0e+6` etc.
  - The runner's `checked_config` type-checks every key against `DEFAULT_CFG` and raises on a mismatch.
  - [F] The parsed draft config now equals `DEFAULT_CFG` in keys, values and types.
- `l2_one_mesh_per_solve` checks the adapter's self-report: a single integer `meta['n_filaments']` per call.
  [I] It is weak on its own; the physical consequence is tested by `l_monotone_in_frequency`.

**What would prove L2 wrong:** an error > 2 % on any case; non-convergence; a reciprocity, scaling or
monotonicity violation; an unreported or too loose solver tolerance; a non-constant refinement ratio.

**Coverage gaps** [I]:
- Rectangular bars at HF have no closed form. They are covered only by convergence, monotonicity and the
  shared filament machinery.
- Inclined legs are not covered.
- Vertical wires over a plane are not supported: `_pair_mutual` raises for a leg collinear with its image.
- Galvanic plane contacts and bar–wire junctions are not tested.

**Not addressed here (T0029 finding 2, out of this packet's scope).** `mfos register` hashes only the YAML, so
geometry, tolerances and bounds in the runner are not frozen by registration. Recommendation: have registration
hash the runner, or record its sha256 in the spec (tools/mfos is protected).

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
- **[RU]** V. H. Rumsey, "Reaction concept in electromagnetic theory", Phys. Rev. 94(6):1483–1491 (1954).
- **[C]** J. R. Carson, "Wave propagation in overhead wires with ground return", Bell Syst. Tech. J. 5:539–554 (1926).
- **[ROA]** P. J. Roache, "Perspective: a method for uniform reporting of grid refinement studies", J. Fluids Eng.
  116(3):405–413 (1994): safety factor 1.25 (≥ 3 grids), 3 (2 grids).
- **[MW]** E. W. Weisstein, "Disk Line Picking", MathWorld: mean distance 128r/(45π).
- Derived here, verified by self-checks (§4.1–4.2): the coaxial-circle mean distance via E(m); χ = −J2(ka)/J0(ka).
- **Mean-value expansion with remainder (§4.2a):** Darboux's equation for spherical (here circular) means,
  R. Courant & D. Hilbert, *Methods of Mathematical Physics* vol. II (1962), ch. VI; the series form is Pizzetti's
  formula (P. Pizzetti, 1909). [I] Citation from memory. The remainder bound is derived in §4.2a and checked by the
  brute-force average.
- **[AS] 9.1.30:** (1/z d/dz)^k [z^ν J_ν(z)] = z^(ν−k) J_(ν−k)(z); with k = 1, ν = 1 it gives the cumulative current
  of the Bessel profile (§4.1).
- [I] Bibliographic details, including the T0041 additions, are from memory of the standard references and were
  not re-fetched. Every formula is verified numerically by the self-checks above, independently of the citation.

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
5. ~~Fix `b1_exact_limits.py`~~ Done by the founder (main b0cafdb); the runner passes it (§4.3).
6. Registration hashes only the YAML (T0029 finding 2). Hash the runner too, or record its sha256 in the spec
   (tools/mfos is protected). Until then, E001's geometry, tolerances and bounds in the runner are not frozen.
7. [I] PyYAML's YAML 1.1 floats can bite any spec. A spec-level type check in `mfos exp check` would catch
   `5.0e6`-style strings for every experiment, not only E001.
8. T0022 must report κ_est in `solver_tol` and `mesh_h` per call, and use a constant refinement ratio (§3).
   [I] At the 100 Hz cases this most likely means a direct LU of the uncompressed system.
9. `b3_mutual_exact.py` at 10 GHz uses the δ → 0, proximity-free limit as "exact". It passes, but the runner-vs-
   reference difference there is mostly physics the reference omits (§4.2a). If the founder wants a tighter M12
   bound (second-order term, ~3e-7), the reference needs the finite-δ profile and the dipole term.
