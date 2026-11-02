# SPDX-License-Identifier: Apache-2.0
"""The reduced mesh artefact of a 2D job (design spec §10.1 "Mesh pictures", issue #39).

The full 2D meshes (``mesh.msh``, gmsh MSH 2.2 ASCII) stay out of the repository. This package
cuts a window around the gate from one and keeps it as a small deterministic ``.npz``, so the
docs' mesh figure and the 3D renders draw the job's own mesh elements:

- :mod:`gf180tcad.meshcut.msh` reads a mesh strictly (MSH 2.2 ASCII, triangles and lines only);
- :mod:`gf180tcad.meshcut.window` keeps the whole elements whose centroid lies in the window,
  with their nodes bit-equal to the full mesh's;
- :mod:`gf180tcad.meshcut.npz` writes the arrays as a byte-for-byte reproducible zip;
- :mod:`gf180tcad.meshcut.artefact` writes and checks the artefact and its meta file, and
  :func:`read` reads one back;
- :mod:`gf180tcad.meshcut.job` is the job that runs in the TCAD image: it checks the mesh's
  sha256, rebuilds the job's cross-section, cuts the window and adds the net doping;
- :mod:`gf180tcad.meshcut.__main__` is the command line: ``cut`` and ``regenerate`` on the
  host, ``cut-job`` and ``regenerate-job`` in the sandbox.

The node coordinates stay in the mesh file's own unit, centimetres, so that every kept
coordinate is the full mesh's double, unconverted. The unit comes from gplugins:
``third_party/gplugins/gplugins/devsim/get_simulation.py`` sets ``um_to_cm = 1e-4`` (line 38),
makes it the default ``mesh_scaling_factor`` of ``create_2Duz_simulation`` (line 49) and
passes it to the mesher as ``global_scaling`` (line 138); :mod:`gf180tcad.tcad.moscap2d`
calls ``create_2Duz_simulation`` without overriding it. :data:`UM_PER_MSH_UNIT` converts the
coordinates to um for the window rule and for drawing.
"""

ARTEFACT = "mesh-window.npz"
"""File name of the reduced mesh artefact (an npz under ``results/tcad/meshes/``)."""
META = "mesh-window.meta.json"
"""File name of the artefact's metadata (sorted-key JSON) beside it."""
MAX_BYTES = 2_000_000
"""Size budget of one artefact in bytes (design spec §10.1: at most 2 MB per job)."""
FORMAT = 1
"""Version of the artefact's member set and metadata schema."""
UM_PER_MSH_UNIT = 1e4
"""Micrometres per mesh-file length unit (cm): the inverse of gplugins' ``mesh_scaling_factor``."""


def read(job_dir):
    """The window of the committed artefact in ``job_dir``: :func:`gf180tcad.meshcut.artefact.read`."""
    from gf180tcad.meshcut import artefact

    return artefact.read(job_dir)
