(pdk-versions)=

# PDK versions: runs 1 and 2 vs the latest

The design spec ({repo}`docs/superpowers/specs/2026-10-18-gf180-tcad-design.md`, §4) names
{{ open_pdks }} commit [`d658698bd8bc`](https://github.com/fossi-foundation/open-pdks/commit/d658698bd8bcf4e05fc7b5991a701247ba0d744c) ([1.0.604](https://github.com/fossi-foundation/open-pdks/commit/d658698bd8bcf4e05fc7b5991a701247ba0d744c)) as the {term}`GF180MCU`
{term}`PDK` of {{ wafer_space }} runs 1 and 2, and asks for it to be compared with the latest.
The {term}`SPICE` {term}`golden reference` ({repo}`results/spice`) uses the latest PDK, the one
in the pinned base image ({repo}`docker/IMAGE`, open_pdks [`1689ac3f2dc7`](https://github.com/fossi-foundation/open-pdks/commit/1689ac3f2dc763876eaf967227c7dfe831b031ae), recorded
in {repo}`docker/base/versions.json`). This page answers whether the {term}`model card` of
{term}`nfet_05v0` and {term}`pfet_05v0` differs between the two. It does not settle which PDK
every run-2 project used ({ref}`pdk-versions-run2`).

**Answer: no, between d658698 and the latest.** For these two devices the models are the
same. Rerun with the d658698 models,
every {{ ngspice }} result file at the {term}`TT` {term}`corner` is byte-identical to the
committed reference: 72 files (12 geometries × 5 {term}`sweep` CSVs and `metrics.json`), so every
metric delta is exactly 0. The two PDKs' model libraries differ in one `.lib` section only,
[`res`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38571), which the transistors never load.

## How it was checked

{py:mod}`gf180tcad.pdkdiff` does it in one command:

```{code-block} shell
uv run --locked python -m gf180tcad.pdkdiff run --out results/spice-pdk-d658698
```

({{ uv }} runs it in the project's locked environment.)

1. **Fetch.** {{ Ciel }} ([2.6.1](https://pypi.org/project/ciel/2.6.1/), shipped in the base
   image) fetches the {{ gf180mcu_pdk }} family at that commit, with only the
   {{ gf180mcu_models }} as a library, from its default public data source
   ([ciel-releases](https://github.com/fossi-foundation/ciel-releases)). This runs in the
   {term}`sandbox` and is the only step with network access.
2. **Pin.** Every model file (the 16 {{ ngspice }} and {{ Xyce }} model files) and the PDK's
   build record must match its sha256 in {repo}`data/pdk-d658698.sha256`, which lists them by
   path. Two independent
   fetches gave the same files. {repo}`data/pdk-d658698.versions.json` records the variant,
   the commit and the three hashes that {py:func}`gf180tcad.pdk.check_against` reads.
3. **Run.** One sandbox {term}`job` per geometry, with no network, runs
   {py:func}`gf180tcad.reference.run_job`, the generator's own job, with only its PDK lookup
   pointed at the pinned copy ({py:func}`gf180tcad.pdkdiff.run_pdk_job`). The SPICE generator
   modules are not edited, so the {term}`provenance` of {repo}`results/spice` does not change
   ({test}`tests/test_pdkdiff.py::test_reference_py_untouched`).
4. **Cards and compare.** {py:func}`gf180tcad.pdkdiff.cards` compares the two PDKs' files,
   `.lib` sections and card values, and {py:func}`gf180tcad.pdkdiff.compare` the metrics.

The results are in {repo}`results/spice-pdk-d658698`: the job tree
({repo}`results/spice-pdk-d658698/ngspice/typical`, the same layout as {repo}`results/spice`),
{repo}`results/spice-pdk-d658698/cards.json`, {repo}`results/spice-pdk-d658698/comparison.json`,
the two unified diffs and {repo}`results/spice-pdk-d658698/provenance.json`. Two runs gave
byte-identical trees. The tree is in {repo}`results/MANIFEST.sha256`. The SPICE cross-check
({ref}`cross-host-determinism`) and {py:func}`gf180tcad.manifest.verify_subset` select only
entries under `spice/`, so they do not include it.

## Which model files differ

| File | d658698 vs latest |
|---|---|
| The ngspice main library ([latest](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice), and its `.spice` copy) | differ: [`.lib res`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38571) only ({repo}`diff <results/spice-pdk-d658698/sm141064.ngspice.diff>`) |
| The Xyce main library (and its `.spice` copy) | differ: `.lib res` only ({repo}`diff <results/spice-pdk-d658698/sm141064.xyce.diff>`) |
| The design files (ngspice, Xyce) | identical |
| The MIM-capacitor and BJT libraries (ngspice, Xyce) | identical |
| The build record (listed in {repo}`data/pdk-d658698.sha256`) | differs (versions and commits) |

Each library has 50 `.lib` sections. 49 are identical, among them [`typical`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L105) (the
TT `.param` values), [`nfet_06v0_t`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37038) and [`pfet_06v0_t`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38074) (the
{term}`BSIM4` cards), and the wrapper subcircuits of the two devices are identical too. The one
change is in the resistor section [`res`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38571): the parasitic capacitor model
[`fox_sub`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38715) of nine poly resistors. d658698 writes it as a [`.model`](https://ngspice.sourceforge.io/docs.html)
line `.model fox_sub c` with a continuation line {repo}`+ cox=8.85e-05 <results/spice-pdk-d658698/sm141064.ngspice.diff#L8>` (ngspice) or
{repo}`+ level=1 <results/spice-pdk-d658698/sm141064.xyce.diff#L8>` (Xyce), and the latest writes
[`.model fox_sub c cj=8.85e-05`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38715). This affects resistor simulations only. The TT
section never loads `res`.

## Metric deltas at TT

The delta is latest − d658698, for every metric and geometry ({term}`geometry id`). Source:
{repo}`results/spice-pdk-d658698/comparison.json`, checked against the trees by
{test}`tests/test_pdkdiff.py::test_committed_comparison_is_current`.

| Device | Geometry | Metrics compared | Largest \|Δ\| | Largest \|Δ\|/\|a\| | Files byte-identical |
|---|---|---|---|---|---|
| {term}`nfet_05v0` | `w10p0_l0p60` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`nfet_05v0` | `w10p0_l0p70` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`nfet_05v0` | `w10p0_l10p00` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`nfet_05v0` | `w10p0_l1p00` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`nfet_05v0` | `w10p0_l2p00` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`nfet_05v0` | `w1p6_l0p70` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`pfet_05v0` | `w10p0_l0p50` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`pfet_05v0` | `w10p0_l0p70` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`pfet_05v0` | `w10p0_l10p00` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`pfet_05v0` | `w10p0_l1p00` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`pfet_05v0` | `w10p0_l2p00` | 13 | 0.0 | 0.0 | 6 of 6 |
| {term}`pfet_05v0` | `w1p6_l0p70` | 13 | 0.0 | 0.0 | 6 of 6 |

Per metric, over the 12 geometries:

| Metric | Largest \|Δ\| | Largest \|Δ\|/\|a\| | Geometries with Δ = 0 |
|---|---|---|---|
| {term}`body_effect_v` | 0.0 | 0.0 | 12 of 12 |
| {term}`cgg_acc_ff` | 0.0 | 0.0 | 12 of 12 |
| {term}`cgg_inv_ff` | 0.0 | 0.0 | 12 of 12 |
| {term}`dibl_mv_per_v` | 0.0 | 0.0 | 12 of 12 |
| {term}`gds_at_5v_s` | 0.0 | 0.0 | 12 of 12 |
| {term}`gm_peak_s` | 0.0 | 0.0 | 12 of 12 |
| {term}`id_lin_a` | 0.0 | 0.0 | 12 of 12 |
| {term}`idsat_ua_per_um` | 0.0 | 0.0 | 12 of 12 |
| {term}`ioff_pa_per_um` | 0.0 | 0.0 | 12 of 12 |
| {term}`ss_mv_per_dec` | 0.0 | 0.0 | 12 of 12 |
| {term}`vt_lin_cc` | 0.0 | 0.0 | 12 of 12 |
| {term}`vt_lin_maxgm` | 0.0 | 0.0 | 12 of 12 |
| {term}`vt_sat_cc` | 0.0 | 0.0 | 12 of 12 |

## Card values re-checked

The design spec §4 quotes card values read from the run-1/2 card. Both cards are re-read here
(`cards.json`). The d658698 card and the latest card have every one of these entries on the
same line with the same expression. The links go to the latest card's source in the
{{ gf180mcu_models }}, which is byte-identical to the image's card ({ref}`process-data`).
Expressions in {term}`corner` parameters (such as `nfet_06v0_tox`) are 0 or 1 at TT, so the
TT value is the leading number.

| Parameter | `nfet_06v0.0` (L 0.7–50 µm) | `nfet_06v0.1` (L 0.6–0.7 µm) | `pfet_06v0.0` | {repo}`Spec §4 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md>`, n / p | Same in both cards |
|---|---|---|---|---|---|
| ACDE | `0.3` ([37059](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37059)) | `0.3` ([37397](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37397)) | `0.7` ([38095](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38095)) | — / — | yes |
| ALPHA0 | `-1.88e-007` ([37067](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37067)) | `-1.88e-007` ([37405](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37405)) | `9.6e-7` ([38099](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38099)) | set / — | yes |
| BETA0 | `36.6` ([37072](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37072)) | `36.6` ([37410](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37410)) | `50.8` ([38104](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38104)) | set / — | yes |
| CAPMOD | `2` ([37080](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37080)) | `2` ([37418](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37418)) | `2` ([38109](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38109)) | — / — | yes |
| CGDL | `1.5e-010*nfet_06v0_cgdo` ([37085](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37085)) | `1.5e-010*nfet_06v0_cgdo` ([37423](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37423)) | `5.25e-11*pfet_06v0_dcgdo` ([38114](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38114)) | — / — | yes |
| CGDO | `1e-010*nfet_06v0_cgdo` ([37086](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37086)) | `1e-010*nfet_06v0_cgdo` ([37424](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37424)) | `7.71e-11*pfet_06v0_dcgdo` ([38115](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38115)) | — / — | yes |
| CGSL | `1.5e-010*nfet_06v0_cgso` ([37088](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37088)) | `1.5e-010*nfet_06v0_cgso` ([37426](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37426)) | `5.25e-11*pfet_06v0_dcgso` ([38116](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38116)) | — / — | yes |
| CGSO | `1e-010*nfet_06v0_cgso` ([37089](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37089)) | `1e-010*nfet_06v0_cgso` ([37427](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37427)) | `7.71e-11*pfet_06v0_dcgso` ([38117](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38117)) | — / — | yes |
| {term}`DLC` | `5.4e-8` ([37104](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37104)) | `5.4e-8` ([37442](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37442)) | `7.4e-9` ([38129](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38129)) | — / — | yes |
| {term}`EPSROX` | `3.9` ([37126](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37126)) | `3.9` ([37464](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37464)) | `3.9` ([38144](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38144)) | — / — | yes |
| IGBMOD | `0` ([37134](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37134)) | `0` ([37472](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37472)) | `0` ([38150](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38150)) | 0 / — | yes |
| IGCMOD | `0` ([37135](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37135)) | `0` ([37473](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37473)) | `0` ([38151](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38151)) | 0 / — | yes |
| K1 | `0.9` ([37147](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37147)) | `0.9` ([37485](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37485)) | `0.9588` ([38162](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38162)) | 0.9 / — | yes |
| K2 | `-0.001` ([37148](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37148)) | `-0.001` ([37486](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37486)) | `8.936e-3` ([38163](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38163)) | — / — | yes |
| LMAX | `5.0001e-005` ([37176](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37176)) | `7e-007` ([37514](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37514)) | `50.01e-6` ([38176](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38176)) | 0.7 µm and 50 µm / — | yes |
| LMIN | `7e-007` ([37177](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37177)) | `6e-007` ([37515](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37515)) | `0.5e-6` ([38177](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38177)) | 0.6 µm and 0.7 µm / 0.5 µm | yes |
| LPE0 | `1.63e-007` ([37182](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37182)) | `1.63e-007` ([37520](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37520)) | `-4.4e-8` ([38178](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38178)) | 163 nm / — | yes |
| MOIN | `15` ([37201](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37201)) | `15` ([37539](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37539)) | `15` ([38197](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38197)) | — / — | yes |
| NDEP | `1.7e+017` ([37202](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37202)) | `1.7e+017` ([37540](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37540)) | `1.7e17` ([38198](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38198)) | 1.7e17 cm⁻³ / 1.7e17 cm⁻³ | yes |
| {term}`NGATE` | `1e+020` ([37204](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37204)) | `1e+020` ([37542](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37542)) | `3.6e19` ([38200](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38200)) | 1e20 cm⁻³ / 3.6e19 cm⁻³ | yes |
| {term}`NSD` | `1e+020` ([37217](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37217)) | `1e+020` ([37555](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37555)) | `6e16` ([38207](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38207)) | 1e20 cm⁻³ / — | yes |
| RDSW | `2175` ([37284](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37284)) | `2175` ([37622](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37622)) | `1.426e3` ([38245](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38245)) | 2175 Ω·µm / — | yes |
| TNOM | `25` ([37308](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37308)) | `25` ([37646](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37646)) | `25` ([38254](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38254)) | — / — | yes |
| TOXE | `1.52e-008+nfet_06v0_tox` ([37309](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37309)) | `1.52e-008+nfet_06v0_tox` ([37647](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37647)) | `1.56e-8+pfet_06v0_dtox` ([38255](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38255)) | 15.2 nm / — | yes |
| TOXP | `1.6e-008+nfet_06v0_tox` ([37311](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37311)) | `1.6e-008+nfet_06v0_tox` ([37649](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37649)) | not set | 16 nm / — | yes |
| U0 | `0.052500014` ([37319](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37319)) | `0.052500361` ([37657](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37657)) | `0.0151` ([38260](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38260)) | 0.0525 m²/(V·s) / 0.0151 m²/(V·s) | yes |
| VSAT | `103999.98*nfet_06v0_vsat` ([37336](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37336)) | `64848.09*nfet_06v0_vsat` ([37674](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37674)) | `8.55e4` ([38273](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38273)) | 1.04e5 m/s / — | yes |
| VTH0 | `0.67314+nfet_06v0_vth0` ([37337](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37337)) | `0.67314+nfet_06v0_vth0` ([37675](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37675)) | `-0.8978+pfet_06v0_dvth0` ([38274](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38274)) | 0.673 V / — | yes |
| {term}`XJ` | `1.5e-007` ([37377](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37377)) | `1.5e-007` ([37715](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37715)) | `1.5e-7` ([38291](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L38291)) | 0.15 µm / — | yes |

Every spec §4 value is confirmed on both cards. Two of them are rounded in the spec: VTH0 is
0.67314 V, and VSAT is 103999.98 m/s. The nfet has two {term}`L bins <L bin>`, 0.6–0.7 µm and
0.7–50 µm; the pfet {term}`Lmin` is 0.5 µm. IGCMOD = IGBMOD = 0 (no gate leakage), and ALPHA0
and BETA0 are set (impact-ionisation substrate current on). The pfet card sets no TOXP.

(pdk-versions-run2)=

## The PDK of a run-2 project checkout

A run-2 project's checkout of the PDK (its `gf180mcuD` directory) reports a different build in
its build record: open_pdks [`40cee970`](https://github.com/fossi-foundation/open-pdks/commit/40cee970d8a9b7eaea35a34fe7d6068f05721f0a) ([1.0.537](https://github.com/fossi-foundation/open-pdks/commit/40cee970d8a9b7eaea35a34fe7d6068f05721f0a)), with an ngspice main
library of sha256 `6edba54d23b38a2c60f8ffdbaa3eb75a7568c615e4820808969bd1121b77b1aa`. That is
neither d658698 (`f6f4a96e…`) nor the latest (`69a7ab87…`), so not every run-2 project used
d658698. This page compares only d658698, the PDK the design spec names. A separate comparison
against 40cee970 is needed before any run-2 silicon is used for validation.

## What this means

The TT reference, and every {term}`TCAD` comparison made against it, also holds for the d658698
PDK, for these two devices. Whether it holds for the 40cee970 build of the run-2 checkout above
is not known yet. Only TT was rerun. The other corners load the same
`nfet_06v0_t`/`pfet_06v0_t` sections, with their own corner `.param` values, which were not
compared here.
