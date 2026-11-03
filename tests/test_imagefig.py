# SPDX-License-Identifier: Apache-2.0
"""The figures of the image page's Charon section (gf180tcad.imagefig)."""

import re
from pathlib import Path

import pytest

from gf180tcad import imagefig

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "reproduce" / "image.md"


@pytest.mark.parametrize("name", list(imagefig.FIGURES))
def test_figures_are_deterministic_twins(tmp_path, name):
    draw = imagefig.FIGURES[name]
    light, dark = draw("light"), draw("dark")
    assert light == draw("light") and dark == draw("dark")
    assert light != dark
    for svg, pal in ((light, "light"), (dark, "dark")):
        text = svg.decode("utf-8")
        assert "<dc:date>" not in text  # no build date in the file
        # opaque background in the twin's own colour
        assert imagefig.PALETTES[pal]["background"] in text
    imagefig.write_all(tmp_path)
    assert (tmp_path / f"{name}-light.svg").read_bytes() == light
    assert (tmp_path / f"{name}-dark.svg").read_bytes() == dark


def test_contrast_matches_the_wcag_reference_values():
    assert imagefig.contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert imagefig.contrast("#ffffff", "#ffffff") == pytest.approx(1.0)
    # #777777 on white is 4.48:1, just under the 4.5:1 floor
    assert imagefig.contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.005)


@pytest.mark.parametrize("palette", list(imagefig.PALETTES))
def test_every_text_and_arrow_reads_on_what_is_under_it(palette):
    pal = imagefig.PALETTES[palette]
    for text, under in imagefig.text_pairs(palette):
        assert imagefig.contrast(text, under) >= imagefig.MIN_TEXT_CONTRAST, (text, under)
    assert len(imagefig.text_pairs(palette)) == len(pal["fill"]) + 1
    assert imagefig.contrast(pal["arrow"], pal["background"]) >= imagefig.MIN_GRAPHIC_CONTRAST


@pytest.mark.parametrize("palette", list(imagefig.PALETTES))
def test_every_drawn_colour_is_in_the_palette(palette):
    """No fill or text colour is drawn that the contrast test does not cover."""
    pal = imagefig.PALETTES[palette]
    allowed = {pal["background"], pal["text"], pal["arrow"], *pal["fill"].values()}
    allowed |= set(pal.get("edge", {}).values())
    for name, draw in imagefig.FIGURES.items():
        drawn = set(re.findall(r"(?:fill|stroke|color):\s*(#[0-9a-f]{6})", draw(palette).decode()))
        assert drawn and drawn <= {c.lower() for c in allowed}, (name, drawn - allowed)


def test_charon_stages_match_the_dockerfile():
    """The drawn stages are the Dockerfile's, in its order, and every box's text is drawn."""
    dockerfile = (REPO / "docker" / "charon-libs" / "Dockerfile").read_text(encoding="utf-8")
    assert tuple(re.findall(r"^FROM \S+ AS (\w+)$", dockerfile, re.MULTILINE)) == imagefig.STAGES
    text = imagefig.charon_stages().decode("utf-8")
    for lines in imagefig.BOXES.values():
        for line in lines:
            assert line.replace("&", "&amp;") in text, line


@pytest.mark.parametrize("name", list(imagefig.FIGURES))
def test_image_page_embeds_both_twins_and_cites_the_figure(name):
    page = PAGE.read_text(encoding="utf-8")
    light = f"```{{figure}} /_generated/reproduce/{name}-light.svg\n:name: {name}\n:figclass: only-light\n"
    dark = f"```{{figure}} /_generated/reproduce/{name}-dark.svg\n:figclass: only-dark\n"
    assert light in page and dark in page
    assert page.index(light) < page.index(dark)
    assert f"{{numref}}`{name}`" in page
