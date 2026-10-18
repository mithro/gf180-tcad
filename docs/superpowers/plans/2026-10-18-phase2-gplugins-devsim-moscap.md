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
  - **meshwell runs with `n_threads=1`.** Every `meshwell.orchestrator.generate_mesh(...)` call passes `n_threads=1`. meshwell 2.5.2 defaults to `cpu_count()` (88 on this host, 4 on GitHub runners) and then sets `General.NumThreads`, `Mesh.MaxNumThreads1D/2D/3D` and `Geometry.OCCParallel` from it (`meshwell/model.py:338-342`), which overwrites any options set earlier. A test reads `gmsh.option.getNumber("General.NumThreads") == 1` after meshing.
  - **gmsh is pinned.** It runs with `Mesh.RandomSeed` fixed and `Geometry.OCCParallel=0`. Mesh files are written as MSH 2.2.
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
  | ε_si | 11.7 | `spice-card`: the BSIM4 default EPSRSUB, since the card sets none |
  | ε_ox | 3.9 | `spice-card`: EPSROX |
  | T | 298.15 K | `spice-card`: TNOM 25 °C, `sm141064.ngspice:37308` |
  | n_i(T) | from a cited source | `literature` |

  The literature citations for these constants are links. Every unit test with a hand value uses the same constants on both sides.
- **Result files.** Floats are written with `repr`, with `\n` line endings and sorted JSON keys. Write through `gf180tcad.io`, and never modify `io.py` (it is a generator module).
  - Register every result in `results/MANIFEST.sha256` (`make manifest`).
  - Every TCAD tree holds a root `provenance.json`, written by `gf180tcad.tcad.provenance()`. It contains:
    - the `docker/TCAD_IMAGE` reference;
    - the contents of `docker/tcad/versions.json`;
    - `gplugins_commit`, taken on the host with `git ls-tree HEAD third_party/gplugins`, because the read-only mount cannot run git;
    - `generator_sha256` over the TCAD modules, `third_party/gplugins/gplugins/devsim/**` and `data/process/*.toml`.

    It deliberately holds no date. `tests/tcad/test_tcad_provenance.py` checks that the committed tree matches the current one, as `tests/test_results_provenance.py` does for SPICE.
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

  The flat band follows from the gate and body doping: Vfb ≈ −0.99 V for the nfet and +0.99 V for the pfet. Accumulation is at +Vg for the pfet. Reuse the Phase 1 rule `polarity·vg` for inversion and accumulation.
- **Units and constants.** Never use DEVSIM `simple_physics` defaults. Use the constants table above.
- **Silent non-convergence.** A bias point that fails to converge, or converges only at a relaxed tolerance, must fail the sweep, never be dropped or interpolated. The tolerance is recorded per point.
- **Calibration leakage.** Only calibration geometries (W10 at L = 10, 2 and Lmin) and calibration targets (Cgg–Vg) may move parameters. Held-out geometries (L = 0.7, 1, 1.6/0.7) are computed after the parameters are frozen.

---

### Task 1: TCAD image (Python 3.13 stack)

**Context.** meshwell ≥ 2.4 requires Python ≥ 3.13, and the base image has 3.12.3. gf180mcu 1.0.0 pins `gdsfactory~=9.40`, so it installs with `--no-deps` against 9.51. The base image's `PDK=gf180mcuD` breaks `gdsfactory.get_active_pdk`.

**Files:**
- Create: `docker/tcad/Dockerfile`, `docker/tcad/requirements.in`, `docker/tcad/requirements.lock`, `docker/tcad/build-requirements.lock` (if needed), `docker/tcad/build`, `docker/tcad/IMAGE_ID`, `docker/tcad/versions.json`, `docker/TCAD_IMAGE`, `tests/test_tcad_image.py`
- Modify: `.github/workflows/image.yml` (build, verify and push both images), `docs/reproduce/image.md`

