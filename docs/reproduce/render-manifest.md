(render-manifest)=

# The render manifest

Each 3D render has a {term}`render manifest` beside its image, `<render>.render.json`. For every number
the render draws, it names the source file, the place inside it, the unit, the value and the scale.
The {repo}`design spec, section 10.1 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#101-3d-renders-of-the-simulated-processes>`
sets this rule.

This page lists the file's keys, the selector kinds and what the check rejects.
The module {py:mod}`gf180tcad.render.manifest` reads and checks the file. The test {test}`tests/test_renders.py::test_every_entry_rereads_its_source`
re-reads every entry of every committed render manifest from its source.
The synthetic example {repo}`tests/fixtures/renders/r-test.render.json` shows each kind of entry.

## Top-level keys

Key is the JSON key, Holds what its value is, Required whether every render manifest has it.

| Key | Holds | Required |
|---|---|---|
| `format` | the format number, 1 | yes |
| `render` | the render's name | yes |
| `inputs` | each source file, repo-relative, mapped to its sha256 | yes |
| `quantities` | each entry's name mapped to the entry | yes |
| `exaggeration` | the statements drawn into the image and printed on its page | yes |
| `device`, `params` | the device and parameter set the render shows | no |
| `outputs`, `scene`, `frames` | the rendered files, the scene description and the animation frames | no |
| `generator`, `image`, `cycles` | the generator hash, the render image and the renderer settings | no |

## Entry keys

An entry is either read from a file (`source` and `selector`) or derived (`derived` and `inputs`).
Its keys, read entries first:

- `source`: the repo-relative path of the file read, with no `..` part;
- `selector`: where the value sits inside that file;
- `derived` and `inputs`: a function of {py:mod}`gf180tcad.derive` and the entries passed to it;
- `unit`: the unit, or one unit per column for a several-column selector;
- `role` and `scale`: `geometry`, `axis`, `value` or `display`, and the factor the render applies;
- `label`: the words that name the entry in its exaggeration statement;
- `value` or `value_sha256`: a scalar's value, or the sha256 of an array's canonical JSON.

An entry with the role `geometry` or `axis` always has a `scale`. An entry whose scale is not 1
always has a `label`. Its exaggeration statement, such as "oxide thickness ×40, not to scale", is
in the file's `exaggeration` list. The canonical JSON is compact, with sorted keys and
shortest round-trip floats ({py:func}`gf180tcad.quantity.canonical_json`).

## Selector kinds

Kind is the selector's one key, Points at what its value names, Reads what comes back.

| Kind | Points at | Reads |
|---|---|---|
| `json` | a key path of key names and list indices | the value at that path |
| `csv` | column names and one row rule | one column or several, over all rows or one row |
| `npz` | the name of one array of an `.npz` archive | that array |
| `toml` | a key path of table and key names | the value at that path |

A CSV row rule is `rows: "all"`, `where` with one column and the value it equals exactly, or
`index` with a row number from 0. A CSV file may be gzip-compressed.

## Derived entries

A derived entry names one function of {py:mod}`gf180tcad.derive`. Each function's page entry
gives its equation and its reference. The functions use {{ numpy }} only and solve nothing, so a
render never recomputes what a simulation computed.

## Display-only values

The file {repo}`data/render/display.toml` holds the {term}`band gaps <band gap>` and the Si–SiO₂ band offsets that a band
diagram is drawn with. No simulation reads the file. Each value has a unit and a source in the
{ref}`literature list <lit-sze>`. The file's `mismatch` text compares the band gap the simulation
implies with the band gap the drawing uses. A committed render manifest reads every `display`
entry from this file and no other ({py:meth}`gf180tcad.render.manifest.Manifest.display_problems`).

## What the check rejects

The method {py:meth}`gf180tcad.render.manifest.Manifest.verify` reports each of these:

- an input file whose sha256 changed;
- a source file that is missing, unreadable, or not listed in `inputs`;
- a value read again that differs from the recorded value;
- a derived value that differs when the function is evaluated again;
- a scale other than 1 without its exaggeration statement;
- an exaggeration statement that no entry's scale matches.
