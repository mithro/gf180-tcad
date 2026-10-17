# Phase 0–1: Foundations and SPICE Golden Reference — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reviewed, published repo in which one command, run inside a resource-capped Docker sandbox built on a pinned IIC-OSIC-TOOLS image, regenerates bit-identical ngspice and Xyce reference data and extracted metrics for `nfet_05v0`/`pfet_05v0`, with results shown on Read the Docs.

**Architecture:** A Python package `gf180tcad` (src layout) holds the device/bias matrix, PDK provenance, SPICE netlisting/running/parsing, metric extraction and the hash manifest. All simulator execution goes through `tools/sandbox-run`, which starts a container from `ghcr.io/mithro/gf180-tcad-base` (a thin layer on IIC-OSIC-TOOLS) with hard memory, CPU and PID limits inside a capped systemd slice. Results are committed as deterministic CSV/JSON with SHA-256s in `results/MANIFEST.sha256`; Sphinx pages are generated from those files only.

**Tech Stack:** Python ≥ 3.12 (whatever the base image ships — record it), uv (lock with hashes), numpy, pytest, ruff, matplotlib, Sphinx + MyST + furo, ngspice and Xyce from IIC-OSIC-TOOLS `2026.10`, Docker (cgroup v2, systemd driver), GitHub Actions (hosted runners only), ghcr.io, Read the Docs.

**Spec:** `docs/superpowers/specs/2026-10-18-gf180-tcad-design.md` (read §3, §5.2, §8, §9, §10 before starting any task).

## Global Constraints

- Licence: Apache-2.0 for everything written here; SPDX header `# SPDX-License-Identifier: Apache-2.0` on every new source file.
- Git: one branch + worktree per task under `../gf180-tcad-worktrees/<branch>`; small logical commits; never commit on `main`; PR inside `mithro/gf180-tcad` (always pass `--repo mithro/gf180-tcad`); reviewed by an independent review subagent, findings fixed; merged with `gh pr merge --merge` (merge commit). No squash or rebase merges.
- Never interact with upstream repos (no PRs/issues/comments); forks live under `github.com/mithro/`.
- Latest versions: base image `hpretl/iic-osic-tools:2026.10` = `sha256:306585de35d198e70ea58950f77147c86f56c698726a19afea9f1c83009557be`; Python deps at latest at lock time (`devsim` 2.11.0, `gdsfactory` 9.51.0 for later phases).
- Every simulator invocation runs via `tools/sandbox-run`; defaults 16 GiB memory (swap = memory), 8 CPUs, 4096 PIDs, `--network=none`; aggregate slice `gf180-tcad.slice` capped at 128 GiB, `MemorySwapMax=0`.
- Determinism: `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1`; ngspice `set num_threads=1`; serial Xyce; PDK statistical switches `sw_stat_global=0 sw_stat_mismatch=0`; no timestamps, hostnames or absolute host paths in any result file.
- Floats in result files are written with `repr()` (shortest round-trip), `\n` line endings, `.` decimal separator, sorted JSON keys, UTF-8.
- Public data only: every process/PDK number in the repo cites a public source; no NDA material.
- No self-hosted runners.

## Review Focus

- PMOS polarity: pfet sweeps use negative Vgs/Vds/Vbs and negative Id; every extractor must return the same magnitudes/semantics as for nfet (Vt reported negative for p, Idsat reported as magnitude per µm).
- Bin boundary L = 0.7 µm (`nfet_06v0` bins 0.6–0.7 and 0.7–50): ngspice and Xyce must both pick a bin without error and agree; a mismatch between engines here is a reference problem.
- Silent data loss: a non-converged or skipped bias point must fail the run, not produce a shorter CSV.
- Statistical randomness: any `agauss` left active makes outputs differ run-to-run; two consecutive runs must be byte-identical.
- OOM / runaway: a job exceeding its memory limit must end as a reported failure (exit 137) with the host and other jobs unaffected.

---