**Interfaces:**
- Produces: `docker/TCAD_IMAGE`, one line holding `ghcr.io/mithro/gf180-tcad-tcad@sha256:…`.
  - Python is `/opt/gf180tcad-tcad/bin/python` (3.13), first on PATH.
  - Installed with hashes: devsim 2.11.1, meshwell 2.5.2, gmsh 4.15.2, gdsfactory 9.51.0, gf180mcu 1.0.0 (`--no-deps`) and their locked dependencies.
  - `PDK` is set so gdsfactory works; the implementer verifies empty vs unset.
  - `versions.json` has the same keys as the base image's, plus meshwell, gmsh, gf180mcu and tcad python.
- Produces: `gf180tcad.sandbox.run(..., image=...)` and `tools/sandbox-run --image "$(cat docker/TCAD_IMAGE)"` work unchanged.

- [ ] **Step 1:** Write the tests first, sandbox-marked:
  - `test_tcad_versions_json_matches_image`;
  - `test_tcad_imports` (`devsim`, `meshwell.orchestrator`, `gmsh`, `gdsfactory`, `gf180mcu`; `gf.get_active_pdk()` does not raise);
  - `test_tcad_numpy_baseline`;
  - `test_devsim_single_thread`.
  Run them: they FAIL because there is no image.
- [ ] **Step 2:** Build `FROM` the base image by digest. Install uv-managed CPython 3.13, pinned to an exact patch version and verified by hash. Create the venv and install from the hashed lock with `--require-hashes`, without bytecode, as Phase 1 did. Use the same `SOURCE_DATE_EPOCH` and `rewrite-timestamp` reproducibility as `docker/base/build`.
- [ ] **Step 3:** Two local `--no-cache` builds must give the same config digest. Commit `IMAGE_ID`, then push via CI and commit `docker/TCAD_IMAGE`. CI checks reproducibility, the IMAGE_ID, the TCAD_IMAGE manifest digest and versions.json for both images.
- [ ] **Step 4:** Run the tests: they PASS. Then commit, open the PR, review and merge.

### Task 2: Fork CI hygiene and submodule wiring

**Context.** The fork inherits upstream workflows. Some of them may publish (PyPI, docs deploy) or need secrets. `gplugins/devsim` is excluded from pytest (`pyproject.toml:95`) and from the CI matrix.

**Files (fork):** `.github/workflows/*` (keep only workflows that run safely on a fork with hosted runners and no secrets; disable publish and deploy jobs with a comment saying why), `README.md` (a "fork for gf180-tcad" note)

**Files (gf180-tcad):** `.gitmodules`, `third_party/gplugins` (submodule at a fork commit), `tools/sandbox-run` (add `/work/src/third_party/gplugins` to `PYTHONPATH` for TCAD jobs only), `tests/test_submodule.py`, `docs/reproduce/index.md`

**Interfaces:**
- Produces: inside a TCAD sandbox job, `import gplugins.devsim` resolves to `/work/src/third_party/gplugins/gplugins/devsim`.
- Produces: `make reproduce` and CI check out submodules (`actions/checkout` with `submodules: true`, pinned).

- [ ] **Step 1:** Fork branch `gf180/ci-hygiene`. Enable Actions on `mithro/gplugins`, and list each workflow with what it does. Disable the unsafe ones. The remaining test workflow must go green on a PR inside the fork.
- [ ] **Step 2:** In gf180-tcad, write `test_submodule.py` first. It checks that the submodule is pinned to a commit that exists on `mithro/gplugins` main, and that a sandbox job imports the plugin from that path. Run it: it FAILS. Then add the submodule and the PYTHONPATH entry. Run it: it PASSES.
- [ ] **Step 3:** For both repos: commit, open the PR, review and merge.

### Task 3: Prove the plugin once worked (committed, re-runnable record)

**Context.** At gplugins v0.8.0 on Sept-2023 packages, `test_pin_waveguide` passed (276 s) and `DDComponent.ddsolver()` converged (5.8 s). `get_refined_mesh` has a `NameError` (`get_solver.py:359`). At v1.4.2 from its frozen lock, the import fails.

**Files (gf180-tcad):** `experiments/plugin-history/README.md`, `experiments/plugin-history/run.py`, `results/plugin-history/{v0.8.0,v1.4.2}.json`, `tests/test_plugin_history.py`

