# SPDX-License-Identifier: Apache-2.0
"""The reduced mesh artefact's jobs in the TCAD image (renders plan Task R0), ``pytest -m sandbox``.

``cut-job`` runs twice on the #35 calibrated nfet ``w10p0_l0p60`` mesh, pulled from the output
cache, and must give the same bytes; ``regenerate-job`` (without ``--cut``) meshes that job's
cross-section again and reports the regenerated sha256 against the committed one. Both run
through the host commands of :mod:`gf180tcad.meshcut.__main__`, so they need Docker and the
pinned stable TCAD image. The cut job is a 4 GiB job and the regeneration a 16 GiB one (it
meshes and solves the equilibrium): neither runs beside another 16 GiB job.
"""

import hashlib
import json
from pathlib import Path

import pytest

from gf180tcad import meshcut
from gf180tcad.meshcut import __main__ as cli
from gf180tcad.meshcut import job

REPO = Path(__file__).resolve().parents[2]
L0P60 = REPO / "results" / "tcad" / "moscap2d" / "nfet_05v0" / "calibrated" / "w10p0_l0p60"
# A window the M1 grid has (renders plan, Step 3): its artefact is over the 2 MB budget, so the
# test keeps the job's scratch output and does not install it.
KX, DEPTH_UM = 0.25, 0.1


def _cut(scratch: Path) -> dict[str, bytes]:
    with pytest.raises(ValueError, match="budget"):
        cli.run_cut(L0P60, scratch / "meshes" / "stable", kx=KX, depth_um=DEPTH_UM,
                    scratch=scratch / "job")  # fmt: skip
    return {n: (scratch / "job" / n).read_bytes() for n in (meshcut.ARTEFACT, meshcut.META)}


@pytest.mark.sandbox
def test_cut_job_byte_identical_twice(tmp_path):
    one, two = _cut(tmp_path / "one"), _cut(tmp_path / "two")
    assert one == two
    meta = json.loads(one[meshcut.META])
    cv_meta = json.loads((L0P60 / "cv.meta.json").read_bytes())
    assert meta["full_mesh_sha256"] == cv_meta["mesh_sha256"]
    assert meta["npz_sha256"] == hashlib.sha256(one[meshcut.ARTEFACT]).hexdigest()


@pytest.mark.sandbox
def test_regenerated_mesh_sha_reported(tmp_path, capsys):
    cli.run_regenerate(L0P60, scratch=tmp_path / "job")
    report = json.loads((tmp_path / "job" / job.REGENERATE_REPORT).read_bytes())
    cv_meta = json.loads((L0P60 / "cv.meta.json").read_bytes())
    assert report["committed_mesh_sha256"] == cv_meta["mesh_sha256"]
    assert len(report["regenerated_mesh_sha256"]) == 64
    assert report["match"] == (report["regenerated_mesh_sha256"] == cv_meta["mesh_sha256"])
    printed = capsys.readouterr().out
    assert report["regenerated_mesh_sha256"] in printed and cv_meta["mesh_sha256"] in printed
