# SPDX-License-Identifier: Apache-2.0
"""A 2D well-edge cross-section for DEVSIM, built from a plain parameter dictionary.

Coordinates in the parameters are micrometres: x along the surface, y down into the
silicon, y = 0 at the active silicon surface, oxide at y < 0. The left edge x = 0 is a
symmetry plane inside the high-voltage well. Runs inside the DEVSIM image.

Parameter dictionary (all lengths in um, dopings in cm^-3):

  width, depth          size of the silicon
  ox_top                height of the dielectric above the surface
  sub                   uniform substrate acceptor doping
  wells                 list of N regions, each {x0, x1, peak, rp, sy, sx[, name]}:
                        donors = peak * exp(-((y-rp)/sy)^2/2) * lateral(x), where lateral
                        falls as erfc with standard deviation sx beyond the drawn edges
                        x0 and x1. The first well is the high-voltage well; further
                        wells are floating rings.
  pfield                optional P surface layers, same keys as wells (acceptors)
  sti                   list of [x0, x1] field regions where the surface is recessed
  sti_depth             depth of that recess (0 for none)
  contacts              {"well": [x0, x1], "sub": [x0, x1]} on the silicon surface
  plates                list of {x0, x1, y0, y1, tie} conductors in the dielectric,
                        y0 < y1 <= 0, tie is "well", "sub" or "gate" (held at
                        the "gate_v" parameter while the well is swept)
  qf                    fixed oxide charge, cm^-2
  cyl                   true for cylindrical coordinates about x = 0 (a round corner of
                        radius equal to the well edge position)
  mesh                  {fine, surf, coarse} spacings
"""

from __future__ import annotations

import devsim as ds

import dd

UM = 1e-4


def _gauss_box(w, sign):
    """DEVSIM expression of one implanted box: Gaussian in depth, erfc roll-off at the edges."""
    x0, x1, sx = w["x0"] * UM, w["x1"] * UM, w["sx"] * UM
    rp, sy = w["rp"] * UM, w["sy"] * UM
    s2 = 1.4142135623730951 * sx
    lateral = f"0.5*(erfc((x-({x1}))/{s2}) - erfc((x-({x0}))/{s2}))"
    return f"{sign}{w['peak']}*exp(-0.5*((y-({rp}))/{sy})^2)*{lateral}"


def net_doping_expr(p):
    terms = [f"-{p['sub']}"]
    terms += [_gauss_box(w, "+") for w in p["wells"]]
    terms += [_gauss_box(w, "-") for w in p.get("pfield", [])]
    return " ".join(terms)


def _lines(p):
    """Mesh lines {pos: spacing} in x and y: fine at every drawn edge and at the surface."""
    m = p["mesh"]
    fine, surf, coarse = m["fine"], m["surf"], m["coarse"]
    xs = {0.0: coarse, p["width"]: coarse}
    edges = []
    for w in p["wells"] + p.get("pfield", []):
        edges += [w["x0"], w["x1"]]
    for a, b in p.get("sti", []):
        edges += [a, b]
    for pl in p.get("plates", []):
        edges += [pl["x0"], pl["x1"]]
    for a, b in p["contacts"].values():
        edges += [a, b]
    for e in edges:
        if 0.0 < e < p["width"]:
            xs[e] = fine
    ys = {0.0: surf, p["depth"]: coarse, -p["ox_top"]: coarse}
    deep = max(w["rp"] + 3 * w["sy"] for w in p["wells"] if w["peak"] < 1e19)
    ys[min(deep, p["depth"] / 2)] = max(fine, 2 * surf)
    if p.get("sti_depth", 0) > 0:
        ys[p["sti_depth"]] = surf
    for pl in p.get("plates", []):
        ys[pl["y0"]] = max(fine, 2 * surf)
        ys[pl["y1"]] = max(fine, 2 * surf)
    return xs, ys