**Interfaces:**
- Produces: `python -m gf180tcad plugin-history --version v0.8.0|v1.4.2 --out DIR` runs in two sandbox steps:
  1. a network-on install: `uv` with `--exclude-newer 2023-09-20T18:00Z` and Python 3.11 for v0.8.0, the frozen `uv.lock` for v1.4.2, into a venv in the workdir;
  2. a network-off run of the fixed checks.
- Produces: a result JSON holding:
  - the resolved versions;
  - the pass/fail of each check: import, PIN test, ddsolver converge, refine;
  - the PIN numbers (contact currents and depletion width), or the exact exception text.

- [ ] **Step 1:** Write the test first, sandbox-marked and allowed to be slow. Assert the v0.8.0 JSON has import ✓, PIN ✓ and ddsolver ✓, with the PIN numbers present. Assert v1.4.2 has the import failure recorded.
- [ ] **Step 2:** Implement and run. Commit the JSON. Two runs must agree on everything except timings, and timings stay out of the committed JSON.
- [ ] **Step 3:** Docs: a page under `docs/limitations/` (or `docs/reproduce/`) giving the plugin's history and the "once worked" evidence. Then commit, open the PR, review and merge.

### Task 4 (fork): import and test `gplugins.devsim` on latest, no physics change

**Context.** These latest-stack failures are documented:
- `pydantic.Extra`/`Config`;
- `get_refined_mesh` uses `c` instead of `self`;
- `delete_device` signature;
- silicon models are applied to non-silicon regions;
- `__init__` imports tidy3d unconditionally;
- the PIN test asserts nothing.

**Files (fork):** `gplugins/devsim/__init__.py`, `gplugins/devsim/get_solver.py`, `gplugins/devsim/test_devsim.py` (split DEVSIM-only from tidy3d), `pyproject.toml` (un-exclude devsim; add devsim to the test extras), the CI matrix

**Interfaces:**
- Produces: `pytest gplugins/devsim -m "not tidy3d"` green in fork CI and inside the TCAD image.

- [ ] **Step 1:** Add real assertions to the PIN test first: the contact currents at two biases and the depletion width, with the expected values taken from `results/plugin-history/v0.8.0.json`. Run on latest: it FAILS on import.
- [ ] **Step 2:** Fix only what's needed to import and run. Make no physics or default changes.
- [ ] **Step 3:** Run it: it PASSES. The PIN numbers should match v0.8.0 within 1e-6 relative. If DEVSIM 2.6.3 → 2.11.1 or the mesher changes move them more, do not loosen the threshold silently: record the measured difference, attribute it with evidence (e.g. same mesh read into both DEVSIM versions), and set the tolerance to the justified value in the test with a comment. This is the "re-verified on latest" evidence.
- [ ] **Step 4:** Commit, open the PR (fork), review and merge. Then bump the submodule in gf180-tcad with its own small PR.

### Task 5 (fork): port `create_2Duz_simulation` meshing to meshwell 2.5

**Context.** meshwell 2.5.2 provides `generate_mesh(..., global_scaling, gmsh_version)` and `resolution_specs` (`ConstantInField`, `ThresholdField`, …). DEVSIM 2.11 reads MSH 2.2. The fork's `gplugins/meshwell/get_meshwell_cross_section.py` and `gplugins/femwell/mode_solver.py` `__main__` blocks import the removed `meshwell.cad`. gdsfactory 9 cells are locked: use `.copy()` before `trim`.

**Files (fork):** `gplugins/devsim/get_simulation.py`, `gplugins/meshwell/get_meshwell_cross_section.py`, `gplugins/femwell/mode_solver.py`, `gplugins/devsim/tests/test_mesh.py`

**Interfaces:**
- Produces: `create_2Duz_simulation(component, xsection_bounds, layer_stack, resolutions: dict[str, list[ResolutionSpec]], ...) -> DDComponent`. It returns the same regions, contacts and interfaces as v0.8.0 for the PN-slab example.
- The interface naming scheme `a___b`/`a___None` is kept and documented.

