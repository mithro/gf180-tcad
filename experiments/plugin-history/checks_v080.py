# SPDX-License-Identifier: Apache-2.0
"""Check driver for gplugins v0.8.0: did the DEVSIM plugin work on its own Sept-2023 stack?

Runs in the sandbox with no network, in the v0.8.0 venv that ``python -m gf180tcad.history``
installs (see README.md here). It is two blocks of the v0.8.0 source turned into named checks,
with only the result recording added:

- the PIN waveguide of ``test_pin_waveguide`` (``gplugins/devsim/test_devsim.py``):
  ``PINWaveguide(core_width=500 nm, core_thickness=220 nm, slab_thickness=90 nm)``,
  ``ddsolver()``, then ``ramp_voltage`` to 0 and to -1 V (the test ramps to -5 V and then solves
  optical modes with tidy3d; neither is part of this record);
- the PN slab of the ``if __name__ == "__main__":`` block of ``gplugins/devsim/get_solver.py``:
  ``straight_pn(length=10)`` trimmed to ``[[3,-4],[3,4],[5,4],[5,-4]]``, the anode/cathode contact
  layers (105, 0)/(106, 0) from VIAC AND NPP / VIAC AND PPP, its ``resolutions``,
  ``xsection_bounds=[(4,-4),(4,4)]`` and ``mesh_scaling_factor=1e-4``; ``DDComponent(...)``,
  ``ddsolver()``, then ``get_refined_mesh(...)`` exactly as in the block. The block solves only at
  equilibrium; it never calls ``ramp_voltage``.

Changes from the v0.8.0 code (also listed in docs/limitations/plugin-history.md):

- the generic PDK is activated first (``get_layer_stack()`` needs an active PDK);
- the layer map is ``gdsfactory.generic_tech.LAYER``: gdsfactory 7.6.1 has no ``gf.tech``, so the
  block's ``gf.tech.LayerMap()`` raises AttributeError;
- **added**: ``ramp_voltage`` of the PN slab to 0.1 and 0.2 V, on ``DDComponent.ramp_voltage``'s
  default contact ``cathode`` (the VIAC AND PPP contact, so forward bias), and the physical
  anchors recorded around it (NetDoping range, built-in potential, depletion width, the
  anode-cathode contact potential difference at each step);
- **added**: the junction probe of the PN slab (``pn_junction``): the physical groups of the
  mesh file, the Potential across the rib's junction on the bottom edge at every step, and each
  silicon region's Potential range. It shows why the bias never reaches the junction: the mesh
  has no ``core___slab90`` group, so the rib, which holds the junction, floats;
- the PIN waveguide is solved, ramped and deleted before the PN slab is built (DEVSIM solves every
  device it holds at once, and DDComponent sets extended precision globally);
- the -5 V ramp and the tidy3d ``make_waveguide`` mode solves of ``test_pin_waveguide`` are not
  run;
- the block's second ``DDComponent`` and ``ddsolver(global_meshsize_array=...)`` after
  ``get_refined_mesh`` are never reached, because ``get_refined_mesh`` raises; they are recorded
  as the ``refined_solve`` check, not run.

Usage: ``python checks_v080.py --mesh-scale R --out RAW.json``. ``R`` multiplies every value of
the PN slab's ``resolutions``; the PIN check uses DEVSIM's own mesh and ignores it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness

PIN_DEVICE = "MyDevice"  # hard-coded in v0.8.0 PINWaveguide
PIN_VOLTAGES = (0.0, -1.0)
PN_VOLTAGES = (0.1, 0.2)
PN_VSTEP = 0.1
#: The junction probe's offset to the neutral n and p sides of the rib's junction (> the
#: ~0.075 um depletion half-width at 1e17 / 1e17, < the rib half-width), as in the fork's probe.
JUNCTION_OFFSET_UM = 0.2


def build_pin():
    from gplugins.devsim import get_simulation_xsection

    nm = 1e-9
    c = get_simulation_xsection.PINWaveguide(
        core_width=500 * nm,
        core_thickness=220 * nm,
        slab_thickness=90 * nm,
    )
    c.ddsolver()
    return c


def pin_bias_point(c, v: float) -> dict:
    """Currents of the PIN contacts and the depletion width on the waveguide-centre cut."""
    import devsim

    cols = {k: [] for k in ("x", "y", "Electrons", "Holes", "NetDoping")}
    for region in ("core", "slab"):
        for k in cols:
            cols[k] += devsim.get_node_model_values(device=PIN_DEVICE, region=region, name=k)
    cm = 1e-2
    y_centre_cm = c.core_thickness / 2 / cm  # the rib's vertical centre, y = 110 nm
    width_cm, y_cut_cm, nodes = harness.depletion_width(
        cols["x"],
        cols["y"],
        cols["Electrons"],
        cols["Holes"],
        cols["NetDoping"],
        y_target=y_centre_cm,
    )
    return {
        "v": v,
        "currents": harness.contact_currents(PIN_DEVICE, ("left", "right")),
        "depletion_width_um": width_cm * 1e4,
        "depletion_cut_y_um": y_cut_cm * 1e4,
        "depleted_nodes": nodes,
    }


def ramp_pin(c) -> list[dict]:
    # as test_pin_waveguide: Vstep is the final voltage, Vinit the previous one
    out = []
    for ind, voltage in enumerate(PIN_VOLTAGES):
        vinit = 0 if ind == 0 else PIN_VOLTAGES[ind - 1]
        c.ramp_voltage(Vfinal=voltage, Vstep=PIN_VOLTAGES[-1], Vinit=vinit)
        out.append(pin_bias_point(c, voltage))
    return out


def pn_slab_inputs(mesh_scale: float) -> dict:
    """The arguments of the block's ``DDComponent(...)``, with the resolutions scaled."""
    import gdsfactory as gf
    from gdsfactory.generic_tech import LAYER as layermap
    from gdsfactory.generic_tech import get_generic_pdk
    from gdsfactory.pdk import get_layer_stack
    from gdsfactory.technology import LayerStack
    from gplugins.devsim.doping import get_doping_info_generic

    get_generic_pdk().activate()

    # We choose a representative subdomain of the component
    waveguide = gf.Component()
    waveguide.add_ref(
        gf.geometry.trim(
            component=gf.components.straight_pn(length=10, taper=None),
            domain=[[3, -4], [3, 4], [5, 4], [5, -4]],
        )
    )

    # We will restrict the physical mesh to a subset of layers:
    physical_layer_stack = LayerStack(
        layers={
            k: get_layer_stack().layers[k]
            for k in (
                "slab90",
                "core",
            )
        }
    )

    # Simulation layers for contacts
    anode_layer = (105, 0)
    cathode_layer = (106, 0)

    # We will generate contacts where the vias intersect heavy doping
    via_contact_locations = waveguide.extract(layermap.VIAC)
    NPP_location = waveguide.extract(layermap.NPP)
    PPP_location = waveguide.extract(layermap.PPP)
    waveguide.add_ref(
        gf.geometry.boolean(via_contact_locations, NPP_location, operation="AND", layer=anode_layer)
    )
    waveguide.add_ref(
        gf.geometry.boolean(
            via_contact_locations, PPP_location, operation="AND", layer=cathode_layer
        )
    )
    contact_info = {
        "anode": {
            "gds_layer": anode_layer,
            "physical_layerlevel_to_replace": "via_contact",
            "physical_layerlevel_to_contact": "slab90",
        },
        "cathode": {
            "gds_layer": cathode_layer,
            "physical_layerlevel_to_replace": "via_contact",
            "physical_layerlevel_to_contact": "slab90",
        },
    }

    waveguide.show()

    return {
        "component": waveguide,
        "xsection_bounds": [(4, -4), (4, 4)],
        "full_layer_stack": get_layer_stack(),
        "physical_layer_stack": physical_layer_stack,
        "doping_info": get_doping_info_generic(),
        "contact_info": contact_info,
        "resolutions": harness.scaled_resolutions(mesh_scale),
        "mesh_scaling_factor": 1e-4,
        "background_tag": None,
    }