def build(p, device="hv"):
    """Create the mesh and device. Returns the names the physics set-up needs."""
    mesh = device + "_mesh"
    ds.create_2d_mesh(mesh=mesh)
    xs, ys = _lines(p)
    for pos, sp in sorted(xs.items()):
        ds.add_2d_mesh_line(mesh=mesh, dir="x", pos=pos * UM, ps=sp * UM)
    for pos, sp in sorted(ys.items()):
        ds.add_2d_mesh_line(mesh=mesh, dir="y", pos=pos * UM, ps=sp * UM)
    w, d, top = p["width"] * UM, p["depth"] * UM, p["ox_top"] * UM
    eps = 1e-9
    ds.add_2d_region(mesh=mesh, material="Si", region="si", xl=0, xh=w, yl=0, yh=d)
    ds.add_2d_region(mesh=mesh, material="Oxide", region="ox", xl=0, xh=w, yl=-top, yh=0)
    ox_regions = ["ox"]
    sd = p.get("sti_depth", 0) * UM
    for k, (a, b) in enumerate(p.get("sti", []) if sd > 0 else []):
        name = f"sti{k}"
        ds.add_2d_region(mesh=mesh, material="Oxide", region=name,
                         xl=a * UM, xh=b * UM, yl=0, yh=sd)  # fmt: skip
        ox_regions.append(name)
    ox_contacts = {}
    for k, pl in enumerate(p.get("plates", [])):
        name = f"plate{k}"
        box = dict(xl=pl["x0"] * UM, xh=pl["x1"] * UM, yl=pl["y0"] * UM, yh=pl["y1"] * UM)
        ds.add_2d_region(mesh=mesh, material="metal", region=name, **box)
        ds.add_2d_contact(mesh=mesh, name=name, region="ox", material="metal", bloat=eps, **box)
        ox_contacts[name] = "ox"
    si_contacts = {}
    for name, (a, b) in p["contacts"].items():
        ds.add_2d_contact(mesh=mesh, name=name, region="si", material="metal",
                          xl=a * UM, xh=b * UM, yl=-eps, yh=eps, bloat=eps)  # fmt: skip
        si_contacts[name] = "si"
    interfaces = []
    for r in ox_regions:
        ds.add_2d_interface(mesh=mesh, name=f"si_{r}", region0="si", region1=r)
        interfaces.append(f"si_{r}")
    for r in ox_regions[1:]:
        ds.add_2d_interface(mesh=mesh, name=f"ox_{r}", region0="ox", region1=r)
        interfaces.append(f"ox_{r}")
    ds.finalize_mesh(mesh=mesh)
    ds.create_device(mesh=mesh, device=device)
    if p.get("cyl"):
        # x becomes the radius about the axis x = 0: the cross-section of a round corner
        ds.set_parameter(name="raxis_variable", value="x")
        ds.set_parameter(name="raxis_zero", value=0.0)
        for r in ds.get_region_list(device=device):
            ds.cylindrical_edge_couple(device=device, region=r)
            ds.cylindrical_node_volume(device=device, region=r)
            ds.cylindrical_surface_area(device=device, region=r)
        for name, value in (
            ("node_volume_model", "CylindricalNodeVolume"),
            ("edge_couple_model", "CylindricalEdgeCouple"),
            ("element_edge_couple_model", "ElementCylindricalEdgeCouple"),
            ("element_node0_volume_model", "ElementCylindricalNodeVolume@en0"),
            ("element_node1_volume_model", "ElementCylindricalNodeVolume@en1"),
            ("surface_area_model", "CylindricalSurfaceArea"),
        ):
            ds.set_parameter(name=name, value=value)
    have = set(ds.get_contact_list(device=device))
    missing = (set(si_contacts) | set(ox_contacts)) - have
    if missing:
        raise RuntimeError(f"contacts not created: {sorted(missing)}")
    interfaces = [i for i in interfaces if i in ds.get_interface_list(device=device)]
    return {"device": device, "si": ["si"], "ox": ox_regions, "si_contacts": si_contacts,
            "ox_contacts": ox_contacts, "interfaces": interfaces}  # fmt: skip


def setup_physics(p, names):
    """Doping, equilibrium Poisson solve, then the drift-diffusion equations."""
    dev = names["device"]
    for r in names["si"]:
        dd.silicon_parameters(dev, r)
        dd.set_doping(dev, r, net_doping_expr(p))
    for r in names["ox"]:
        dd.oxide_parameters(dev, r)
    dd.potential_only(dev, names["si"], names["ox"], names["si_contacts"],
                      names["ox_contacts"], names["interfaces"])  # fmt: skip
    dd.solve(abs_=1.0, rel=1e-9, iters=60)
    qf = p.get("qf", 0.0)
    if qf:
        dd.add_interface_charge(dev, "si", 0.0)
    dd.undamp_oxide(dev, names["ox"])
    dd.drift_diffusion(dev, names["si"], names["si_contacts"], with_qf=bool(qf))
    dd.solve(iters=60)
    # the oxide charge is switched on in steps, halved when a step does not converge: at
    # full strength the equilibrium solve does not converge from the charge-free start
    done, step = 0.0, qf / 8
    while qf and done < qf * (1 - 1e-9):
        nxt = min(qf, done + step)
        ds.set_parameter(device=dev, region="si", name="Qf", value=nxt)
        try:
            dd.solve(iters=40)
        except ds.error:
            ds.set_parameter(device=dev, region="si", name="Qf", value=done)
            step /= 2
            if step < qf / 4096:
                raise
            continue
        done = nxt
        step = min(step * 1.5, qf / 8)
