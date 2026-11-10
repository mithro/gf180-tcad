# SPDX-License-Identifier: Apache-2.0
"""One variant of a calibrated 2D MOS capacitor cell's cross-section, solved QS at its plateau
biases (issue #189: what in the cross-section supplies the card's edge capacitance).

Runs inside the sandbox (tools/sandbox-run, the stable TCAD image), from run.py:

    python3 /work/src/experiments/edge-sensitivity/variant.py DEVICE GID VARIANT OUT.json

VARIANT is ``base`` (the committed cell's cross-section, to check the harness against the
committed cv.csv), ``plugs`` (the source/drain electrodes run up as contact plugs of the PDK's
height, 0.86 um, with the inter-layer oxide around them), or ``bias<nm>`` (the poly and gate
oxide longer by <nm> nm at each end, the source/drain doping still self-aligned to them), or a
``+``-joined combination (``plugs+bias30``). ``ldd<peak>`` (e.g. ``ldd1e18``) adds a lightly
doped extension self-aligned to the (biased) poly edge: a Gaussian of that surface peak that
falls to the body doping at ``ldddepth<nm>`` (default 100 nm), and then moves the heavy
source/drain out by ``sp<nm>`` (the spacer, default 0) from the poly edge.
"""

import dataclasses
import json
import math
import sys
import time
from pathlib import Path

from gf180tcad.tcad import meshconv, moscap2d
from gf180tcad.tcad import stack as st
from gf180tcad.tcad.__main__ import geometry_of, load_params

# The PDK's contact height, diffusion to Metal1 (gf180mcuD libs.tech/klayout/tech/d25/
# gf180mcu.lyd25: contact_not_over_poly, zstart 0 nm, height 860 nm).
PLUG_UM = 0.86


def _rect(x0, x1, y, layer, component):
    component.add_polygon(
        [
            (x0, y - st._BAND_UM),
            (x1, y - st._BAND_UM),
            (x1, y + st._BAND_UM),
            (x0, y + st._BAND_UM),
        ],
        layer=layer,
    )


def _ldd_doping(proc, xs: st.CrossSection, *, peak: float, depth_um: float, spacer_um: float):
    """``xs.doping`` with the body's source/drain profiles replaced: the heavy one masked by the
    spacer (``spacer_um`` out from each poly edge), and an extension of surface ``peak`` that
    falls to the body doping at ``depth_um``, masked by the poly."""
    from gplugins.devsim import doping

    v = proc.values()
    g0, g1 = xs.gate_u
    s_sd = xs.sd_straggle_um
    s_ldd = depth_um / math.sqrt(2 * math.log(peak / v["n_ch_cm3"]))
    heavy = doping.gaussian(xs.sd_peak_cm3, 0.0, s_sd)
    light = doping.gaussian(peak, 0.0, s_ldd)
    lat_sd, lat_ldd = st.LATERAL_STRAGGLE_RATIO * s_sd, st.LATERAL_STRAGGLE_RATIO * s_ldd
    sd = (
        heavy * doping.lateral(lat_sd, None, g0 - spacer_um),
        heavy * doping.lateral(lat_sd, g1 + spacer_um, None),
        light * doping.lateral(lat_ldd, None, g0),
        light * doping.lateral(lat_ldd, g1, None),
    )
    donors, acceptors = xs.doping[st.BODY]
    body = (sd, acceptors) if proc.polarity == "n" else (donors, sd)
    return {**xs.doping, st.BODY: body}


def cross_section(
    proc, geometry, *, bias_um: float, plugs: bool, ldd: dict | None = None
) -> st.CrossSection:
    """The committed cell's cross-section (stack.build), with the gate longer by ``bias_um`` at
    each end and, with ``plugs``, the source/drain electrodes PLUG_UM tall. Its ``l_um`` is the
    poly's length (the mesh check compares them), so use ``cgg_ff_per_um``, not C per area."""
    from gdsfactory import Component

    base = st.build(proc, st.cell(proc.device, geometry), with_sd=True)
    (a0, y), (a1, _) = base.line
    g0, g1 = base.gate_u
    gx0, gx1 = a0 + g0 - bias_um, a0 + g1 + bias_um
    sim = Component()
    # the electrodes and the body as stack.build drew them, the gate rectangles widened
    drawn = base.component
    for name in ("source_contact", "drain_contact"):
        layer = st.MARKERS[name]
        pts = next(iter(drawn.get_polygons_points(layers=[layer]).values()))[0]
        xs = sorted({float(p[0]) for p in pts})
        _rect(xs[0], xs[-1], y, layer, sim)
    for name in (st.BODY, "body_contact"):
        _rect(a0, a1, y, st.MARKERS[name], sim)
    for name in (st.OXIDE, st.POLY, "gate_contact"):
        _rect(gx0, gx1, y, st.MARKERS[name], sim)
    xs = st._section(
        proc,
        component=sim,
        line=base.line,
        gate_u=(gx0 - a0, gx1 - a0),
        l_um=base.l_um + 2 * bias_um,
        w_um=base.w_um,
        with_sd=True,
        background=True,
        sd_peak_cm3=None,
    )
    if plugs:
        levels = dict(xs.levels)
        for region in ("source_contact", "drain_contact"):
            layer, _z, _t, material = levels[region]
            levels[region] = (layer, 0.0, PLUG_UM, material)
        xs = dataclasses.replace(xs, levels=levels)
    if ldd is not None:
        xs = dataclasses.replace(xs, doping=_ldd_doping(proc, xs, **ldd))
    return xs


def parse(variant: str) -> tuple[float, bool, dict | None]:
    bias_nm, plugs = 0.0, False
    ldd: dict | None = None
    depth_nm, spacer_nm = 100.0, 0.0
    for part in variant.split("+"):
        if part == "base":
            continue
        if part == "plugs":
            plugs = True
        elif part.startswith("bias"):
            bias_nm = float(part[len("bias") :])
        elif part.startswith("ldddepth"):
            depth_nm = float(part[len("ldddepth") :])
        elif part.startswith("ldd"):
            ldd = {"peak": float(part[len("ldd") :])}
        elif part.startswith("sp"):
            spacer_nm = float(part[len("sp") :])
        else:
            raise SystemExit(f"unknown variant part {part!r}")
    if ldd is not None:
        ldd.update(depth_um=depth_nm * 1e-3, spacer_um=spacer_nm * 1e-3)
    return bias_nm * 1e-3, plugs, ldd


def main(argv: list[str]) -> int:
    device, gid, variant, out = argv
    bias_um, plugs, ldd = parse(variant)
    proc, _ = load_params(device, "calibrated")
    geometry = geometry_of(device, gid)
    pol = 1.0 if proc.polarity == "n" else -1.0
    vg = (-5.0 * pol, 5.0 * pol)  # from accumulation, as the jobs sweep
    xs = cross_section(proc, geometry, bias_um=bias_um, plugs=plugs, ldd=ldd)
    t0 = time.monotonic()
    cv = moscap2d.simulate(
        proc,
        None,
        vg=vg,
        with_sd=True,
        method="qs",
        mesh=meshconv.selected_spec(device, 2),
        structure=xs,
        mesh_file=Path(out).with_suffix(".msh"),
        log=lambda line: print(line, flush=True),
    )
    d = moscap2d.to_dict(cv)
    d.update(
        variant=variant,
        bias_um=bias_um,
        plugs=plugs,
        ldd=ldd,
        plug_um=PLUG_UM if plugs else None,
        gid=gid,
        elapsed_s=time.monotonic() - t0,
    )
    Path(out).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{device} {gid} {variant}: done in {d['elapsed_s']:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
