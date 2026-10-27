# SPDX-License-Identifier: Apache-2.0
"""The reduced mesh artefact of a 2D job (design spec §10.1 "Mesh pictures", issue #39).

The full 2D meshes (``mesh.msh``, gmsh MSH 2.2 ASCII) stay out of the repository. This package
cuts a window around the gate from one and keeps it as a small deterministic ``.npz``, so the
docs' mesh figure and the 3D renders draw the job's own mesh elements:

- :mod:`gf180tcad.meshcut.msh` reads a mesh strictly (MSH 2.2 ASCII, triangles and lines only);
- :mod:`gf180tcad.meshcut.window` keeps the whole elements whose centroid lies in the window,
  with their nodes bit-equal to the full mesh's;
- :mod:`gf180tcad.meshcut.npz` writes the arrays as a byte-for-byte reproducible zip.

The node coordinates stay in the mesh file's own unit, centimetres (gplugins writes the mesh
with ``mesh_scaling_factor = 1e-4``, um to cm), so that every kept coordinate is the full
mesh's double, unconverted. :data:`UM_PER_MSH_UNIT` converts them to um for the window rule
and for drawing.
"""

ARTEFACT = "mesh-window.npz"
META = "mesh-window.meta.json"
MAX_BYTES = 2_000_000
FORMAT = 1
UM_PER_MSH_UNIT = 1e4
"""Micrometres per mesh-file length unit (cm): the inverse of gplugins' ``mesh_scaling_factor``."""
