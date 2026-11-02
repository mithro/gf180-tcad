# SPDX-License-Identifier: Apache-2.0
"""The figure of the image page's Charon section (gf180tcad.imagefig)."""

import re
from pathlib import Path

from gf180tcad import imagefig

REPO = Path(__file__).resolve().parents[1]


def test_charon_stages_is_deterministic_and_transparent(tmp_path):
    svg = imagefig.charon_stages()
    assert svg == imagefig.charon_stages()
    text = svg.decode("utf-8")
    assert "<dc:date>" not in text  # no build date in the file
    imagefig.write_all(tmp_path)
    assert (tmp_path / "charon-stages.svg").read_bytes() == svg


def test_charon_stages_match_the_dockerfile():
    """The drawn stages are the Dockerfile's, in its order, and every box's text is drawn."""
    dockerfile = (REPO / "docker" / "charon-libs" / "Dockerfile").read_text(encoding="utf-8")
    assert tuple(re.findall(r"^FROM \S+ AS (\w+)$", dockerfile, re.MULTILINE)) == imagefig.STAGES
    text = imagefig.charon_stages().decode("utf-8")
    for lines in imagefig.BOXES.values():
        for line in lines:
            assert line.replace("&", "&amp;") in text, line


def test_image_page_names_the_figure():
    page = (REPO / "docs" / "reproduce" / "image.md").read_text(encoding="utf-8")
    assert "```{figure} /_generated/reproduce/charon-stages.svg\n:name: charon-stages\n" in page
    assert "{numref}`charon-stages`" in page
