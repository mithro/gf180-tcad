# SPDX-License-Identifier: Apache-2.0
"""The public sources of the display values (data/render/display-sources.toml, issue #88): every
source is a literature entry, the display file takes one row of each quantity, each listed
density of states is the formula at the mass its source gives, and the page tabulates every
row."""

import re
import tomllib

import pytest

from gf180tcad import display_sources as ds
from gf180tcad.sandbox import REPO_ROOT

LITERATURE = REPO_ROOT / "docs" / "limitations" / "literature.md"
PAGE = REPO_ROOT / "docs" / "reproduce" / "display-values.md"


def _display() -> dict:
    with ds.DISPLAY.open("rb") as f:
        return tomllib.load(f)


def _display_value(d: dict, quantity: str):
    section, key = quantity.split(".")
    return d[section][key], d[section]["sources"][key]


def test_every_source_is_a_literature_entry_with_a_name():
    anchors = set(
        re.findall(r"^\((lit-[a-z0-9-]+)\)=$", LITERATURE.read_text("utf-8"), re.MULTILINE)
    )
    d = ds.load()
    sources = {r["source"] for r in d["row"]} | {d["ioffe_gap"]["source"]}
    assert sources <= anchors, sources - anchors
    assert set(d["names"]) == sources
    assert d["note"] == "display only: not an input to any simulation"


def test_the_quantities_are_the_display_files():
    d, display = ds.load(), _display()
    keys = {f"{s}.{k}" for s in ("silicon", "sio2") for k in display[s]["sources"]}
    assert set(d["quantities"]) == keys
    assert {r["quantity"] for r in d["row"]} == keys
    assert all(r["basis"] in ("listed", "computed") for r in d["row"])


def test_the_display_file_takes_the_used_row_of_each_quantity():
    """One used row per quantity; the display file holds its value and cites its source."""
    d, display = ds.load(), _display()
    used = ds.used()
    assert set(used) == set(d["quantities"])
    for q, r in used.items():
        value, source = _display_value(display, q)
        assert value == r["value"], q
        assert f"({r['source']})" in source, (q, source)
        if "mass_m0" in r:
            assert f"m = {r['mass_m0']:g} m_0" in source, (q, source)


def test_used_refuses_two_used_rows(tmp_path):
    text = ds.SOURCES.read_text("utf-8").replace("used = false", "used = true", 1)
    path = tmp_path / "s.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="silicon.band_gap_ev: more than one row is used"):
        ds.used(path)


def test_density_of_states_hand_value():
    """At 300 K and the free-electron mass, 2 (2π m_0 k_B T / h²)^{3/2} = 2.5094e19 cm⁻³; the
    value scales as m^{3/2}."""
    assert ds.density_of_states_cm3(1.0, 300.0) == pytest.approx(2.5094e19, rel=1e-4)
    assert ds.density_of_states_cm3(1.21, 300.0) == pytest.approx(1.331 * 2.5094e19, rel=1e-4)


def test_each_density_of_states_is_the_formula_at_its_mass():
    """Every N_c and N_v, listed or computed, is the formula at the source's mass and the file's
    temperature, to the figures the value carries."""
    d = ds.load()
    t = d["dos"]["temperature_k"]
    rows = [r for r in d["row"] if "mass_m0" in r]
    assert {r["quantity"] for r in rows} == {"silicon.nc_cm3", "silicon.nv_cm3"}
    for r in rows:
        n = ds.density_of_states_cm3(r["mass_m0"], t)
        assert ds.round_to(n, r["digits"]) == r["value"], (r, n)


def test_ioffe_band_gap_formula():
    """Ioffe's E_g(T) at 300 K: 1.17 − 4.73e-4 · 300² / 936 = 1.124519 eV, which Ioffe lists to
    two decimals as 1.12 eV."""
    g = ds.load()["ioffe_gap"]
    eg = ds.ioffe_band_gap_ev(300.0, g["e0_ev"], g["alpha_ev_per_k"], g["beta_k"])
    assert eg == pytest.approx(1.124519, abs=1e-6)
    (ioffe,) = [r for r in ds.rows() if r["quantity"] == "silicon.band_gap_ev"
                and r["source"] == g["source"]]  # fmt: skip
    assert ds.round_to(eg, 3) == ioffe["value"]


def test_number_format():
    assert ds.number(1.124) == "1.124"
    assert ds.number(3.2e19, 2) == "3.2×10¹⁹"
    assert ds.number(3.09e19, 3) == "3.09×10¹⁹"


