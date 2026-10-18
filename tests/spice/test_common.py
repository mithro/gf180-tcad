# SPDX-License-Identifier: Apache-2.0
"""Engine-agnostic result assembly shared by the ngspice and Xyce runners."""

import numpy as np
import pytest

from gf180tcad.devices import DEVICES, SWEEPS
from gf180tcad.spice import common, ngspice
from gf180tcad.spice.common import SpiceError
from gf180tcad.spice.netlist import bias_plan

NFET = DEVICES["nfet_05v0"]
SW = {s.name: s for s in SWEEPS}


class _OtherError(SpiceError):
    engine = "Other"


def test_assemble_with_custom_vectors_and_error_class():
    plan = bias_plan(NFET, SW["idvd"])
    grid = plan.grid()
    raw = {"V(D)": grid["vd"] + 1e-12, "I(VD)": -np.ones(plan.npoints)}
    vectors = {"vd": ("V(D)", 1.0), "id": ("I(VD)", -1.0)}
    res = common.assemble(plan, raw, vectors=vectors, error=_OtherError)
    assert list(res) == ["vd", "id"]
    assert res["vd"].tobytes() == grid["vd"].tobytes()
    np.testing.assert_array_equal(res["id"], np.ones(plan.npoints))
    raw["V(D)"] = raw["V(D)"] + 1e-6
    with pytest.raises(_OtherError, match="vd: Other bias values differ") as exc:
        common.assemble(plan, raw, "log line", vectors=vectors, error=_OtherError)
    assert "--- Other log" in str(exc.value)


def test_ngspice_reexports_the_shared_pieces():
    assert ngspice.SpiceError is common.SpiceError
    assert ngspice.SpiceResult is common.SpiceResult
    assert ngspice.GRID_TOL == common.GRID_TOL == 1e-9
