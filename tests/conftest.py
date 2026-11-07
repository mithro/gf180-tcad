# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures: pretend to be inside a confined sandbox container; the generated pages and
the offline docs build, each made once per session."""

import pytest
from confined_root import make_confined_root

from gf180tcad import sandbox


@pytest.fixture
def inside(monkeypatch, tmp_path):
    """Pretend to be inside the sandbox: marker set and a confined fake filesystem root."""
    monkeypatch.setenv(sandbox.IN_SANDBOX_ENV, "1")
    monkeypatch.setattr(sandbox, "CONFINEMENT_ROOT", make_confined_root(tmp_path / "fakeroot"))


@pytest.fixture(scope="session")
def generated_pages(tmp_path_factory):
    """``docgen.generate`` of the committed result trees, run once per session. Every test that
    only reads the generated pages shares it (issue #169); a test that changes a tree or the
    output makes its own."""
    from optional import importorskip

    importorskip("matplotlib", reason="needs the docs dependency group")
    from gf180tcad import docgen

    out = tmp_path_factory.mktemp("generated")
    docgen.generate(out)
    return out


@pytest.fixture(scope="session")
def offline_html(tmp_path_factory):
    """The HTML folder of one offline ``sphinx-build -W`` of docs/ per session
    (:func:`offline_build.build`), shared by the docs-build tests (issue #169)."""
    from offline_build import build
    from optional import importorskip

    importorskip("sphinx")
    importorskip("matplotlib", reason="needs the docs dependency group")
    return build(tmp_path_factory.mktemp("htmlbuild"))
