# charon-libs image: licence note

This directory builds [Charon](https://charon.sandia.gov/) 2.2.0 and the
[Trilinos](https://github.com/trilinos/Trilinos) commit it pins, from Sandia's source tarball.
The build recipe and the image description are on the
[image page](../../docs/reproduce/image.md#charon-images).

## Licences

Charon is licensed GPL-3.0-or-later (`LICENSE/Charon_LICENSE` in the tarball). Trilinos and
TriBITS are BSD-3-Clause, with some Trilinos packages under LGPL-2.1-or-later.

Two kinds of file here quote Charon and are therefore GPL-3.0-or-later, not under the
repository's Apache-2.0 grant. Each carries `SPDX-License-Identifier: GPL-3.0-or-later`:

- `opts/gf180.opts` (Charon's `General.opts` and `Linux.opts`, then the project's lines);
- every patch under `patches/`:
  - `0001-codata2018-constants.patch`.

Every other file in this directory is Apache-2.0, like the rest of gf180-tcad.

## Corresponding source

The image distributes Charon binaries, so its corresponding source is published with it:

- the input mirror release
  [`gf180-tcad/inputs/charon-20261102`](https://github.com/mithro/gf180-tcad/releases/tag/gf180-tcad/inputs/charon-20261102)
  holds the Charon, Trilinos and TriBITS tarballs named in `upstream.json`;
- this directory holds the patches, the opts file and the build scripts;
- `/opt/charon/share/gf180tcad/SOURCES.json` in the image lists each of those files with its
  sha256, and `/opt/charon/share/doc/charon/` holds Charon's licence.