def build_ddcomponent(mesh_scale: float):
    from gplugins.devsim.get_solver import DDComponent

    return DDComponent(**pn_slab_inputs(mesh_scale))


def _si_values(c, name) -> list[float]:
    import devsim

    out = []
    for r in c.regions["si"]:
        out += devsim.get_node_model_values(device=c.device, region=r, name=name)
    return out


def pn_junction(c) -> dict:
    """Does the bias reach the junction itself? (an addition; see harness.junction_probe)

    ``junction``: the Potential across the junction, which lies in the rib (``core``), on the
    bottom edge. ``potential_range_by_region``: ``[min, max]`` Potential of each silicon region,
    which shows where the extrema of ``potential_span_v`` lie.
    """
    import devsim

    rows, ranges = {}, {}
    for r in c.regions["si"]:
        v = {
            k: devsim.get_node_model_values(device=c.device, region=r, name=k)
            for k in ("x", "y", "Potential", "NetDoping")
        }
        rows[r] = list(zip(v["x"], v["y"], v["Potential"], v["NetDoping"]))
        ranges[r] = [min(v["Potential"]), max(v["Potential"])]
    return {
        "junction": harness.junction_probe(
            rows, rib="core", slab="slab90", offset_um=JUNCTION_OFFSET_UM
        ),
        "potential_range_by_region": ranges,
    }


