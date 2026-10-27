# SPDX-License-Identifier: Apache-2.0
"""The named numbers of the explainer pages, each read from a committed file or computed.

A page writes ``{{ x_<name> }}`` and the docs build prints the value: ``docs/conf.py`` merges
:func:`substitutions` into ``myst_substitutions`` when it is read. Every entry of
:data:`REGISTRY` names its kind (:data:`KINDS`):

- ``committed``: a file under ``data/`` or ``results/``, read by a :class:`gf180tcad.quantity.Selector`;
- ``textbook``: a value of ``data/render/display.toml`` (or ``data/explain/textbook.toml``, in
  the same layout), whose ``sources`` table cites an anchor of ``docs/limitations/literature.md``
  (:func:`citation`);
- ``idealised``: a formula of :mod:`gf180tcad.explain.idealised` (or a shared one of
  :mod:`gf180tcad.derive`) over other entries, its ``inputs``.

The page sentence says which kind a value is; ``x_<name>_label`` gives the words
(:data:`LABELS`). A value is shown to ``digits`` significant digits in ``unit``, after
multiplying by ``factor`` (1000 shows a value in V as mV).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from gf180tcad import derive, quantity
from gf180tcad.explain import idealised

ROOT = Path(__file__).resolve().parents[3]
KINDS = ("committed", "idealised", "textbook")
LABELS = {
    "committed": "this repo's committed value",
    "idealised": "idealised example",
    "textbook": "textbook value",
}
DISPLAY = "data/render/display.toml"
TEXTBOOK = "data/explain/textbook.toml"


@dataclass(frozen=True)
class Number:
    """One registry entry (see the module docstring)."""

    name: str
    kind: str
    unit: str
    digits: int
    source: str | None = None
    key: dict | None = None
    formula: str | None = None
    inputs: tuple[str, ...] = ()
    factor: float = 1.0


def _meta(device: str, params: str = "calibrated") -> str:
    return f"results/tcad/moscap1d/{device}/{params}/per_area.meta.json"


def _proc(device: str) -> str:
    return f"data/process/{device}.toml"


_CM3 = "cm⁻³"
_ENTRIES = (
    Number("n_i_tcad", "committed", _CM3, 3, _meta("nfet_05v0"), {"json": ["constants", "n_i_cm3"]}),
    Number("t_tcad", "committed", "K", 5, _meta("nfet_05v0"), {"json": ["constants", "t_k"]}),
    Number("vt_tcad", "committed", "V", 3, _meta("nfet_05v0"), {"json": ["constants", "vt_v"]}),
    Number("ndep_nfet", "committed", _CM3, 2, _proc("nfet_05v0"), {"toml": ["param", "ndep_cm3", "value"]}),
    Number("n_ch_nfet_cal", "committed", _CM3, 3, _meta("nfet_05v0"), {"json": ["stack", "n_ch_cm3"]}),
    Number("n_ch_pfet_cal", "committed", _CM3, 3, _meta("pfet_05v0"), {"json": ["stack", "n_ch_cm3"]}),
    Number("ngate_nfet", "committed", _CM3, 1, _proc("nfet_05v0"), {"toml": ["param", "ngate_cm3", "value"]}),
    Number("sd_peak_nfet", "committed", _CM3, 1, _proc("nfet_05v0"), {"toml": ["param", "sd_peak_cm3", "value"]}),
    Number("nc_si", "textbook", _CM3, 2, DISPLAY, {"toml": ["silicon", "nc_cm3"]}),
    Number(
        "n_minority_nfet", "idealised", _CM3, 3,
        formula="mass_action", inputs=("n_i_tcad", "n_ch_nfet_cal"),
    ),
    Number(
        "degenerate_offset_gate", "idealised", "mV", 2,
        formula="degenerate_offset", inputs=("ngate_nfet", "nc_si", "vt_tcad"), factor=1e3,
    ),
)  # fmt: skip
REGISTRY: dict[str, Number] = {n.name: n for n in _ENTRIES}


def _formula(name: str):
    if name in idealised.FORMULAS:
        return idealised.FORMULAS[name]
    return derive.FORMULAS[name]


@cache
def value(name: str) -> float:
    """The value of entry ``name`` (before :attr:`Number.factor`)."""
    n = REGISTRY[name]
    if n.kind == "idealised":
        f = _formula(n.formula)
        return float(f.fn(*(value(i) for i in n.inputs)))
    sel = quantity.Selector.from_dict(n.key)
    return float(quantity.read(sel, ROOT / n.source))


def citation(name: str) -> str:
    """The literature source of a ``textbook`` entry: its file's ``sources`` entry."""
    n = REGISTRY[name]
    if n.kind != "textbook":
        raise ValueError(f"{name} is a {n.kind} number, not a textbook value")
    *table, key = n.key["toml"]
    sel = quantity.Selector.from_dict({"toml": [*table, "sources", key]})
    return quantity.read(sel, ROOT / n.source)


_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def format_value(v: float, digits: int, unit: str) -> str:
    """``v`` to ``digits`` significant digits with its unit: plain from 0.001 to 9999, else as
    a mantissa times a power of ten; a typographic minus sign."""
    if not math.isfinite(v):
        raise ValueError(f"{v!r} is not a finite number")
    sign = "−" if v < 0 else ""
    mant, exp = f"{abs(v):.{digits - 1}e}".split("e")
    e = int(exp)
    if -3 <= e < 4:
        body = f"{abs(v):.{max(digits - 1 - e, 0)}f}"
    else:
        body = f"{mant} × 10{str(e).translate(_SUP)}"
    return f"{sign}{body} {unit}"


def text(name: str) -> str:
    """The value of entry ``name`` as a page prints it."""
    n = REGISTRY[name]
    return format_value(value(name) * n.factor, n.digits, n.unit)


def substitutions() -> dict[str, str]:
    """``{"x_<name>": text, "x_<name>_label": label}`` for every entry, for MyST."""
    out: dict[str, str] = {}
    for name, n in REGISTRY.items():
        out[f"x_{name}"] = text(name)
        out[f"x_{name}_label"] = LABELS[n.kind]
    return out
