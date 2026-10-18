# Phase 2: gplugins DEVSIM fix and MOS capacitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Changes after plan review

An independent review checked this plan against the code on main and the research. The decisions below came out of it, and each is written into the task it affects.
- **SPICE provenance is protected.** `tools/sandbox-run` and every module in `reference.GENERATOR_MODULES` feed `results/spice/provenance.json`, which `tests/test_results_provenance.py` checks. So Phase 2 does not touch them:
  - TCAD has its own CLI, `python -m gf180tcad.tcad` / `gf180tcad.history`;
  - the plugin path comes from a `.pth` file in the TCAD venv, not from the sandbox wrapper.
- **Physics constants are explicit**, not DEVSIM's `simple_physics` defaults (ε_si = 11.1, T = 300 K, ε0 = 8.85e-14). Using those defaults would let a wrong permittivity leak into calibrated doping.
- **Both MOSCAPs use a poly-gate region.** NGATE is a fixed `spice-card` value, so poly depletion comes from physics. The metal-gate "either/or" is dropped, because a single effective oxide cannot fit the pfet's 6 % accumulation/inversion asymmetry.
- **The analytic references are exact.** They use the 1D Poisson–Boltzmann solution, not the depletion approximation; the depletion-approximation Cmin is a high-frequency quantity.
- **QS vs AC tests respect the minority-carrier response time** (≈ 10² s with only a body contact). The 1 Hz equality is required only in accumulation and depletion.
- **`t_ox_eff` may exceed TOXP.** The SPICE L10−L2 slope needs t_eff ≈ 16.4–16.7 nm. The upper bound adds a cited charge-centroid/poly allowance to TOXP, and the fit reports when it hits a bound.
- **The agreement metric is defined.** It is the plateau max \|ΔCgg\|/Cgg ≤ 5 % in accumulation and in inversion. The transition region is judged by a voltage shift (≤ 50 mV, a proposal).
- **Anti-goal A1 is enforced in code, not prose:** role guards, a frozen-result hash, and calibrated values kept only in `results/tcad/calibration/`.
- **gmsh threading is fixed.** meshwell defaults to `n_threads=cpu_count()` and overwrites gmsh's thread options, so every call passes `n_threads=1`.
- **The "once worked" record covers the path that actually broke.** That path is `DDComponent` with the mesher; the PIN path uses DEVSIM's own mesh and never broke.
- **The fork gains a 1D stack builder.** gf180-tcad consumes it instead of building its own DEVSIM device.
- **`MeshSpec` is defined before its first use**, in Task 9b.
- **Submodule bumps are batched**: at Task 2, after Task 8, and at Task 15.
- **Process files are TOML** (stdlib `tomllib`), with card line citations.
- **TCAD results carry their own `provenance.json`**, which pins the image, the fork commit and a content hash.
- **Tasks 9 and 13 are each split in two.**

### Second review

A second independent review checked the revised plan against the code on main, the meshwell 2.5.2 source and the card. Its decisions:
- **meshwell threading needs more than `n_threads=1`.** `generate_mesh` builds its meshing `ModelManager` without `n_threads` (`meshwell/orchestrator.py:246`), so it takes the import-time `cpu_count()` default. Its `_initialize` also calls `gmsh.finalize()`/`initialize()` (`model.py:89-94`), which wipes gmsh options set beforehand. So:
  - the TCAD image sets `ENV PYTHON_CPU_COUNT=1` (Python 3.13 makes `os.cpu_count()` honour it);
  - the fork calls `cad()` and then `mesh(model=ModelManager(n_threads=1), ...)` directly, and sets gmsh options (`Mesh.RandomSeed`, `Geometry.OCCParallel=0`) in `pre_2d_hook`;
  - the tests that read `General.NumThreads == 1` after meshing stay.
- **pytest is in the TCAD image**, because fork tests run inside it.
- **TCAD locks are reproducible offline.** The main TCAD lock comes from a uv project in `docker/tcad/` (`uv export --locked`, as for the base). The two single-purpose locks record `--exclude-newer`. A test checks that the numpy pin equals the base lock's.
- **The `t_ox_eff` upper bound is numeric before any fit.** It is TOXP + Δ, where Δ is the charge-centroid allowance only (BSIM4 ACDE/MOIN), computed in Task 9a. Poly depletion is never in Δ, because the poly-gate region simulates it. The fallback is TOXP + 0.5 nm, labelled a project choice. The three tunables and their bounds are written in Task 9a.
- **The transition metric has two crossings.** ΔV is reported at both mid-capacitance crossings (depletion side: Vfb and doping; inversion side: Vt), each ≤ 50 mV (a proposal), with a five-corner "Same process" window per crossing. max |ΔC|/C in depletion is still reported. Replacing the spec §5.2 depletion-region ≤ 5 % with ΔV is a **deliberate spec deviation**: there, C goes from 82 to 144 fF within 0.2 V, so a relative-C metric measures the slope, not the agreement.
- **Constants are complete.** n_i follows Altermatt et al. 2003 (9.65e9 cm⁻³ at 300 K) with a cited T-scaling. ε_si = 11.7 is tagged `literature` (Sze & Ng). Mobility and lifetimes are explicit and cited. Tests expect the Boltzmann-statistics flat band (−1.029 V nfet, +1.003 V pfet). Boltzmann statistics in the degenerate gate are a documented limitation.
- **`dv_fb_v` is a lumped flat-band offset**, applied as a rigid gate-bias shift (exact in 1D). It is not described as fixed oxide charge. Its ±0.2 V is a project choice.
- **Results layout:** `results/tcad/moscap{1d,2d}/<device>/{start,calibrated}/`. TCAD jobs have 3 parts. There is one `provenance.json` per tree root. The cross-check reruns exactly the committed configuration, and `verify_subset` gets `full=` explicitly.
- **Every non-gate contact gets its own voltage source** in `sweep_cv`. The `tie` argument is gone. Charge conservation sums Cgx over every non-gate contact. The `tie` mechanics test moves to a minimal `create_2d_mesh` device in the fork.
- **TCAD provenance is structural.** `TCAD_GENERATOR_MODULES` has an import-graph test (Task 9b). The plugin commit comes from `git -C third_party/gplugins rev-parse HEAD` with a clean-tree check.
- Smaller fixes:
  - `MeshSpec` gains `h_poly_nm`;
  - the accumulation series test uses a metal gate;
  - `moscap2d.simulate` takes `vg`, and `converge` takes a protocol;
  - card expressions are evaluated at TT;
  - the Cox spec-entry convention is defined;
  - the TCAD image package is made public;
  - fork CI reproduces the sandbox environment;
  - the history CLI gains `--mesh-scale`;
  - 1D contacts are `InterfaceRef(region, None)`;
  - the calibration-set citation is corrected to `devices.py:81-92`;
  - the pfet S/D doping is named, with a sensitivity test;
  - meshconv, calibrate and validate have CLIs;
  - the duplicate Review Focus bullet is removed.

**Goal:** Restore the gdsfactory `gplugins.devsim` plugin in the `mithro/gplugins` fork. First prove it once worked on its original stack, then port it to the latest stack and re-verify it. Extend it with typed contacts, analytic doping and a C–V solver. Then use it from gf180-tcad to build mesh-converged 1D and 2D MOS capacitors whose Cgg–Vg is calibrated against the committed SPICE reference for `nfet_05v0`/`pfet_05v0`, with the results published reproducibly.

**Architecture:** Plugin work happens on fork branches with PRs inside `mithro/gplugins`. gf180-tcad consumes the fork as a git submodule `third_party/gplugins`, pinned to a fork commit and mounted read-only into the sandbox with the rest of the repo, so a plugin change never needs an image rebuild. A new reproducible image `ghcr.io/mithro/gf180-tcad-tcad` adds a uv-managed CPython 3.13 venv on top of the pinned base image; meshwell ≥ 2.4 needs Python 3.13. TCAD jobs run in that image through the existing `tools/sandbox-run` (`--image`). SPICE jobs keep using the base image, so the committed SPICE reference is untouched. MOSCAP results are written with the same deterministic I/O and manifest as Phase 1, and the generated docs pages overlay TCAD against SPICE.

**Tech Stack:** DEVSIM 2.11.1, meshwell 2.5.2, gmsh 4.15.2 (Python package), gdsfactory 9.51.0, gf180mcu (gdsfactory PDK) 1.0.0, CPython 3.13 (uv-managed), plus the Phase 0–1 stack (uv, pytest, ruff, numpy, Sphinx/MyST, Docker, GitHub Actions, ghcr.io, Read the Docs). Versions are the latest at plan time (2026-10-18). Re-check them at lock time and take the newest.

**Spec:** `docs/superpowers/specs/2026-10-18-gf180-tcad-design.md`. Read §2 (anti-goals), §5.2 (calibration/validation split, parameter sources, 8-parameter budget, held-out geometries, numerical acceptance), §6, §9, §12 and §13 before any task.