### Task 1: Repository scaffold, GitHub repo and contribution rules

**Files:**
- Create: `LICENSE` (Apache-2.0 text), `README.md`, `CONTRIBUTING.md`, `pyproject.toml`, `uv.lock`, `src/gf180tcad/__init__.py`, `tests/test_import.py`, `.gitignore`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: importable package `gf180tcad` with `__version__: str`; `uv run pytest` and `uv run ruff check` as the standard commands; CI job `lint-test` on GitHub-hosted `ubuntu-latest`.

- [ ] **Step 1:** Create GitHub repo `mithro/gf180-tcad` (public, description from spec §1), add as `origin`, push `main`. Configure: `gh api -X PATCH repos/mithro/gf180-tcad -F allow_squash_merge=false -F allow_rebase_merge=false -F allow_merge_commit=true -F delete_branch_on_merge=true`; branch protection on `main` requiring the `lint-test` check.
- [ ] **Step 2:** Write `tests/test_import.py::test_version` asserting `gf180tcad.__version__` matches `pyproject.toml`'s version (`0.1.0.dev0`). Run `uv run pytest` → FAIL (no package).
- [ ] **Step 3:** Add `pyproject.toml` (hatchling, src layout, `requires-python = ">=3.12"`, dev group: pytest, ruff), package `__init__.py`. Run → PASS.
- [ ] **Step 4:** `CONTRIBUTING.md`: the git rules from Global Constraints verbatim, the review process (agent review, user spot-checks), the forks-only rule, the public-data rule (spec A2), the "latest version; old only to prove it once worked" rule.
- [ ] **Step 5:** `ci.yml`: `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest -m "not sandbox"`. Push branch, open PR, confirm CI green.
- [ ] **Step 6:** Commit(s), review, merge with merge commit.

### Task 2: Resource sandbox

**Files:**
- Create: `tools/sandbox-run` (bash), `tools/sandbox-setup` (bash, uses sudo once), `src/gf180tcad/sandbox.py`, `tests/sandbox/test_limits.py`, `docs/reproduce/sandbox.md` (stub, filled in Task 5)

**Interfaces:**
- Produces:
  - `tools/sandbox-run [--mem 16g] [--cpus 8] [--pids 4096] [--image REF] [--workdir DIR] -- CMD...` — exit code of CMD; 137 on OOM. Mounts repo read-only at `/work/src`, `DIR` read-write at `/work/out`, runs as host UID:GID, `--network=none`, `--read-only` root with tmpfs `/tmp` (1 GiB), `--cgroup-parent=gf180-tcad.slice`, thread env vars from Global Constraints.
  - `gf180tcad.sandbox.run(cmd: list[str], *, out_dir: Path, mem: str = "16g", cpus: int = 8, image: str | None = None) -> subprocess.CompletedProcess` — raises `SandboxOOM` on 137, `SandboxError` on other non-zero.
  - Image default read from `docker/IMAGE` (one line, `ghcr.io/mithro/gf180-tcad-base@sha256:...`), until Task 3 lands use the IIC digest.

- [ ] **Step 1:** `tools/sandbox-setup`: create `/etc/systemd/system/gf180-tcad.slice` with `MemoryMax=128G`, `MemorySwapMax=0`, `TasksMax=32768`; `systemctl daemon-reload`; idempotent. Run it once.
- [ ] **Step 2:** Write tests (marker `sandbox`, need Docker):
  - `test_oom_is_reported`: `python3 -c "b=bytearray(3*2**30)"` with `mem="1g"` raises `SandboxOOM`; afterwards `docker ps` shows no leftover container.
  - `test_network_disabled`: `python3 -c "import socket; socket.create_connection(('1.1.1.1',53),2)"` exits non-zero.
  - `test_pids_limited`: fork bomb guarded by `ulimit`-free loop spawning 200 `sleep` with `pids=64` fails, host unaffected.
  - `test_in_slice`: inside the container, `/proc/self/cgroup` path contains `gf180-tcad.slice`.
  - `test_outputs_owned_by_user`: file written to `/work/out` is owned by the host UID.
