# charon-libs image: licence note

This directory builds [Charon](https://charon.sandia.gov/) 2.2.0 and the
[Trilinos](https://github.com/trilinos/Trilinos) commit it pins, from Sandia's source tarball.
The build recipe and the image description are on the
[image page](../../docs/reproduce/image.md#charon-images).

## Licences

Charon is licensed GPL-3.0-or-later (`LICENSE/Charon_LICENSE` in the tarball). Trilinos and
TriBITS are BSD-3-Clause, with some Trilinos packages under LGPL-2.1-or-later.

The patches under `patches/` change upstream source code, so each one keeps the licence of
the files it changes, not the repository's Apache-2.0 grant. Its first line is the
`SPDX-License-Identifier`. These patches change Charon and are GPL-3.0-or-later:

- `0001-codata2018-constants.patch`;
- `0005-interpreter-copy-without-rsync.patch`.

These patches change the Trilinos packages Kokkos, SEACAS and Teuchos, and are
BSD-3-Clause, the licence of those packages:

- `0002-kokkos-include-cstdint.patch`;
- `0003-exodus-netcdf-szip-macro.patch`;
- `0004-teuchos-include-cstdint.patch`.

Every other file in this directory is Apache-2.0, like the rest of gf180-tcad. The opts file
`opts/gf180.opts` holds only the project's own CMake options. The build reads Charon's
`General.opts` and `Linux.opts` from the tarball itself.

## Corresponding source

A published image distributes Charon binaries, so its corresponding source goes with it:

- `upstream.json` names the Charon, Trilinos and TriBITS tarballs, each with its URL and sha256;
- every `mirror_url` there points at the input mirror release `gf180-tcad/inputs/charon-20261102`;
- this directory holds the patches, the opts file and the build scripts;
- `/opt/charon/share/gf180tcad/SOURCES.json` in the image lists each of those files with its
  sha256. The build scripts it lists are `Dockerfile`, `build`, `build-charon.sh`,
  `fetch_sources.py`, `inputs.py` and `upstream.json`;
- `/opt/charon/share/doc/charon/` in the image holds Charon's licence.