def test_table_has_every_row_and_the_page_includes_it():
    """One table per quantity under its name; one row per source with one value per cell."""
    d = ds.load()
    lines = ds.table_markdown().splitlines()
    quantities = list(dict.fromkeys(r["quantity"] for r in d["row"]))
    titles = [i for i, line in enumerate(lines) if line.startswith("**")]
    assert len(titles) == len(quantities)
    plain = [re.sub(r"\{term\}`([^`]+)`", r"\1", lines[i].split("**")[1]) for i in titles]
    assert [s.lower() for s in plain] == [d["quantities"][q].lower() for q in quantities]
    for i, q in zip(titles, quantities, strict=True):
        figure = f"{{numref}}`Figure %s of {ds.PAGE_TITLE} <{ds.FIGURE_OF[q]}>`"
        assert lines[i].endswith(f"** ({figure})")
        rows = [r for r in d["row"] if r["quantity"] == q]
        extra = {"silicon.band_gap_ev": ["T (K)"], "silicon.nc_cm3": ["m* (m₀)"],
                 "silicon.nv_cm3": ["m* (m₀)"]}.get(q, [])  # fmt: skip
        head = ["Source", f"Value ({d['units'][q]})", *extra, "Basis"]
        assert lines[i + 2] == "| " + " | ".join(head) + " |"
        body = lines[i + 4 : i + 4 + len(rows)]
        for line, r in zip(body, rows, strict=True):
            cells = dict(zip(head, (c.strip() for c in line.strip("|").split("|")), strict=True))
            assert cells["Source"] == f"{{ref}}`{d['names'][r['source']]} <{r['source']}>`"
            assert cells[head[1]] == ds.number(r["value"], r.get("digits"))
            if "T (K)" in cells:
                assert (
                    cells["T (K)"] == f"{r.get('temperature_k', 'none'):g}"
                    if "temperature_k" in r
                    else cells["T (K)"] == "none"
                )
            if "m* (m₀)" in cells:
                assert cells["m* (m₀)"] == f"{r['mass_m0']:g}"
            assert cells["Basis"] == r["basis"] + (", used" if r["used"] else "")
    assert "not stated" not in "\n".join(lines)
    text = "\n".join(lines)
    for term in ds.TERMS:  # linked once, at the first use
        link = f"{{term}}`{term}`"
        assert text.count(link) == 1
        assert text.replace(link, term, 1).index(term) == text.index(link)
    page = PAGE.read_text("utf-8")
    assert f"\n# {ds.PAGE_TITLE}\n" in page
    assert "```{include} /_generated/reproduce/display-sources.inc.md\n```" in page


def test_page_prose_states_the_files_numbers():
    """Every mass and every eV number of the sources file is on the page as the file gives it,
    and the page's sums and formula values are the file's."""
    d = ds.load()
    page = " ".join(PAGE.read_text("utf-8").split())
    for r in d["row"]:
        if "mass_m0" in r:
            assert f"{r['mass_m0']:g} m₀" in page, r
        elif r["quantity"].endswith("_ev"):
            assert f"{r['value']:g} eV" in page, r
    g = d["ioffe_gap"]
    assert f"$E_0$ is the band gap at 0 K, {g['e0_ev']:g}, in eV" in page
    assert f"$\\beta$ is a temperature of the fit, {g['beta_k']:g}, in K" in page
    for t, shown in ((300.0, "1.1245 eV"), (302.0, "1.1240 eV")):
        eg = ds.ioffe_band_gap_ev(t, g["e0_ev"], g["alpha_ev_per_k"], g["beta_k"])
        assert f"{eg:.4f} eV" == shown and shown in page
    rows = {(r["source"], r["quantity"]): r["value"] for r in d["row"]}
    for src, total in (("lit-alkauskas", "8.9"), ("lit-shaltaf", "8.6")):
        parts = [rows[(src, q)] for q in ("silicon.band_gap_ev", "sio2.valence_offset_ev",
                                          "sio2.conduction_offset_ev")]  # fmt: skip
        assert f"{sum(parts):.1f}" == total
        assert " + ".join(f"{v:g}" for v in parts) + f" = {total} eV" in page
    used = ds.used()
    drawn = [used[q]["value"] for q in ("silicon.band_gap_ev", "sio2.conduction_offset_ev",
                                         "sio2.valence_offset_ev")]  # fmt: skip
    assert " + ".join(f"{v:g}" for v in drawn) + f" = {sum(drawn):.2f} eV" in page