- [ ] **Step 3:** Run `uv run pytest -m sandbox tests/sandbox` → FAIL.
- [ ] **Step 4:** Implement `tools/sandbox-run` and `sandbox.py` (thin `subprocess` wrapper over the script). Containers use `--rm` and a `--name gf180tcad-<uuid>` so a killed job is cleaned up (`trap` → `docker rm -f`).
- [ ] **Step 5:** Run → PASS. Commit, PR, review, merge.

### Task 3: Base image, provenance probe and reproducible ghcr build

**Files:**
- Create: `docker/base/Dockerfile`, `docker/IMAGE`, `docker/base/probe_versions.py`, `docker/base/versions.json` (generated, committed), `.github/workflows/image.yml`, `tests/test_versions.py`

**Interfaces:**
- Consumes: Task 2 `sandbox-run`.
- Produces: `ghcr.io/mithro/gf180-tcad-base@sha256:<digest>` recorded in `docker/IMAGE`; `docker/base/versions.json` with keys `base_image`, `python`, `ngspice`, `xyce`, `klayout`, `gdsfactory`, `devsim`, `pdk_root`, `gf180mcu_variant` (`"gf180mcuD"`), `open_pdks_commit`, `sm141064_ngspice_sha256`, `sm141064_xyce_sha256`, `design_ngspice_sha256`.

- [ ] **Step 1:** Known facts from probing the digest during planning (re-confirm, put in the PR description):
  - `PDK_ROOT=/foss/pdks`; variant dir `/foss/pdks/gf180mcuD`; open_pdks commit in `/foss/pdks/gf180mcuD/.config/nodeinfo.json` → `commit.open_pdks` = `1689ac3f2dc763876eaf967227c7dfe831b031ae` (version `1.0.608`); nodeinfo options `MIM_2P0`, `METAL5` (irrelevant to FET models but recorded).
  - System `python3` is 3.12.3 at `/usr/bin/python3`; gdsfactory preinstalled in `/usr/local/lib/python3.12/dist-packages`; DEVSIM not installed.
  - ngspice at `/foss/tools/ngspice/bin/ngspice`, Xyce at `/foss/tools/xyce/bin/Xyce`; **neither is on `PATH`** when the default entrypoint is bypassed — the Dockerfile must add both to `PATH`.
  - `/foss/pdks/versions.txt` is **stale** (claims Python 3.10.12, ngspice 43) — the probe must read versions from the tools themselves, never from that file.
  - UID 1000 has no `/etc/passwd` entry, so `getpass.getuser()` (gdsfactory import) raises `KeyError` — set `ENV USER=gf180tcad LOGNAME=gf180tcad HOME=/tmp/home` in the Dockerfile and create `$HOME` in the sandbox tmpfs.
  - Confirm Xyce is a serial build (`Xyce -capabilities`); if parallel-only, stop and report — Task 9 depends on it.
