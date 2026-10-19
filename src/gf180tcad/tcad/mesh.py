# SPDX-License-Identifier: Apache-2.0
"""Mesh specifications of the TCAD MOS capacitors (:class:`MeshSpec`).

A :class:`MeshSpec` gives the node spacing at the three places where the C-V physics lives:
the poly/oxide interface (poly depletion), the oxide, and the silicon/oxide interface (the
accumulation and inversion layers), plus the bulk spacing and the grading (the largest ratio
of neighbouring spacings). :meth:`MeshSpec.scaled` refines all of them uniformly, which is the
"uniform refinement" of the mesh-convergence study
(:repo:`spec section 5.2 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#52-technical-definition>`,
:repo:`Task 10 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-10-mesh-convergence-tooling>`).

The same spec drives both meshers: :meth:`MeshSpec.to_mesh1d` gives the
`gplugins.devsim.Mesh1D <https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/stack1d.py>`_ of the 1D stack and :meth:`MeshSpec.to_resolution_specs` the
`meshwell <https://github.com/simbilod/meshwell>`_ resolution specs of the 2D cross-section
(:repo:`Task 11 <docs/superpowers/plans/2026-10-18-phase2-gplugins-devsim-moscap.md#task-11-2d-moscap-from-gdsfactory-geometry-and-the-ccox--1-artefact>`).
Both import the plugin lazily
(it needs the TCAD image), so this module imports on the host.

Lengths are nm in the spec and um in the plugin and in
`meshwell <https://github.com/simbilod/meshwell>`_.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from typing import ClassVar

NM_TO_UM = 1e-3


@dataclass(frozen=True)
class MeshSpec:
    """Node spacings (nm) and the grading of a MOS capacitor mesh.

    - ``h_poly_nm``: the spacing at the poly/oxide interface, graded into the poly bulk. Poly
      depletion adds to the capacitance in inversion, so the poly is refined like the rest.
    - ``h_ox_nm``: the largest spacing in the oxide. In 1D (:meth:`spacing_um`) the oxide
      spacing is ``min(h_ox, neighbour)`` at each face, so with spacings at the interfaces
      below ``h_ox`` (as in :attr:`MeshSpec.DEFAULT_1D`) ``h_ox`` has no effect; that is exact, since the
      charge-free oxide has a linear potential. The 1D results record the effective spacings.
    - ``h_si_surface_nm``: the spacing at the silicon/oxide interface.
    - ``h_si_bulk_nm``: the spacing the poly and the body grade to, away from the oxide.
    - ``grading``: the largest ratio of neighbouring spacings (> 1).
    """

    h_poly_nm: float
    h_ox_nm: float
    h_si_surface_nm: float
    h_si_bulk_nm: float
    grading: float

    DEFAULT_1D: ClassVar[MeshSpec]
    DEFAULT_2D: ClassVar[MeshSpec]

    # meshwell samples a threshold field's distance at mass / (sizemin / 2) points per curve,
    # capped by ``max_sampling`` (meshwell's default 100). gmsh's Distance field measures the
    # distance to those samples, so with the cap a 1 um interface is sampled every 10 nm and the
    # size there reaches sizemin + (grading - 1) * 5 nm (about 1.5 nm instead of 0.5 nm). The cap
    # is lifted to this value, far above any curve here (10 um / 0.1 nm = 1e5).
    MAX_SAMPLING: ClassVar[int] = 10**7

    def __post_init__(self) -> None:
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
                raise ValueError(f"MeshSpec.{f.name} must be a finite number, got {v!r}")
            if v <= 0:
                raise ValueError(f"MeshSpec.{f.name} must be > 0, got {v!r}")
            object.__setattr__(self, f.name, float(v))
        if self.grading <= 1:
            raise ValueError(f"MeshSpec.grading must be > 1, got {self.grading!r}")

    def scaled(self, r: float) -> MeshSpec:
        """Every spacing times ``r`` (> 0), the grading unchanged (uniform refinement)."""
        if not (r > 0 and math.isfinite(r)):
            raise ValueError(f"the scale must be > 0, got {r!r}")
        return MeshSpec(
            h_poly_nm=self.h_poly_nm * r,
            h_ox_nm=self.h_ox_nm * r,
            h_si_surface_nm=self.h_si_surface_nm * r,
            h_si_bulk_nm=self.h_si_bulk_nm * r,
            grading=self.grading,
        )

    def as_dict(self) -> dict[str, float]:
        """The fields by name (for result metadata)."""
        return asdict(self)

    def spacing_um(self, poly: str, oxide: str, body: str) -> dict[str, tuple[float, float]]:
        """The 1D spacing (um) of the stack ``poly | oxide | body`` (in that order along x).

        The poly grades from ``h_si_bulk`` at its contact to ``h_poly`` at the oxide, the
        oxide from ``min(h_ox, h_poly)`` to ``min(h_ox, h_si_surface)`` (the oxide has no
        charge, so its potential is linear and any spacing is exact there; matching its ends
        to the neighbours keeps the grading across both interfaces), and the body from
        ``h_si_surface`` at the oxide to ``h_si_bulk`` at its contact.
        """
        u = NM_TO_UM
        return {
            poly: (self.h_si_bulk_nm * u, self.h_poly_nm * u),
            oxide: (
                min(self.h_ox_nm, self.h_poly_nm) * u,
                min(self.h_ox_nm, self.h_si_surface_nm) * u,
            ),
            body: (self.h_si_surface_nm * u, self.h_si_bulk_nm * u),
        }

    def to_mesh1d(self, poly: str, oxide: str, body: str):
        """The `gplugins.devsim.Mesh1D <https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/stack1d.py>`_ of :meth:`spacing_um`, ``max_ratio = grading``."""
        from gplugins.devsim import Mesh1D

        return Mesh1D(self.spacing_um(poly, oxide, body), max_ratio=self.grading)

    def threshold_distmax_um(self, sizemin_nm: float) -> float:
        """The distance (um) over which a linear size field grows from ``sizemin_nm`` to bulk.

        A size growing linearly at the slope ``grading - 1`` has neighbouring cells within
        the grading, as the geometric 1D grading does: distmax = (h_bulk - h_min)/(grading - 1).
        """
        return (self.h_si_bulk_nm - sizemin_nm) / (self.grading - 1) * NM_TO_UM

    def to_resolution_specs(
        self, poly: str, oxide: str, body: str, *, background: str | None = None
    ) -> Mapping[str, list]:
        """`meshwell <https://github.com/simbilod/meshwell>`_ resolution specs (um) by region, for 2D.

        ``ConstantInField(h_ox)`` on the oxide surface, and threshold fields on the curves
        that the body and the poly share with the oxide (and the body with ``background``, the
        dielectric over the silicon outside the gate, if given): ``h_si_surface`` and
        ``h_poly`` at the interface, growing to ``h_si_bulk`` over
        :meth:`threshold_distmax_um`. The threshold fields sample their curves densely
        (:attr:`MAX_SAMPLING`).
        """
        from meshwell.resolution import ConstantInField, ThresholdField

        u = NM_TO_UM
        return {
            oxide: [ConstantInField(resolution=self.h_ox_nm * u, apply_to="surfaces")],
            body: [
                ThresholdField(
                    apply_to="curves",
                    sharing=[oxide] if background is None else [oxide, background],
                    sizemin=self.h_si_surface_nm * u,
                    sizemax=self.h_si_bulk_nm * u,
                    distmax=self.threshold_distmax_um(self.h_si_surface_nm),
                    max_sampling=self.MAX_SAMPLING,
                )
            ],
            poly: [
                ThresholdField(
                    apply_to="curves",
                    sharing=[oxide],
                    sizemin=self.h_poly_nm * u,
                    sizemax=self.h_si_bulk_nm * u,
                    distmax=self.threshold_distmax_um(self.h_poly_nm),
                    max_sampling=self.MAX_SAMPLING,
                )
            ],
        }


# The fixed starting spec of the 1D MOS capacitor. Task 10's mesh-convergence study replaces
# it by the selected level (results/tcad/meshconv/moscap1d/<device>/selected.json).
MeshSpec.DEFAULT_1D = MeshSpec(
    h_poly_nm=0.05, h_ox_nm=0.5, h_si_surface_nm=0.05, h_si_bulk_nm=20.0, grading=1.1
)

# The fixed starting spec of the 2D MOS capacitor (Task 11), refined by meshconv --dim 2 into
# results/tcad/meshconv/moscap2d/<device>/selected.json. Triangles are isotropic, so 0.05 nm at a
# 10 um interface is out of reach: the interfaces start at 0.5 nm. Unlike in 1D the oxide spacing
# matters in 2D: triangles of 2 nm in the 15 nm oxide over-estimate its discrete capacitance by
# about 0.3 % (0.6 % at 2 nm, 0.4 % at 1 nm, 0.3 % at 0.5 nm on the uniform stack, Task 11 report),
# so the oxide starts at 1 nm.
MeshSpec.DEFAULT_2D = MeshSpec(
    h_poly_nm=0.5, h_ox_nm=1.0, h_si_surface_nm=0.5, h_si_bulk_nm=100.0, grading=1.2
)