- [ ] **Step 1:** Write `test_mesh.py` first. The PN-slab example must build a DEVSIM device whose region, contact and interface names equal the v0.8.0 record. Node count must be within a stated, justified tolerance, and two builds must give an identical mesh file. Run it: it FAILS (`NotImplementedError`).
- [ ] **Step 2:** Implement with meshwell 2.5.2 and gmsh `General.NumThreads=1`. Run it: it PASSES. Fix the two `meshwell.cad` `__main__` blocks.
- [ ] **Step 3:** Commit, PR, review, merge, submodule bump.

### Task 6 (fork): typed contacts and interfaces

**Context.** `CreateOxideContact` has no work-function term, so the gate offset has to be applied as a bias offset: about +0.56 V for n⁺ poly and −0.56 V for p⁺. The alternative is a poly-silicon gate region, as in DEVSIM `testing/mos_2d.py`.

**Files (fork):** `gplugins/devsim/contacts.py` (new), `gplugins/devsim/get_simulation.py`, `gplugins/devsim/get_solver.py`, `gplugins/devsim/tests/test_contacts.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) Contact(name: str, location: LayerRef | InterfaceRef, kind: Literal["ohmic", "gate"], workfunction_offset_v: float = 0.0, circuit: bool = False)`.
- Produces: interfaces chosen by material pair: Si/oxide gets continuous potential; Si/Si gets drift-diffusion continuity.
- The old `contact_info` dict keeps working through an adapter, with a deprecation note.

- [ ] **Step 1:** Write the test first: a parallel-plate oxide device gives C = εox·A/t within 0.1 %, measured through `get_contact_charge` (dQ/dV) AND through small-signal AC (`circuit_element` + `solve(type="ac")`, the `testing/ssac_cap.py` pattern). A second check confirms the work-function offset shifts the flat-band voltage of a 1D MOS stack by the offset within 1 mV. Run it: it FAILS.
- [ ] **Step 2:** Implement. Run it: it PASSES. Then commit, PR, review, merge, and bump the submodule.

### Task 7 (fork): doping from analytic profiles

**Context.** `gplugins/process` has Gaussian and skewed-Gaussian implant profiles, which the plugin does not use. Reading `silicon_diffused_gaussian_profile` suggests a missing factor of 2 in the exponent and a missing µm→cm prefactor. These are unconfirmed until tested.

**Files (fork):** `gplugins/devsim/doping.py`, `gplugins/process/diffusion.py` (fix only after a failing test proves the bug), `gplugins/devsim/tests/test_doping.py`

**Interfaces:**
- Produces: `DopingProfile` callables `(x_um, y_um) -> cm⁻³` for `constant`, `gaussian(peak, depth, straggle)`, `erfc(surface, xj)` and `lateral(straggle)`. They accept gdsfactory `technology.processes` `ImplantGaussian`/`DopingConstant`. The doping is assigned to DEVSIM `NetDoping` / `Donors` / `Acceptors` node models.

- [ ] **Step 1:** Write the tests first:
  - the integrated dose of the assigned doping equals the input dose within 0.5 %;
  - `silicon_diffused_gaussian_profile` at t=0 equals `silicon_gaussian_profile`;
  - a uniform 1.7e17 region gives the analytic bulk potential within 0.1 mV.

  Run them: they FAIL wherever a bug exists.
- [ ] **Step 2:** Implement and fix. Run the tests: they PASS. Then commit, open the PR, get it reviewed, merge, and bump the submodule.

### Task 8 (fork): C–V solver API

**Context.** There are two routes:
- quasi-static `C = dQgate/dVg`, a central difference of `get_contact_charge`;
- small-signal AC, using `ssac_imag`/(−2πf).

The spike's tolerance failures at relative 1e-12 point to using the spec's 1e-10 with extended precision (`extended_solver`/`extended_model`/`extended_equation`).

**Files (fork):** `gplugins/devsim/cv.py` (new), `gplugins/devsim/tests/test_cv.py`

**Interfaces:**
- Produces: `sweep_cv(device, gate: str, vg: Sequence[float], *, method: Literal["qs", "ac"], freq_hz: float | None = None, rel_tol: float = 1e-10, abs_tol: float = ..., tie: Sequence[str] = ()) -> CVResult`.
  - `CVResult` holds `vg`, `cgg_f`, and per-point `{converged, iterations, rel_error}`.
  - For `ac` with `tie` contacts, it also holds `cgx_f` per contact, for the charge-conservation check.