- [ ] **Step 2:** `Dockerfile`: `FROM hpretl/iic-osic-tools@sha256:306585de…557be`; `ARG SOURCE_DATE_EPOCH`; copy `uv.lock`-exported `requirements.lock` and `pip install --require-hashes --no-deps -r` into a venv at `/opt/gf180tcad`; set `ENTRYPOINT []` (the IIC image's default entrypoint starts a desktop — must not run), `ENV` thread vars, `PDK=gf180mcuD`.
- [ ] **Step 3:** Test `tests/test_versions.py::test_versions_json_matches_image` (marker `sandbox`): runs `probe_versions.py` in the sandbox and asserts its output equals committed `versions.json`. Run → FAIL. Implement probe (hash model files, read versions from tool `--version` output). Run → PASS.
- [ ] **Step 4:** `image.yml` on GitHub-hosted runner: free disk (remove `/usr/share/dotnet`, `/usr/local/lib/android`, `/opt/ghc`), `docker buildx build` with `--build-arg SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)`, `--output type=image,rewrite-timestamp=true`, push to ghcr on `main` only; a second job rebuilds and fails if the digest differs. Also build locally and compare digest with CI's — record both in the PR.
- [ ] **Step 5:** Update `docker/IMAGE`; commit, PR, review, merge.

### Task 4: Deterministic result I/O and hash manifest

**Files:**
- Create: `src/gf180tcad/io.py`, `src/gf180tcad/manifest.py`, `tests/test_io.py`, `tests/test_manifest.py`, `results/MANIFEST.sha256` (empty)

**Interfaces:**
- Produces:
  - `write_csv(path: Path, columns: dict[str, Sequence[float]], meta: Mapping[str, str]) -> None` — header lines `# key: value` (sorted keys), then a CSV header row and rows with `repr(float)`.
  - `read_csv(path: Path) -> tuple[dict[str, np.ndarray], dict[str, str]]`
  - `write_json(path: Path, obj) -> None` — `sort_keys=True, indent=2`, floats via `repr`, trailing newline.
  - `manifest.update(root: Path, manifest: Path) -> None`, `manifest.verify(root: Path, manifest: Path) -> list[str]` (returns mismatching/missing/extra paths, relative, sorted). Line format `<sha256>  <relpath>` sorted by path.
  - CLI `python -m gf180tcad.manifest {update,verify} results/`.

- [ ] **Step 1:** Tests: `test_csv_roundtrip_exact` (values incl. `1e-300`, `-0.0`, `0.1+0.2` round-trip bit-exactly); `test_csv_bytes_stable_under_locale` (set `LC_ALL=de_DE.UTF-8` if available — output bytes identical); `test_json_sorted_and_stable`; `test_manifest_detects_change_missing_extra`. Run → FAIL.
- [ ] **Step 2:** Implement. Run → PASS. Commit, PR, review, merge.

### Task 5: Sphinx documentation skeleton and Read the Docs

**Files:**
- Create: `docs/conf.py`, `docs/index.md`, `docs/reproduce/index.md`, `docs/reproduce/sandbox.md`, `docs/results/index.md`, `docs/comparison/index.md`, `docs/comparison/agreement.md`, `docs/limitations/index.md`, `docs/limitations/silicon-validation.md`, `docs/limitations/literature.md`, `.readthedocs.yaml`, `docs/requirements` group in `pyproject.toml`; modify `.github/workflows/ci.yml` (add `docs` job: `sphinx-build -W -b html docs docs/_build`).

**Interfaces:**
- Produces: the four top-level sections (a)–(d) from spec §10; `docs/_generated/` (git-ignored) reserved for pages written by Task 13.

- [ ] **Step 1:** Content: `agreement.md` carries spec §5 (both levels, the tolerance table, calibration/validation split, verdict levels) and §6 taxonomy, adapted for readers; `silicon-validation.md` carries spec §7; `literature.md` spec §11 with `[verify]` items marked "unverified"; `limitations/index.md` lists: no silicon data, Phase 0–1 only SPICE, TCAD not started, unverified citations.
- [ ] **Step 2:** `.readthedocs.yaml`: `build.os: ubuntu-24.04`, python 3.12, install docs group, `sphinx.configuration: docs/conf.py`, `fail_on_warning: true`.
- [ ] **Step 3:** Run `uv run sphinx-build -W -b html docs docs/_build` → PASS. Build twice and `diff -r` (excluding `.doctrees`, `_static` hashes) to confirm stable output.
- [ ] **Step 4:** Hand-off: ask the user to create the Read the Docs project for `mithro/gf180-tcad` (or authorise it). Commit, PR, review, merge.

### Task 6: Device, geometry and bias matrix

**Files:**
- Create: `src/gf180tcad/devices.py`, `tests/test_devices.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Geometry: w_um: float; l_um: float; role: Literal["calibration", "validation"]`
  - `@dataclass(frozen=True) class Device: name: str; polarity: Literal[1, -1]; spice_model: str; geometries: tuple[Geometry, ...]`
  - `DEVICES: dict[str, Device]` with keys `"nfet_05v0"`, `"pfet_05v0"`.
  - `@dataclass(frozen=True) class Sweep: name: str; kind: Literal["idvg", "idvd", "cv"]; vds: tuple[float, ...]; vgs: tuple[float, ...]; vbs: tuple[float, ...]` — magnitudes; polarity applied by the netlister.
  - `SWEEPS: tuple[Sweep, ...]`, `CORNERS = ("typical", "ff", "ss", "fs", "sf")`, `TEMPS_C = (25.0,)`.
  - `geometry_id(g: Geometry) -> str` → e.g. `"w10p0_l0p60"`.

- [ ] **Step 1:** Tests pin spec §5.2 values:
  - nfet geometries `(10, 0.6) (10, 0.7) (10, 1) (10, 2) (10, 10) (1.6, 0.7)`; pfet `(10, 0.5) (10, 0.7) (10, 1) (10, 2) (10, 10) (1.6, 0.7)`.
  - roles: calibration = W10 at L ∈ {10, 2, Lmin}; validation = W10 at L ∈ {0.7, 1} and 1.6/0.7.
  - `idvg_lin`: vds (0.1,), vgs 0→5 step 0.01 (501 points), vbs (0, 1, 2); `idvg_sat`: vds (5.0,), same vgs, vbs (0, 1, 2); `idvd`: vgs (1, 2, 3, 4, 5), vds 0→5 step 0.01, vbs (0,); `cv`: vgs −5→5 step 0.05, vds (0,), vbs (0,), f = 1 MHz; plus `ioff`: vgs (0,), vds (5.5,).
  - `geometry_id(Geometry(10, 0.6, ...)) == "w10p0_l0p60"`.
- [ ] **Step 2:** Run → FAIL; implement; run → PASS. Commit, PR, review, merge.

### Task 7: PDK provenance

**Files:**
- Create: `src/gf180tcad/pdk.py`, `tests/test_pdk.py`

**Interfaces:**
- Consumes: `docker/base/versions.json` (Task 3).
- Produces: `@dataclass(frozen=True) class PdkInfo: root: Path; variant: str; open_pdks_commit: str; ngspice_lib: Path; ngspice_design: Path; xyce_lib: Path; xyce_design: Path`; `locate(pdk_root: Path | None = None) -> PdkInfo` (defaults to `$PDK_ROOT`, variant `gf180mcuD`); `check_against(info: PdkInfo, versions: Path) -> None` raises `PdkMismatch` if model-file hashes differ from `versions.json`.

- [ ] **Step 1:** Tests (unit, using a temp fake PDK tree) for path resolution and hash mismatch; one `sandbox` test calling `locate()` in the image and `check_against` → no error. Run → FAIL; implement; run → PASS. Commit, PR, review, merge.

### Task 8: ngspice netlist, runner and parser

**Files:**
- Create: `src/gf180tcad/spice/__init__.py`, `src/gf180tcad/spice/netlist.py`, `src/gf180tcad/spice/ngspice.py`, `src/gf180tcad/spice/rawfile.py`, `tests/spice/test_netlist.py`, `tests/spice/test_ngspice.py`

**Interfaces:**
- Consumes: `Device`, `Geometry`, `Sweep` (Task 6), `PdkInfo` (Task 7), `sandbox.run` (Task 2).
- Produces:
  - `instance_params(device: Device, g: Geometry) -> dict[str, str]` — PDK xschem defaults (from `libs.tech/xschem/symbols/nfet_05v0.sym`), nf = 1: `ad = as = W·0.18u`, `pd = ps = 2·(W + 0.18u)`, `nrd = nrs = 0.18u/W`, `sa = sb = sd = 0`, `m = 1`.
  - `ngspice_netlist(device, g, sweep, corner: str, temp_c: float, pdk: PdkInfo) -> str` — `.include design.ngspice`, `.lib sm141064.ngspice <corner>`, `.option` with `num_threads=1`; terminal sources d/g/s/b; DC `.dc` nested sweeps for idvg/idvd; `.ac` at 1 MHz per Vg point for `cv`, producing `cgg = imag(i(vg))/(2π f)` with sign handled; outputs a binary raw file.
  - `run_ngspice(netlist: str, out_dir: Path) -> dict[str, np.ndarray]` — runs in sandbox, parses raw, raises `SpiceError` on any ngspice error/warning about convergence or on a point count ≠ expected.
  - `read_raw(path: Path) -> dict[str, np.ndarray]` (ngspice binary raw, real and complex).

- [ ] **Step 1:** Unit tests: `test_instance_params_w10` (`ad == "1.8e-12"` … exact strings), `test_pfet_polarity` (pfet netlist has negative Vds/Vgs sources, source tied to 0, bulk sweep positive for |Vbs|), `test_netlist_has_no_stat` (contains `sw_stat_global=0` and `sw_stat_mismatch=0` effective — assert `design.ngspice` included and no `.lib ... statistical`), `test_rawfile_roundtrip` on a checked-in tiny raw fixture.
- [ ] **Step 2:** Sandbox tests: `test_idvg_nfet_w10_l0p6_runs` (501 × 3 points, Id monotonic in Vgs at Vds = 5), `test_bin_boundary_l0p7` (both n and p run without error), `test_two_runs_byte_identical` (raw-derived CSV bytes equal across two runs), `test_failure_on_bad_model` (model name typo → `SpiceError`).
- [ ] **Step 3:** Run → FAIL; implement; run → PASS. Commit, PR, review, merge.

### Task 9: Xyce runner and engine cross-check

**Files:**
- Create: `src/gf180tcad/spice/xyce.py`, `tests/spice/test_xyce.py`

**Interfaces:**
- Consumes: Task 8 `instance_params`, `Sweep`, `PdkInfo`.
- Produces: `xyce_netlist(...)` same signature as `ngspice_netlist`; `run_xyce(netlist, out_dir) -> dict[str, np.ndarray]` (CSV `.print` output parsed); `engine_diff(a: dict, b: dict, key: str = "id") -> float` (max relative difference where |Id| > 1e-12 A).

- [ ] **Step 1:** Sandbox test `test_engines_agree` for every geometry of both devices, `idvg_sat` and `idvd`, typical corner: `engine_diff < 0.005` (spec: > 0.5 % flags a reference problem). If any geometry fails, the test reports it; the task must document the cause in `docs/limitations/` rather than loosen the threshold.
- [ ] **Step 2:** Run → FAIL; implement; run → PASS (or documented failure, decided with the reviewer). Commit, PR, review, merge.

### Task 10: Metric extraction

**Files:**
- Create: `src/gf180tcad/metrics.py`, `tests/test_metrics.py`

**Interfaces:**
- Produces (all inputs are magnitudes: |Vgs|, |Id|; callers strip polarity; W, L in µm):
  - `vt_maxgm(vgs, id, vds) -> float` — linear extrapolation at max gm, minus vds/2.
  - `vt_cc(vgs, id, w_um, l_um, i0=100e-9) -> float` — Vgs where Id = i0·W/L (log-linear interpolation).
  - `idsat_per_um(id_at_5v5v, w_um) -> float` (µA/µm).
  - `id_lin(vgs, id, vt) -> float` at Vgs = Vt + 0.5 V (interpolated).
  - `gm(vgs, id) -> np.ndarray`, `gds(vds, id) -> np.ndarray` (central differences, 2nd-order at ends).
  - `subthreshold_slope(vgs, id, i_lo=1e-11, i_hi=1e-8) -> float` (mV/dec, fit over the window per µm W).
  - `ioff_per_um(id, w_um) -> float`, `dibl(vt_lin, vt_sat, vds_lin=0.1, vds_sat=5.0) -> float` (mV/V), `body_effect(vt_vbs0, vt_vbs2) -> float` (V).
  - `extract_all(device: Device, g: Geometry, data: Mapping[str, dict[str, np.ndarray]]) -> dict[str, float]` with keys `vt_lin_maxgm, vt_lin_cc, vt_sat_cc, dibl_mv_per_v, body_effect_v, idsat_ua_per_um, id_lin_a, gm_peak_s, gds_at_5v_s, ss_mv_per_dec, ioff_pa_per_um, cgg_inv_ff, cgg_acc_ff`.

- [ ] **Step 1:** Tests on synthetic curves with known answers: square-law + exponential subthreshold model with Vt = 0.7 V, SS = 85 mV/dec → `vt_maxgm` within 2 mV, `subthreshold_slope` within 0.5 mV/dec, `vt_cc` exact at constructed point; gm of `id = k(vgs-vt)^2` equals `2k(vgs-vt)` to 1e-6 relative; `dibl(0.70, 0.66) == 8.163...` mV/V; pfet-derived magnitudes give identical results to nfet input.
- [ ] **Step 2:** Run → FAIL; implement; run → PASS. Commit, PR, review, merge.

### Task 11: Reference generation command and committed results

**Files:**
- Create: `src/gf180tcad/reference.py`, `src/gf180tcad/__main__.py`, `Makefile`, `tests/test_reference.py`, `results/spice/**` (generated, committed)

**Interfaces:**
- Consumes: Tasks 4, 6–10.
- Produces:
  - CLI `python -m gf180tcad spice-reference [--engine ngspice|xyce|both] [--corner …] [--device …] [--jobs N] --out results/spice` (jobs admitted so that `N × 16 GiB ≤ 128 GiB`).
  - Layout: `results/spice/<engine>/<corner>/<device>/<geometry_id>/<sweep>.csv`, `.../metrics.json`, `results/spice/provenance.json` (copy of `versions.json` + git commit of the generator, not the date).
  - `make reproduce` → runs spice-reference for both engines, all corners, then `manifest verify`.

- [ ] **Step 1:** Test `test_reference_subset_hash_stable` (sandbox): run nfet 10/0.6 typical ngspice twice into two temp dirs; all bytes equal.
- [ ] **Step 2:** Run → FAIL; implement; run → PASS.
- [ ] **Step 3:** Generate the full set locally with a progress Monitor (ETA per the user's cadence rule); `manifest update`; commit results in a separate commit from code. Commit, PR, review, merge.

### Task 12: PDK spec-window sanity and corner envelope

**Files:**
- Create: `src/gf180tcad/specwindow.py`, `data/pdk_elec_spec.json`, `tests/test_specwindow.py`, `results/spice/envelope.json` (generated)

**Interfaces:**
- Consumes: metrics JSON from Task 11.
- Produces:
  - `data/pdk_elec_spec.json` — public PDK electrical spec values with source URL `https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_3.html`: NE2 W/L 10/0.6 VT0 0.58/0.70/0.82 V, Idsat 400/500/600 µA/µm, Ioff ≤ 10 pA/µm; PE2 10/0.5 values as published (implementer copies exact numbers from the page and its VT0/Idsat bias definitions).
  - `envelope(metrics_by_corner: dict[str, dict[str, float]]) -> dict[str, tuple[float, float]]`; `window(metric, spec, envelope) -> tuple[float, float]` = wider of spec min–max and corner envelope (spec §5.2).
- [ ] **Step 1:** Tests: `test_tt_within_pdk_spec` — TT ngspice metrics at nfet 10/0.6 and pfet 10/0.5 lie inside the published min–max (using the spec page's own Vt definition); `test_envelope_contains_tt` for every metric and geometry. Run → FAIL; implement; run → PASS. A failing TT-vs-spec check is a finding to document, not to suppress.
- [ ] **Step 2:** Generate `envelope.json`, update manifest. Commit, PR, review, merge.

### Task 13: Generated results and comparison pages

**Files:**
- Create: `src/gf180tcad/docgen.py`, `src/gf180tcad/plots.py`, `tests/test_docgen.py`; modify `docs/conf.py` (run docgen at build start), `docs/results/index.md`, `docs/comparison/index.md`.

**Interfaces:**
- Consumes: `results/spice/**`, `envelope.json`, `pdk_elec_spec.json`.
- Produces: per device/geometry page `docs/_generated/results/<device>/<geometry_id>.md` with Id–Vg (lin/log), Id–Vd, Cgg–Vg plots (all corners shaded envelope, TT line, ngspice vs Xyce) and a metrics table; a summary page listing TT-vs-spec status and ngspice-vs-Xyce max difference. Plots as SVG with `svg.hashsalt="gf180tcad"` and `metadata={"Date": None}` so they are byte-stable.

- [ ] **Step 1:** Tests: `test_svg_deterministic` (render twice → identical bytes); `test_pages_cover_all_geometries` (one page per device × geometry); `test_docs_build_offline` (docs build reads only committed files — run with no network).
- [ ] **Step 2:** Run → FAIL; implement; run → PASS; `sphinx-build -W` clean. Commit, PR, review, merge.

### Task 14: GitHub-hosted determinism cross-check

**Files:**
- Create: `.github/workflows/crosscheck.yml`, `tests/crosscheck_subset.txt`

**Interfaces:**
- Consumes: `make reproduce` pieces (Task 11), `docker/IMAGE`.
- Produces: workflow on PRs and weekly: free disk, pull image by digest, run the subset listed in `crosscheck_subset.txt` (nfet & pfet, W10/Lmin and 1.6/0.7, typical, ngspice and Xyce, all sweeps) with `--mem 12g --cpus 4`, then `manifest verify` restricted to those paths; fail on any hash difference and upload differing files as an artefact.

- [ ] **Step 1:** Run the workflow on a branch; confirm hashes equal the locally generated ones. If they differ, stop and diagnose (systematic-debugging) — record the cause and fix in docs (d); never weaken to a tolerance compare without an explicit documented reason (spec §9 fallback).
- [ ] **Step 2:** Add the cross-check status to `docs/reproduce/index.md` (which results are cross-checked on GitHub, which only local). Commit, PR, review, merge.

### Task 15: Secondary PDK (`d658698`) comparison

**Files:**
- Create: `src/gf180tcad/pdkdiff.py`, `tests/test_pdkdiff.py`, `results/spice-pdk-d658698/**`, `docs/comparison/pdk-versions.md`

**Interfaces:**
- Consumes: Task 7 `locate(pdk_root=…)`, Task 11 CLI with `--pdk-root`.
- Produces: `ciel`-fetched gf180mcu `d658698bd8bc` PDK (inside the sandbox, network enabled only for the fetch step, then pinned by file hashes in `data/pdk-d658698.sha256`); TT ngspice run of all geometries; `pdkdiff.compare(a_metrics_dir, b_metrics_dir) -> dict` summarising per-metric differences; a doc page stating whether the run-1/2 PDK models differ from latest for these devices, and re-checking the spec §4 card values (TOXE, NDEP, …) against the latest card.

- [ ] **Step 1:** Test `test_pdkdiff_zero_for_identical` and `test_pdkdiff_reports_metric_delta`. Run → FAIL; implement; run → PASS.
- [ ] **Step 2:** Generate, update manifest, write page. Commit, PR, review, merge.

---

## Phase exit

- [ ] `make reproduce` on a clean clone reproduces every file in `results/` (manifest verify clean).
- [ ] GitHub cross-check green; Read the Docs build green and public.
- [ ] Whole-branch review of `main` since the spec merge by a fresh reviewer; findings fixed.
- [ ] Write the Phase 2 plan (gplugins fork + MOSCAP) using the then-current state.
