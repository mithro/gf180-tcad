# SPDX-License-Identifier: Apache-2.0
"""The 2D cross-section of a :term:`MOSCAP` from the PDK cell: layer stack, contacts and doping.

:func:`cell` builds the `gf180mcu <https://github.com/gdsfactory/gf180mcu>`_ gdsfactory cell
``nfet(volt="5.0V")`` or ``pfet(volt="5.0V")`` at a geometry; these are the devices the
:term:`SPICE` reference describes. :func:`build` cuts it across the gate, along L, through the
middle of the gate width, and returns a :class:`CrossSection`: a gdsfactory ``LayerStack`` on
marker layers, the contacts, and per silicon region the doping profiles (the analytic profiles
of the plugin's ``gplugins.devsim.doping``).

**The thick oxide.** The 5 V devices have the thick gate oxide, which the PDK marks with
Dualgate (55,0) over the gate. :func:`build` requires Dualgate over the whole gate
(poly2 over COMP) and raises :class:`DualgateMissing` otherwise: without it the cell is a
thin-oxide device, whose oxide the process files do not describe.

**The vertical stack** comes from the process file (:mod:`gf180tcad.tcad.process`), because the
PDK's gdsfactory ``LayerStack`` is illustrative (no gate oxide, no doping):

- the silicon body, ``BODY_UM`` deep, under the active area (the COMP region holding the gate),
  uniformly doped at ``n_ch_cm3`` (p-type for the nfet, n-type, the n-well, for the pfet);
- the gate oxide, ``t_ox_eff_nm`` thick (permittivity :term:`EPSROX`), under the gate;
- the poly gate, ``POLY_UM`` thick, uniformly doped at :term:`NGATE`;
- with ``with_sd``: n+ (nfet) or p+ (pfet) source and drain in the active area outside the gate,
  a Gaussian of peak ``sd_peak_cm3`` at the surface that falls to the body doping at the
  junction depth :term:`XJ`, with a Gaussian lateral straggle under the poly edge (the
  self-aligned implant; spacers and LDD are not modelled). The lateral straggle is the
  vertical one times :data:`LATERAL_STRAGGLE_RATIO`, a project choice;
- with ``background``: an oxide (the spacer and inter-layer dielectric, :data:`BACKGROUND`) that
  fills the rest of the domain above the silicon up to the top of the gate electrode, so the
  gate's fringe field reaches the silicon outside the gate.

**Contacts** are equation-free electrode regions on marker layers (:data:`MARKERS`); each contact
is the boundary between its electrode and the one region it is placed on (the plugin's
``InterfaceRef(electrode, region)``), so it is exactly where it is drawn and every other outer
boundary is a zero-flux (Neumann) boundary: ``gate`` on top of the poly, ``body`` under the whole body, and with ``with_sd``
``source`` and ``drain`` on the silicon at the source/drain contact (CO) openings of the cell.

The domain is the active area along the cut: its sides are zero-flux boundaries (the shallow
trench isolation is not modelled). The thicknesses ``POLY_UM`` and ``BODY_UM`` are the 1D ones
(:mod:`gf180tcad.tcad.moscap1d`), project choices well beyond every depletion width.

:func:`uniform` builds the test structure of the 2D-equals-1D check: no source/drain, and a
gate that spans the whole domain, so the 2D device is the 1D one extruded.

This module imports gdsfactory and gf180mcu lazily (they are in the TCAD image), so it imports
on the host. It is TCAD code, not one of the SPICE generator modules
(:data:`gf180tcad.reference.GENERATOR_MODULES`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from gf180tcad.devices import Geometry
from gf180tcad.tcad.moscap1d import BODY_UM, POLY_UM
from gf180tcad.tcad.process import ProcessDescription

# PDK layers (gf180mcu layer map, gf180mcu/layers.py).
COMP = (22, 0)
POLY2 = (30, 0)
CONTACT = (33, 0)
DUALGATE = (55, 0)

# Marker layers of the simulated cross-section (not PDK layers): the regions and electrodes.
MARKERS = {
    "body": (1001, 0),
    "oxide": (1002, 0),
    "gate_poly": (1003, 0),
    "gate_contact": (1004, 0),
    "body_contact": (1005, 0),
    "source_contact": (1006, 0),
    "drain_contact": (1007, 0),
}

# Region names; the electrode regions are "<contact>_contact".
BODY, OXIDE, POLY = "body", "oxide", "gate_poly"
GATE, BODY_CONTACT, SOURCE, DRAIN = "gate", "body", "source", "drain"
BACKGROUND = "ild"

# Electrode thickness (um): any value works (the electrodes carry no equations); project choice.
ELECTRODE_UM = 0.05

# The lateral straggle of the source/drain profile as a multiple of its vertical straggle: a
# project choice (an implant's lateral straggle is comparable to its vertical one; no public
# value for this process). Not load-bearing for the plateaus, which the gate area sets.
LATERAL_STRAGGLE_RATIO = 1.0

# meshwell's vertex grid (um) for the cross-section. meshwell's default (1e-3 um) snaps every
# vertex to 1 nm, which meshes a 15.2 nm oxide 15 nm thick (1.3 % too large a Cox; Task 11's
# C/Cox > 1 artefact); 1e-6 um keeps any thickness to 3e-5 relative at 15 nm.
POINT_TOLERANCE_UM = 1e-6

# Half-height (um) of the marker rectangles across the cut line (any value > 0).
_BAND_UM = 0.5


class DualgateMissing(ValueError):
    """The gate is not covered by Dualgate (55,0), so it is no thick-oxide (5 V) device."""


@dataclass(frozen=True)
class CrossSection:
    """A 2D MOS capacitor cross-section, ready for ``create_2Duz_simulation``.

    ``component`` holds the marker rectangles; ``line`` is the cut (``xsection_bounds``) and
    u, the position along it, runs from 0 to ``length_um``. ``gate_u`` is the gate's (u0, u1)
    and ``l_um``/``w_um`` the drawn gate length and width. ``levels`` maps each region to
    ``(marker layer, zmin, thickness, material)`` (um). ``doping`` maps each silicon region to
    its ``(donors, acceptors)`` profiles in the plugin's frame: x is u, y the depth below the
    surface of the region (the silicon top, or the poly bottom). ``contacts`` maps each contact
    to its electrode region.
    """

    device: str
    polarity: Literal["n", "p"]
    component: object = field(repr=False, compare=False)
    line: tuple[tuple[float, float], tuple[float, float]]
    length_um: float
    gate_u: tuple[float, float]
    l_um: float
    w_um: float
    t_ox_nm: float
    eps_ox: float
    levels: Mapping[str, tuple[tuple[int, int], float, float, str]]
    doping: Mapping[str, tuple[tuple, tuple]] = field(repr=False, compare=False)
    contacts: Mapping[str, str]
    background: str | None
    with_sd: bool
    sd_peak_cm3: float | None
    sd_straggle_um: float | None

    def contact_region(self, contact: str) -> str:
        """The region a contact is placed on: the poly for the gate, else the body."""
        if contact not in self.contacts:
            raise KeyError(f"no contact {contact!r}: {sorted(self.contacts)}")
        return POLY if contact == GATE else BODY

    @property
    def silicon(self) -> tuple[str, ...]:
        return (BODY, POLY)

    @property
    def region_classes(self) -> dict[str, str | None]:
        """The plugin's region class of every region (electrodes carry no equations)."""
        out = {BODY: "silicon", POLY: "silicon", OXIDE: "oxide"}
        out.update({e: None for e in self.contacts.values()})
        if self.background:
            out[self.background] = "oxide"
        return out

    def layer_stack(self):
        """The gdsfactory ``LayerStack`` of :attr:`levels`."""
        from gdsfactory.technology import LayerLevel, LayerStack, LogicalLayer

        return LayerStack(
            layers={
                name: LayerLevel(
                    layer=LogicalLayer(layer=layer),
                    thickness=t,
                    zmin=z,
                    material=m,
                    mesh_order=1,
                )
                for name, (layer, z, t, m) in self.levels.items()
            }
        )