- Any non-converged point raises `CVConvergenceError` listing the points. It never drops them.

- [ ] **Step 1:** Write the tests first, on a 1D MOS stack:
  - QS and AC at 1 Hz agree within 0.1 %;
  - accumulation C approaches the series combination of Cox and silicon within 0.5 %;
  - forcing a non-convergent tolerance raises `CVConvergenceError`;
  - AC charge conservation, Cgg = −ΣCgx, holds within 0.1 % when contacts are tied.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS. Then commit, open the PR, get it reviewed, merge, and bump the submodule.

### Task 9: process files and 1D MOSCAP (gf180-tcad)

**Context.** These values are taken from the image's card. All are tagged `spice-card` and serve as starting points and bounds, never as fixed truths:

| Parameter | nfet | pfet |
|---|---|---|
| TOXE | 15.2 nm | 15.6 nm |
| TOXP | 16.0 nm | — |
| NDEP | 1.7e17 | 1.7e17 |
| NGATE | 1e20 | 3.6e19 |
| XJ | 0.15 µm | — |
| DLC | 54 nm | 7.4 nm |
| CGSO/CGDO | 1e-10 F/m | 7.71e-11 F/m |
| CGSL/CGDL | 1.5e-10 F/m | 5.25e-11 F/m |

SPICE W10/L10 TT is the target to match:
- nfet: 212.26 fF in accumulation, 212.51 fF in inversion, a minimum of 80.14 fF at 0.4 V;
- pfet: 222.43 / 210.28 fF.

**Files:** `data/process/nfet_05v0.yaml`, `data/process/pfet_05v0.yaml` (each value has a provenance tag and source citation, e.g. a card file plus line or a PDK doc URL), `src/gf180tcad/process.py`, `src/gf180tcad/tcad/__init__.py`, `src/gf180tcad/tcad/moscap1d.py`, `tests/tcad/test_process.py`, `tests/tcad/test_moscap1d.py`

**Interfaces:**
- Produces: `process.load(device: str) -> ProcessDescription`. It validates the provenance tags and bounds, and every `calibrated` value must lie within its bounds.
- Produces: `moscap1d.simulate(proc, *, vg, method="qs", mesh: MeshSpec, rel_tol=1e-10) -> CVResult`, scaled to fF using `area_um2 = (L − 2·DLC)·W`. The parasitic overlap and fringe estimate is reported separately and never folded in silently.
- Produces: CLI `python -m gf180tcad tcad-moscap --device D --dim 1 --out DIR`. It runs in the TCAD image and writes `results/tcad/moscap1d/<device>/<geometry_id>/{cv.csv,meta.json}`.

- [ ] **Step 1:** Write the tests first:
  - unit conversions: Cox(15.2 nm) = 2.272 fF/µm², 224.7 fF for W10/L10;
  - the depletion-approximation Cmin and flat-band C match the analytic values within 1 % for uniform doping;
  - two sandbox runs give byte-identical CSVs;
  - the pfet curve is the polarity mirror of an nfet stack with swapped doping types.

  Run them: they FAIL.
- [ ] **Step 2:** Implement with a DEVSIM-native 1D mesh (`create_1d_mesh`). Use either a gate offset or a poly region, and record which. Run the tests: they PASS. Then commit, open the PR, get it reviewed, and merge.

### Task 10: mesh-convergence tooling, and the C/Cox > 1 artefact

**Context.** In the spike, 2D C/Cox was ≈ 1.004–1.006 at |Vg| = 5 V, which is unphysical, and depletion C moved by 2 % between meshes. Spec §5.2 requires that uniform refinement changes every metric by less than 1 %.

**Files:** `src/gf180tcad/tcad/meshconv.py`, `tests/tcad/test_meshconv.py`, `results/tcad/meshconv/**`, `docs/limitations/` (page section)

**Interfaces:**
- Produces: `@dataclass(frozen=True) MeshSpec(h_ox_nm, h_si_surface_nm, h_si_bulk_nm, grading)` and `MeshSpec.scaled(r)`.
- Produces: `converge(simulate, spec, levels=(1, 2**-0.5, 0.5, 2**-1.5), metric="cgg") -> ConvergenceReport`. The report holds per-level curves, node counts, the max relative change against the next finer level, the Richardson estimate, the observed order, and the selected level, which is the coarsest with < 1 % at every bias.