def pn_bias_state(c) -> dict:
    """Does the bias applied on the cathode reach the device?

    The mean Potential of each contact's nodes, their difference, and the Potential span (max -
    min) over the silicon, which is the built-in potential at equilibrium and drops by the
    forward bias if the junction sees it; then the junction probe (:func:`pn_junction`).
    """
    si = c.regions["si"]
    pot = {k: harness.contact_potential(c.device, k, si) for k in ("anode", "cathode")}
    potential = _si_values(c, "Potential")
    return {
        "contact_potential_v": pot,
        "anode_minus_cathode_v": pot["anode"] - pot["cathode"],
        "potential_span_v": max(potential) - min(potential),
        **pn_junction(c),
    }


def pn_equilibrium(c) -> dict:
    """Physical anchors of the solved PN slab at equilibrium (all contacts at 0 V).

    The depletion width is taken on the device's bottom edge (y = 0), the only mesh row through
    the junction: the gmsh mesh is unstructured, so the slab has no mid-height row. Under the rib
    (which holds the junction) that edge belongs to the ``core`` region, so both silicon regions
    are used.
    """
    doping, potential = _si_values(c, "NetDoping"), _si_values(c, "Potential")
    cols = [_si_values(c, k) for k in ("x", "y", "Electrons", "Holes", "NetDoping")]
    width_cm, y_cut_cm, nodes = harness.depletion_width(*cols, y_target=0.0)
    return {
        "net_doping_min_cm3": min(doping),
        "net_doping_max_cm3": max(doping),
        "builtin_potential_v": max(potential) - min(potential),
        "depletion_width_um": width_cm * 1e4,
        "depletion_cut_y_um": y_cut_cm * 1e4,
        "depleted_nodes": nodes,
        **pn_bias_state(c),
    }


def describe_ddcomponent(c) -> dict:
    import devsim

    regions = devsim.get_region_list(device=c.device)
    counts = {
        r: len(devsim.get_node_model_values(device=c.device, region=r, name="x")) for r in regions
    }
    return {
        "device": c.device,
        "regions": {k: list(v) for k, v in c.regions.items()},
        "devsim_regions": list(regions),
        "contacts": list(devsim.get_contact_list(device=c.device)),
        "interfaces": list(devsim.get_interface_list(device=c.device)),
        # the mesh file ddsolver() wrote and DEVSIM read (an addition: is core___slab90 there?)
        "msh_physical_groups": harness.msh2_physical_names(Path(c.temp_file_name)),
        "node_count_by_region": counts,
        "node_count": sum(counts.values()),
        "equilibrium": pn_equilibrium(c),
    }


