# SPDX-License-Identifier: Apache-2.0
"""The ideal abrupt-junction depletion width of the v0.8.0 PN slab's rib (issue #80).

Host-side arithmetic, no simulator. It writes one record, ``results/plugin-history/
abrupt-junction.json``, that the plugin-history page compares the recorded depletion widths
with.

The junction is the rib's: ``get_doping_info_generic`` of gplugins v0.8.0 dopes the N and P
layers of ``straight_pn`` with step profiles of 1e17 cm^-3 each (``n_conc``, ``p_conc``,
:data:`DOPING_SOURCE`). The constants are those of DEVSIM's ``simple_physics``, which v0.8.0's
``DDComponent`` solves with at 300 K (:data:`CONSTANTS_SOURCE`, :data:`TEMPERATURE_SOURCE`).

The depletion approximation of a step junction (the glossary entry "depletion approximation" of
docs/glossary.md and its source):

- built-in potential ``V_bi = V_t ln(N_A N_D / n_i^2)``, with ``V_t = k T / q``;
- total depletion width ``W = sqrt(2 eps V_bi (N_A + N_D) / (q N_A N_D))``, at zero bias;
- the n-side and p-side widths ``x_n = W N_A / (N_A + N_D)`` and ``x_p = W N_D / (N_A + N_D)``.

The record's measured width is the span where both carrier densities are below
``FRACTION`` |NetDoping| (``harness.depletion_width``). In the depletion approximation the
potential on each side is parabolic, ``V_t ln(1 / FRACTION)`` below its neutral level at
``sqrt(2 eps V_t ln(1 / FRACTION) / (q N))`` inside the depletion edge. So that span is
``W - sqrt(2 eps V_t ln(1/f) / (q N_D)) - sqrt(2 eps V_t ln(1/f) / (q N_A))``
(``inner_width_um``), the definition of the fork's ``_analytic_inner_width_um``
(:data:`FORK_TEST_SOURCE`).

Usage: ``uv run --locked python experiments/plugin-history/abrupt_junction.py --out DIR``.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import harness  # this directory: the recorded width's definition

from gf180tcad import io
from gf180tcad.explain import idealised

NAME = "abrupt-junction.json"
#: Where the rib's dopings come from: ``get_doping_info_generic`` of gplugins v0.8.0.
DOPING_SOURCE = (
    "https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/"
    "gplugins/devsim/doping.py#L29-L33"
)
#: The rib's dopings (cm^-3): ``n_conc`` and ``p_conc`` of :data:`DOPING_SOURCE`.
N_D_CM3 = 1e17
N_A_CM3 = 1e17
#: Where the constants come from: DEVSIM's ``simple_physics`` at the commit the page links.
CONSTANTS_SOURCE = (
    "https://github.com/devsim/devsim/blob/ec9905bbfdfacaf66e0cae7f2d98748f9bb8aeb0/"
    "python_packages/simple_physics.py#L34-L41"
)
#: ``q``, ``k``, ``eps_0``, ``eps_si`` and ``n_i`` of :data:`CONSTANTS_SOURCE`.
CONSTANTS = {
    "q_c": 1.6e-19,
    "k_j_per_k": 1.3806503e-23,
    "eps_0_f_per_cm": 8.85e-14,
    "eps_si": 11.1,
    "n_i_cm3": 1.0e10,
}
#: Where the temperature comes from: v0.8.0's ``DDComponent`` sets silicon at 300 K.
TEMPERATURE_SOURCE = (
    "https://github.com/mithro/gplugins/blob/624574ced6d9407306878c9fd00bede825640d94/"
    "gplugins/devsim/get_solver.py#L152-L154"
)
T_K = 300.0
#: The carrier-density threshold of the recorded depletion width (``harness.depletion_width``).
FRACTION = harness.FRACTION
#: The fork test that uses the same inner-width definition.
FORK_TEST_SOURCE = (
    "https://github.com/mithro/gplugins/blob/400f8423d7b0d1aac48eea1c0145342d0c1f766a/"
    "gplugins/devsim/tests/test_mesh.py#L210-L225"
)
CM_TO_UM = 1e4


def compute() -> dict:
    """The record: inputs, their sources, the formulas and the widths (µm), from the shared
    formulas of :mod:`gf180tcad.explain.idealised`."""
    c = CONSTANTS
    q, eps_r, eps0 = c["q_c"], c["eps_si"], c["eps_0_f_per_cm"]
    vt = c["k_j_per_k"] * T_K / q
    vbi = idealised.built_in_potential(N_A_CM3, N_D_CM3, c["n_i_cm3"], vt)
    w_cm = idealised.depletion_width(N_A_CM3, N_D_CM3, vbi, eps_r, eps0, q)
    total = N_A_CM3 + N_D_CM3
    # n (or p) falls below FRACTION of the doping where the potential is V_t ln(1/FRACTION)
    # inside the depletion edge: the depth of that bending in the depletion approximation.
    # depletion_depth is documented for the MIS depth of a p-type body, sqrt(2 eps psi / (q N)).
    # The same parabola holds on either side of a step junction: inside a uniformly charged
    # layer of density q N, a potential drop psi from its edge is reached at that depth, so it
    # is called with N_D for the n side and N_A for the p side.
    psi_f = vt * math.log(1 / FRACTION)
    tail_n = idealised.depletion_depth(psi_f, N_D_CM3, eps_r, eps0, q)
    tail_p = idealised.depletion_depth(psi_f, N_A_CM3, eps_r, eps0, q)
    inner_cm = w_cm - tail_n - tail_p
    return {
        "doping": {"n_d_cm3": N_D_CM3, "n_a_cm3": N_A_CM3, "source": DOPING_SOURCE},
        "constants": {**c, "source": CONSTANTS_SOURCE},
        "t_k": T_K,
        "t_source": TEMPERATURE_SOURCE,
        "fraction": FRACTION,
        "formulas": {
            "v_t": "k T / q",
            "v_bi": "V_t ln(N_A N_D / n_i^2)",
            "width": "sqrt(2 eps_si eps_0 V_bi (N_A + N_D) / (q N_A N_D))",
            "inner_width": "W - sqrt(2 eps_si eps_0 V_t ln(1/f) / (q N_D))"
            " - sqrt(2 eps_si eps_0 V_t ln(1/f) / (q N_A))",
        },
        "inner_width_definition_source": FORK_TEST_SOURCE,
        "v_t_v": vt,
        "v_bi_v": vbi,
        "x_n_um": w_cm * N_A_CM3 / total * CM_TO_UM,
        "x_p_um": w_cm * N_D_CM3 / total * CM_TO_UM,
        "width_um": w_cm * CM_TO_UM,
        "inner_width_um": inner_cm * CM_TO_UM,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, required=True, help="directory of the record")
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    io.write_json(args.out / NAME, compute())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