def cell(device: str, geometry: Geometry):
    """The gf180mcu cell ``nfet``/``pfet(volt="5.0V", w_gate, l_gate)`` of ``device``."""
    from gf180mcu.cells import nfet, pfet

    make = {"nfet_05v0": nfet, "pfet_05v0": pfet}[device]
    return make(volt="5.0V", w_gate=geometry.w_um, l_gate=geometry.l_um)


def _shapes(component, layer):
    """The union of ``component``'s polygons on ``layer`` (flattened), as shapely geometry."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    polys = [
        Polygon(p) for pts in component.get_polygons_points(layers=[layer]).values() for p in pts
    ]
    return unary_union(polys)


def _intervals(geom, y: float) -> list[tuple[float, float]]:
    """The x intervals where ``geom`` meets the horizontal line at ``y``, sorted."""
    from shapely.geometry import LineString

    xmin, _, xmax, _ = geom.bounds
    cut = geom.intersection(LineString([(xmin - 1, y), (xmax + 1, y)]))
    parts = getattr(cut, "geoms", [cut])
    out = [(p.bounds[0], p.bounds[2]) for p in parts if not p.is_empty and p.length > 0]
    return sorted(out)


def sd_straggle_um(proc: ProcessDescription, sd_peak_cm3: float) -> float:
    """The vertical straggle (um) of the S/D Gaussian: peak at the surface, body doping at XJ.

    peak * exp(-XJ^2 / (2 s^2)) = n_ch, so s = XJ / sqrt(2 ln(peak / n_ch)).
    """
    v = proc.values()
    return v["xj_um"] / math.sqrt(2 * math.log(sd_peak_cm3 / v["n_ch_cm3"]))


def _doping(proc, *, length_um, gate_u, with_sd, sd_peak_cm3):
    from gplugins.devsim import doping

    v = proc.values()
    body_kind = "acceptor" if proc.polarity == "n" else "donor"
    gate_kind = "donor" if proc.polarity == "n" else "acceptor"
    body = {"donor": [], "acceptor": []}
    body[body_kind].append(doping.constant(v["n_ch_cm3"]))
    straggle = None
    if with_sd:
        straggle = sd_straggle_um(proc, sd_peak_cm3)
        vertical = doping.gaussian(sd_peak_cm3, 0.0, straggle)
        lat = LATERAL_STRAGGLE_RATIO * straggle
        # self-aligned implant: masked by the poly; open to the domain's side walls
        body[gate_kind] += [
            vertical * doping.lateral(lat, None, gate_u[0]),
            vertical * doping.lateral(lat, gate_u[1], None),
        ]
    poly = {"donor": [], "acceptor": []}
    poly[gate_kind].append(doping.constant(v["ngate_cm3"]))
    out = {
        BODY: (tuple(body["donor"]), tuple(body["acceptor"])),
        POLY: (tuple(poly["donor"]), tuple(poly["acceptor"])),
    }
    return out, straggle


def _levels(t_ox_um: float, contacts: Mapping[str, str]):
    levels = {
        BODY: (MARKERS[BODY], -BODY_UM, BODY_UM, "si"),
        OXIDE: (MARKERS[OXIDE], 0.0, t_ox_um, "sio2"),
        POLY: (MARKERS[POLY], t_ox_um, POLY_UM, "si"),
    }
    zs = {
        "gate_contact": t_ox_um + POLY_UM,
        "body_contact": -BODY_UM - ELECTRODE_UM,
        "source_contact": 0.0,
        "drain_contact": 0.0,
    }
    for region in contacts.values():
        levels[region] = (MARKERS[region], zs[region], ELECTRODE_UM, "metal")
    return levels


def _section(
    proc, *, component, line, gate_u, l_um, w_um, with_sd, background, sd_peak_cm3
) -> CrossSection:
    v = proc.values()
    length = line[1][0] - line[0][0]
    contacts = {GATE: "gate_contact", BODY_CONTACT: "body_contact"}
    if with_sd:
        contacts.update({SOURCE: "source_contact", DRAIN: "drain_contact"})
    if with_sd and sd_peak_cm3 is None:
        sd_peak_cm3 = v["sd_peak_cm3"]
    doping_, straggle = _doping(
        proc, length_um=length, gate_u=gate_u, with_sd=with_sd, sd_peak_cm3=sd_peak_cm3
    )
    return CrossSection(
        device=proc.device,
        polarity=proc.polarity,
        component=component,
        line=line,
        length_um=length,
        gate_u=gate_u,
        l_um=l_um,
        w_um=w_um,
        t_ox_nm=v["t_ox_eff_nm"],
        eps_ox=v["epsrox"],
        levels=_levels(v["t_ox_eff_nm"] * 1e-3, contacts),
        doping=doping_,
        contacts=contacts,
        background=BACKGROUND if background else None,
        with_sd=with_sd,
        sd_peak_cm3=sd_peak_cm3 if with_sd else None,
        sd_straggle_um=straggle,
    )


def build(
    proc: ProcessDescription,
    component,
    *,
    with_sd: bool,
    background: bool = True,
    sd_peak_cm3: float | None = None,
) -> CrossSection:
    """The cross-section of the PDK cell ``component`` across its gate (along L).

    The cut is horizontal, through the middle of the gate width, from one end of the active
    area (the COMP region holding the gate) to the other. ``sd_peak_cm3`` overrides the
    process file's source/drain peak (for the sensitivity check). Raises
    :class:`DualgateMissing` unless Dualgate covers the gate, and ValueError if the cell does
    not have one gate over one active area with one source and one drain contact on the cut.
    """
    from gdsfactory import Component

    comp = _shapes(component, COMP)
    poly = _shapes(component, POLY2)
    gates = poly.intersection(comp)
    parts = [g for g in getattr(gates, "geoms", [gates]) if g.area > 0]
    if len(parts) != 1:
        raise ValueError(f"{proc.device}: expected one gate (poly2 over COMP), found {len(parts)}")
    gate = parts[0]
    dualgate = _shapes(component, DUALGATE)
    if dualgate.is_empty or not dualgate.covers(gate):
        raise DualgateMissing(
            f"{proc.device}: the gate is not covered by Dualgate {DUALGATE}, which marks the "
            "thick (5 V) gate oxide; the process files describe only that oxide"
        )
    gx0, gy0, gx1, gy1 = gate.bounds
    y = 0.5 * (gy0 + gy1)
    (active,) = [iv for iv in _intervals(comp, y) if iv[0] <= gx0 and gx1 <= iv[1]]
    contacts = [iv for iv in _intervals(_shapes(component, CONTACT), y)
                if active[0] <= iv[0] and iv[1] <= active[1]]  # fmt: skip
    src = [iv for iv in contacts if iv[1] <= gx0]
    drn = [iv for iv in contacts if iv[0] >= gx1]
    if len(src) != 1 or len(drn) != 1 or len(contacts) != 2:
        raise ValueError(
            f"{proc.device}: expected one source and one drain contact on the cut, found {contacts}"
        )
    a0, a1 = active
    sim = Component()
    rects = {
        BODY: (a0, a1),
        "body_contact": (a0, a1),
        OXIDE: (gx0, gx1),
        POLY: (gx0, gx1),
        "gate_contact": (gx0, gx1),
    }
    if with_sd:
        rects["source_contact"] = src[0]
        rects["drain_contact"] = drn[0]
    for name, (x0, x1) in rects.items():
        sim.add_polygon(
            [(x0, y - _BAND_UM), (x1, y - _BAND_UM), (x1, y + _BAND_UM), (x0, y + _BAND_UM)],
            layer=MARKERS[name],
        )
    return _section(
        proc,
        component=sim,
        line=((a0, y), (a1, y)),
        gate_u=(gx0 - a0, gx1 - a0),
        l_um=gx1 - gx0,
        w_um=gy1 - gy0,
        with_sd=with_sd,
        background=background,
        sd_peak_cm3=sd_peak_cm3,
    )


def uniform(proc: ProcessDescription, l_um: float) -> CrossSection:
    """The 1D stack extruded over ``l_um``: a gate spanning the domain, no S/D, Neumann sides."""
    from gdsfactory import Component

    sim = Component()
    for name in (BODY, "body_contact", OXIDE, POLY, "gate_contact"):
        sim.add_polygon(
            [(0, -_BAND_UM), (l_um, -_BAND_UM), (l_um, _BAND_UM), (0, _BAND_UM)],
            layer=MARKERS[name],
        )
    return _section(
        proc,
        component=sim,
        line=((0.0, 0.0), (l_um, 0.0)),
        gate_u=(0.0, l_um),
        l_um=l_um,
        w_um=1.0,
        with_sd=False,
        background=False,
        sd_peak_cm3=None,
    )