- [ ] **Step 1:** Write the tests first:
  - on a uniform-doping 1D case the converged C approaches the analytic Poisson solution, with observed order ≈ 2 (between 1.5 and 2.5);
  - the selected level satisfies < 1 % against the next finer one;
  - the report JSON is deterministic.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS.
- [ ] **Step 3:** Diagnose the C/Cox > 1 artefact from evidence. Candidates are contact-charge discretisation at oxide/contact corner nodes, side boundaries, and Boltzmann statistics in strong accumulation. Fix the cause, or document it with numbers if it is below tolerance and explained. Never paper over it.
- [ ] **Step 4:** Commit, open the PR, get it reviewed, and merge.

### Task 11: 2D MOSCAP from gdsfactory geometry

**Context.** `gf180mcu.cap_mos` and `nfet(volt="5.0V")` build under gdsfactory 9.51. Their LayerStack is illustrative, with no gate oxide and no doping, so the vertical stack comes from `data/process/*.yaml`.

**Files:** `src/gf180tcad/tcad/stack.py` (build a gdsfactory LayerStack plus doping from a ProcessDescription), `src/gf180tcad/tcad/moscap2d.py`, `tests/tcad/test_moscap2d.py`

**Interfaces:**
- Produces: `moscap2d.simulate(proc, geometry, *, with_sd: bool, method, mesh, freq_hz=None) -> CVResult`, built through `gplugins.devsim` (Tasks 5–8). It uses a cross-section across the gate. When `with_sd` is true, n⁺ (or p⁺) S/D are tied to the body, so a 1 MHz AC run can supply the inversion charge.
- CLI `tcad-moscap --dim 2`.

- [ ] **Step 1:** Write the tests first:
  - with S/D removed and a uniform stack, 2D Cgg per area equals the 1D result within 0.5 %;
  - with S/D, 1 MHz AC recovers to inversion as SPICE does, and charge conservation holds within 0.1 %;
  - the mesh is converged per Task 10;
  - two runs give byte-identical results.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS. Then commit, open the PR, get it reviewed, and merge.

### Task 12: calibrate against SPICE Cgg–Vg

**Context.** At TOXE 15.2 nm, effective oxide is the dominant knob. Poly depletion (1–1.5 % n, 3–4 % p), quantum confinement (2–3 %) and the TOXE→TOXP gap (5.3 %) are each comparable to the 5 % tolerance. DEVSIM has no density-gradient model, so confinement is folded into the effective oxide and documented as such.

**Files:** `src/gf180tcad/calibrate/__init__.py`, `src/gf180tcad/calibrate/cv.py`, `results/tcad/calibration/{nfet_05v0,pfet_05v0}.json`, `data/process/*.yaml` (calibrated values written back with `calibrated` provenance and the target used), `tests/test_calibrate_cv.py`

**Interfaces:**
- Produces: `calibrate_cv(device, *, geometries=CALIBRATION_GEOMETRIES, params=("t_ox_eff_nm", "n_ch_cm3", "v_fb_v"), bounds from the process file) -> CalibrationResult`. Fit with at most 3 parameters of the 8-parameter budget, and record how much of the budget is used. The fit is deterministic: a fixed starting point and a deterministic optimiser (no random restarts), or a seeded one.
- Produces: per-region residuals for accumulation, depletion and inversion; the verdict per spec §5 (Agree / Same process / Disagree, with the window from `specwindow.window`); and the validation results at the held-out geometries, computed only after freezing.

- [ ] **Step 1:** Write the tests first, on synthetic data built from the 1D model:
  - the calibration recovers known parameters within 0.5 %;
  - a test asserts that validation geometries are never passed to the fitter;
  - bounds are enforced.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. Run the tests: they PASS.
- [ ] **Step 3:** Calibrate both devices on W10/L10, L2 and Lmin at TT, with ngspice as reference. Apply the overlap and fringe estimate from the card explicitly (CGSO/CGDO, CGSL, CF) and document it.
  - Target: |ΔCgg|/Cgg ≤ 5 % at every bias.
  - If the target is not reached within budget, publish the best fit with its verdict and the §6 mismatch analysis. Never raise the budget silently.