def ramp_pn(c) -> list[dict]:
    # an addition: the v0.8.0 block never ramps; DDComponent.ramp_voltage's default contact
    out = []
    for ind, voltage in enumerate(PN_VOLTAGES):
        vinit = 0.0 if ind == 0 else PN_VOLTAGES[ind - 1]
        c.ramp_voltage(Vfinal=voltage, Vstep=PN_VSTEP, Vinit=vinit, contact_name="cathode")
        out.append(
            {
                "v": voltage,
                "currents": harness.contact_currents(c.device, ("anode", "cathode")),
                **pn_bias_state(c),
            }
        )
    return out


def refine(c):
    import numpy as np

    return c.get_refined_mesh(
        factor=2.0,
        refine_dict={
            "Potential": {
                "func": lambda x0, x1: abs(x0 - x1),
                "threshold": 0.05,
            },
            "Electrons": {
                "func": lambda x0, x1: np.abs(np.log10(x0) - np.log10(x1)),
                "threshold": 1,
            },
        },
        refine_regions=["si"],
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh-scale", type=float, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    checks: dict = {}
    result: dict = {"checks": checks, "mesh_scale": args.mesh_scale}

    def skip(name, missing):
        checks[name] = harness.not_run(f"needs {missing}, which did not pass")

    # DEVSIM solves every device it holds at once, and DDComponent sets the extended-precision
    # solver globally, so the PIN waveguide is solved, ramped and deleted before the PN slab
    # exists: each sees the state its own block would have.
    checks["import"], _ = harness.run_check(lambda: __import__("gplugins.devsim"))
    ramps = {}
    if checks["import"]["status"] == "pass":
        checks["pin_test"], pin = harness.run_check(build_pin)
        if pin is not None:
            ramps["pin"], bias = harness.run_check(lambda: ramp_pin(pin))
            if bias is not None:
                result["pin"] = {"bias": bias}
            from gplugins.devsim import clear_devsim_cache

            clear_devsim_cache()
        checks["ddcomponent_mesh"], dd = harness.run_check(
            lambda: build_ddcomponent(args.mesh_scale)
        )
    else:
        skip("pin_test", "import")
        skip("ddcomponent_mesh", "import")
        dd = None
    if dd is not None:
        checks["ddsolver"], _ = harness.run_check(dd.ddsolver)
    else:
        skip("ddsolver", "ddcomponent_mesh")
    solved = checks["ddsolver"]["status"] == "pass"
    if solved:
        result["ddcomponent"] = describe_ddcomponent(dd)
        ramps["pn_slab"], bias = harness.run_check(lambda: ramp_pn(dd))
        if bias is not None:
            result["ddcomponent"]["bias"] = bias
    if set(ramps) == {"pin", "pn_slab"}:
        failed = [r for r in ramps.values() if r["status"] != "pass"]
        checks["ramp"] = {**(failed[0] if failed else {"status": "pass"}), "parts": ramps}
    else:
        skip("ramp", "pin_test and ddsolver")
    if solved:
        checks["refine"], _ = harness.run_check(lambda: refine(dd))
    else:
        skip("refine", "ddsolver")
    # The block's last step: a new DDComponent solved on the refined mesh,
    # ddsolver(global_meshsize_array=meshing_field). It needs refine's result.
    if checks["refine"]["status"] == "pass":
        checks["refined_solve"] = harness.not_run("refine passed, but this driver stops at refine")
    else:
        skip("refined_solve", "refine (it needs get_refined_mesh's meshing field)")

    result["versions"] = harness.versions()
    harness.write(args.out, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