**Research basis:** the Phase 2 research report, with sources and command logs, is summarised in each task's Context line. Its findings that bind this plan:
- the plugin's history: added `a019e5a` 2023-08-01; import broken since `0ce7b30` (v0.8.1); `create_2Duz_simulation` raises `NotImplementedError` since `017cede`;
- the "once worked" stack: gplugins v0.8.0, devsim 2.6.3, gdsfactory 7.6.1, meshwell 1.0.1, gmsh 4.11.1, Python 3.11;
- the C–V physics notes (quasi-static vs high-frequency; effective oxide as the dominant knob);
- the public card values (all `spice-card`, from the image's `sm141064.ngspice`, sha256 `69a7ab87…`).

## Global Constraints

- **Licences.** gf180-tcad code is Apache-2.0, with `# SPDX-License-Identifier: Apache-2.0` on every new file. Code in the `mithro/gplugins` fork is under the fork's existing MIT licence. New fork files carry `# SPDX-License-Identifier: MIT`. Fork changes are not relicensed.
- **gf180-tcad git rules (as in Phase 0–1).**
  - One branch plus worktree per task under `../gf180-tcad-worktrees/`.
  - Small logical commits. Never commit on `main`.
  - PRs use `gh pr create --repo mithro/gf180-tcad --base main`.
  - Each PR gets an independent review agent, then `gh pr merge --merge --repo mithro/gf180-tcad`.
- **Fork git rules.**
  - Clone at `/home/tim/github/wafer-space/gplugins`; worktrees under `/home/tim/github/wafer-space/gplugins-worktrees/`.
  - Branches are `gf180/<task>`.
  - PRs use `gh pr create --repo mithro/gplugins --base main`. Always pass `--repo`: the default base for a fork is upstream.
  - Each PR is reviewed, then merged with `gh pr merge --merge --repo mithro/gplugins`.
  - The `upstream-readonly` remote has its push URL set to `DISABLED`.
  - Never open PRs, issues or comments on, or push to, `gdsfactory/gplugins` or any other upstream repo.
- **Latest versions.** Use the versions above; an older stack is only for proving the plugin once worked (Task 3). Base image: `docker/IMAGE`, unchanged by this phase.
- **Sandbox.**
  - Every simulator, mesher and package install runs inside `tools/sandbox-run`. Installs that need network use `--network bridge`, in a separate step; runs use `--network none`.
  - Defaults are 16 GiB / 8 CPU per job. TCAD jobs may request less, never more than 16 GiB, without a ledgered ruling.
  - The aggregate slice limit is 128 GiB.
- **SPICE provenance is frozen.** `reference.GENERATOR_MODULES` (`src/gf180tcad/reference.py:78`) lists `gf180tcad`, `gf180tcad.__main__`, `.devices`, `.io`, `.metrics`, `.pdk`, `.reference`, `.sandbox`, `.specwindow` and `.spice.*`. Together with `tools/sandbox-run` (`GENERATOR_EXTRA_FILES`), they feed `results/spice/provenance.json`.
  - `tests/test_results_provenance.py` fails on any change to them.
  - `tests/test_reference.py::test_generator_modules_match_the_import_graph` ties the list to what `gf180tcad.__main__` imports.
  - **No Phase 2 PR edits those files**, unless the same PR also does all of the following: regenerates `results/spice` (`python -m gf180tcad spice-reference --engine both --out results/spice`), runs `make manifest`, and passes crosscheck.
  - TCAD code lives in the new subpackages `gf180tcad.tcad`, `gf180tcad.calibrate` and `gf180tcad.history`, with their own entry points. The TCAD image reference is a constant in `gf180tcad/tcad/__init__.py`, never in `sandbox.py`.
- **Host vs image split (as for SPICE).** The two halves of each TCAD CLI command are:
  - the host command, which reads `docker/TCAD_IMAGE` and calls `sandbox.run(cmd, out_dir=..., image=TCAD_IMAGE, mem=..., cpus=1)`;
  - a `*-job` command, which runs inside the image and writes only to `/work/out`.

  Note that `sandbox.run` refuses `image=` when it is already inside the sandbox (`sandbox.py:191-193`). Concurrent TCAD jobs go through an admission check (jobs × mem ≤ 128 GiB), as `reference.check_admission` does for SPICE.
- **Determinism.** Keep the Phase 0–1 environment: single-threaded BLAS/OMP, `OPENBLAS_CORETYPE=Haswell`, `DEVSIM_MATH_LIBS=libopenblas.so.0` (inherited from the base image), and numpy on baseline kernels (`NPY_DISABLE_CPU_FEATURES` from `tools/sandbox-run`). In addition:
  - **DEVSIM runs single-threaded.** `test_devsim_single_thread` (Task 1) asserts three things during a solve:
    - `devsim.get_parameter(name="threads_available")` is 1, or unset, which means the default of 1;
    - the `Threads:` line of `/proc/self/status` is 1;
    - DEVSIM's start-up log says `Loading "libopenblas.so.0"` and mentions no MKL.
  - **meshwell and gmsh run single-threaded.** meshwell 2.5.2 defaults `n_threads` to `os.cpu_count()` (88 on this host, 4 on GitHub runners). It then sets `General.NumThreads`, `Mesh.MaxNumThreads1D/2D/3D` and `Geometry.OCCParallel` from that value (`meshwell/model.py:336-342`). `generate_mesh(..., n_threads=1)` is **not enough**: it builds its meshing `ModelManager` without `n_threads` (`meshwell/orchestrator.py:246`), so that stage still uses `cpu_count()`. Two measures, both required:
    - the TCAD image sets `ENV PYTHON_CPU_COUNT=1`, which Python 3.13 makes `os.cpu_count()` honour (Task 1);
    - the fork never calls `generate_mesh`. It calls `meshwell.orchestrator.cad(..., n_threads=1)` and then `meshwell.mesh.mesh(..., model=ModelManager(n_threads=1, ...), n_threads=1)` directly (Task 5).

    Tests read `gmsh.option.getNumber("General.NumThreads") == 1` after meshing (Tasks 1 and 5).
  - **gmsh is pinned.** meshwell's `ModelManager._initialize` calls `gmsh.finalize()`/`gmsh.initialize()` (`model.py:89-94`), which resets every option set before it. So `Mesh.RandomSeed` (fixed) and `Geometry.OCCParallel=0` are set in `mesh(..., pre_2d_hook=...)`, after initialisation. Mesh files are written as MSH 2.2.
  - **The optimiser is deterministic.** Task 12 uses `scipy.optimize.least_squares(method="trf", jac="2-point")` with fixed `x0`, `diff_step`, `x_scale`, `ftol`/`xtol`/`gtol` and `max_nfev`. It has no random restarts and runs in the sandbox.
  - **Results are compared within one image.** Comparisons and verdicts between TCAD and SPICE are computed inside one stated image (the TCAD image), from SPICE CSVs parsed bit-exactly with `io.read_csv`. Numbers computed in different images are never compared bit-wise, because the cp312 and cp313 numpy wheels may differ in the last ulp.
  - Two runs must give byte-identical result files.
  - No timestamps, hostnames or host paths in results.
- **Physics constants (all TCAD, fork and gf180-tcad).** DEVSIM's `python_packages/simple_physics.py` hard-codes `eps_0=8.85e-14`, `eps_si=11.1`, `q=1.6e-19`, `n_i=1e10` and `T=300` (lines 13–20). None of these defaults is used. The fork's material setup takes these constants explicitly:

  | Quantity | Value | Provenance |
  |---|---|---|
  | ε0 | 8.8541878128e-14 F/cm | `literature`, CODATA 2018 |
  | q | 1.602176634e-19 C | `literature`, exact SI |
  | k_B | 1.380649e-23 J/K | `literature`, exact SI |
  | ε_si | 11.7 | `literature`: Sze & Ng, *Physics of Semiconductor Devices*, 3rd ed., Appendix ([doi:10.1002/0470068329](https://doi.org/10.1002/0470068329)). It equals the BSIM4 EPSRSUB default; the card sets no EPSRSUB. |
  | ε_ox | 3.9 | `spice-card`: EPSROX (`sm141064.ngspice`, nfet card) |
  | T | 298.15 K | `spice-card`: TNOM 25 °C, `sm141064.ngspice:37308` |
  | n_i(300 K) | 9.65e9 cm⁻³ | `literature`: Altermatt et al., J. Appl. Phys. 93, 1598 (2003), [doi:10.1063/1.1529297](https://doi.org/10.1063/1.1529297) |
  | n_i(T) | n_i(300 K)·(T/300)^2.54·exp(−6726 K·(1/T − 1/300 K)) → **8.266e9 cm⁻³** at 298.15 K | `literature`: the Misiakos & Tsamakis T-dependence, J. Appl. Phys. 74, 3293 (1993), [doi:10.1063/1.354551](https://doi.org/10.1063/1.354551), normalised to Altermatt's 300 K value |
  | µ_n, µ_p | 1417, 470.5 cm²/(V·s), constant (no field or doping dependence in Phase 2) | `literature`: Masetti et al., IEEE TED 30, 764 (1983), µ_max, [doi:10.1109/T-ED.1983.21207](https://doi.org/10.1109/T-ED.1983.21207) |
  | τ_n, τ_p (SRH) | 1e-5 s each; n1 = p1 = n_i (midgap trap) | `literature`: Sze & Ng ch. 1 (SRH recombination; the Task 6 PR quotes the page). QS C–V does not depend on them. The 1D HF argument (Task 8) holds for any τ ≥ 1e-9 s. |

  The literature citations for these constants are links. Every unit test with a hand value uses the same constants on both sides.
  - **Statistics are Boltzmann** (DEVSIM `simple_physics`-style models, with the constants above). The derived Vt = k_B·T/q is 25.6926 mV. The poly-gate flat band is Vfb = −V_t·ln(NGATE·N_A/n_i²): **−1.029 V** for the nfet (n⁺ 1e20 on p 1.7e17) and **+1.003 V** for the pfet (p⁺ 3.6e19 on n 1.7e17). Every test expects these Boltzmann values.
  - Boltzmann statistics in the degenerate gates (1e20 and 3.6e19) place E_F beyond the band edge. The degenerate-pinned flat band is ≈ −0.99 V. This difference (≈ 40 mV) is absorbed by `dv_fb_v` and listed as a limitation (Task 13a).
- **Result files.** Floats are written with `repr`, with `\n` line endings and sorted JSON keys. Write through `gf180tcad.io`, and never modify `io.py` (it is a generator module).
  - Register every result in `results/MANIFEST.sha256` (`make manifest`).
  - **TCAD results layout.** Results live under `results/tcad/`:
    - `moscap1d/<device>/{start,calibrated}/` and `moscap2d/<device>/{start,calibrated}/`;
    - `meshconv/{moscap1d,moscap2d}/<device>/`;
    - `calibration/<device>.json` and `validation/<device>.json`.

    A TCAD *job* is a 3-part path such as `moscap1d/nfet_05v0/calibrated`. Each *tree root* holds exactly one `provenance.json`: `results/tcad/moscap1d/provenance.json`, `results/tcad/moscap2d/provenance.json`, `results/tcad/meshconv/provenance.json`, `results/tcad/calibration/provenance.json` and `results/tcad/validation/provenance.json`.
  - Each tree root's `provenance.json` is written by `gf180tcad.tcad.provenance()`. It contains:
    - the `docker/TCAD_IMAGE` reference;
    - the contents of `docker/tcad/versions.json`;
    - `gplugins_commit`: taken on the host with `git -C third_party/gplugins rev-parse HEAD`, because the read-only mount cannot run git. Writing raises unless `git -C third_party/gplugins status --porcelain` is empty and the commit equals the gitlink in `git ls-tree HEAD third_party/gplugins`;
    - `generator_sha256`, over the files of `gf180tcad.tcad.TCAD_GENERATOR_MODULES`, `tools/sandbox-run`, `third_party/gplugins/gplugins/devsim/**` and `data/process/*.toml`;
    - for trees computed with calibrated values, the `param_sha256` and sha256 of `results/tcad/calibration/<device>.json`.

    It deliberately holds no date.
  - **`TCAD_GENERATOR_MODULES`** (in `gf180tcad/tcad/__init__.py`, Task 9b) lists every gf180tcad module that the TCAD entry points import: `gf180tcad.tcad.__main__` and `gf180tcad.calibrate.__main__`. The list includes the shared modules (`gf180tcad.io`, `.devices`, `.sandbox`, …).
    - `tests/tcad/test_tcad_provenance.py::test_tcad_generator_modules_match_the_import_graph` ties the list to the import graph, as the SPICE test does. Every later task that adds a TCAD module extends the list in the same PR.
    - `tests/tcad/test_tcad_provenance.py::test_committed_tcad_provenance_current` checks that every committed tree root's `provenance.json` matches the current one, as `tests/test_results_provenance.py` does for SPICE.
- **Public data only.** Every process number cites a public source and carries a provenance tag: `pdk-doc`, `spice-card`, `literature` or `calibrated`. No NDA material.
- **SPICE reference is the golden reference.** TCAD is never tuned on validation targets (spec §5.2).
- **Documentation.** Every reference in the docs to a file, term, tool or code object is a link (`{repo}`, `{term}`, tool substitutions, `{py:*}`), as `tests/test_doc_links.py` enforces.
  - **Requires the docs-links infrastructure on main** (PR #15: `tests/test_doc_links.py`, `docs/glossary.md` and `docs/conf.py:_TOOLS`) before any docs-touching task starts.
  - New tools (DEVSIM, meshwell, gmsh, gplugins, gf180mcu, scipy) are added to `docs/conf.py:_TOOLS`. New terms (MOSCAP, QS, HF C–V, effective oxide, poly depletion) are added to the glossary.
  - Files inside the submodule are linked as `https://github.com/mithro/gplugins/blob/<pinned commit>/…`, because `git ls-files` does not list them.
  - Docs changes also get a dedicated missing-links review.
- **Submodule hygiene.** Every gf180-tcad worktree runs `git submodule update --init` after `git worktree add`.
  - `[tool.ruff]` gets `extend-exclude = ["third_party"]` (Task 2), so that `ruff check`/`ruff format --check` never lint the fork.
  - pytest is already confined to `testpaths = ["tests"]`.
- **CI.** GitHub-hosted runners only, for the fork as well.

## Review Focus

- **Quasi-static vs high-frequency C–V.** SPICE Cgg (BSIM4 capmod=2) is quasi-static and recovers to about Cox in inversion. A MOSCAP solved with AC at 1 MHz and only a body contact gives the high-frequency curve instead. A comparison must use matching physics: quasi-static/equilibrium in 1D, or S/D contacts tied to the body in 2D. A reviewer should reject any mismatched pairing.
- **Units.** DEVSIM works in cm (charge in C/cm², capacitance in F/cm²). gdsfactory, the SPICE data and the docs use µm and fF. Every conversion needs a unit test with a hand-computed value, for example Cox(15.2 nm) = 2.272 fF/µm², or 224.7 fF for W10/L10 with DLC = 54 nm.
- **pfet MOSCAP.** The pfet MOSCAP has:
  - an n-type body (n-well);
  - a p⁺ poly-gate region (NGATE 3.6e19, versus 1e20 n⁺ for the nfet).

  The flat band follows from the gate and body doping (Boltzmann, Global Constraints): Vfb = −1.029 V for the nfet and +1.003 V for the pfet. Accumulation is at +Vg for the pfet. Reuse the Phase 1 rule `polarity·vg` for inversion and accumulation.
- **Silent non-convergence.** A bias point that fails to converge, or converges only at a relaxed tolerance, must fail the sweep, never be dropped or interpolated. The tolerance is recorded per point.
- **Calibration leakage.** Only calibration geometries (W10 at L = 10, 2 and Lmin) and calibration targets (Cgg–Vg) may move parameters. Held-out geometries (L = 0.7, 1, 1.6/0.7) are computed after the parameters are frozen.

---

### Task 1: TCAD image (Python 3.13 stack)

**Context.**
- meshwell ≥ 2.4 requires Python ≥ 3.13, and the base image has 3.12.3. The base venv has no pip, and the base image has no uv.
- gf180mcu 1.0.0 pins `gdsfactory~=9.40`, so it installs with `--no-deps` against 9.51.
- The base image's `PDK=gf180mcuD` breaks gdsfactory. gdsfactory 9.51 `get_active_pdk()` (`gdsfactory/pdk.py:715-752`) imports `$PDK` as a module and calls `PDK.activate()`. When `PDK` is empty or unset, it raises "No active PDK".
- The base `docker/base/probe_versions.py:39-41` exits unless `PDK=gf180mcuD`.
- A 3.13-only meshwell cannot enter the project's `uv.lock`, because the project's `requires-python` is `>=3.12`.

**Files:**
- Create:
  - `docker/tcad/Dockerfile`;
  - `docker/tcad/pyproject.toml` and `docker/tcad/uv.lock`: a non-package uv project (`requires-python = "==3.13.*"`, `[tool.uv] package = false`) whose dependencies are the image's package set;
  - `docker/tcad/requirements.lock` (`uv export --project docker/tcad --locked --no-emit-project --format requirements-txt --hashes`);
  - `docker/tcad/gf180mcu.in` and `docker/tcad/gf180mcu.lock` (the single `--no-deps` package, hashed);
  - `docker/tcad/build-requirements.in` and `docker/tcad/build-requirements.lock` (holding uv, hashed; Task 3 reuses it);
  - `docker/tcad/build`, `docker/tcad/IMAGE_ID`, `docker/tcad/versions.json`, `docker/tcad/probe_versions.py`, `docker/TCAD_IMAGE`;
  - `tests/test_tcad_image.py`, `tests/test_tcad_lock.py`.
- Modify: `.github/workflows/image.yml` (build, verify and push both images), `docs/reproduce/image.md`.
- Do not modify `docker/base/**`, `docker/IMAGE`, `tools/sandbox-run` or `src/gf180tcad/sandbox.py`.

**Interfaces:**
- Produces: `docker/TCAD_IMAGE`, one line `ghcr.io/mithro/gf180-tcad-tcad@sha256:<64 hex>\n`.
  - Python is `/opt/gf180tcad-tcad/bin/python` (3.13), first on PATH, so `python3` is 3.13 in this image. The uv-managed CPython is installed under `/opt/uv-python`, with `UV_PYTHON_INSTALL_DIR` set at build time.
  - Installed with hashes:
    - devsim 2.11.1, meshwell 2.5.2, gmsh 4.15.2, gdsfactory 9.51.0;
    - scipy (for Task 12), numpy at the **same version as the base lock** (`numpy==2.5.4` today, `docker/base/requirements.lock:881`);
    - pytest, because the fork's tests run inside this image (Fork-task conventions);
    - the gplugins runtime dependencies (gdsfactory, pint, tqdm, xarray<2026.10, …), but **not** gplugins itself;
    - gf180mcu 1.0.0 in a second install step, `--no-deps --require-hashes` from `gf180mcu.lock`.
  - A `.pth` file in the venv site-packages, `gf180tcad-gplugins.pth`, holds `/work/src/third_party/gplugins`. This puts the submodule on `sys.path` in the TCAD image only, with no wrapper change (see Task 2).
  - `ENV PDK=gf180mcu`, so gdsfactory imports gf180mcu and activates its PDK. `PDK_ROOT=/foss/pdks` is kept.
  - `ENV PYTHON_CPU_COUNT=1`, so `os.cpu_count()` is 1 and meshwell's import-time `n_threads` defaults are 1 (Global Constraints, Determinism). The base `PATH` is replaced explicitly, with `/opt/gf180tcad-tcad/bin` first and otherwise the base `PATH`. The base ENV (thread variables, `DEVSIM_MATH_LIBS`, `OPENBLAS_CORETYPE`, `PYTHONDONTWRITEBYTECODE`) is inherited.
  - `docker/tcad/probe_versions.py` prints sorted-key JSON. It holds every base key (with `python` = the 3.13 patch), plus `tcad_python`, `meshwell`, `gmsh`, `gf180mcu`, `scipy`, `numpy`, `base_image_ref` (the contents of `docker/IMAGE`), and `devsim` = 2.11.1. It reads open_pdks facts from `$PDK_ROOT/gf180mcuD` directly, never from `$PDK`.
  - `docker/tcad/build` copies `docker/base/build`. `NAME` is `ghcr.io/mithro/gf180-tcad-tcad`. `INPUTS` are the Dockerfile, the three `.lock` files and `docker/IMAGE`; the base digest is the `FROM` (via `ARG BASE_IMAGE`), so it must date the build.
- Produces: `sandbox.run(cmd, out_dir=..., image=TCAD)` and `tools/sandbox-run --image "$(cat docker/TCAD_IMAGE)"` work unchanged (`sandbox.py:148-180`, `sandbox-run:20`).

- [ ] **Step 1:** Write the tests first.
  - These are sandbox-marked and run in the TCAD image:
    - `test_tcad_versions_json_matches_image`: the probe output equals `docker/tcad/versions.json` byte for byte.
    - `test_tcad_imports`: `devsim`, `meshwell.orchestrator`, `gmsh`, `gdsfactory` and `gf180mcu` all import. `gf.get_active_pdk()` does not raise, and its name is gf180mcu.
    - `test_tcad_numpy_baseline`: the numpy dispatch list is empty, as in `tests/sandbox/test_numpy_dispatch.py`.
    - `test_devsim_single_thread`: as in the Global Constraints.
    - `test_python_cpu_count_one`: `os.cpu_count() == 1` in the image.
    - `test_gmsh_single_thread`: a tiny mesh through meshwell's default `generate_mesh` (no `n_threads` argument), then `General.NumThreads == 1` and `Geometry.OCCParallel == 0`. This proves that `PYTHON_CPU_COUNT=1` reaches meshwell's defaults.
    - `test_pytest_in_image`: `python -m pytest --version` succeeds.
  - These are not sandbox-marked:
    - `test_tcad_image_pinned_by_digest`: the regex above.
    - `test_tcad_lock_in_sync` (offline): `uv export --project docker/tcad --locked ...` reproduces `requirements.lock` except for the header echo, as `tests/test_requirements_lock.py` does for the base.
    - `test_tcad_single_locks_fresh` (needs network): re-running each recorded command reproduces `gf180mcu.lock` and `build-requirements.lock` except for the header echo. The command is `uv pip compile docker/tcad/<name>.in --no-deps --generate-hashes --python-version 3.13.<patch> --python-platform x86_64-manylinux_2_28 --exclude-newer <timestamp>`. The `--exclude-newer` timestamp is the one recorded in the lock header, so later PyPI releases never break the test.
    - `test_tcad_numpy_matches_base`: the numpy pin in `docker/tcad/requirements.lock` equals the one in `docker/base/requirements.lock`.

  Run them: they FAIL because there is no image.
- [ ] **Step 2:** Build `FROM` the base image by digest.
  - Install uv from the hashed `build-requirements.lock` with `/usr/bin/python3 -m pip --require-hashes` into a throwaway build venv.
  - Install uv-managed CPython `3.13.<patch>`, pinned exactly. uv verifies the download against the sha256 it embeds for that pinned version.
  - Create the venv. Install `requirements.lock`, then `gf180mcu.lock --no-deps`, with `--require-hashes`, no bytecode and `test -z "$(find … -name '*.pyc')"`, as `docker/base/Dockerfile` does.
  - Use the same `SOURCE_DATE_EPOCH` and `rewrite-timestamp` as `docker/base/build`.
- [ ] **Step 3:** Two local `--no-cache` builds must give the same config digest. Commit `IMAGE_ID`, then push via CI and commit `docker/TCAD_IMAGE`.
  - Generalise `image.yml` into a matrix over `{base, tcad}`. Each image has its own build, IMAGE_ID, pinned-manifest and versions-probe checks, and its own reproducible rebuild job.
  - The tcad entry pulls the pinned base by digest; the package is public, so no login is needed on schedule runs.
  - New ghcr packages are private by default. After the first push, set `ghcr.io/mithro/gf180-tcad-tcad` to public (`gh api --method PATCH` on the package's visibility, or the package settings page), and record the step in `docs/reproduce/image.md`. The fork CI and the GitHub cross-check pull it without credentials. A test-free check in the PR: an anonymous `docker pull` of the digest succeeds.
  - If a future PR changes the base, `docker/IMAGE` is updated first, and the TCAD image and its results are rebuilt in a follow-up PR. Document this in `docs/reproduce/image.md`.
- [ ] **Step 4:** Run the tests: they PASS. Then commit, open the PR, review and merge.

### Task 2: Fork CI hygiene and submodule wiring

**Context.**
- Actions are already enabled on `mithro/gplugins`.
- The fork inherits these upstream workflows: `copilot-setup-steps.yml`, `pages.yml`, `release-drafter.yml`, `release.yml` and `test_code.yml`.
  - `pages.yml` deploys docs and uses `SIMCLOUD_APIKEY`.
  - `release.yml` publishes to PyPI with `PYPI_*` secrets.
  - `test_code.yml` installs unpinned with `uv pip install .[plugin,dev]` on Python 3.12, which cannot take meshwell 2.5.
- `gplugins/devsim` is excluded from pytest (`pyproject.toml:95` of the fork) and from the CI matrix (`test_code.yml:28`).

**Files (fork):** `.github/workflows/*`, `README.md`.
- In `.github/workflows/*`:
  - disable `pages.yml` deploy and `release.yml`, each with a comment saying why;
  - keep `test_code.yml` and `release-drafter.yml` only if they run without secrets.
- In `README.md`, add a "fork for gf180-tcad" note.

**Files (gf180-tcad):**
- `.gitmodules` (URL `https://github.com/mithro/gplugins.git`);
- `third_party/gplugins`, the submodule at a fork commit;
- `pyproject.toml`: `[tool.ruff] extend-exclude = ["third_party"]`;
- `tests/test_submodule.py`, `docs/reproduce/index.md` (clone with `--recurse-submodules`; `git submodule update --init` per worktree).

**`tools/sandbox-run` is not modified** (Global Constraints). The plugin path comes from the TCAD image's `.pth` (Task 1).

**Interfaces:**
- Produces: inside the TCAD image, `gplugins.__file__` starts with `/work/src/third_party/gplugins/`.
- Produces: the jobs that need TCAD code check out submodules: `actions/checkout` with `submodules: true`, in the Task 13b crosscheck TCAD job. `make reproduce` documents `--recurse-submodules`. The existing lint-test and SPICE crosscheck jobs keep checking out without submodules.

- [ ] **Step 1:** Fork branch `gf180/ci-hygiene`. List each workflow with what it does, in the PR description. Disable the unsafe ones. The remaining test workflow must go green on a PR inside the fork.
- [ ] **Step 2:** In gf180-tcad, write `test_submodule.py` first.
  - `test_submodule_pinned_on_fork_main` (not sandbox-marked; needs `gh`): `gh api repos/mithro/gplugins/compare/main...<sha>` reports `status` `behind` or `identical`. Take `<sha>` from `git ls-tree HEAD third_party/gplugins`.
  - `test_plugin_imports_from_submodule` (sandbox-marked, in the TCAD image): `gplugins.__file__` is under `/work/src/third_party/gplugins/`.
  - `test_ruff_excludes_third_party`: `third_party` is in `extend-exclude`.

  Run them: they FAIL. Add the submodule and the ruff exclude. Run them: they PASS.
- [ ] **Step 3:** For both repos: commit, open the PR, review and merge. This is submodule bump 1 of 3.

### Task 3: Prove the plugin once worked (committed, re-runnable record)

**Context.** At gplugins v0.8.0 on Sept-2023 packages, `test_pin_waveguide` passed (276 s) and `DDComponent.ddsolver()` converged (5.8 s). `get_refined_mesh` has a `NameError` (`get_solver.py:359`). At v1.4.2 from its frozen lock, the import fails.

**Sources of the checks** (all in the fork's history; no research scratch files are needed):
- **PIN:** `git -C third_party/gplugins show v0.8.0:gplugins/devsim/test_devsim.py`, the body of `test_pin_waveguide`. It builds `get_simulation_xsection.PINWaveguide(core_width=500 nm, core_thickness=220 nm, slab_thickness=90 nm)`, runs `ddsolver()` and then `ramp_voltage`.
- **PN slab (`DDComponent`):** `git -C third_party/gplugins show v0.8.0:gplugins/devsim/get_solver.py`, its `if __name__ == "__main__":` block (from l.412). It trims `straight_pn(length=10)` to `[[3,-4],[3,4],[5,4],[5,-4]]`, uses the anode/cathode layers (105,0)/(106,0) from VIAC∧NPP and VIAC∧PPP, and its `resolutions` dict, `xsection_bounds=[(4,-4),(4,4)]` and `mesh_scaling_factor=1e-4`.
- `checks_v080.py` is these two blocks turned into named checks, with only the result recording added:
  - `import`: `import gplugins.devsim`;
  - `pin_test`: the PIN build plus `ddsolver()`;
  - `ramp`: `ramp_voltage` on PIN to 0 and then −1 V, and on the PN slab to 0.1 and 0.2 V;
  - `ddcomponent_mesh`: the `DDComponent(...)` construction;
  - `ddsolver`: `c.ddsolver()` on the PN slab;
  - `refine`: `c.get_refined_mesh(...)` exactly as in the block.
- `checks_v142.py` runs the `import` check only, because the import is what fails.

**Files (gf180-tcad):**
- `src/gf180tcad/history/__init__.py`, `src/gf180tcad/history/__main__.py`;
- `experiments/plugin-history/README.md`;
- `experiments/plugin-history/v080.lock` (the hashed, resolved v0.8.0 set);
- `experiments/plugin-history/checks_v080.py` and `checks_v142.py` (the in-venv check drivers);
- `results/plugin-history/{v0.8.0,v1.4.2}.json`, plus `results/plugin-history/v0.8.0-mesh0p5.json` (the PN slab at half mesh size, for Task 5's tolerance);
- `tests/test_plugin_history.py`.
- uv itself comes from `docker/tcad/build-requirements.lock` (Task 1). No new uv lock is added.

The CLI is **not** `python -m gf180tcad …`: `__main__` is a SPICE generator module (Global Constraints).

**Interfaces:**
- Produces: `python -m gf180tcad.history --version v0.8.0|v1.4.2 [--mesh-scale R] --out DIR`. `--mesh-scale R` (default 1) multiplies every value in the PN slab's `resolutions` dict by R, and is recorded in the JSON. The PIN check uses DEVSIM's own mesh and ignores it. The command runs on the host, uses the base image, and works in these steps:
  1. **Sources, on the host.** `git -C third_party/gplugins archive <tag> | tar -x -C <workdir>/gplugins`. CI submodule clones are shallow and have no tags, so the command first runs `git -C third_party/gplugins fetch --depth 1 origin tag <tag>` if the tag is missing.
  2. **Network-on install**, `sandbox.run(..., network=True)`:
     - All state lives in the workdir, because HOME is a 1 GiB tmpfs that disappears between containers. Set `UV_CACHE_DIR=/work/out/uvcache`, `UV_PYTHON_INSTALL_DIR=/work/out/uvpython` and `PIP_CACHE_DIR=/work/out/pipcache`.
     - uv is pinned and hashed, installed from `docker/tcad/build-requirements.lock` (read from `/work/src`) with `/usr/bin/python3 -m pip --require-hashes` into `/work/out/toolvenv`.
     - **v0.8.0:** Python `3.11.17`. Install from `experiments/plugin-history/v080.lock` with `--require-hashes`. The lock was generated once, with `uv pip compile --exclude-newer 2023-09-20T18:00:00Z --exclude-newer-package klayout=2024-04-01T00:00:00Z`, from `-e ./gplugins[devsim,gmsh,tidy3d]`, `pytest` and `"klayout<0.29"`. The klayout exemption is required, because old 0.28 wheels carry 2024 upload dates. The lock keeps the record re-runnable after PyPI yanks.
     - **v1.4.2:** `uv sync --frozen --extra devsim --extra gmsh --extra tidy3d --extra dev`, with the base Python 3.12.
  3. **Network-off run**, `sandbox.run(...)` without network, of the fixed checks with `PDK` unset. These checks may access the network only in step 2; if tidy3d tries to reach the web in step 3, record the failure text.
- Produces: a result JSON (`gf180tcad.io.write_json`, no timings) holding:
  - `versions`, the resolved package versions;
  - `checks`, the pass/fail of each check: `import`, `pin_test`, `ddcomponent_mesh`, `ddsolver`, `ramp`, `refine`. A failed check records its exact exception type and message.
  - `pin`: the contact currents at V = 0 and −1 V of the PINWaveguide ramp. `depletion_width_um` is defined as the width of the region where n and p are both < 1e-2·|NetDoping|, measured along the waveguide-centre cut.
  - `ddcomponent`: the region, contact and interface names; the node count; and the anode/cathode contact currents after `ramp_voltage` to 0.1 and 0.2 V. Task 5 re-verifies these, because this is the path that broke. The PIN path uses DEVSIM's own mesh and still works today.

- [ ] **Step 1:** Write the tests first, sandbox-marked and allowed to be slow.
  - `test_v080_once_worked`:
    - `import`, `pin_test`, `ddcomponent_mesh`, `ddsolver` and `ramp` all pass;
    - `refine` fails with `NameError` (the `c`/`self` bug at `get_solver.py:359`);
    - the numbers are present.
  - `test_v142_import_broken`: the import fails with an `ImportError` naming `fuse_polygons`.
  - Not sandbox-marked: `test_history_json_has_no_timings_or_paths`.

  Run them: they FAIL.
- [ ] **Step 2:** Implement and run, then commit the JSON. This includes `--version v0.8.0 --mesh-scale 0.5` into `v0.8.0-mesh0p5.json`.
  - Two local runs must agree byte for byte.
  - `results/plugin-history` is **not** part of the GitHub crosscheck, because the old stack has no cross-host bit-identity guarantee. The docs say so.
- [ ] **Step 3:** Docs: `docs/limitations/plugin-history.md`, giving the plugin's history (commits `a019e5a`, `0ce7b30`, `017cede`) and the "once worked" evidence. It has a placeholder section, "Re-verified on latest", which Tasks 4 and 5 fill in (spec §3). Requires the docs-links infrastructure on main. Then commit, open the PR, review and merge.

### Fork-task conventions (Tasks 4–8, 15)

- **Verification in the TCAD image, before any submodule bump.** Run the fork worktree as the sandbox workdir:

  `tools/sandbox-run --image "$(cat docker/TCAD_IMAGE)" --workdir /home/tim/github/wafer-space/gplugins-worktrees/<branch> -- env PYTHONPATH=/work/out python -m pytest -p no:cacheprovider gplugins/devsim -m "not tidy3d"`

  `PYTHONPATH=/work/out` puts the worktree ahead of the image's `.pth` entry. Record the log in the PR.
- **Fork CI.** Add a `devsim` job to `test_code.yml` that runs inside the pinned TCAD image: `docker run` of `ghcr.io/mithro/gf180-tcad-tcad@sha256:…`, the digest copied from gf180-tcad's `docker/TCAD_IMAGE` and recorded in the workflow. The fork CI then uses exactly the locked environment and does not resolve a new one. The job uses hosted runners and no secrets.
  - The `docker run` reproduces `tools/sandbox-run`'s container settings (gf180-tcad `tools/sandbox-run:48-61`):
    - `--read-only --tmpfs /tmp:rw,size=1g,exec`, `--network none` and a non-root `--user`;
    - `-e HOME=/tmp/home`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1` and `MKL_NUM_THREADS=1`;
    - `NPY_DISABLE_CPU_FEATURES="X86_V3 X86_V4 AVX512_ICL AVX512_SPR"` (the same list as `sandbox-run:41`);
    - the checkout mounted at `/work/out` (rw) with `PYTHONPATH=/work/out`.

    A comment in the workflow names the gf180-tcad commit the settings were copied from. `PYTHON_CPU_COUNT=1` comes from the image.
- **Physics constants** are those in the Global Constraints table. The fork's material helpers take them as arguments: `gplugins/devsim/materials.py`, `set_silicon(device, region, *, T_K, eps_r, n_i_cm3, mu_n, mu_p, tau_n, tau_p, ...)` and `set_oxide(...)`. `simple_physics.SetSiliconParameters`/`SetOxideParameters` are never called with their defaults.
- **Submodule bumps are batched.** There is one gf180-tcad bump after Task 8 (bump 2 of 3), covering Tasks 4–8 together. Tasks 4–7 do not bump.

### Task 4 (fork): import and test `gplugins.devsim` on latest, no physics change

**Context.** These latest-stack failures are documented:
- `pydantic.Extra`/`Config` (`get_solver.py:24,142`);
- `get_refined_mesh` uses `c` instead of `self` (`:359-371`);
- `delete_device` signature (`:326`);
- silicon models are applied to non-silicon regions (`:220-227`);
- `__init__` imports tidy3d unconditionally;
- the PIN test asserts nothing (`test_devsim.py:20-21`).

**Files (fork):**
- `gplugins/devsim/__init__.py`: lazy-import the tidy3d parts;
- `gplugins/devsim/get_solver.py`;
- `gplugins/devsim/test_devsim.py`: split the DEVSIM-only tests from the tidy3d tests, and register the `tidy3d` marker in `pyproject.toml`;
- `pyproject.toml`: un-exclude devsim; the devsim extra requires Python ≥ 3.13 and `meshwell~=2.5`;
- `.github/workflows/test_code.yml`: the TCAD-image devsim job.

**Interfaces:**
- Produces: `pytest gplugins/devsim -m "not tidy3d"` green in fork CI and inside the TCAD image.

- [ ] **Step 1:** Add real assertions to the PIN test first, as `test_pin_currents_match_v080` and `test_pin_depletion_width_match_v080`. Copy the expected values as constants from gf180-tcad `results/plugin-history/v0.8.0.json` (biases 0 and −1 V; depletion width with the Task 3 definition), and cite the file and gf180-tcad commit in a comment. Run on latest: it FAILS on import.
- [ ] **Step 2:** Fix only what's needed to import and run. Make no physics or default changes; the new material constants come in Task 6.
- [ ] **Step 3:** Run it: it PASSES. The PIN numbers should match v0.8.0 within 1e-6 relative.
  - If DEVSIM 2.6.3 → 2.11.1 moves them more, do not loosen the threshold silently.
  - Record the measured difference and attribute it with evidence, e.g. by reading the same mesh into both DEVSIM versions.
  - Set the tolerance to the justified value in the test, with a comment.
- [ ] **Step 4:** Commit, open the PR (fork), review and merge. Append the numbers to the gf180-tcad "Re-verified on latest" section (Task 3 page) in the after-Task-8 bump PR.

### Task 5 (fork): port `create_2Duz_simulation` meshing to meshwell 2.5

**Context.**
- meshwell 2.5.2 provides `meshwell.orchestrator.generate_mesh(entities, dim, output_mesh, **kw)`. It is a thin pipeline: `cad(...)` → `ModelManager(point_tolerance=...)` → `ensure_initialized` → `load_occ_entities` → `meshwell.mesh.mesh(model=mm, ...)` (`orchestrator.py:185-266`).
  - Its `ModelManager` gets no `n_threads` (`:246`), so gmsh would mesh with `cpu_count()` threads (Global Constraints, Determinism).
  - So the fork **replicates that pipeline**, as `gplugins/devsim/meshing.py::mesh_xsection(...)`, with `ModelManager(n_threads=1, point_tolerance=...)`, `cad(..., n_threads=1)` and `mesh(..., model=mm, n_threads=1, global_scaling=1e-4, gmsh_version=2.2, pre_2d_hook=_pin_gmsh)`.
  - `_pin_gmsh` sets `Mesh.RandomSeed` to a fixed value, `Geometry.OCCParallel=0` and `General.NumThreads=1`. It runs after meshwell's gmsh re-initialisation, so nothing resets it.
- It also provides `resolution_specs` (`ConstantInField`, `ThresholdField`, …).
- DEVSIM 2.11 reads MSH 2.2. Physical names come out as `a___b` and `a___None`.
- The fork's `gplugins/meshwell/get_meshwell_cross_section.py` and `gplugins/femwell/mode_solver.py` `__main__` blocks import the removed `meshwell.cad`.
- gdsfactory 9 cells are locked: use `.copy()` before `trim`, and `gf.boolean` (not `gf.geometry`).

**Files (fork):** `gplugins/devsim/meshing.py` (new), `gplugins/devsim/get_simulation.py`, `gplugins/meshwell/get_meshwell_cross_section.py`, `gplugins/femwell/mode_solver.py`, `gplugins/devsim/tests/test_mesh.py`

**Interfaces:**
- Produces: `create_2Duz_simulation(component, xsection_bounds, layer_stack, resolutions: dict[str, list[ResolutionSpec]], ...) -> DDComponent`.
  - It meshes through `meshing.mesh_xsection` (above), never through `generate_mesh`.
  - For the PN-slab example, it returns the same regions, contacts and interfaces as the v0.8.0 record.
- The interface naming scheme `a___b`/`a___None` is kept and documented.

- [ ] **Step 1:** Write `test_mesh.py` first.
  - `test_pn_slab_names_match_v080`: the PN-slab device has the v0.8.0 region, contact and interface names.
  - `test_pn_slab_currents_match_v080`: the anode/cathode currents after the ramp to 0.1 and 0.2 V match `ddcomponent` in `v0.8.0.json`. The tolerance comes from refining both meshers, taking the larger of the two self-differences:
    - v0.8.0: `v0.8.0.json` against `v0.8.0-mesh0p5.json` (Task 3, `--mesh-scale 0.5`);
    - latest: this port at scale 1 against scale 0.5 of the same `resolutions`. Record the measured values and the tolerance in a comment. Node count is reported but not asserted; the OCC pipeline differs from meshwell 1.0.1.
  - `test_mesh_deterministic`: two builds give byte-identical `.msh` files.
  - `test_gmsh_threads_one`: after `mesh_xsection`, `General.NumThreads == 1`, `Mesh.MaxNumThreads2D == 1`, `Geometry.OCCParallel == 0`, and `Mesh.RandomSeed` equals the pinned value. Run it once with `PYTHON_CPU_COUNT` unset (`env -u PYTHON_CPU_COUNT`), to prove the fork does not rely on the image ENV alone.

  Run them: they FAIL (`NotImplementedError`).
- [ ] **Step 2:** Implement with meshwell 2.5.2. Run the tests: they PASS. Fix the two `meshwell.cad` `__main__` blocks.
- [ ] **Step 3:** Commit, open the PR, review and merge. Record the re-verification numbers for the gf180-tcad Task 3 page; they land in the after-Task-8 bump PR.

### Task 6 (fork): materials, typed contacts, interfaces and the 1D stack builder

**Context.**
- `CreateOxideContact` has no work-function term.
- Both MOSCAPs use a **poly-silicon gate region** (DEVSIM `testing/mos_2d.py` structure), with NGATE doping and an ohmic contact on top. Poly depletion and the gate work function then follow from the physics.
- `workfunction_offset_v` stays in the API for metal gates. Phase 2 uses it only in the parallel-plate and offset tests.

**Files (fork):** `gplugins/devsim/materials.py` (new), `gplugins/devsim/contacts.py` (new), `gplugins/devsim/stack1d.py` (new), `gplugins/devsim/get_simulation.py`, `gplugins/devsim/get_solver.py`, `gplugins/devsim/tests/test_contacts.py`, `gplugins/devsim/tests/test_stack1d.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) LayerRef(layer: tuple[int, int])` and `InterfaceRef(a: str, b: str | None)`. `b=None` means the outer boundary (`a___None`).
  - `LayerRef` is for 2D (a GDS contact layer).
  - In 1D there are no GDS layers. A 1D contact is always `InterfaceRef(<layer name>, None)`, meaning the free end of that `Layer1D`. For example, the gate contact is `InterfaceRef("gate_poly", None)` and the body contact is `InterfaceRef("body", None)`.
  - `create_1d_stack` raises on a `LayerRef`, and on an `InterfaceRef` naming an interior end.
- Produces: `@dataclass(frozen=True) Contact(name: str, location: LayerRef | InterfaceRef, kind: Literal["ohmic", "gate"], workfunction_offset_v: float = 0.0, circuit: bool = False)`.
- Produces: `materials.Constants` (frozen dataclass), with defaults from the Global Constraints table. The fields are `eps0_F_cm`, `q_C`, `kB_J_K`, `eps_si`, `eps_ox`, `T_K`, `n_i_cm3` (computed from `n_i_300_cm3` = 9.65e9 with the table's T-scaling), `mu_n`, `mu_p`, `tau_n_s` and `tau_p_s`. Each field's docstring carries its citation link. Also produces `set_silicon(...)` and `set_oxide(...)`.
- Produces: `@dataclass(frozen=True) Layer1D(name: str, material: Literal["silicon", "oxide"], thickness_um: float, doping: DopingProfile | None)`. DopingProfile comes from Task 7; until then, constants only.
- Produces: `create_1d_stack(name, layers: Sequence[Layer1D], contacts: Sequence[Contact], mesh: Mesh1D, constants: Constants) -> DDComponent`. It builds the device with `devsim.create_1d_mesh`.
  - `Mesh1D(spacing_um: Mapping[str, tuple[float, float]])` gives the start and end spacing per layer, with geometric grading in between.
  - gf180-tcad's `MeshSpec` (Task 9b) maps onto it.
- Produces: interfaces chosen by material pair. Si/oxide and poly/oxide get continuous potential; Si/Si gets drift-diffusion continuity.
- The old `contact_info` dict keeps working through an adapter, with a deprecation note.

- [ ] **Step 1:** Write the tests first:
  - `test_parallel_plate_charge` and `test_parallel_plate_ac`: an oxide-only 1D stack gives C = ε_ox·ε0/t. It is measured through `get_contact_charge` (dQ/dV), and through small-signal AC (`circuit_element` + `solve(type="ac")`, the `testing/ssac_cap.py` pattern). Each agrees within 1e-6 relative (the field is uniform, so this is exact up to solver tolerance).
  - `test_workfunction_offset_shifts_vfb`: on a 1D metal-gate/oxide/p-Si stack, the flat band moves by exactly the offset, within 1 mV. Vfb is the Vg where the gate charge is 0.
  - `test_stack1d_regions_and_spacing`: `create_1d_stack` gives the stated regions, interfaces and contacts, and node spacings within the `Mesh1D` limits, with the grading ratio respected.
  - `test_constants_not_simple_physics_defaults`: the region parameters read back as ε_si = 11.7·ε0, T = 298.15, n_i = 8.266e9 (relative 1e-3), µ_n = 1417, µ_p = 470.5 and τ_n = τ_p = 1e-5.
  - `test_ni_scaling`: `Constants().n_i_cm3` equals the table formula at 298.15 K, and equals 9.65e9 at 300 K, both within 1e-12 relative.
  - `test_poly_gate_flatband`: a p-Si 1.7e17 / 15.2 nm oxide / n⁺ 1e20 poly stack gives the Boltzmann flat band Vfb = −V_t·ln(NGATE·N_A/n_i²) within 1 mV. This is −1.029 V with the Global Constraints constants. The pfet mirror (n-Si 1.7e17 / 15.6 nm / p⁺ 3.6e19) gives +1.003 V.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS. Then commit, open the PR, review and merge.

### Task 7 (fork): doping from analytic profiles

**Context.** `gplugins/process` has Gaussian and skewed-Gaussian implant profiles, which the plugin does not use. Reading `silicon_diffused_gaussian_profile` suggests two bugs, both unconfirmed until tested:
- the exponent is missing a factor of 2 (`diffusion.py:132`);
- the prefactor is missing the µm→cm factor (`:131`).

**Files (fork):** `gplugins/devsim/doping.py`, `gplugins/process/diffusion.py` (fixed only after a failing test proves the bug), `gplugins/devsim/tests/test_doping.py`

**Interfaces:**
- Produces: `DopingProfile` callables `(x_um, y_um) -> cm⁻³` for `constant`, `gaussian(peak, depth, straggle)`, `erfc(surface, xj)` and `lateral(straggle)`.
  - They accept gdsfactory `technology.processes` `ImplantGaussian`/`DopingConstant`.
  - The doping is assigned to DEVSIM `NetDoping` / `Donors` / `Acceptors` node models, as node-model expressions where possible.
  - `Layer1D.doping` and the 2D builder both take a `DopingProfile`.

- [ ] **Step 1:** Write the tests first:
  - `test_dose_conserved`: the integrated dose of the assigned doping equals the input dose within 0.5 %;
  - `test_diffused_equals_gaussian_at_t0`: `silicon_diffused_gaussian_profile` at t=0 equals `silicon_gaussian_profile` (relative 1e-12);
  - `test_uniform_bulk_potential`: a uniform 1.7e17 region gives the analytic bulk potential −V_t·ln(N_A/n_i) within 0.1 mV, using the Task 6 constants.

  Run them: they FAIL wherever a bug exists.
- [ ] **Step 2:** Implement and fix. Run the tests: they PASS. Then commit, open the PR, get it reviewed and merge.

### Task 8 (fork): C–V solver API

**Context.** There are two routes:
- quasi-static: `C = dQgate/dVg`, a central difference of `get_contact_charge`;
- small-signal AC: `ssac_imag`/(−2πf).

The spike failed to converge at relative 1e-12. Use the spec's 1e-10, with extended precision (`extended_solver`, `extended_model`, `extended_equation`).

The inversion response time with only a body contact is ≈ 2·τ_g·N_A/n_i ≈ 2·1e-5 s·2.1e7 ≈ 4e2 s (Nicollian & Brews; τ and n_i from the Global Constraints table). So 1D AC is the HF curve in inversion at any practical frequency.

**Contacts and sources.** Every non-gate contact of the device gets its own voltage source, held at 0 V DC. The gate gets the swept source. Nothing is "tied" by choice, so no contact can be left out of the AC measurement.

**Files (fork):** `gplugins/devsim/cv.py` (new), `gplugins/devsim/tests/test_cv.py`

**Interfaces:**
- Produces: `sweep_cv(device, gate: str, vg: Sequence[float], *, method: Literal["qs", "ac"], freq_hz: float | None = None, dv_qs: float = 1e-3, rel_tol: float = 1e-10, abs_tol: float = 1e-12) -> CVResult`. There is no `tie` argument.
  - **QS:** each grid point is solved at vg ± `dv_qs` and differenced centrally. Neighbouring grid points are never used. Every non-gate contact stays at 0 V.
  - **AC:** the AC excitation is on the gate source only. The AC current of every non-gate source is read.
  - **`abs_tol`:** the DEVSIM `absolute_error` on the potential update, in V.
- Produces: `@dataclass(frozen=True) CVResult`. Its fields:
  - `vg`;
  - `cgg`;
  - `unit: Literal["F/cm^2", "F/cm"]`, depending on mesh dimension;
  - `points: tuple[PointInfo(converged, iterations, rel_error, abs_error), ...]`;
  - `cgx: Mapping[str, tuple[float, ...]]`, for `ac`, keyed by **every non-gate contact**. Here Cxg = −∂Q_x/∂Vg is the charge response of contact x to the gate excitation, read from x's AC current. Charge conservation is Cgg = Σ_{x ≠ gate} Cxg, with the sum over every non-gate contact (spec §5.2: Cgg = −(Cgd + Cgs + Cgb));
  - `method`, `freq_hz`, `dv_qs`.

  Use `solve(..., info=True)` for the per-point info.
- Any non-converged point raises `CVConvergenceError(points: list[float])`. So does a point that converges only at a relaxed tolerance. It never drops or interpolates points.

- [ ] **Step 1:** Write the tests first, on a 1D poly/oxide/Si stack from `create_1d_stack`:
  - `test_qs_equals_ac_low_freq_acc_dep`: QS and AC at 1 Hz agree within 0.1 % for `polarity·vg ≤ Vfb + 0.3 V` (accumulation and depletion only).
  - `test_ac_inversion_is_hf`: at 1 MHz, 1D AC in strong inversion is below QS by more than 30 %. This shows the HF behaviour is understood, not hidden.
  - `test_accumulation_series_exact`: on a **metal-gate** 1D stack (`kind="gate"` contact on the oxide), so that no gate-side capacitance enters, accumulation C equals the series combination of Cox and the exact Poisson–Boltzmann semiconductor capacitance C_s(ψ_s) within 0.5 %. ψ_s is taken from the solution, and C_s comes from the Sze & Ng ch. 4 charge function, with a link. With a poly gate, the n⁺ poly's own accumulation capacitance (≈ 0.3–0.9 % of Cox) would sit inside the tolerance.
  - `test_qs_step_converged`: halving `dv_qs` changes C by less than 0.01 % at every point.
  - `test_nonconvergence_raises`: forcing `rel_tol=1e-16` with a low iteration limit raises `CVConvergenceError`.
  - `test_cgx_sum_2d`: a 1D line cannot carry a third contact, so this test uses a minimal 2D device built directly with `devsim.create_2d_mesh`. It is a rectangle of oxide on p-Si, with a gate contact on top, a body contact at the bottom and one side ohmic contact on n⁺ silicon. At 1 kHz, in depletion and in inversion, Cgg = Σ_{x ≠ gate} Cxg over body and side contacts within 1e-6 relative, and both Cxg are non-zero in inversion. The full S/D case is tested again in Task 11.
  - `test_every_non_gate_contact_sourced`: on the same device, `CVResult.cgx` has exactly the non-gate contact names.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS. Then commit, open the PR, get it reviewed and merge.
- [ ] **Step 3: submodule bump 2 of 3.** Open a gf180-tcad PR that does three things:
  - bumps `third_party/gplugins` to the fork main containing Tasks 4–8;
  - runs the Task 2 tests;
  - fills in the "Re-verified on latest" section of `docs/limitations/plugin-history.md` with the Task 4 and 5 numbers and tolerances.

### Task 9a: process data files and loader (gf180-tcad)

**Context.** These values are taken from the image's card: `/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice`, sha256 `69a7ab87…de8bc8`, as in `docker/base/versions.json`. nfet values are from `.model nfet_06v0.0` and pfet values from `.model pfet_06v0.0` (l.38091). All are tagged `spice-card` and serve as starting points and bounds, never as fixed truths, except where marked *fixed* below.

| Parameter | nfet (card line) | pfet (card line) | Use |
|---|---|---|---|
| TOXE | 15.2 nm (37309) | 15.6 nm (38255) | `t_ox_eff` lower bound and start |
| TOXP | 16.0 nm (37311) | none, = TOXE | basis of the `t_ox_eff` upper bound |
| NDEP | 1.7e17 (37202) | 1.7e17 (38198) | `n_ch` start |
| K1 | 0.9 (37147) | 0.9588 (38162) | `n_ch` lower bound (below) |
| NGATE | 1e20 (37204) | 3.6e19 (38200) | poly-gate doping, *fixed* |
| XJ | 0.15 µm (37377) | 0.15 µm (38291) | S/D depth, 2D |
| DLC | 54 nm (37104) | 7.4 nm (38129) | 1D area bookkeeping, *fixed* |
| CGSO=CGDO | 1e-10 F/m (37089) | 7.71e-11 F/m (38117) | 1D parasitics, *fixed* |
| CGSL=CGDL | 1.5e-10 F/m (37088) | 5.25e-11 F/m (38116) | 1D parasitics, *fixed* |
| CF | none: BSIM4 default 2·ε_ox/π·ln(1+4e-7/TOXE) ≈ 7.3e-11 F/m | the same | 1D parasitics, *fixed* |
| TNOM | 25 °C (37308) | 25 °C (38254) | T = 298.15 K |
| EPSROX | 3.9 (37126) | 3.9 (38144) | ε_ox |
| ACDE | 0.3 (37397) | 0.7 (38095) | charge-centroid allowance Δ (below) |
| MOIN | 15 (37201) | 15 (38197) | charge-centroid allowance Δ (below) |

**Card values are expressions at TT.** Several card entries are expressions in corner parameters, e.g. `toxe='1.52e-008+nfet_06v0_tox'` and `cgso='1e-010*nfet_06v0_cgso'`.
- The stated values are the expressions evaluated with the `.param` values of the card's `.lib typical` section, which starts at card l.105 (e.g. `nfet_06v0_tox=0` at l.114, `nfet_06v0_cgso=1` at l.115, `pfet_06v0_dtox=0` at l.127, `pfet_06v0_dcgso=1` at l.129).
- The TOML `source` cites both the model line and the `.param` line.
- The evaluator handles only `number`, `+`, `*` and parameter names, and raises on anything else.

**Calibration tunables (3 of the 8-parameter budget per device type).** These are written into the TOML files here, with numeric bounds, before any fit. Task 12 only reads them.

| Name | Start (n / p) | Bounds (n / p) | `bounds_source` |
|---|---|---|---|
| `t_ox_eff_nm` | TOXE: 15.2 / 15.6 | lower: TOXE, 15.2 / 15.6. Upper: TOXP + Δ, i.e. 16.0 + Δ_n / 15.6 + Δ_p | TOXE/TOXP card lines, and Δ below |
| `n_ch_cm3` | NDEP: 1.7e17 / 1.7e17 | lower: 0.5 × the K1-implied doping N = (K1·Cox(TOXE))²/(2·q·ε_si·ε0), i.e. 6.30e16 / 6.78e16. Upper: 2 × NDEP = 3.4e17 | lower: K1 and TOXE card lines plus the BSIM4 K1 definition ([BSIM4 manual](https://bsim.berkeley.edu/models/bsim4/)). Upper: the factor of 2 is a **project choice**; no public channel profile exists. |
| `dv_fb_v` | 0 | −0.2 / +0.2 V | **Project choice.** It is a lumped flat-band offset (below). |

- **Δ, the charge-centroid allowance only.** Poly depletion is never part of Δ: the poly-gate region simulates it directly (Task 6). Δ is computed here, before any fit:
  - Take the BSIM4 v4.5 charge-thickness (CTM, `capMod=2`) centroid X_DC: the `Tcen` expressions, which use ACDE (accumulation/depletion) and MOIN, NDEP, TOXP, VTH0 and the surface potential (inversion). Cite the BSIM4 v4.5 manual's charge-thickness model section, quoting its equation numbers ([BSIM4 manual](https://bsim.berkeley.edu/models/bsim4/)).
  - Evaluate X_DC with the TT card values over the cv sweep range (|Vg| ≤ 5 V).
  - Set Δ = max over biases of X_DC·ε_ox/ε_si, rounded up to 0.01 nm.
  - The calculation is a small committed function, `process.centroid_allowance_nm(card_values, constants)`, with a hand-checked unit test. The docs show the numbers.
  - **Fallback:** if the CTM equations cannot be evaluated from public information, Δ = 0.5 nm. It is then labelled a **project choice** in `bounds_source`, and the docs say why.
- **Expected outcome.** The SPICE slopes (Task 9b) imply a total CET of 16.4/16.6 nm (nfet acc/inv) and 15.7/16.7 nm (pfet). Those CETs already include poly depletion and the classical Si accumulation/inversion layer, which the model simulates (≈ 0.2 nm each; ≈ 0.5 nm for the p⁺ 3.6e19 poly). So the oxide actually needed is ≈ 16.2 nm for the nfet and ≈ 15.5–16.0 nm for the pfet. The pfet accumulation side may hit the TOXE lower bound: that is a reported result, not a failure.
- **`dv_fb_v` is a lumped offset.** It is applied as a rigid gate-bias shift, `vg_device = vg − dv_fb_v` (Task 9b), which is exact for a 1D MOSCAP. It lumps together:
  - Boltzmann statistics in the degenerate gate (≈ 40 mV, Global Constraints);
  - SPICE's empirical flat band;
  - interface and fixed charge.

  It is **not** a fixed-oxide-charge parameter. For scale only: 3e11 cm⁻² of charge at the interface would shift Vfb by q·Q/Cox = 0.21 V.

The *fixed* rows are **reference-model bookkeeping**, tagged `spice-card (reference bookkeeping, fixed)`:
- They describe how BSIM4 splits the SPICE Cgg into an intrinsic part and extrinsic parts. They are not process data.
- They apply only to the 1D comparison (Task 12), never to 2D, where S/D geometry gives the overlap physically.
- They are listed separately and do not count against the 8-parameter budget. The docs state this, with the reason.

NGATE is a fixed doping input of the poly-gate region; it is not calibrated.

The pfet NSD of 6e16 (38207) has no clear physical meaning and is **not** used. The pfet S/D doping in 2D is `sd_peak_cm3` = 1e20, tagged `literature` (Task 11 gives the citation and a sensitivity test).

**Files:** `data/process/nfet_05v0.toml`, `data/process/pfet_05v0.toml`, `src/gf180tcad/tcad/__init__.py` (`TCAD_IMAGE` constant, `provenance()`), `src/gf180tcad/tcad/process.py` (loader, card-expression evaluator, `centroid_allowance_nm`), `tests/tcad/test_process.py`

**Interfaces:**
- **TOML schema.** Each parameter is a table with these keys:
  - `value`, `unit`;
  - `provenance` ∈ {`pdk-doc`, `spice-card`, `literature`, `calibrated`};
  - `source` (a URL, or `sm141064.ngspice:<line>` plus the card sha256);
  - `fixed: bool`, and `bounds = [lo, hi]` with `bounds_source` for tunables;
  - `note`.

  The files are read with stdlib `tomllib`, so no new dependency is needed. These files never hold calibrated values; those live in `results/tcad/calibration/*.json` (Task 12).
- Produces: `process.load(device: str) -> ProcessDescription`, a frozen dataclass. It validates:
  - the tags;
  - that bounds exist for every non-fixed parameter;
  - lo ≤ start ≤ hi;
  - that every `source` is a link or a card-line reference.

  `ProcessDescription.with_values(mapping) -> ProcessDescription` returns a copy with tunables replaced. It raises if a value is outside the bounds or names a fixed parameter.

- [ ] **Step 1:** Write the tests first:
  - `test_card_values_and_lines`: every card-line citation, re-read from the card in the base image (sandbox-marked), holds the stated value once evaluated with the TT `.param` values;
  - `test_card_expression_evaluator`: hand cases (`'1.52e-008+nfet_06v0_tox'` with tox=0 gives 1.52e-8; an unknown operator raises);
  - `test_tunables_present`: both files hold exactly `t_ox_eff_nm`, `n_ch_cm3` and `dv_fb_v` as non-fixed parameters, with numeric bounds;
  - `test_k1_bound_recomputed`: the `n_ch_cm3` lower bound equals 0.5·(K1·Cox(TOXE))²/(2·q·ε_si·ε0), recomputed from the card values and the Global Constraints constants (relative 1e-6);
  - `test_centroid_allowance`: `centroid_allowance_nm` matches a hand-evaluated bias point, and the TOML upper bound equals TOXP + Δ. Under the fallback, the test asserts Δ = 0.5 and the "project choice" label;
  - `test_bounds_enforced`;
  - `test_fixed_cannot_change`;
  - `test_no_calibrated_values_in_data`.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS. Then commit, open the PR, get it reviewed and merge.

### Task 9b: 1D MOSCAP and `MeshSpec` (gf180-tcad)

**Context.**
- **SPICE targets, W10/L10 TT:**
  - nfet: 212.26 fF in accumulation, 212.51 fF in inversion, minimum 80.14 fF at 0.4 V;
  - pfet: 222.43 / 210.28 fF.
- **Intrinsic per-area C.** The SPICE slope (Cgg(L10) − Cgg(L2))/(8 µm·W) does not depend on DLC or the parasitics. Values from `results/spice/ngspice/typical/*/w10p0_l{10p00,2p00}/metrics.json`:
  - nfet: 2.106 (acc) / 2.083 (inv) fF/µm²;
  - pfet: 2.195 / 2.064 fF/µm².
- **Hand checks:**
  - Cox(15.2 nm) = 2.2718 fF/µm² (exact ε0);
  - area (L − 2·DLC)·W = 98.92 µm²;
  - 224.73 fF for W10/L10.

**Files:** `src/gf180tcad/tcad/mesh.py` (MeshSpec), `src/gf180tcad/tcad/moscap1d.py`, `src/gf180tcad/tcad/__main__.py`, `src/gf180tcad/tcad/analytic.py` (exact Poisson–Boltzmann reference), `src/gf180tcad/tcad/__init__.py` (adds `TCAD_GENERATOR_MODULES`), `tests/tcad/test_mesh.py`, `tests/tcad/test_moscap1d.py`, `tests/tcad/test_analytic.py`, `tests/tcad/test_tcad_provenance.py`

**Interfaces:**
- Produces: `TCAD_GENERATOR_MODULES` and the two provenance tests, as specified in the Global Constraints ("Result files"). This task creates `tests/tcad/test_tcad_provenance.py`. Tasks 10, 11 and 12 extend the module list when they add modules, and the import-graph test fails if they do not.
- Produces: `@dataclass(frozen=True) MeshSpec(h_poly_nm, h_ox_nm, h_si_surface_nm, h_si_bulk_nm, grading)` and `MeshSpec.scaled(r)`.
  - `h_poly_nm` is the spacing at the poly/oxide interface, graded into the poly bulk. Poly depletion contributes to C in inversion, so the poly is refined with everything else.
  - `grading` is the maximum ratio between neighbouring spacings.
  - `scaled(r)` multiplies every h by r and keeps `grading` fixed. This is the "uniform refinement" of spec §5.2.
  - `MeshSpec.to_mesh1d(layers) -> gplugins.devsim.Mesh1D`.
  - `MeshSpec.to_resolution_specs(...)` gives meshwell `ConstantInField(h_ox)` on the oxide, `ThresholdField(sizemin=h_si_surface, sizemax=h_si_bulk, distmax=…)` on the Si/oxide interface curve, and `ThresholdField(sizemin=h_poly, …)` on the poly/oxide curve. It is used in Task 11.
  - `MeshSpec.DEFAULT_1D` is a fixed starting spec. Task 10 replaces it with the selected converged level, and from then on every 1D result uses `results/tcad/meshconv/moscap1d/<device>/selected.json`.
- Produces: `@dataclass(frozen=True) MoscapCV(device, vg, c_per_area_ff_um2, points, method, constants, mesh)`.
  - `area_scaled(geometry) -> (vg, cgg_intrinsic_ff, cgg_parasitic_ff, cgg_total_ff)`.
  - The area is `(L − 2·DLC)·W`, for 1D only. The parasitic term is reported separately and never folded in silently.
  - The parasitic term is computed with the **exact BSIM4 v4.5 capMod=2 overlap equations** (CGSO, CGSL, CKAPPAS, VFBCV) plus CF, citing the BSIM4 manual section ([BSIM4 manual](https://bsim.berkeley.edu/models/bsim4/)).
  - It is cross-checked against the SPICE intercept: the L10/L2 fit implies ≈ 4.0 fF at W10 for the nfet, against 3.45–6.45 fF from the card.
- Produces: `moscap1d.simulate(proc, *, vg, method="qs", mesh: MeshSpec, rel_tol=1e-10) -> MoscapCV`.
  - It builds with `gplugins.devsim.create_1d_stack`, using an n⁺ (nfet) or p⁺ (pfet) poly-gate region at NGATE, then oxide (`t_ox_eff_nm`), then uniform silicon at `n_ch_cm3`. The contacts are `InterfaceRef("gate_poly", None)` and `InterfaceRef("body", None)`.
  - It sweeps with `gplugins.devsim.sweep_cv`, applying `dv_fb_v` as a **rigid gate-bias shift**: the device is solved at `vg − dv_fb_v`, and the result is reported at `vg`. This is exact for a 1D MOSCAP. Task 11 uses the same shift in 2D.
  - `CVResult` is converted from F/cm² to fF/µm² (1 F/cm² = 1e7 fF/µm², one helper, unit-tested).
- Produces: `analytic.lf_cv_uniform(n_cm3, t_ox_nm, gate_doping, vg, constants) -> c_per_area`. It is the exact 1D Poisson–Boltzmann low-frequency C–V, built from the semiconductor charge function Q_s(ψ_s) (Sze & Ng, *Physics of Semiconductor Devices*, 3rd ed., ch. 4, [doi:10.1002/0470068329](https://doi.org/10.1002/0470068329)), solved to 1e-12. Poly depletion is included by applying the same charge function to the gate.
- Produces: CLI `python -m gf180tcad.tcad moscap --device D --dim 1 --params start|calibrated --out ROOT` (host), and `moscap-job` (in the image).
  - `ROOT` is the tree root, e.g. `results/tcad/moscap1d`.
  - `--params calibrated` loads `results/tcad/calibration/<device>.json`, and refuses if it is absent.
  - The command writes:
    - `ROOT/<device>/<params>/per_area.csv` (vg, c_per_area, rel_error, iterations);
    - `ROOT/<device>/<params>/per_area.meta.json` (including the MeshSpec used);
    - `ROOT/provenance.json`, the one per tree root (Global Constraints).

  Per-geometry values are derived from `per_area.csv` by `area_scaled`; they are not separate simulations. The job `moscap1d/<device>/start` holds the spice-card start values and `moscap1d/<device>/calibrated` the Task 12 values, so start results are never mistaken for calibrated ones.

- [ ] **Step 1:** Write the tests first:
  - `test_units`: Cox(15.2 nm) = 2.2718 fF/µm² and W10/L10 = 224.73 fF, both within 1e-4 relative, with the Global Constraints constants. Also check the F/cm² → fF/µm² conversion.
  - `test_matches_exact_poisson_boltzmann`: for uniform doping, the TCAD QS curve matches `analytic.lf_cv_uniform` within 0.1 % at every bias, including flat band and the LF minimum. The depletion approximation is **not** a reference, because its Cmin is an HF quantity and is off by several percent.
  - `test_flatband_exact`: at flat band, C = series(Cox, ε_s/L_D) within 0.1 %.
  - `test_mirror`: stack B (n-body N, p⁺ gate) gives C_B(vg) = C_A(−vg) within 1e-9 relative, where stack A is a p-body N with an n⁺ gate at the same |N|, NGATE and t_ox.
  - `test_parasitics_match_spice_intercept`: within 25 %. This is a sanity check of the BSIM4 bookkeeping only.
  - `test_dv_fb_rigid_shift`: C(vg; dv_fb = 0.1) = C(vg − 0.1; dv_fb = 0) within 1e-12 relative.
  - `test_mesh_poly_refined`: `scaled(0.5)` halves the poly spacing too.
  - `test_byte_identical` (sandbox): two runs give byte-identical outputs.
  - `tests/tcad/test_tcad_provenance.py` (see Interfaces).

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS. Commit the `moscap1d/<device>/start` results, run `make manifest`, then open the PR, get it reviewed and merge.

### Task 10: mesh-convergence tooling

**Context.** In the spike, depletion C moved by 2 % between meshes a and b. Spec §5.2 requires that uniform refinement changes every metric by less than 1 %.

**Files:** `src/gf180tcad/tcad/meshconv.py`, `src/gf180tcad/tcad/__main__.py` (the `meshconv` commands), `src/gf180tcad/tcad/__init__.py` (extend `TCAD_GENERATOR_MODULES`), `tests/tcad/test_meshconv.py`, `results/tcad/meshconv/moscap1d/**`, `docs/limitations/` (page section; requires the docs-links infrastructure on main)

**Interfaces:**
- Consumes: `MeshSpec` (Task 9b).
- Produces: `class CVCurve(Protocol)` with the attributes `vg: tuple[float, ...]`, `c_per_area_ff_um2: tuple[float, ...]` and `node_count: int`. Both `MoscapCV` (Task 9b) and `MoscapCV2D` (Task 11) satisfy it.
- Produces: `converge(simulate: Callable[[MeshSpec], CVCurve], spec: MeshSpec, levels=(1, 2**-0.5, 0.5, 2**-1.5)) -> ConvergenceReport`.
- Produces: CLI `python -m gf180tcad.tcad meshconv --device D --dim 1|2 --out ROOT` (host; `ROOT` = `results/tcad/meshconv`), and `meshconv-job` (in the image).
  - It writes `ROOT/moscap{1d,2d}/<device>/report.json`, plus `selected.json` (the selected `MeshSpec`), plus `ROOT/provenance.json`.
  - It always uses the spice-card start values.
  - The 2D levels run as separate sandbox jobs under the admission check (jobs × mem ≤ 128 GiB).
- The report holds, per level:
  - the curves;
  - node counts;
  - the max relative change against the next finer level, at every bias;
  - the Richardson estimate;
  - the observed order p = log(|C₁−C₂|/|C₂−C₃|)/log(√2), per bias and as a median.

  It also holds the selected level, which is the coarsest with < 1 % at every bias. Solver tolerance, `dv_qs` and the constants are fixed across levels. Runtimes are kept out of the JSON.

- [ ] **Step 1:** Write the tests first:
  - `test_converges_to_exact`: on a uniform-doping 1D case, the finest level matches `analytic.lf_cv_uniform` within 0.05 %, and the median observed order is between 1.5 and 2.5;
  - `test_selected_level_criterion`: the selected level is < 1 % against the next finer one;
  - `test_report_deterministic`: the report JSON is deterministic.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS.
- [ ] **Step 3:** Run `meshconv --dim 1` for both devices. Commit `results/tcad/meshconv/moscap1d/**`. If the selected spec differs from `MeshSpec.DEFAULT_1D`, regenerate `results/tcad/moscap1d/<device>/start` with it. Then run `make manifest`.
- [ ] **Step 4: 1D C/Cox check.** Show that 1D C/Cox < 1 at |Vg| = 5 V. Classical accumulation and inversion add a series capacitance, so C/Cox > 1 is impossible in 1D. This isolates the spike's artefact to 2D. The artefact itself is diagnosed in Task 11.
- [ ] **Step 5:** Commit, open the PR, get it reviewed and merge.

### Task 11: 2D MOSCAP from gdsfactory geometry, and the C/Cox > 1 artefact

**Context.**
- `gf180mcu.cells` `nfet(volt="5.0V")` and `pfet(volt="5.0V")` build under gdsfactory 9.51 and contain Dualgate `(55,0)`. These are the devices the SPICE reference describes. `cap_mos` is a different device with its own SPICE model, and is not used.
- The gf180mcu LayerStack is illustrative (`gf180mcu/layers.py:121-`), with no gate oxide and no doping, so the vertical stack comes from `data/process/*.toml`.
- Spike evidence for the artefact (research §5.4):
  - At 15.2 nm, C/Cox is 1.0039 at −5 V.
  - With the same structure at 16 nm, it is 0.9909. These disagree by about 1.3 %, which points to normalisation or contact area rather than physics.
  - Candidates: contact-charge discretisation at the oxide/contact corner nodes, side boundaries, and statistics (DEVSIM ships `python_packages/fermi_physics.py`).

**Files:** `src/gf180tcad/tcad/stack.py`, `src/gf180tcad/tcad/moscap2d.py`, `src/gf180tcad/tcad/__init__.py` (extend `TCAD_GENERATOR_MODULES`), `data/process/pfet_05v0.toml` (adds `sd_peak_cm3`), `tests/tcad/test_moscap2d.py`, `results/tcad/meshconv/moscap2d/**`, `results/tcad/moscap2d/<device>/start/**`, `docs/limitations/` (artefact section)
- `stack.py` builds a gdsfactory LayerStack plus a `DopingProfile` from a `ProcessDescription`. It **requires Dualgate `(55,0)` over the gate** to select the thick oxide, and raises otherwise (cf. spec §7, ISHI).

**Interfaces:**
- Produces: `moscap2d.simulate(proc, geometry: devices.Geometry, *, vg: Sequence[float], with_sd: bool, method: Literal["qs", "ac"], mesh: MeshSpec, freq_hz: float | None = None, rel_tol: float = 1e-10) -> MoscapCV2D`.
  - `MoscapCV2D` satisfies Task 10's `CVCurve` protocol, and also carries `cgx` (from `CVResult.cgx`) and the geometry.
  - `dv_fb_v` is applied as the same rigid gate-bias shift as in 1D (Task 9b).
  - It builds the cell `nfet`/`pfet(volt="5.0V", w_gate=geometry.w_um, l_gate=geometry.l_um)` and cuts a uz cross-section across the gate (along L).
  - The device is built through `gplugins.devsim.create_2Duz_simulation`, with the Task 6 contacts and Task 7 doping, using `MeshSpec.to_resolution_specs`. Meshing goes through the fork's single-thread `mesh_xsection` (Task 5).
  - Per-area values use the drawn L·W; DLC and the parasitics are never applied in 2D.
  - When `with_sd` is true:
    - the nfet uses n⁺ S/D at NSD 1e20 (`spice-card`, `sm141064.ngspice:37217`), with XJ 0.15 µm and Gaussian lateral straggle;
    - the pfet uses p⁺ S/D with `sd_peak_cm3` = 1e20, XJ 0.15 µm (card l.38291) and the same straggle model. The peak is tagged `literature`: Plummer, Deal & Griffin, *Silicon VLSI Technology* (Prentice Hall, 2000), ch. 2, the CMOS process flow's p⁺ S/D implant. The PR quotes the page. The value is not load-bearing for C–V, which `test_pfet_sd_doping_insensitive` shows;
    - source, drain and body are all non-gate contacts, so `sweep_cv` holds each at 0 V with its own source (Task 8). A 1 MHz AC run can therefore supply the inversion charge from S/D. The channel RC time at L10 is ~1e-9 s.
- CLI `python -m gf180tcad.tcad moscap --device D --dim 2 --params start|calibrated --geometry <gid> --out results/tcad/moscap2d` (host), and `moscap-job` (image).
  - It writes `results/tcad/moscap2d/<device>/<params>/<gid>/cv.csv`, `cgx.csv` and `mesh.msh` (the mesh picture source for Task 13a).
  - It writes `results/tcad/moscap2d/provenance.json` at the tree root.

- [ ] **Step 1:** Write the tests first:
  - `test_2d_equals_1d_without_sd`: with S/D removed, a uniform stack, and a gate spanning the full domain with Neumann sides (no gate-edge fringe), 2D Cgg per area equals the 1D result within 0.5 %.
  - `test_ac_1mhz_recovers_inversion`: with S/D, 1 MHz AC recovers to inversion as SPICE does (C_inv/C_acc > 0.9).
  - `test_charge_conservation`: Cgg = Σ_{x ≠ gate} Cxg over **every non-gate contact** (body, source, drain), within 0.1 % (spec §5.2). The set of summed contacts equals the device's non-gate contact list.
  - `test_pfet_sd_doping_insensitive`: pfet Cgg changes by < 0.1 % at every bias for `sd_peak_cm3` in {5e19, 1e20, 2e20}.
  - `test_2d_mesh_converged`: the mesh is converged per Task 10 (< 1 %).
  - `test_dualgate_required`: `stack.py` raises if Dualgate is missing.
  - `test_byte_identical` (sandbox): two runs give byte-identical results.
  - `test_c_over_cox_le_1`: 2D C/Cox ≤ 1 at |Vg| = 5 V without S/D, after the artefact fix.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Diagnose the C/Cox > 1 artefact from evidence: fix the cause, or document it with numbers if it is below tolerance and explained. Never paper over it.
- [ ] **Step 3:** Run `meshconv --dim 2` for both devices, then the `start` 2D runs at the calibration geometries with the selected spec. Expect hours at the finest level; the spike's failures to converge at r ≤ 1/4 were at 1e-12, and this study uses 1e-10. Commit the results, run `make manifest`, then open the PR, get it reviewed and merge.

### Task 12: calibrate against SPICE Cgg–Vg

**Context.**
- At TOXE 15.2 nm, effective oxide is the dominant knob.
- Poly depletion is now physical: the poly-gate region at the fixed NGATE.
- Quantum confinement (≈ 2–3 %) is not modelled. DEVSIM 2.11.1 has **no built-in** density-gradient model: its `python_packages` hold only `simple_physics`, `mos_physics`, `fermi_physics`, `Klaassen`, `model_create`, `simple_dd`, `ramp` and `pythonmesh`. A custom-equation DG model (Ancona–Iafrate) is possible but deferred, so confinement is folded into `t_ox_eff` and documented.
- The SPICE intrinsic slope (Task 9b) needs t_eff ≈ 16.4 / 16.6 nm (nfet acc / inv) and 15.7 / 16.7 nm (pfet acc / inv) under classical physics. So `t_ox_eff` may legitimately exceed TOXP.

**Calibrated parameters (3 of the 8-parameter budget per device type):**

| Parameter | Start | Bounds | Bounds source |
|---|---|---|---|
| `t_ox_eff_nm` | TOXE | lower: TOXE (15.2 n / 15.6 p) | `spice-card` |
| | | upper: TOXP + Δ_centroid+poly | Δ is **TBD in Task 12 from a cited source**. Candidate: the BSIM4 v4.5 charge-centroid (ACDE, MOIN) and poly-depletion equations evaluated with the card values ([BSIM4 manual](https://bsim.berkeley.edu/models/bsim4/)). |
| `n_ch_cm3` | NDEP 1.7e17 | lower: 0.5 × the K1-implied doping, N = (K1·Cox)²/(2·q·ε_si) → 6.3e16 n, 6.8e16 p | K1 and NDEP from the card (Task 9a lines), and the BSIM4 K1 definition |
| | | upper: 2 × NDEP = 3.4e17 | The factor of 2 is a stated project choice; no public channel profile exists. |
| `dv_fb_v` | 0 | ±0.2 V | Shift from fixed oxide charge, Q_f ≤ ~3e11 cm⁻²: q·Q_f/Cox ≈ 0.21 V. Source: Sze & Ng ch. 4 ([doi:10.1002/0470068329](https://doi.org/10.1002/0470068329)) [verify]. |

The work function itself comes from the poly-gate physics, not from a parameter. The fit **must report** any parameter within 1e-3 of a bound; hitting a bound is published, not hidden.

**Agreement metric (spec §5.2, Cgg ≤ 5 %).** Regions are defined in `u = polarity·vg`, using SPICE's own curve:
- **accumulation plateau:** u ≤ u_fb − 1.0 V;
- **inversion plateau:** u ≥ u_t + 1.0 V.

Here u_fb is the u at which SPICE C = 0.9·C_acc(u = −5), and u_t is the u at which SPICE C, rising from its minimum, reaches (Cmin + C_inv)/2. Both are computed once from the TT ngspice curve and recorded.
- **Plateau metric:** max |ΔCgg|/Cgg_SPICE over each plateau, ≤ 5 % each.
- **Transition:** the voltage shift ΔV at C = (Cmin + Cacc)/2, between the TCAD and SPICE curves, ≤ 50 mV. This is a **proposal; no published standard exists**, and it is labelled as such in the docs.
- **"Same process" window:**
  - Plateaus use the per-bias corner envelope, built from the five corners' `results/spice/ngspice/<corner>/<device>/<gid>/cv.csv` (`gf180tcad.calibrate.envelope_cv`, pure min/max).
  - Plateau per-area values are also checked against the public 6 V Cox spec, 1.8/2.3/2.8 fF/µm². It is added to `data/pdk_elec_spec.json` as a new entry for both devices, with `metric: "cox_ff_per_um2"`, taken from the public gf180mcu-pdk.readthedocs.io electrical-spec page that lists the 6 V Cox (design spec §4). The entry carries its own `source_url` and section, because the existing top-level `source_url` is the 5 V page (`elec_specs_3.html`).
  - `specwindow.window(metric, spec, envelope)` combines them. `specwindow.py` itself is not modified.
- Xyce has no CV analysis, so the spec's 0.5 % engine check cannot apply to Cgg. ngspice is the only Cgg reference, and the docs say so.

**Files:**
- `src/gf180tcad/calibrate/__init__.py`, `src/gf180tcad/calibrate/cv.py`, `src/gf180tcad/calibrate/__main__.py`;
- `data/pdk_elec_spec.json` (the Cox entry; `specwindow.load_spec` reads it unchanged). The SPICE spec-check page (`docgen._spec_status`) and `tests/test_specwindow.py` must handle a metric that SPICE does not extract: list it as "TCAD only", with a test;
- `results/tcad/calibration/{nfet_05v0,pfet_05v0}.json`, `results/tcad/validation/{nfet_05v0,pfet_05v0}.json`;
- `tests/test_calibrate_cv.py`.

`data/process/*.toml` is **not** written: calibrated values live only in `results/tcad/calibration/*.json`.

**Interfaces:**
- Produces: `calibrate_cv(device, *, geometries: Sequence[Geometry], params=("t_ox_eff_nm", "n_ch_cm3", "dv_fb_v")) -> CalibrationResult`. Bounds come from `process.load(device)`.
  - **Guards that raise `CalibrationLeak`:**
    - any geometry has `role != "calibration"` (`devices.Geometry.role`; the calibration set is W10 at L = 10, 2 and Lmin, `devices.py:152-166`);
    - any target is not the TT ngspice `cv` sweep;
    - any parameter is not a non-fixed tunable.
  - **Model:** 1D (`moscap1d`) at the three calibration geometries, through `area_scaled`, with the fixed DLC and parasitic bookkeeping (Task 9b). Lmin is dominated by that bookkeeping, and the docs say so.
  - **Optimiser:** `scipy.optimize.least_squares(method="trf", jac="2-point")`.
    - The residuals are the plateau relative errors at every grid point, plus the transition ΔV scaled by 50 mV.
    - `x0` is the start values; `x_scale`, `diff_step=1e-4`, `ftol=xtol=gtol=1e-10` and `max_nfev=200` are fixed.
    - It runs in the sandbox via `python -m gf180tcad.calibrate run` (host) and `calibrate-job` (image).
  - `CalibrationResult` holds:
    - the values;
    - the bound hits;
    - `budget_used = 3` of 8;
    - the geometries used;
    - per-region residuals;
    - the verdict per spec §5 (Agree / Same process / Disagree, with the window and its `source`);
    - `param_sha256`, a hash of the sorted values that freezes the result.
- Produces: `validate_cv(device, frozen: CalibrationResult) -> ValidationResult`.
  - It runs at the held-out geometries (L = 0.7, 1, and 1.6/0.7) and, for the 2D check, at the calibration geometries too.
  - It raises unless `frozen` was loaded from the committed `results/tcad/calibration/<device>.json`, and its `param_sha256` matches that file.
  - It records the hash. Results at 1.6/0.7 and Lmin are pre-tagged with the causes `geometry-2d` and `spice-fit`.

- [ ] **Step 1:** Write the tests first, on synthetic data built from the 1D model:
  - `test_recovers_known_params`: `t_ox_eff` and `n_ch` within 0.5 %, and `dv_fb` within 1 mV absolute;
  - `test_validation_geometry_raises`: passing any `role="validation"` geometry raises `CalibrationLeak`;
  - `test_non_cv_target_raises`;
  - `test_fixed_param_raises`;
  - `test_bounds_enforced_and_hits_reported`;
  - `test_validate_requires_frozen_hash`: an edited value raises;
  - `test_deterministic`: two fits are byte-identical;
  - `test_envelope_cv`;
  - `test_metric_regions`: hand-built curves exercise the plateau and ΔV logic.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS.
- [ ] **Step 3:** Fix Δ (the `t_ox_eff` upper bound) from the cited source, and record the calculation in the docs. Calibrate both devices at TT, with ngspice as the reference.
  - Target: both plateaus ≤ 5 %, and the transition ΔV ≤ 50 mV.
  - If the target is not reached within budget, publish the best fit with its verdict and the §6 mismatch analysis. Never raise the budget silently.
- [ ] **Step 4:** Commit `results/tcad/calibration/*.json` in a results-only commit. **Only then** run `validate_cv` and commit `results/tcad/validation/*.json` in a separate later commit. Regenerate the calibrated 1D and 2D result trees (`results/tcad/moscap{1d,2d}/<device>/calibrated/`), and run `make manifest`. Then open the PR, get it reviewed and merge.
- [ ] **Budget note (Phase 3 carry-over).** These 3 parameters use 3 of the 8 per device type for all later phases. A Phase 3 channel profile may replace the uniform `n_ch` and must re-justify it.

### Task 13a: TCAD results and docs pages

Requires the docs-links infrastructure on main.

**Files:**
- `src/gf180tcad/docgen.py` (not a generator module). It renders MOSCAP pages from the committed `results/tcad/**` only:
  - the TCAD vs ngspice Cgg–Vg overlay, with the per-bias corner envelope;
  - the 1D intrinsic and parasitic split;
  - mesh-convergence plots;
  - **mesh pictures** of the 2D cross-section (spec §10b), rendered from the committed mesh file;
  - the parameter table, with provenance, bounds, bound hits and budget use. The fixed reference-bookkeeping rows are listed separately.
  - verdicts per plateau, the transition ΔV, and the validation geometries.
- `docs/results/`, `docs/comparison/`.
- `docs/limitations/`, which states:
  - QS vs HF;
  - no built-in density-gradient model in DEVSIM 2.11.1, with the effective-oxide folding;
  - the poly-gate treatment;
  - that DLC and the parasitics are reference bookkeeping;
  - that Xyce has no CV analysis;
  - that the ΔV ≤ 50 mV transition tolerance is a proposal;
  - that `results/plugin-history` is not cross-checked.
- `docs/conf.py:_TOOLS` gains the new tools; `docs/glossary.md` gains the new terms.
- `tests/test_docgen.py`.

- [ ] **Step 1:** Write the tests first:
  - `test_moscap_page_per_device_geometry`;
  - `test_moscap_pages_deterministic`;
  - `test_docs_build_offline`;
  - `test_doc_links` covers the new pages.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS. Commit, open the PR, get it reviewed (including the dedicated missing-links review), and merge.

### Task 13b: `make reproduce` and the TCAD cross-host check

**Context.**
- `manifest.load_subset` accepts only 4-part `<engine>/<corner>/<device>/<geometry_id>` jobs, and expands `all` from the SPICE plan (`manifest.py:94-121`).
- `verify_subset` always requires a root `provenance.json` (`:139-170`).
- `manifest.py` is not a generator module, so it may change.

**Files:**
- `src/gf180tcad/manifest.py`: generalise the subset parser. A `kind` argument (`spice` | `tcad`) selects the job shape. TCAD jobs are `moscap1d/<device>`, 2 parts under the prefix `tcad/`; the SPICE behaviour is unchanged.
- `tests/crosscheck_tcad_subset.txt` (the coarse 1D MOSCAP set, both devices, calibrated);
- `tests/test_manifest_subset.py`;
- `Makefile`: `reproduce` regenerates SPICE, then TCAD (1D, 2D, meshconv, calibration, validation), then verifies. `docs/reproduce/index.md` states the expected runtime, which is hours because of 2D meshconv. A `reproduce-quick` target runs only the cross-checked TCAD subset.
- `.github/workflows/crosscheck.yml`: a second job, `crosscheck-tcad`, which:
  - uses `actions/checkout` with `submodules: true`;
  - pulls `docker/TCAD_IMAGE` by digest;
  - runs the coarse 1D set into a temporary `--out`;
  - runs `verify-subset --kind tcad --prefix tcad/`.

  Add `third_party/**` and `data/process/**` to its paths.

- [ ] **Step 1:** Write the tests first:
  - `test_tcad_subset_parse`;
  - `test_tcad_verify_subset_detects_change`;
  - `test_spice_subset_unchanged`.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. `make reproduce` on a clean `--recurse-submodules` clone regenerates SPICE and TCAD and verifies the manifest. The `crosscheck-tcad` job regenerates the coarse 1D MOSCAP set on a GitHub-hosted runner, byte-identical.
- [ ] **Step 3:** Commit, open the PR, get it reviewed and merge.

### Task 14: secondary PDK `d658698` comparison (carried over from Phase 0–1 Task 15)

**Context.**
- `spice-reference` lives in `reference.py`, which is a generator module. Adding `--pdk-root` there therefore changes SPICE provenance (Global Constraints).
- `_image_pdk` checks the PDK against `docker/base/versions.json`, which would reject d658698.

**Files:**
- `src/gf180tcad/pdkdiff.py`, with its own entry point `python -m gf180tcad.pdkdiff run|compare`;
- `data/pdk-d658698.sha256`, `data/pdk-d658698.versions.json` (the expected variant, commit and file sha256s);
- `results/spice-pdk-d658698/**`;
- `tests/test_pdkdiff.py`;
- `docs/comparison/pdk-versions.md` (requires the docs-links infrastructure on main).

**Decision:** `reference.py` is not modified.
- `pdkdiff run` plans the same jobs as `reference.plan_jobs`, restricted to TT and ngspice.
- It runs each job in the base image with `PDK_ROOT` pointing at the fetched PDK inside the workdir.
- It checks the PDK with `pdk.check_against(info, "data/pdk-d658698.versions.json")`.
- It writes the same file layout as `run_job`, through the generator's own functions, imported but not modified.

If that proves impossible without editing a generator module, the PR also regenerates `results/spice`, as the Global Constraints require.

**Interfaces:**
- Consumes: `pdk.locate(pdk_root=…)` (`pdk.py:44`) and `pdk.check_against(info, versions)`.
- Produces: the gf180mcu `d658698bd8bc` PDK, fetched inside the sandbox with `ciel`, which comes from a hashed lock if it is not in the base image. Only the fetch step has network access. The files are pinned by hash in `data/pdk-d658698.sha256`.
- Produces: a TT ngspice run of all geometries.
- Produces: `pdkdiff.compare(a_metrics_dir, b_metrics_dir) -> dict`, a per-metric delta summary.
- Produces: a docs page. It states whether the run-1/2 PDK models differ from the latest for these devices, and re-checks the spec §4 card values against the latest card. The research already found that the run-2 card sha differs from the image's (`6edba54d…` vs `69a7ab87…`).

- [ ] **Step 1:** Write the tests first: `test_pdkdiff_zero_for_identical`, `test_pdkdiff_reports_metric_delta` and `test_reference_py_untouched` (the generator_sha256 is unchanged). Run them: they FAIL.
- [ ] **Step 2:** Implement, then run the tests again: they PASS.
- [ ] **Step 3:** Generate the results, update the manifest and write the page. Then commit, open the PR, get it reviewed and merge.

### Task 15 (optional, Phase 4 prep): backend seam in the plugin

**Files (fork):** split `gplugins/devsim/get_solver.py` into `device_description.py` (mesh, regions, contacts, doping, bias plan) and `backends/devsim.py`.

- [ ] **Step 1:** All existing fork tests pass unchanged through the new seam, verified with the fork-worktree pattern. No Charon code yet.
- [ ] **Step 2:** Commit, open the PR, get it reviewed and merge. Then do **submodule bump 3 of 3**: the gf180-tcad TCAD results must be byte-identical before and after the bump. `make reproduce-quick` plus `make manifest` give no diff.

---

## Risks

- **Base image changes cascade.** Any change to `docker/IMAGE` forces a TCAD image rebuild, a new `docker/TCAD_IMAGE`, and regenerated TCAD results, because the TCAD image is built FROM the base digest.
- **Plugin changes and the image.** A fork change that adds a dependency **does** require a TCAD image rebuild. "A plugin change never needs an image rebuild" holds only for pure-code changes.
- **numpy dispatch names.** `NPY_DISABLE_CPU_FEATURES` names are tied to the numpy version. The TCAD lock pins the base lock's numpy, and `test_tcad_numpy_baseline` verifies it.
- **Python 3.12 vs 3.13.** Python `repr` is the same in both. The cp312 and cp313 numpy wheels may differ in the last ulp, so TCAD and SPICE numbers are compared only within the TCAD image, and never bit-wise across images.
- **DEVSIM solver selection.** A different `DEVSIM_MATH_LIBS`, or an MKL that appears in the image, would switch DEVSIM's solver and change the bits. `test_devsim_single_thread` asserts the OpenBLAS load line.
- **The old stack.**
  - The v0.8.0 run's tidy3d 2.4 may try network access under `--network none`.
  - Old-stack results have no cross-host bit-identity guarantee, so `results/plugin-history` is not cross-checked.
- **2D cost and convergence.**
  - The spike failed to converge at r ≤ 1/4 with 1e-12. At 1e-10 it may converge but take hours.
  - `make reproduce` runtime is stated in the docs.
  - Concurrent jobs go through admission control.
- **Interpreting Lmin and narrow width.** In 1D, Lmin and 1.6/0.7 results are dominated by the DLC and parasitic bookkeeping and by missing 2D/3D effects. They are pre-tagged `geometry-2d`/`spice-fit` so that a "Disagree" there is not over-read.
- **Budget carry-over.** The 3 calibrated parameters use part of the 8-parameter budget for Phase 3 as well. A channel profile may later replace `n_ch`.
- **The `t_ox_eff` upper bound** depends on a citation that Task 12 must find. If none is found, the bound stays TBD, and the fit reports a bound hit rather than hiding it.

## Phase exit

- [ ] The fork's `gplugins.devsim` tests are green in fork CI, inside the pinned TCAD image. The "once worked" record (including `DDComponent`) and its "re-verified on latest" numbers are committed and documented.
- [ ] 1D and 2D MOSCAPs are mesh-converged (< 1 %). The C/Cox > 1 artefact is resolved or explained with numbers.
- [ ] At the calibration geometries, nfet and pfet Cgg–Vg reach both plateau maxima ≤ 5 % and a transition ΔV ≤ 50 mV (the latter a proposal). Otherwise they carry a published verdict with the §6 analysis. Held-out geometries are validated against the frozen `param_sha256` and reported.
- [ ] `make reproduce` verifies on a clean `--recurse-submodules` clone. The GitHub cross-check is green for both SPICE and `crosscheck-tcad`. Read the Docs is green, and the docs-links checks pass. `results/spice/provenance.json` is unchanged from the Phase 1 exit, unless a PR regenerated it by the Global Constraints rule.
- [ ] A whole-branch review of main since the Phase 1 exit is done and its findings fixed. The Phase 3 plan (2D MOSFET) is written.