- [ ] **Step 4:** Commit the results (results-only commit), run `make manifest`, then open the PR, get it reviewed, and merge.

### Task 13: TCAD results, docs and cross-host check

**Files:** `src/gf180tcad/docgen.py` (MOSCAP pages: TCAD vs ngspice Cgg–Vg overlay with corner envelope, mesh-convergence plots, parameter table with provenance and budget use, verdicts), `docs/results/`, `docs/comparison/`, `docs/limitations/` (QS vs HF, no density-gradient, poly-depletion treatment, effective-oxide folding), `Makefile` (`reproduce` also regenerates TCAD results), `.github/workflows/crosscheck.yml` (add a coarse-mesh 1D MOSCAP job set in the TCAD image), `tests/test_docgen.py`

- [ ] **Step 1:** Write the tests first:
  - one page per device/geometry with TCAD data;
  - determinism;
  - the offline build;
  - `test_doc_links` covers the new pages.

  Run them: they FAIL.
- [ ] **Step 2:** Implement. `make reproduce` regenerates SPICE and TCAD and verifies the manifest. The crosscheck workflow regenerates the coarse 1D MOSCAP set on a GitHub-hosted runner, byte-identical.
- [ ] **Step 3:** Commit, open the PR, get it reviewed (including the dedicated missing-links review), and merge.

### Task 14: secondary PDK `d658698` comparison (carried over from Phase 0–1 Task 15)

**Files:** `src/gf180tcad/pdkdiff.py`, `tests/test_pdkdiff.py`, `data/pdk-d658698.sha256`, `results/spice-pdk-d658698/**`, `docs/comparison/pdk-versions.md`

**Interfaces:**
- Consumes: `pdk.locate(pdk_root=…)`, and `spice-reference` with a new `--pdk-root` option.
- Produces: the gf180mcu `d658698bd8bc` PDK, fetched with `ciel` inside the sandbox. Only the fetch step has network access. The files are pinned by hash in `data/pdk-d658698.sha256`.
- Produces: a TT ngspice run of all geometries.
- Produces: `pdkdiff.compare(a_metrics_dir, b_metrics_dir) -> dict`, a per-metric delta summary.
- Produces: a docs page stating whether the run-1/2 PDK models differ from the latest for these devices, and re-checking the spec §4 card values against the latest card. The research already found that the run-2 card sha differs from the image's (`6edba54d…` vs `69a7ab87…`).

- [ ] **Step 1:** Write `test_pdkdiff_zero_for_identical` and `test_pdkdiff_reports_metric_delta`, then run them: they FAIL.
- [ ] **Step 2:** Implement, then run them again: they PASS.
- [ ] **Step 3:** Generate the results, update the manifest and write the page. Then commit, open the PR, get it reviewed, and merge.

### Task 15 (optional, Phase 4 prep): backend seam in the plugin

**Files (fork):** split `gplugins/devsim/get_solver.py` into `device_description.py` (mesh, regions, contacts, doping, bias plan) and `backends/devsim.py`.

- [ ] **Step 1:** All existing fork tests pass unchanged through the new seam. No Charon code yet. Commit, open the PR, get it reviewed, merge, and bump the submodule.

---

## Phase exit

- [ ] The fork's `gplugins.devsim` tests are green in fork CI on the latest stack, and the "once worked" record is committed.
- [ ] 1D and 2D MOSCAPs are mesh-converged (< 1 %). The C/Cox > 1 artefact is resolved or explained with numbers.
- [ ] nfet and pfet Cgg–Vg reach |ΔCgg|/Cgg ≤ 5 % at the calibration geometries, or carry a published verdict with the §6 analysis. Held-out geometries are reported as validation.
- [ ] `make reproduce` on a clean clone verifies; the GitHub cross-check is green, including TCAD; Read the Docs is green; docs-links checks pass.
- [ ] A whole-branch review of main since the Phase 1 exit is done and its findings fixed. The Phase 3 plan (2D MOSFET) is written.
