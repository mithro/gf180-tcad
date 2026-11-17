# SPDX-License-Identifier: Apache-2.0
"""The public sources of the render display values (``data/render/display-sources.toml``).

``data/render/display.toml`` holds one value per display quantity. The sources file lists every
value the read public sources give for each, and marks the one the display file takes. This
module reads it, gives the two formulas that relate the sources' numbers (the band-edge density
of states and Ioffe's temperature dependence of silicon's band gap), and writes the table of
``docs/reproduce/display-values.md``. No simulation imports it.
"""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

from scipy.constants import h, k, m_e

from gf180tcad.sandbox import REPO_ROOT

#: The sources file.
SOURCES = REPO_ROOT / "data" / "render" / "display-sources.toml"
#: The display file, which takes one row of each quantity.
DISPLAY = REPO_ROOT / "data" / "render" / "display.toml"
#: Cubic centimetres in one cubic metre.
CM3_PER_M3 = 1e6
#: The glossary terms of the table's quantity names: the table links each at its first use.
TERMS = ("band gap", "conduction band", "valence band")
#: The digits Unicode writes as superscripts, for the powers of ten in the table.
_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def load(path: Path = SOURCES) -> dict:
    """The sources file as a dict."""
    with Path(path).open("rb") as f:
        return tomllib.load(f)


def rows(path: Path = SOURCES) -> list[dict]:
    """Every row of the sources file, in file order."""
    return load(path)["row"]


def used(path: Path = SOURCES) -> dict[str, dict]:
    """The row the display file takes, by quantity (``section.key`` of the display file)."""
    out = {}
    for r in rows(path):
        if r["used"]:
            if r["quantity"] in out:
                raise ValueError(f"{r['quantity']}: more than one row is used")
            out[r["quantity"]] = r
    return out


def density_of_states_cm3(mass_m0: float, temperature_k: float) -> float:
    """The effective density of states at a band edge, N = 2 (2π m k_B T / h²)^{3/2} (cm⁻³), for
    the density-of-states mass ``mass_m0`` (in free-electron masses) at ``temperature_k`` (K).

    Reference: Ioffe archive (lit-ioffe), silicon, "Effective density of states in the conduction
    band", N_c = 4.82·10¹⁵·M·(m_c/m_0)^{3/2}·T^{3/2} cm⁻³, the same formula.
    """
    m = mass_m0 * m_e
    return 2 * (2 * math.pi * m * k * temperature_k / h**2) ** 1.5 / CM3_PER_M3


def ioffe_band_gap_ev(temperature_k, e0_ev: float, alpha_ev_per_k: float, beta_k: float):
    """Silicon's band gap at ``temperature_k`` (K), E_g = E_0 − α T² / (T + β) (eV).

    Reference: Ioffe archive (lit-ioffe), silicon, "Temperature dependence of the energy gap".
    """
    return e0_ev - alpha_ev_per_k * temperature_k**2 / (temperature_k + beta_k)


def round_to(value: float, digits: int) -> float:
    """``value`` rounded to ``digits`` significant figures."""
    return float(f"{value:.{digits - 1}e}")


def number(value: float, digits: int | None = None) -> str:
    """``value`` as the table prints it: plain below 10³, else a × 10ⁿ with ``digits`` figures."""
    if abs(value) < 1e3:
        return f"{value:g}"
    mantissa, exponent = f"{value:.{(digits or 3) - 1}e}".split("e")
    return f"{mantissa}×10{str(int(exponent)).translate(_SUPERSCRIPT)}"


def _basis(r: dict) -> str:
    if r["basis"] == "computed":
        return f"computed from m* = {r['mass_m0']:g} m₀"
    if "mass_m0" in r:
        return f"listed, m* = {r['mass_m0']:g} m₀"
    return "listed"


def _value(r: dict) -> str:
    text = number(r["value"], r.get("digits"))
    if "temperature_k" in r:
        text += f" at {r['temperature_k']:g} K"
    return text


def table_markdown(path: Path = SOURCES) -> str:
    """The table of every row: quantity, source (a link to its literature entry), value, basis
    and whether the display file takes it. Each term of :data:`TERMS` links to the glossary at
    its first use."""
    d = load(path)
    lines = [
        "| Quantity | Source | Value | Basis | Used |",
        "|---|---|---|---|---|",
    ]
    linked: set[str] = set()
    for r in d["row"]:
        quantity = d["quantities"][r["quantity"]]
        for term in TERMS:
            if term in quantity and term not in linked:
                quantity = quantity.replace(term, f"{{term}}`{term}`", 1)
                linked.add(term)
        source = f"{{ref}}`{d['names'][r['source']]} <{r['source']}>`"
        cells = (quantity, source, _value(r), _basis(r), "yes" if r["used"] else "no")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
