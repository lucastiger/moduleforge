# ModuleForge infrastructure: measured requirements and the recommended setup

**Version 1.1 · 2026-09-28 · supersedes the deployment parts of `docs/ARCHITECTURE.md` (§3.6, §20)**

> **Revision 1.1 — fixes from the first real setup on a MacBook Air M5.**
> (1) `scripts/provision_compute.sh` could not build FastHenry with Apple's clang: clang ≥ 16 rejects
> the solver's 1990s C by default, and the script hid the compiler output. It now builds with
> compatibility flags on clang and gcc, prints the log on failure, and self-tests the binary against
> a closed-form inductance. (2) The guard hook denied read-only agents' scratch writes to `/tmp`,
> because on macOS `/tmp` is a symlink to `/private/tmp`; the bootstrap test caught it. (3) Bootstrap
> now reports the step at which it stopped. (4) `.python-version` pins Python 3.12, so uv no longer
> builds the environment on whichever Python (e.g. conda's) comes first on PATH. If you ran version
> 1.0, follow "Recovering from a failed version 1.0 setup" in §12.

This report audits the earlier recommendation (a persistent 16–32 vCPU / 64 GB Ubuntu VM) against
measurements instead of intuition. Every number marked *measured* was produced by the scripts in
`benchmarks/infra/` on a deliberately weak machine: **1 vCPU (Intel Xeon, 2.1 GHz) and ~3 GB RAM**.
Anything that runs comfortably there runs comfortably on an M5. Where the report extrapolates to the
MacBook Air M5 it says so, and §13 lists the benchmarks that replace each extrapolation with a
measurement on your machine.

---

## 1. Executive answer

**Yes — the MacBook Air M5 (16 GB, ~100 GB free) can run the entire agentic framework and the
ModuleForge MVP experiments for the first several months.** The expensive always-on server was an
artifact of two errors: treating the agents' resource needs as if they were the simulations' needs,
and overestimating the reference-solver workload by roughly an order of magnitude.

* **The agent framework is nearly free locally.** Model inference runs on Anthropic's servers. A Claude
  Code process starts at ~220 MB (*measured*) and should be budgeted at ~1 GiB as sessions grow
  (Anthropic's hosting guidance). The orchestrator peaks at 35 MB and used 0.28 s of CPU for an entire
  objective lifecycle (*measured*).
* **The MVP science is laptop-sized.** A validated reference-grade FastHenry solve of a half-bridge
  commutation loop takes 18–103 s and 0.2–0.55 GB (*measured*); an L1 evaluation takes 15 ms at 400
  filaments (*measured*); a 3-million-unknown 3D thermal solve takes 26 s and 2.1 GB (*measured*).
* **Only large sweeps need more.** Thousands of reference solves, transient thermal-impedance
  campaigns, or very large 3D meshes go to **ephemeral cloud VMs rented by the hour**, launched per
  experiment by `scripts/burst.sh` and deleted automatically.

**Recommended architecture:** MacBook Air as control plane and default compute, plus ephemeral burst
VMs for experiments above 6 estimated CPU-hours. No persistent VM until one of three triggers (§14).
Expected infrastructure cost for month 1: **$0**; with occasional bursts: **~€10–25/month**.

---

## 2. Audit of the previous recommendation

| Element of the old recommendation | Verdict | Why |
|---|---|---|
| 16–32 vCPU | **Over-engineered** | Agents use essentially no local CPU. The science needs cores only for sweeps, which are bursty; paying for 32 idle cores 24/7 buys nothing. |
| 64 GB RAM | **Over-engineered** | The largest planned MVP job measured here peaks at ~2 GB. 64 GB was sized for imagined 10⁷-unknown meshes. |
| 200 GB SSD | Convenient default | Real usage is ~10–30 GB in the first months (§9). |
| Ubuntu 24.04 | Convenient default | No MVP dependency requires Linux (§5). Linux is right for *burst VMs*, because that is what cheap ephemeral machines run. |
| Persistent cloud VM ("forge box") | **Deferrable** | Justified only for lid-closed 24/7 autonomy, customer-data isolation, or sustained heavy compute (§14). |
| systemd service | Convenient default | macOS has launchd; `scripts/com.moduleforge.mfos.plist` now provided. |
| "E002 ≈ 20 CPU-hours; O001 ≈ 45–60 CPU-hours" | **Overestimated ~5–10×** | Measured reference solves put E002 at ~3–5 sandbox-core-hours, ≈ 0.5–1 hour of wall time on the M5's 4 performance cores (§7). |

**What the agent framework actually requires:** ~1 GiB RAM per concurrent agent, tens of MB for the
orchestrator, ~40 ms per guarded tool call, a stable network connection, and a few GB of disk.
**What ModuleForge's science requires:** cores for L2 sweeps, RAM for large 3D FEM, and sustained
throughput that a fanless laptop cannot provide for many hours at a time. **The earlier
recommendation sized the first by the second.**

---

## 3. Minimum hardware (Tier A — technically works, not comfortable)

| | |
|---|---|
| CPU | 2 cores, x86-64 or ARM64 |
| RAM | 4 GB (Claude Code's documented minimum); 8 GB to also run L2 |
| Disk | 20 GB free |
| OS | macOS 13+ or Ubuntu 20.04+ |
| Policy | `concurrency.agents = 1`, `local_cpu_hours_max = 1` |

Limitations: one agent at a time; L2 limited to ~10k filaments and ~1M-unknown thermal meshes;
every batch experiment goes to burst compute; slow gates. It proves the framework runs; it is not a
place to work.

## 4. Recommended solo-founder hardware (Tier B) and heavy workloads (Tier C)

**Tier B is the machine you already own.**

| | |
|---|---|
| Machine | MacBook Air M5: 10-core CPU (4 performance + 6 efficiency), 16 GB unified memory |
| Disk | ≥ 60 GB free (you have ~100 GB) |
| OS | macOS (current) |
| Concurrency | 2 Claude agents + 1 experiment process using up to 4 worker processes |
| Local compute limit | experiments with `cpu_hours_est ≤ 6` run locally; larger ones go to burst |

**Memory budget on 16 GB** (estimates; B1 measures the agent part): macOS and background ~4–5 GB,
browser and editor ~2–4 GB, two agents 0.5–2 GB, orchestrator 0.04 GB, one experiment 0.3–2.5 GB
(four FastHenry workers at ≤ 0.6 GB each, or one 3M-unknown thermal solve at 2.1 GB). Total
≈ 9–14 GB — it fits, and macOS compresses memory before swapping. Rules: never run a 3D thermal mesh
above ~5M unknowns locally, and keep `concurrency.agents = 2`.

**Tier C — heavy autonomous workloads — is rented, not owned.**

| | |
|---|---|
| Typical burst VM | Hetzner CCX53: 32 dedicated vCPU, 128 GB RAM, 600 GB disk, Ubuntu 24.04, €0.855/hour |
| Mid-size burst | Hetzner CCX33: 8 dedicated vCPU, 32 GB RAM, €0.2219/hour |
| Parallelism | several VMs at once for sweeps (one experiment per VM) |
| GPU | **none** — see below |
| Workloads | L2 surrogate datasets (10³–10⁴ solves), transient thermal-impedance campaigns, 3D FEM above ~5M unknowns, L2-in-the-loop optimization audits |

**Why no GPU.** ModuleForge's physics runs in float64 (conventions skill). Apple's GPU backends for
JAX exclude float64 entirely (the jax-mps project lists it as unsupported on Metal; jax-metal appears
unmaintained), and consumer NVIDIA GPUs execute float64 at a small fraction of their float32 rate.
Only data-center GPUs (A100/H100 class) are fast in float64, and dense PEEC at our sizes is already
fast on CPU. Revisit GPUs when a float32-tolerant workload appears (e.g. training a surrogate model).

---

## 5. MacBook Air M5 compatibility

### 5.1 Component matrix

| Component | macOS arm64 status | How to install | Verified here |
|---|---|---|---|
| Claude Code | native (macOS 13+, ARM64) | `brew install --cask claude-code` | docs |
| Python 3.12/3.13, uv | native | `brew install python`; uv installer | — |
| numpy, scipy, jaxlib, shapely, gmsh, cadquery-ocp (STEP), klayout (GDS/DRC), ray, pyamg, duckdb | **native arm64 wheels on PyPI** | `uv add …` | *queried PyPI for `macosx_*_arm64` wheels, all present* |
| pyaedt | pure Python, but drives Ansys AEDT (x86 Windows/Linux + license) | only for L3 decks, at the customer | — |
| JAX CPU | native, float64 works | via jaxlib | *float64 L1 kernel measured (Linux)* |
| JAX on the Apple GPU | experimental, **no float64** | not used | docs |
| ngspice | native | `brew install ngspice` | *DPT measured (Linux)* |
| FastHenry | builds from C source with compatibility flags; MacPorts ships arm64 packages | `scripts/provision_compute.sh` (builds, then self-tests) | *built and self-tested with gcc 13 and clang 18; identical results* |
| FEniCSx (dolfinx) | native osx-arm64 conda-forge builds (0.11.0) | `conda install -c conda-forge fenics-dolfinx mpich` in its own env, only when an objective needs it | docs |
| OpenMPI / MPICH | native | conda-forge (with FEniCSx) or Homebrew | — |
| Ray | supports Apple Silicon; multi-node clusters untested | `uv add ray` | docs |
| Docker | Docker Desktop runs a Linux VM; arm64 images native, x86 images emulated | **not needed**; also incompatible with Claude Code's sandbox | docs |
| Linux VM (UTM/OrbStack) | works | **not needed**; would take 4–8 GB of 16 GB | — |

**No MVP dependency requires Linux or Rosetta.** The only x86-only software in the plan is Ansys
AEDT (Q3D/Icepak), which is L3 — it runs at the customer on their licenses, and ModuleForge only
generates the PyAEDT decks.

### 5.2 Apple-specific findings (and what the repository now does about them)

1. **`/usr/bin/python3` on macOS is 3.9** — it has no `tomllib`. Any Claude Code session whose hooks
   resolve `python3` to it makes the guard fail closed, denying *every* agent tool call (*reproduced
   with Python 3.9*). Launchd jobs get exactly that PATH. **Fixed:** the orchestrator puts its own
   Python 3.12 first on each agent's PATH (tested); the launchd plist sets PATH explicitly; bootstrap
   refuses to continue without Homebrew's `python3` for interactive sessions.
2. **Laptop sleep.** A closed lid suspends everything; after waking, wall-clock deadlines would have
   timed out every running agent. **Fixed:** the loop detects the gap and extends run deadlines
   (tested). `caffeinate -is` in the launchd job prevents idle sleep and, on power, system sleep; lid
   close still sleeps the machine — work simply pauses and resumes.
3. **QoS.** macOS runs `Background` launchd jobs on efficiency cores only. The plist uses
   `ProcessType = Standard`.
4. **Fanless thermals.** Short benchmarks show almost no penalty versus the actively cooled MacBook
   Pro, but multi-hour all-core loads will throttle. Unknown magnitude → benchmark B6; the
   `local_cpu_hours_max` threshold exists so long jobs leave the laptop.
5. **Legacy C.** FastHenry is K&R-era C. Apple clang (≥ 16) and gcc ≥ 14 reject it by default:
   implicit function declarations, `return;` in implicit-int functions and pointer mismatches are
   errors, and both compilers default to `-fno-common`. `-w` does not help because these are errors,
   not warnings. `provision_compute.sh` applies `-fcommon` and `-Wno-error=…` for each case through a
   compiler wrapper (so the `sparse/` sub-build gets them too), then self-tests the binary. Separately,
   FastHenry's `.units mm` mode returned inductance exactly 1000× too high in our build while resistance
   was correct, so all inputs use meters (validated: 5.704 nH vs 5.695 nH closed form for a
   10×1×1 mm bar).
6. **Cross-host floating point.** Accelerate (macOS) and OpenBLAS (Linux) give results differing in
   the last bits. Evidence already records the host; acceptance criteria use tolerances, never bitwise
   equality — keep it that way when comparing Mac and burst results.
7. **Security of autonomous agents on a personal machine.** Enable Claude Code's built-in sandbox
   (Seatbelt on macOS, nothing to install) after the canary passes (§12, step 9); it restricts writes
   to the working directory and network access to approved domains for every shell command.
8. **`/tmp` is a symlink.** macOS's `/tmp`, `/var` and `/etc` point into `/private`, and `$TMPDIR` is a
   per-user `/var/folders/…/T`. Anything comparing resolved paths to temp-directory names must accept
   all forms; the guard hook now does, with path-boundary matching.
9. **Several Pythons.** With conda/miniforge, its `python` is usually first on PATH. That is fine for
   the hooks (any Python ≥ 3.11 works), but the project environment should not depend on it:
   `.python-version` pins 3.12 and uv downloads its own copy if none is present.

---

## 6. Claude Code resource usage

```text
Agent work                                        Engineering work
MacBook ─ claude process (~0.2–1 GiB, idle CPU)   MacBook (or burst VM)
   │  prompts, tool results  ▲                       │
   ▼  (HTTPS)                │ tokens                ├─ Python/JAX L1 evaluations
Anthropic infrastructure: model inference            ├─ FastHenry / FEM / ngspice
   (subscription usage or API billing)               └─ all CPU and RAM is yours
```

| Question | Answer |
|---|---|
| Does Claude Code need a powerful CPU? | No. It is a native client; inference is remote. Local CPU is spent only on the tools it runs (search, tests, your simulations). |
| Local or remote inference? | Remote, always. An internet connection is required. |
| What does local RAM affect? | How many sessions and tool processes run at once. Each session holds its conversation state and spawns shells. |
| RAM per process | *Measured:* `claude --version` 38 MB; a full `claude -p` start 215–230 MB. Anthropic's hosting guidance: plan ~1 GiB per agent, growing with session length. |
| Several sessions | Linear: N × (0.25–1 GiB). Two concurrent agents are comfortable on 16 GB; three to four are possible; B1 measures it. |
| Subagents | Run inside the parent session: little extra RAM, but separate context windows cost tokens. |
| Agent teams | Separate Claude Code instances: N × RAM *and* roughly proportional token usage (Anthropic cites ~7× a normal session in plan mode). Mostly a usage cost, secondarily RAM. Still not recommended. |
| Background agents/tasks | Their tools execute locally, so they use local resources exactly like foreground work. |
| Agent SDK | Spawns the same `claude` CLI as a subprocess: same footprint as the CLI (Anthropic suggests 1 GiB RAM, 5 GiB disk, 1 CPU per agent as a starting point). |
| Does the custom orchestrator change requirements? | No: 35 MB peak, 0.28 s CPU per objective lifecycle, 121 ms per tick including git (*measured*). Hooks add ~39 ms per guarded tool call (*measured*). |

**Subscription versus API does not change hardware at all.** It changes what limits concurrency: on a
subscription, usage windows cap how many agent-hours you get long before 16 GB of RAM does. The
orchestrator already treats rate/usage-limit errors as a 30-minute pause that does not count against
the task. The practical ceiling on a subscription is about two concurrent agents — the same number
the Mac's memory budget suggests.

---

## 7. ModuleForge simulation resource usage

### 7.1 Measurements (1 vCPU Xeon 2.1 GHz sandbox; M5 performance core ≈ 2–2.5× faster, *estimate*)

| Workload | Size | Time | Peak RAM | Notes |
|---|---|---|---|---|
| L1 PEEC evaluation (fill + complex solve, float64) | 200 / 400 / 800 / 1600 filaments | 3 / 15 / 70 / 380 ms | 0.3–0.55 GB per process | JAX compile 0.4–0.8 s per shape; NumPy and JAX equal speed on CPU |
| L1 sustained throughput | 400 filaments, 1 worker | 3,606 evaluations/min | — | embarrassingly parallel |
| L2 FastHenry, half-bridge loop, no plane | 4.1k filaments | 2.9 s | 64 MB | L = 9.68 nH |
| L2 FastHenry, with backside-copper plane | 11.4k / 21.3k filaments | 18 s / 103 s | 187 / 541 MB | L = 7.670 / 7.675 nH (converged to 0.1%) |
| L2 FastHenry, plane 4 filaments thick | 33.4k filaments | 67 s | 474 MB | L = 7.52 nH (plane thickness resolution matters ~2%) |
| 3D steady thermal (AMG-CG) | 0.29M / 1.44M / 3.0M unknowns | 2.3 / 11.6 / 26 s | 2.1 GB at 3M | energy balance 1.0000; FEniCSx of similar size behaves comparably |
| ngspice double-pulse test | 14 µs transient, SiC models, 8 nH loop | 0.17 s | 19 MB | 69 V turn-off overshoot |
| Output per reference solve | — | — | 24 KB on disk | — |

### 7.2 Resource profile of each workload

| Workload | CPU | RAM | GPU | Parallelism | On the Mac? |
|---|---|---|---|---|---|
| Claude Code sessions | ~0 | 0.25–1 GiB each | no | 2 concurrent | yes |
| Orchestrator, git, hooks | ~0 | 35 MB | no | — | yes |
| Geometry generation, DRC | ms per layout | < 0.3 GB | no | high | yes |
| L1 PEEC | 3–70 ms per evaluation | < 0.6 GB/process | no | high | yes |
| L1 thermal (spectral/layered Green's function) | ms per evaluation (*estimate*) | small | no | high | yes |
| Optimization over L1 (10⁴–10⁵ evaluations) | minutes | low | no | high | yes |
| L2 PEEC (FastHenry) | 20 s–2 min per solve | 0.2–0.6 GB | no | one solve per core | yes, batches ≤ 6 CPU-h |
| L2 steady thermal FEM | 10–30 s at 1–3M unknowns | 1–2 GB | no | per solve | yes, up to ~5M unknowns |
| L2 transient thermal impedance | minutes per layout (*estimate*) | 1–2 GB | no | per layout | campaigns → burst |
| ngspice DPT | 0.2 s | 20 MB | no | high | yes |
| CAD generation (STEP, DXF) | seconds per layout (*estimate*) | < 0.5 GB | no | high | yes |
| Evidence queries (DuckDB) | trivial | trivial | no | — | yes |
| L2 surrogate datasets (10³–10⁴ solves) | 25–250 core-hours | 0.6 GB/solve | no | high | **burst** |

### 7.3 What this means for the actual objectives

* **O001 E001** (reference vs closed forms, ~80 small solves): ~15 sandbox-core-minutes → minutes on
  the Mac. Local.
* **O001 E002** (60 layouts × 3 frequencies × reference solve at 20–35k filaments): ≈ 60 × 3 × 85 s
  ≈ 4.3 sandbox-core-hours ≈ 1.7–2.1 M5 core-hours ≈ **30–40 minutes on 4 performance cores**.
  Caveat: real layouts with more dies and wires can have 2–3× more trace filaments, and FastHenry's
  cost grew steeply with trace resolution (11k → 21k filaments took 5.6× longer). Worst case E002 is
  a few hours locally, or about one hour and ~€1–3 on a CCX53. The spec's `cpu_hours_est` decides
  automatically (§8); B3 on the first real layouts removes the uncertainty.
* **O001 E003** (L1 timing): trivial. A6 (≤ 50 ms median) looks reachable at ~600–800 filaments on an
  M5 core, based on the 70 ms measured at 800 filaments on the sandbox core.
* **O003-style optimization headroom** (population search over L1 plus L2 audits of the best ~50
  designs): minutes of L1, 1–2 hours of L2 on 4 cores. Local, or a short burst.
* **Surrogate datasets and transient-thermal campaigns**: burst.

---

## 8. Local vs cloud architecture

```text
MacBook Air M5  (control plane + default compute)
 ├─ Claude Code agents (2), orchestrator (launchd), hooks
 ├─ Git repository = project state; GitHub remote (push each tick)
 ├─ L0/L1, optimizers, ngspice, small L2 (experiments with cpu_hours_est ≤ 6)
 └─ scripts/burst.sh E0xx  ──►  ephemeral Hetzner VM (Ubuntu 24.04, 8–32 dedicated vCPU)
                                 ├─ receives `git bundle` of main (no credentials leave the Mac)
                                 ├─ provisions solvers, runs `mfos exp run E0xx`
                                 ├─ results copied back to experiments/results/E0xx/
                                 └─ VM deleted on every exit path (trap)
```

How it works in the loop (implemented and tested):

1. A registered experiment's `cpu_hours_est` exceeds `[compute] local_cpu_hours_max` (6). The
   orchestrator does not run it locally; it opens an inbox item: *"E002 needs burst compute
   (~20 CPU-h): run `scripts/burst.sh E002`"*, and marks the task as waiting.
2. You run the command (or run it locally anyway with `uv run mfos exp run E002`).
3. Results arrive with full provenance (commit, spec hash, sealed seed, host). The orchestrator marks
   the task done, closes the inbox item, and evaluates — exactly as for a local run.

Why this shape: the orchestrator's value is continuity and state, which a laptop provides when it is
awake; compute is the only thing that benefits from scale, and it scales best when rented per job.
Moving orchestration to a VM is a separate decision with separate triggers (§14).

---

## 9. Storage architecture

### 9.1 Budget for the first months

| Item | Size | Category | Source |
|---|---|---|---|
| Xcode Command Line Tools, Homebrew and formulae | a few GB | tooling | estimate |
| Claude Code | 231 MB per installed version | tooling | *measured*; `brew cleanup` removes old versions |
| Claude Code transcripts (`~/.claude/projects`) | MB–low GB | cache | pruned by Claude Code after 30 days by default |
| uv package cache | ~0.6 GB | cache | *measured* |
| Project environment (numpy, scipy, jax, pyamg, …) | ~0.6 GB | environment | *measured* |
| Per-worktree environments | near zero extra on APFS | environment | uv links from its cache (copy-on-write on macOS) |
| FEniCSx conda environment | a few GB | environment | only when an objective needs FEM |
| Repository `.git` | ~1.4 MB after one objective; tens of MB in months | Git-tracked | *measured* |
| Task worktrees | source only (MB each); removed after merge | temporary | — |
| Experiment results (`result.json`, `run.json`) | KB–MB per run | Git-tracked | — |
| L2 FastHenry run outputs | 24 KB per solve | artifact | *measured* |
| FEM fields and meshes (XDMF/HDF5) | 0.1–1 GB each at millions of unknowns | artifact | estimate; **not saved by default** |
| Docker images | 0 | — | Docker is not used |

Expected use: **~10–15 GB in month 1, ~20–30 GB by month 3.** 100 GB free is sufficient.

### 9.2 Categories and retention

* **Git-tracked source:** code, specs, objectives, `result.json`, reports. Small forever.
* **Large artifacts:** written only through `run.artifact()` into the content-addressed store
  (`.mfos/artifacts/`). Keep artifacts referenced by a claim or by one of an objective's last two
  evaluations; delete others after 30 days. Copy claim-referenced artifacts to Cloudflare R2
  (10 GB free tier, then $0.015/GB-month, no egress fees).
* **Caches:** `uv cache prune` and `brew cleanup` monthly; Claude transcripts self-prune.
* **Temporary:** task and experiment worktrees are deleted by the orchestrator after use; smoke runs
  write to `/tmp`.
* **Guard rail:** `mfos doctor` now warns when free disk falls below 20 GB. Keep ≥ 30 GB free for
  macOS updates and swap.

Git LFS, DVC, and external disks are **not needed**.

---

## 10. Cloud scaling strategy

| Stage | Compute | When |
|---|---|---|
| Development machine | the MacBook | always |
| Burst CPU | Hetzner CCX33 (8 vCPU, €0.2219/h) or CCX53 (32 vCPU, 128 GB, €0.855/h), one VM per experiment, several in parallel for sweeps | any experiment with `cpu_hours_est > 6` |
| High-memory | CCX53 (128 GB) | 3D FEM above ~5M unknowns |
| GPU | none | only for a future float32 workload |
| Batch cluster | AWS/GCP spot + Ray autoscaler, or a queue of Hetzner VMs | when sweeps routinely need > 10 VMs at once or > ~100 VM-hours/month |

**Why Hetzner for bursts.** Dedicated vCPUs (no noisy neighbors — timing metrics like A6 stay
meaningful), hourly billing capped at the monthly price, simple CLI (`hcloud`), and a 32-vCPU/128 GB
machine at €0.855/hour versus $1.64/hour on-demand for AWS's 32-vCPU/64 GB c7a.8xlarge. AWS spot is
cheaper per core but interruptible; it becomes the better choice when a Ray cluster with
checkpointing needs dozens of nodes.

**Burst beats a persistent large VM until utilization exceeds ~86%.** The CCX53's monthly cap
(€533.49) equals 624 hours at its hourly rate; a persistent machine only pays off if it would be busy
more than ~624 of the ~730 hours in a month.

### Burst compute on Google Cloud (`scripts/burst_gcp.sh`)

The founder's burst provider since 2026-10-04 (Hetzner's `scripts/burst.sh` still works). Same contract: one
ephemeral VM per run, the code shipped as a git bundle (no GitHub credentials on the VM), results copied back with
provenance, the VM deleted on every exit path. Default machine `n2-highmem-32` (32 vCPU, 256 GB) in
`us-central1-a`; any machine type and zone can be passed. On-demand by default (a registered run must not be
preempted); `MF_GCP_SPOT=1` gives a cheaper Spot VM for benchmarks.

One-time setup (founder, in a terminal):

```bash
brew install --cask google-cloud-sdk         # then open a new terminal
gcloud auth login                            # browser sign-in
gcloud projects create <PROJECT_ID>          # or use an existing project
gcloud config set project <PROJECT_ID>
gcloud billing accounts list                 # note the ACCOUNT_ID
gcloud billing projects link <PROJECT_ID> --billing-account <ACCOUNT_ID>
gcloud services enable compute.googleapis.com
ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/google_compute_engine   # key gcloud compute ssh uses
scripts/burst_gcp.sh --check                 # account, project, API, machine type, CPU quota
```

New projects usually have a regional CPU quota below 32 vCPU. If `--check` reports too little quota, request an
increase for "CPUs" and "N2 CPUs" in the VM's region (Console > IAM & Admin > Quotas); approval can take a day.

Runs: `scripts/burst_gcp.sh E001` (a registered experiment; the orchestrator picks the results up on its next
tick) or `scripts/burst_gcp.sh --cmd "<command>" <path>` (a benchmark: runs in the repository on the VM and copies
`<path>` back).

---

## 11. Cost analysis (infrastructure only; Claude usage excluded)

Hetzner prices after its June 2026 increase (dedicated vCPU plans roughly doubled), EU locations,
excluding VAT and IPv4 add-ons.

| Scenario | Monthly | Composition |
|---|---|---|
| **Completely local** | **$0** | MacBook; GitHub free private repo; R2 free tier |
| **Local + occasional bursts** | **~€10–25** | ~10–25 CCX53-hours (€9–21) for sweeps; R2 free tier |
| Persistent small VM (orchestrator only) | ~€20 + bursts | CPX22 (2 vCPU, 4 GB) €19.49; the cheaper cost-optimized plans are currently unavailable to order |
| Persistent large VM (the old recommendation) | €276–533 | CCX43 (16 vCPU/64 GB) €275.99 or CCX53 (32 vCPU/128 GB) €533.49; AWS c7a.8xlarge ≈ $1,200 on-demand if run 24/7 |
| Heavy autonomous development | ~€110–300 | 100–300 CCX53-hours (€85–260) + small VM €20 + R2/B2 a few € |

Optional: GitHub Pro (a few dollars a month) if you want rulesets on the private repository; not
needed while merges happen locally.

---

## 12. Exact setup instructions (MacBook Air)

About 45 minutes plus the canary run.

```bash
# 1. Base tools
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python git gh ngspice hcloud
brew install --cask claude-code          # stable channel; Homebrew installs do not auto-update (= pinned)
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL -l
python3 --version                        # must print 3.11 or newer (Homebrew's or conda's); never /usr/bin/python3 (3.9)
claude --version                         # write it down; upgrade deliberately with `brew upgrade claude-code`

# 2. Repository
mkdir -p ~/mf && cd ~/mf && unzip ~/Downloads/moduleforge-os.zip && mv moduleforge main && cd main
scripts/bootstrap.sh <your-github-username>
#   must end with "bootstrap OK: <commit>". If it prints "bootstrap STOPPED", stop here and fix that first.
scripts/provision_compute.sh             # ngspice + FastHenry into ~/.local/bin, ~2 min
#   must end with "FastHenry self-test: L = 5.704 nH (closed form 5.695 nH) -> PASS"
gh auth login && gh repo create <you>/moduleforge --private --source . --push   # optional remote; needs the bootstrap commit

# 3. Log in once; accept the workspace trust prompt; then /exit
claude

# 4. Canary (from Terminal, on power)
uv run mfos exp register E000
uv run mfos objective approve O000
uv run mfos loop --cycles 80 --poll 20   # expect O000 passed within ~30 min, ~$2–5 of usage

# 5. Run permanently with launchd
sed "s|__HOME__|$HOME|g" scripts/com.moduleforge.mfos.plist > ~/Library/LaunchAgents/com.moduleforge.mfos.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.moduleforge.mfos.plist
tail -f ~/Library/Logs/mfos.log          # restart: launchctl kickstart -k gui/$(id -u)/com.moduleforge.mfos
                                         # stop:    launchctl bootout gui/$(id -u)/com.moduleforge.mfos

# 6. Benchmarks (§13) — about 25 minutes
uv run --with pyamg bash benchmarks/infra/run_all.sh | tee ~/mf/bench-$(date +%F).txt
for k in 1 2 3; do benchmarks/infra/cc_concurrency.sh $k; done
```

**Recovering from a failed version 1.0 setup** (bootstrap stopped at the test suite, FastHenry did not
build). Nothing was committed and nothing outside `~/mf/main` was changed except the uv cache, so start
that directory over with the new archive:

```bash
# If `gh auth login` is waiting for input, press Ctrl-C first.
cd ~ && rm -rf ~/mf/main
cd ~/mf && unzip ~/Downloads/moduleforge-os.zip && mv moduleforge main && cd main   # the new zip
scripts/bootstrap.sh <your-github-username>        # expect: 25 passed ... bootstrap OK: <commit>
scripts/provision_compute.sh                       # expect: FastHenry self-test ... PASS
```
Then continue with `gh auth login …` and step 3. If you already created the GitHub repository in the
meantime, use `git remote add origin git@github.com:<you>/moduleforge.git && git push -u origin main`
instead of `gh repo create`.

7. **Power:** System Settings → Battery → Options → enable preventing automatic sleep on the power
   adapter when the display is off. Plug in when you want the loop to run unattended.
8. **Burst compute, only when first needed:** create a Hetzner Cloud project and an API token, then
   `hcloud context create moduleforge` and
   `hcloud ssh-key create --name mf --public-key-from-file ~/.ssh/id_ed25519.pub`. Test once with the
   canary: `scripts/burst.sh E000 ccx33` (costs one hour of a CCX33, ~€0.22).
9. **Sandbox (after the canary passes):** in `~/mf/main` run `claude`, then `/sandbox`, choose the
   auto-allow mode, and make sure the setting lands in your *user* settings (`~/.claude/settings.json`)
   so agents in worktrees inherit it. Add `~/.cache/uv` to `sandbox.filesystem.allowWrite` and set
   `sandbox.failIfUnavailable` to `true`. Re-run the canary; if `uv sync` cannot reach PyPI inside the
   sandbox, allow `pypi.org` and `files.pythonhosted.org` when prompted in an interactive session.

---

## 13. Benchmark plan

The scripts are in `benchmarks/infra/`. The reference column is this sandbox (1 vCPU Xeon, 3 GB);
your M5 should beat it by ~2–2.5× per core.

| # | Command | Reference result | Decision it drives |
|---|---|---|---|
| B1 | `benchmarks/infra/cc_concurrency.sh 1`, `2`, `3` — concurrent headless sessions reading the orchestrator code (≤ $0.50 each) | ~0.22 GB per process at start | If 3 sessions exceed ~4 GB total or `memory_pressure` leaves "normal": keep `concurrency.agents = 2` (default). If 3 sessions stay under ~3 GB and responsive, 3 is allowed. |
| B2 | `python l1_bench.py 200 400 800 1600` | 3 / 15 / 70 / 380 ms | Gives the real sandbox→M5 factor for every extrapolation here, and tells you where A6 (≤ 50 ms) is reachable. |
| B3 | FastHenry sweep in `run_all.sh` (11k, 21k filaments) | 18 s / 103 s; 0.19 / 0.54 GB | If a reference solve on real layouts exceeds ~5 min or 3 GB, E002-class experiments go to burst: set their `cpu_hours_est` honestly. |
| B4 | `python thermal_bench.py` | 3M unknowns: 26 s, 2.1 GB | Upper bound for local thermal FEM size. |
| B5 | ngspice DPT in `run_all.sh` | 0.17 s | Confirms DPT sweeps are free. |
| B6 | `python l1_throughput.py 4 10` — 4 workers for 10 minutes | per-minute counts | If minute-10 throughput is > 30% below minute 1, the Air throttles: lower `local_cpu_hours_max` to 2. |
| B7 | The canary under launchd with the lid closed for 30 minutes, then opened | — | Confirms sleep handling on your machine: runs resume, no spurious timeouts (`sleep_detected` event in `project/events.jsonl`). |

Extrapolation rule: estimated CPU-hours for an experiment = (solves × frequencies × seconds per solve
from B3) / 3600. Put it in the spec's `cpu_hours_est`; the orchestrator routes it.

---

## 14. Final recommendation

**One architecture: the MacBook Air is the control plane and the default compute; ephemeral Hetzner
VMs, launched per experiment by `scripts/burst.sh`, absorb anything above 6 estimated CPU-hours. No
persistent VM until one of these triggers fires:**

1. **Lid-closed autonomy matters.** At autonomy level 3, work is waiting while the laptop sleeps on
   most days of a week → add a small always-on VM for the *orchestrator only* (CPX22-class, ~€20/month),
   and keep bursting for compute.
2. **Customer pilots.** Confidential customer layouts must not live on a personal laptop → a separate,
   isolated environment per engagement (§14.4).
3. **Sustained heavy compute.** Burst usage exceeds ~600 VM-hours/month → a persistent or dedicated
   machine becomes cheaper.

```text
Initial setup
  Local:  MacBook Air M5, 16 GB, ≥ 60 GB free, macOS
          Homebrew python3 (>= 3.11), uv, git, Claude Code (Homebrew cask, pinned), ngspice, FastHenry,
          mfos under launchd; concurrency: 2 agents + 1 experiment (≤ 4 workers); local_cpu_hours_max = 6
  Cloud:  nothing running. On demand: Hetzner CCX33 (8 vCPU/32 GB) or CCX53 (32 vCPU/128 GB),
          Ubuntu 24.04, provisioned per experiment by scripts/burst.sh, deleted afterwards.
          No GPU. Object storage: Cloudflare R2 free tier for claim-referenced artifacts.
```

### 14.1 Month 1 — O000 canary and O001 (L1 ranking fidelity)
Mac only. E001 and E003 are minutes; E002 is 30–40 minutes on 4 cores (a few hours in the worst
case, or ~€1–3 on one burst). Storage ~10–15 GB. **Cost: $0.** Run the benchmarks in week 1 and set
`concurrency.agents` and `local_cpu_hours_max` from B1 and B6.

### 14.2 Month 3 — thermal fidelity, optimization headroom, first derivative re-layouts
Mac plus bursts for L2 audit sweeps and any transient-thermal campaign (a few to ~25 VM-hours).
Consider the ~€20 orchestrator VM if trigger 1 has fired. Storage ~20–30 GB with retention.
**Cost: ~€10–50/month.**

### 14.3 When the MVP becomes compute-heavy
Surrogate datasets of 10³–10⁴ reference solves, L2-in-the-loop optimization, large 3D FEM. Parallel
burst VMs (several CCX53 at once, one experiment per VM), or AWS/GCP spot with Ray once jobs need
dozens of nodes; the orchestrator VM becomes worthwhile. **Cost: ~€110–300/month.** Re-examine GPUs
only if a float32 workload appears.

### 14.4 When customer pilots begin
Customer data never touches the laptop. Per engagement: an isolated Linux VM (or the customer's own
environment), a separate repository or data vault for their layouts, encrypted object storage, and
the burst pattern inside that account. If the customer requires it, run Claude through a cloud
provider's regional endpoints or with zero-data-retention terms. Budget is driven by the customer's
security requirements, not by compute.

### 14.5 What to do today
1. Keep working on the MacBook. **Do not provision any VM.**
2. Install the tools and the repository exactly as in §12 steps 1–3.
3. Run the O000 canary from Terminal (step 4).
4. Install the launchd agent (step 5) and set the power option (step 7).
5. Run the benchmarks (step 6) this week; adjust `concurrency.agents` and `local_cpu_hours_max` per §13.
6. Approve O001 at autonomy level 1 (ARCHITECTURE.md §22).
7. Set up `hcloud` only when the first experiment is routed to burst compute, and test the path once
   with the canary.
8. Enable the Claude Code sandbox after the canary passes (step 9).

---

## References

* Claude Code system requirements and installation — https://code.claude.com/docs/en/setup
* Claude Code cost management (agent teams token usage) — https://code.claude.com/docs/en/costs
* Hosting the Agent SDK (per-agent resource guidance) — https://code.claude.com/docs/en/agent-sdk/hosting
* Claude Code sandboxing — https://code.claude.com/docs/en/sandboxing
* MacBook Air (M5) technical specifications — https://www.apple.com/macbook-air/specs/
* jax-mps (float64 unsupported on Metal) — https://pypi.org/project/jax-mps/
* DOLFINx installation — https://github.com/FEniCS/dolfinx
* Ray installation (Apple Silicon) — https://docs.ray.io/en/latest/ray-overview/installation.html
* FastHenry (Whiteley Research version; MacPorts `fasthenry-wr`) — https://github.com/hohe/fasthenry-3.0wr
* Hetzner Cloud prices after June 2026 — https://costgoat.com/pricing/hetzner ; https://northflank.com/blog/hetzner-cloud-server-price-increases
* AWS c7a.8xlarge on-demand price — https://www.devzero.io/instances/aws/c7a.8xlarge
* Cloudflare R2 and Backblaze B2 pricing — https://www.spendbase.co/?p=35561 ; https://swarmify.com/blog/video-hosting-egress-pricing-compared/
