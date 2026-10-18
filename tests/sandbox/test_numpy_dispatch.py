# SPDX-License-Identifier: Apache-2.0
"""numpy runs its baseline (x86-64-v2) kernels in the sandbox, on every host.

numpy picks SIMD kernels at run time by CPU (X86_V3 = AVX2, X86_V4 = AVX-512, ...), and they
are not bit-identical: ``np.log10`` differs by 1 ulp between the AVX-512 and AVX2 paths, which
made metrics differ between an AVX-512 host and an AVX2-only GitHub runner although every
simulator CSV was identical. ``tools/sandbox-run`` therefore sets ``NPY_DISABLE_CPU_FEATURES``
to every dispatch target. Run with ``pytest -m sandbox``.
"""

import json

import pytest

from gf180tcad import sandbox

pytestmark = pytest.mark.sandbox

_ENABLED = (
    "import json, numpy._core._multiarray_umath as m; "
    "print(json.dumps({'dispatch': m.__cpu_dispatch__, "
    "'enabled': [f for f in m.__cpu_dispatch__ if m.__cpu_features__.get(f)]}))"
)


def _dispatch(tmp_path, *env_prefix):
    res = sandbox.run([*env_prefix, "python3", "-W", "error", "-c", _ENABLED], out_dir=tmp_path)
    assert res.stderr == "", res.stderr  # no warning, even with -W error
    return json.loads(res.stdout)


def test_sandbox_runs_numpy_baseline_kernels(tmp_path):
    got = _dispatch(tmp_path)
    assert {"X86_V3", "X86_V4"} <= set(got["dispatch"])
    assert got["enabled"] == []


def test_control_without_the_variable_dispatches_on_this_host(tmp_path):
    got = _dispatch(tmp_path, "env", "-u", "NPY_DISABLE_CPU_FEATURES")
    if not got["enabled"]:
        pytest.skip("this host has no CPU feature above x86-64-v2, so there is nothing to disable")
    assert "X86_V3" in got["enabled"]


def test_disabling_features_the_host_lacks_is_silent(tmp_path):
    # Every dispatch target is disabled, including ones this CPU may not have (on the AVX2-only
    # runners: X86_V4 and the AVX512_* targets); numpy must neither fail nor warn.
    got = _dispatch(tmp_path, "env", "NPY_DISABLE_CPU_FEATURES=AVX512_SPR AVX512_ICL")
    assert "AVX512_SPR" not in got["enabled"] and "AVX512_ICL" not in got["enabled"]


# Every committed job: extract the metrics from its CSVs in the image, with the sandbox's
# baseline-only numpy and with only the AVX-512 targets disabled (an AVX2 host).
_EXTRACT = """
import json, sys
from pathlib import Path
from gf180tcad import io, metrics, reference
from gf180tcad.devices import CORNERS, DEVICES
out = {}
for job in reference.plan_jobs(reference.ENGINES, CORNERS, tuple(DEVICES)):
    root = Path("/work/src/results/spice") / job.relpath
    data = {s: io.read_csv(root / f"{s}.csv")[0] for s in reference.engine_sweeps(job.engine)}
    g = reference.geometry_of(job.device, job.geometry)
    out[job.relpath.as_posix()] = metrics.extract_all(DEVICES[job.device], g, data)
print(json.dumps(out, sort_keys=True))
"""
_AVX2_HOST = "NPY_DISABLE_CPU_FEATURES=X86_V4 AVX512_ICL AVX512_SPR"


def _extract(tmp_path, *env_prefix) -> dict:
    res = sandbox.run([*env_prefix, "python3", "-c", _EXTRACT], out_dir=tmp_path)
    return json.loads(res.stdout)


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    return _extract(tmp_path_factory.mktemp("baseline"))


def test_baseline_metrics_equal_an_avx2_host_bit_for_bit(baseline, tmp_path):
    avx2 = _extract(tmp_path, "env", _AVX2_HOST)
    assert len(baseline) == 120
    diff = [(j, k) for j in baseline for k in baseline[j] if baseline[j][k] != avx2[j][k]]
    assert json.dumps(baseline, sort_keys=True) == json.dumps(avx2, sort_keys=True), diff


def test_committed_metrics_are_the_baseline_extraction(baseline):
    """results/spice/**/metrics.json equals what the sandbox computes from the committed CSVs."""
    stale = []
    for j, m in baseline.items():
        committed = json.loads(
            (sandbox.REPO_ROOT / "results" / "spice" / j / "metrics.json").read_bytes()
        )
        if committed["metrics"] != m:
            stale.append(j)
    assert stale == [], f"{len(stale)} metrics.json differ from the baseline extraction: {stale}"
