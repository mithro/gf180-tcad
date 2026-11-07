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


@pytest.mark.parametrize("palette", list(imagefig.PALETTES))
def test_box_edges_read_on_the_container_fill(palette):
    """The container and the dashed boxes have edges in the arrow colour, drawn on that fill."""
    pal = imagefig.PALETTES[palette]
    assert (
        imagefig.contrast(pal["arrow"], pal["fill"]["container"]) >= imagefig.MIN_GRAPHIC_CONTRAST
    )


def _drawn(svg: bytes, lines) -> None:
    text = svg.decode("utf-8")
    for line in lines:
        assert line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") in text, line


def test_charon_mpi_names_the_image_setting_and_draws_every_box():
    dockerfile = (REPO / "docker" / "charon-libs" / "Dockerfile").read_text(encoding="utf-8")
    final = dockerfile[dockerfile.rindex("FROM ${BASE_IMAGE}") :]
    assert imagefig.MPI_ENV in final
    tests = (REPO / "tests" / "test_charon_image.py").read_text(encoding="utf-8")
    key, value = imagefig.MPI_ENV.split("=")
    assert f'OMPI_ENV = {{"{key}": "{value}"}}' in tests
    svg = imagefig.charon_mpi()
    for lines in imagefig.MPI_BOXES.values():
        _drawn(svg, lines)


def test_charon_ci_matches_the_workflow_and_draws_every_box():
    """The checks are the workflow's step names, and the gate's paths those of its git diff."""
    workflow = (REPO / ".github" / "workflows" / "image.yml").read_text(encoding="utf-8")
    steps = re.findall(r"^      - name: (.+)$", workflow, re.MULTILINE)
    names = [name for name, _ in imagefig.CI_CHECKS.values()]
    assert [s for s in steps if s in names] == names  # present, once each, in this order
    gate = re.search(r"git diff --quiet \"\$base\" HEAD -- (.+);", workflow).group(1)
    assert tuple(gate.split()) == imagefig.CI_GATE_PATHS
    svg = imagefig.charon_ci()
    for lines in imagefig.CI_BOXES.values():
        _drawn(svg, lines)
    for _, lines in imagefig.CI_CHECKS.values():
        _drawn(svg, lines)


def test_charon_layers_match_the_dockerfile_and_draw_every_box():
    """The named stages are the charon Dockerfile's, the image is FROM the dev image with
    /opt/charon copied from charon-libs, and every ENV name the figure draws is set there."""
    dockerfile = (REPO / "docker" / "charon" / "Dockerfile").read_text(encoding="utf-8")
    stages = tuple(re.findall(r"^FROM \S+ AS ([\w-]+)$", dockerfile, re.MULTILINE))
    assert stages == imagefig.LAYER_STAGES
    final = dockerfile[dockerfile.rindex("FROM ${TCAD_DEV_IMAGE}\n") :]
    assert "COPY --from=charon-libs /opt/charon /opt/charon" in final
    for name in ("CHARON_EXECUTABLE_PATH", "CHARON_EXECUTABLE", "PATH"):
        assert re.search(rf"\b{name}=", final), name
    assert imagefig.MPI_ENV in final
    svg = imagefig.charon_layers()
    for lines in imagefig.LAYER_BOXES.values():
        _drawn(svg, lines)


def _layer_texts_and_arrows(palette):
    """``({box: drawn text}, [((source, target), start, end), ...])`` read from the drawn
    figure; every arrow drawn is listed, so a duplicate shows up twice."""
    ax = imagefig.charon_layers_figure(palette).axes[0]
    texts, arrows = {}, []
    for t in ax.texts:
        gid = t.get_gid() or ""
        if gid.startswith("layers-text-"):
            texts[gid.removeprefix("layers-text-")] = t.get_text()
        elif gid.startswith("layers-arrow-"):
            src, dst = gid.removeprefix("layers-arrow-").split("-")
            arrows.append(((src, dst), tuple(t.xyann), tuple(t.xy)))
    # nothing else on the axes is an arrow
    drawn = [t for t in ax.texts if getattr(t, "arrow_patch", None) is not None]
    assert len(drawn) == len(arrows)
    return texts, arrows


