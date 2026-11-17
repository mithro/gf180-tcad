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
    band", N_c = 4.82·10¹⁵·M·(m_c/m_0)^{3/2}·T^{3/2} cm⁻³: this formula with its constants
    evaluated (2 (2π m_0 k_B / h²)^{3/2} = 4.83·10¹⁵ cm⁻³ K^{-3/2}).
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


def label(d: dict, quantity: str) -> str:
    """A quantity's name with its unit, as the figures print it."""
    return f"{d['quantities'][quantity]} ({d['units'][quantity]})"


def table_name(quantity: str) -> str:
    """The file name of a quantity's generated table, included by the page section on it."""
    return f"display-sources-{quantity.replace('.', '-').replace('_', '-')}.inc.md"


def table_markdown(quantity: str, path: Path = SOURCES) -> str:
    """The table of one quantity: a row per source with its value, its basis ("listed" or
    "computed") and whether the display file takes it ("yes" or "no"). A quantity whose sources state
    a temperature has a T column ("none" for a source that states none); one whose numbers go
    with a mass has an m* column. The table holds no prose: the page section that includes it
    names the quantity and its figure."""
    d = load(path)
    picked = [r for r in d["row"] if r["quantity"] == quantity]
    if not picked:
        raise ValueError(f"{quantity}: no row")
    has_t = any("temperature_k" in r for r in picked)
    has_m = any("mass_m0" in r for r in picked)
    head = ["Source", f"Value ({d['units'][quantity]})"]
    head += ["T (K)"] * has_t + ["m* (m₀)"] * has_m + ["Basis", "Used"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in picked:
        cells = [f"{{ref}}`{d['names'][r['source']]} <{r['source']}>`",
                 number(r["value"], r.get("digits"))]  # fmt: skip
        if has_t:
            cells.append(f"{r['temperature_k']:g}" if "temperature_k" in r else "none")
        if has_m:
            cells.append(f"{r['mass_m0']:g}")
        cells += [r["basis"], "yes" if r["used"] else "no"]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"
