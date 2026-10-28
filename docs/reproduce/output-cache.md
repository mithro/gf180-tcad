(output-cache)=

# The output cache

Some generated files are too large to commit but take hours to regenerate: today the 25–62 MB
`mesh.msh` of each 2D {term}`job` ({ref}`moscap2d-meshes`). The output cache,
{{ output_cache }}, is a separate plain git repository that holds such files so that anyone can
fetch them instead of rerunning the job. It is effectively a shared cache for everyone
({repo}`design spec, section 9.1 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#91-output-cache-for-large-regenerable-artefacts>`).

The cache holds seven objects, the `mesh.msh` of seven calibrated cells of
[issue #35](https://github.com/mithro/gf180-tcad/issues/35):

| Cell | Mesh sha256 |
|---|---|
| nfet W10/L0.6 | `8dad0ca787dc…` |
| nfet W10/L0.7 and W1.6/L0.7 | `e0437cde0b28…` |
| nfet W10/L1 | `3715e9d78507…` |
| nfet W10/L2 | `95e3225699ce…` |
| pfet W10/L0.5 | `1a8513e2d300…` |
| pfet W10/L0.7 | `c3d2585f18a2…` |
| pfet W10/L1 | `62e0517082a3…` |

The meshes of the four committed 2D start jobs are not in it and are on no disk.
They have to be regenerated before they can be pushed ({ref}`first population <output-cache-first-population>`).

## The contract

- **Everything in it is regenerable** from this repository. It holds no original data.
- **It may be wiped and recreated at any time.** Clone it with `git clone --depth 1` and never
  depend on its history.
- **No {term}`provenance` lives there.** {repo}`results/MANIFEST.sha256` and the `provenance.json` and
  `cv.meta.json` files here are the truth. The cache stores a file under the sha256 of its
  uncompressed content, the hash a committed meta already names (`mesh_sha256`), and
  `tools/output-cache pull` writes a file only if its sha256 is that hash. Using the cache never
  changes a result or its provenance: {py:mod}`gf180tcad.outcache` is not a generator module,
  so it is not part of any {term}`generator_sha256`.
- **The documentation build never fetches from it.** The build stays offline and uses only
  committed files.
- No Git Large File Storage (git-LFS): it has bandwidth quotas. Each object is a plain git blob under 95 MB after
  compression; a file that does not fit is reported and left out.

## Layout

- `objects/sha256/<first 2 hex>/<sha256>.<ext>.gz`: the file, gzip-compressed deterministically
  (level 9, no file name, mtime 0), keyed by the sha256 of the uncompressed content.
- `index.json`: sorted JSON mapping each sha256 to its object path, sizes, the results paths it
  was found at, the `generator_sha256` of its results folder, the commit of this repository it was
  pushed from, the date and the job (device, dimension, parameter set, directory).
- a README: the contract, written by `tools/output-cache init`, so the whole repository can
  be recreated from nothing.

The cacheable files, the repository URLs and the size cap are in {repo}`data/output-cache.json`.
A {{ gmsh }} mesh compresses from 27.5 MB to 9.5 MB (measured, 10 s).

## Commands

{repo}`tools/output-cache` (all logic in {py:mod}`gf180tcad.outcache`); run with
`uv run --locked python tools/output-cache ...`.

```sh
tools/output-cache status          # which files the committed metas name are in the cache
tools/output-cache pull 8dad0ca787dc3d805661e6262725bb833ba33edf1b46bf7b4a3ce69afbc2ea64 --out mesh.msh
tools/output-cache pull results/tcad/moscap2d/<device>/<params>/<geometry>/mesh.msh
```

The first `pull` fetches the one cached mesh by its sha256. The second form writes a
committed job's mesh into place by the `mesh_sha256` its `cv.meta.json` names; the committed
start meshes are not in the cache, so for them it fails.

`status` and `pull` clone the cache shallow and blobless into a temporary directory under `tmp/`
(`--scratch` elsewhere) and download only `index.json` and the one object; `--cache` takes a
local checkout or another URL. `pull` refuses a file whose sha256 does not match and an existing
destination with other content (`--force` overwrites it). `make cache-status` runs `status`.

To add files after a run (needs write access to the cache repository):

```sh
git clone --depth 1 git@github.com:mithro/gf180-tcad-output-cache.git tmp/output-cache
tools/output-cache push --cache tmp/output-cache --dry-run
tools/output-cache push --cache tmp/output-cache --publish   # or: make cache-push
tools/output-cache verify --cache tmp/output-cache
```

(output-cache-first-population)=

**First population.** While the cache repository is still empty, a clone of it has no
`index.json`, and `push`, `status` and `pull` say the cache is not initialised. Create the
checkout with `init` instead of cloning, then push:

```sh
tools/output-cache init tmp/output-cache --remote git@github.com:mithro/gf180-tcad-output-cache.git
tools/output-cache push --cache tmp/output-cache --publish
```

`push` scans {repo}`results/` (`--results` elsewhere) for the configured files, refuses one whose
sha256 differs from the hash its meta names (a stale mesh), compresses and adds the missing
objects, rewrites `index.json` and the README, and commits with a message naming this
repository's commit; `--publish` then pushes. `verify` checks every object's hash against its
name, the sizes, the size cap and that the index and the objects agree.

To recreate the cache from nothing (every listed file must be present locally, for example
after rerunning the 2D jobs):

```sh
tools/output-cache init tmp/output-cache-new
tools/output-cache push --cache tmp/output-cache-new
git -C tmp/output-cache-new push --force origin main
```