@pytest.mark.parametrize("palette", list(imagefig.PALETTES))
def test_charon_layers_text_and_arrows_are_the_dockerfiles(palette):
    """Review of #164: what the layer figure draws is checked against the Dockerfile, the pin
    files and the dev image, not against the figure's own table."""
    dockerfile = (REPO / "docker" / "charon" / "Dockerfile").read_text(encoding="utf-8")
    final = dockerfile[dockerfile.rindex("FROM ${TCAD_DEV_IMAGE}\n") :]
    dev = (REPO / "docker" / "tcad-dev" / "Dockerfile").read_text(encoding="utf-8")
    lock = (REPO / "docker" / "charon" / "requirements.lock").read_text(encoding="utf-8")
    texts, arrows = _layer_texts_and_arrows(palette)
    assert set(texts) == {"container", "dev", "opt", "venv", "env", "libs", "wheels"}
    # pin files named in the boxes exist, and the Dockerfile builds from them
    assert "docker/CHARON_IMAGE" in texts["container"]
    assert (REPO / "docker" / "CHARON_IMAGE").is_file()
    assert (
        "docker/TCAD_DEV_IMAGE" in texts["dev"] and (REPO / "docker" / "TCAD_DEV_IMAGE").is_file()
    )
    assert (
        "CHARON_LIBS_IMAGE" in texts["libs"] and (REPO / "docker" / "CHARON_LIBS_IMAGE").is_file()
    )
    assert "FROM ${CHARON_LIBS_IMAGE} AS charon-libs" in dockerfile
    # the dev image's Python is the version the box names
    py = re.search(r"^ARG TCAD_PYTHON=(\d+)\.(\d+)\.\d+$", dev, re.MULTILINE)
    assert py and f"Python {py[1]}.{py[2]} venv" in texts["dev"]
    # layer 1 is the copied /opt/charon, layer 2 the locked wheels with no network
    copied = re.search(r"^COPY --from=charon-libs (\S+) (\S+)$", final, re.MULTILINE)
    assert copied and copied[1] == copied[2] and f"{copied[1]}," in texts["opt"]
    for pkg in ("netCDF4", "cftime"):
        assert pkg in texts["venv"] and re.search(
            rf"^{pkg.lower()}==", lock, re.MULTILINE | re.IGNORECASE
        )
    assert "--network=none" in final and "no network" in texts["venv"]
    assert "requirements.lock" in texts["wheels"] and "--hash=sha256:" in lock
    # every ENV name the box draws is set in the final stage, and the OpenMPI line is there
    label, names = texts["env"].split(":", 1)
    assert label == "ENV"
    drawn = re.findall(r"\b[A-Z][A-Z_]+[A-Z]\b", names)
    assert drawn == ["CHARON_EXECUTABLE_PATH", "CHARON_EXECUTABLE", "PATH"]
    for name in drawn:
        assert re.search(rf"\b{name}=", final), name
    assert "OpenMPI singleton setting" in texts["env"] and imagefig.MPI_ENV in final
    # exactly two arrows, each from its side box's right edge to its layer's left edge
    box = imagefig.STYLE["layers"]
    pad = imagefig.STYLE["pad"]
    assert sorted(pair for pair, _, _ in arrows) == [("libs", "opt"), ("wheels", "venv")]
    for (src, dst), start, end in arrows:
        mid = (box[src][1] + box[src][3]) / 2
        assert start == pytest.approx((box[src][2] + pad, mid))
        assert end == pytest.approx((box[dst][0] - pad, mid))
        assert box[dst][1] <= mid <= box[dst][3]  # the arrow lands on the layer, not beside it
