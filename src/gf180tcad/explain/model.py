# SPDX-License-Identifier: Apache-2.0
"""The one source model of the device that every explainer diagram draws.

:func:`device` builds the model from committed files only: the 1D stack and constants of
``results/tcad/moscap1d/<device>/<params>/per_area.meta.json`` (the gate poly-silicon, the
oxide and the body, with their thicknesses and dopings). A figure draws the same model with the
page's part highlighted, so a fix here fixes every page. A diagram not to scale carries its
scale factors in :attr:`Device.scales`, and :func:`exaggeration` writes the statement from
them; the factors are the same for every device (passed in by
:data:`gf180tcad.explain.figures.STYLE`).

It reads no simulator module and imports nothing outside the docs dependency group (tested).
The 2D cell joins in a later task of the explainer plan (E1).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from gf180tcad import quantity
from gf180tcad.explain.numbers import ROOT

UNITS = {"nm_per_um": 1e3}

# Which dopant the gate and the body hold, by the stack's polarity (gf180tcad.tcad.moscap1d.Stack:
# "n" is a p-type body under an n-type gate).
_DOPANTS = {"n": ("donor", "acceptor"), "p": ("acceptor", "donor")}
# The words of an exaggeration statement, per drawn part.
_SCALED = {"gate": "gate thickness", "oxide": "oxide thickness", "body": "body depth"}


@dataclass(frozen=True)
class Layer:
    """One layer of the 1D stack, from the gate down: ``part`` names it on every page."""

    part: str
    material: str
    thickness_um: float
    dopant: str | None
    doping_cm3: float | None


@dataclass(frozen=True)
class Device:
    """The model of one device: its layers from the gate down, the committed intrinsic density
    and the drawing's scale factors (part to factor; a missing part or 1 is to scale)."""

    name: str
    params: str
    polarity: str
    layers: tuple[Layer, ...]
    n_i_cm3: float
    t_k: float
    scales: Mapping[str, float] = field(default_factory=dict)

    def layer(self, part: str) -> Layer:
        """The layer named ``part``; KeyError if the model has none."""
        for layer in self.layers:
            if layer.part == part:
                return layer
        raise KeyError(f"{self.name} has no part {part!r}")


def meta_path(device: str, params: str) -> str:
    """The committed 1D metadata file of ``device`` at ``params`` (start or calibrated)."""
    return f"results/tcad/moscap1d/{device}/{params}/per_area.meta.json"


def device(
    device: str, params: str = "calibrated", geometry: str | None = None, *, scales: Mapping
) -> Device:
    """The model of ``device`` at ``params`` from its committed 1D metadata. ``geometry`` is
    for the 2D cell (task E1) and must be None here."""
    if geometry is not None:
        raise NotImplementedError("the 2D cell joins the model in explainer task E1")
    path = ROOT / meta_path(device, params)
    stack = quantity.read(quantity.Selector("json", ["stack"]), path)
    consts = quantity.read(quantity.Selector("json", ["constants"]), path)
    gate_dopant, body_dopant = _DOPANTS[stack["polarity"]]
    layers = (
        Layer("gate", "poly-silicon", stack["poly_um"], gate_dopant, stack["ngate_cm3"]),
        Layer("oxide", "silicon dioxide", stack["t_ox_nm"] / UNITS["nm_per_um"], None, None),
        Layer("body", "silicon", stack["body_um"], body_dopant, stack["n_ch_cm3"]),
    )
    return Device(
        device,
        params,
        stack["polarity"],
        layers,
        consts["n_i_cm3"],
        consts["t_k"],
        dict(scales),
    )


def exaggeration(scales: Mapping[str, float]) -> str:
    """The statement a figure and its caption carry: which parts are stretched, and by what."""
    parts = [f"{_SCALED[p]} ×{f:g}" for p, f in sorted(scales.items()) if f != 1]
    if not parts:
        return "Drawn to scale."
    first = parts[0][0].upper() + parts[0][1:]
    return " and ".join([first, *parts[1:]]) + ", not to scale."
