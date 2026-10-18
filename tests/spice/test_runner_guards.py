# SPDX-License-Identifier: Apache-2.0
"""Both SPICE runners: out_dir must hold only their own files; a hung simulator times out."""

import shutil
import subprocess
from pathlib import Path

import pytest

from gf180tcad import sandbox
from gf180tcad.devices import DEVICES, SWEEPS
from gf180tcad.spice import ngspice, xyce
from gf180tcad.spice.common import SpiceError
from gf180tcad.spice.netlist import bias_plan, ngspice_netlist
from gf180tcad.spice.xyce import xyce_netlist

DATA = Path(__file__).parent / "data"
NFET = DEVICES["nfet_05v0"]
SW = {s.name: s for s in SWEEPS}

XYCE_LOG = "***** Executing netlist xyce.cir\n\nTiming summary of 1 processor\n"
NGSPICE_LOG = 'Note: No compatibility mode selected!\nbinary raw file "out.raw"\n'


def _fake_ngspice(out_dir: Path, extra: str | None = None) -> None:
    (out_dir / ngspice.LOG_NAME).write_text(NGSPICE_LOG)
    shutil.copy(DATA / "rc_dc.raw", out_dir / ngspice.RAW_NAME)
    if extra:
        (out_dir / extra).write_text("written by the simulator\n")


def _fake_xyce(out_dir: Path, extra: str | None = None) -> None:
    (out_dir / xyce.LOG_NAME).write_text(XYCE_LOG)
    (out_dir / xyce.CSV_NAME).write_text("V(D),I(VD)\n0.0,1e-3\n")
    if extra:
        (out_dir / extra).write_text("written by the simulator\n")


RUNNERS = {
    "ngspice": (ngspice.run_ngspice, _fake_ngspice, ngspice),
    "xyce": (xyce.run_xyce, _fake_xyce, xyce),
}


@pytest.fixture
def fake_sandbox(monkeypatch):
    """Replace sandbox.run by a fake that writes a simulator's outputs (no Docker)."""
    calls = []

    def install(writer, extra=None, returncode=0):
        def run(cmd, *, out_dir, **kw):
            calls.append(cmd)
            writer(Path(out_dir), extra)
            res = subprocess.CompletedProcess(cmd, returncode, "", "")
            if returncode:
                raise sandbox.SandboxError(res)
            return res

        monkeypatch.setattr(sandbox, "run", run)
        return calls

    return install


# --- out_dir must hold only the runner's own files ------------------------------------------


@pytest.mark.parametrize("engine", RUNNERS)
@pytest.mark.parametrize(
    "planted", ["sm141064.spice", "sm141064.ngspice", "models.lib", "sm141064.xyce", ".spiceinit"]
)
def test_planted_model_file_is_refused(tmp_path, fake_sandbox, engine, planted):
    run, writer, _ = RUNNERS[engine]
    calls = fake_sandbox(writer)
    (tmp_path / planted).write_text(".lib typical\n.endl typical\n")
    with pytest.raises(SpiceError, match=planted.replace(".", r"\.")):
        run("* x\n.end\n", tmp_path)
    assert calls == [], "the simulator must not be started"
    assert (tmp_path / planted).exists(), "a foreign file is never deleted"


@pytest.mark.parametrize("engine", RUNNERS)
def test_any_unexpected_file_or_directory_is_refused(tmp_path, fake_sandbox, engine):
    run, writer, _ = RUNNERS[engine]
    calls = fake_sandbox(writer)
    (tmp_path / "notes.txt").write_text("x")
    with pytest.raises(SpiceError, match="notes.txt"):
        run("* x\n.end\n", tmp_path)
    (tmp_path / "notes.txt").unlink()
    (tmp_path / "sub").mkdir()
    with pytest.raises(SpiceError, match="sub"):
        run("* x\n.end\n", tmp_path)
    assert calls == []


@pytest.mark.parametrize("engine", RUNNERS)
def test_previous_own_outputs_are_replaced(tmp_path, fake_sandbox, engine):
    run, writer, mod = RUNNERS[engine]
    fake_sandbox(writer)
    run("* first\n.end\n", tmp_path)
    run("* second\n.end\n", tmp_path)  # its own netlist, log and data file are allowed
    assert (tmp_path / mod.NETLIST_NAME).read_text() == "* second\n.end\n"


@pytest.mark.parametrize("engine", RUNNERS)
def test_explicit_inputs_are_allowed(tmp_path, fake_sandbox, engine):
    run, writer, _ = RUNNERS[engine]
    fake_sandbox(writer)
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "sm141064.spice").write_text("* patched\n")
    run("* x\n.end\n", tmp_path, inputs=("lib",))
    assert (tmp_path / "lib" / "sm141064.spice").is_file()
    with pytest.raises(ValueError, match="own"):
        run("* x\n.end\n", tmp_path, inputs=("lib", "out.raw", "out.csv"))


@pytest.mark.parametrize("engine", RUNNERS)
def test_file_written_by_the_simulator_is_an_error(tmp_path, fake_sandbox, engine):
    run, writer, _ = RUNNERS[engine]
    fake_sandbox(writer, extra="other.dat")
    with pytest.raises(SpiceError, match="other.dat"):
        run("* x\n.end\n", tmp_path)


@pytest.mark.parametrize("engine", RUNNERS)
def test_own_name_that_is_a_directory_is_spice_error(tmp_path, fake_sandbox, engine):
    run, writer, mod = RUNNERS[engine]
    calls = fake_sandbox(writer)
    (tmp_path / mod.LOG_NAME).mkdir()
    with pytest.raises(SpiceError, match="directory"):
        run("* x\n.end\n", tmp_path)
    assert calls == []


BSIM4_REPORT = (
    "BSIM4v5: mosfet m.xdut.m0, model nfet_06v0.1:\n"
    "Warning: Pbswgd = 0.01 is less than 0.1. Pbswgd is set to 0.1.\n"
)


@pytest.mark.parametrize("name", ["bsim4v5.out", "bsim4v6.out", "bsim4v7.out", "bsim4.out"])
def test_ngspice_bsim4_report_is_read_into_warnings_and_deleted(
    tmp_path, fake_sandbox, monkeypatch, name
):
    def writer(out_dir, extra):
        _fake_ngspice(out_dir)
        (out_dir / name).write_text(BSIM4_REPORT)

    fake_sandbox(writer)
    res = ngspice.run_ngspice("* x\n.end\n", tmp_path)
    assert res.warnings == (
        f"{name}: BSIM4v5: mosfet m.xdut.m0, model nfet_06v0.1:",
        f"{name}: Warning: Pbswgd = 0.01 is less than 0.1. Pbswgd is set to 0.1.",
    )
    assert not (tmp_path / name).exists()
    # a report left over from an older run is the runner's own file: replaced, not refused
    (tmp_path / name).write_text("stale\n")
    fake_sandbox(_fake_ngspice)
    assert ngspice.run_ngspice("* x\n.end\n", tmp_path).warnings == ()
    assert not (tmp_path / name).exists()


def test_xyce_has_no_optional_report_files(tmp_path, fake_sandbox):
    fake_sandbox(_fake_xyce, extra="bsim4v5.out")
    with pytest.raises(SpiceError, match="bsim4v5.out"):
        xyce.run_xyce("* x\n.end\n", tmp_path)


# --- timeout --------------------------------------------------------------------------------


@pytest.mark.parametrize("engine", RUNNERS)
def test_command_has_timeout(tmp_path, fake_sandbox, engine):
    run, writer, mod = RUNNERS[engine]
    calls = fake_sandbox(writer)
    run("* x\n.end\n", tmp_path)
    assert mod.TIMEOUT_S == 600
    assert calls[0][:2] == ["sh", "-c"] and calls[0][2].startswith("exec timeout 600 ")


@pytest.mark.parametrize("engine", RUNNERS)
def test_timeout_exit_is_spice_error(tmp_path, fake_sandbox, engine):
    run, writer, _ = RUNNERS[engine]
    fake_sandbox(writer, returncode=124)
    with pytest.raises(SpiceError, match="timed out after 600 s"):
        run("* x\n.end\n", tmp_path)


def _long_idvd(text: str) -> str:
    # 5 V in 1 uV steps x 5 gate values: minutes of work, far beyond a 2 s timeout
    return text.replace(".dc vd 0.0 5.0 0.01 ", ".dc vd 0.0 5.0 1e-06 ")


@pytest.mark.sandbox
def test_ngspice_real_timeout(image_pdk, tmp_path, monkeypatch):
    monkeypatch.setattr(ngspice, "TIMEOUT_S", 2)
    text = _long_idvd(
        ngspice_netlist(NFET, NFET.geometries[0], SW["idvd"], "typical", 25, image_pdk)
    )
    assert "1e-06" in text
    with pytest.raises(SpiceError, match="timed out after 2 s"):
        ngspice.run_ngspice(text, tmp_path, plan=bias_plan(NFET, SW["idvd"]))


@pytest.mark.sandbox
def test_xyce_real_timeout(image_pdk, tmp_path, monkeypatch):
    monkeypatch.setattr(xyce, "TIMEOUT_S", 2)
    text = _long_idvd(xyce_netlist(NFET, NFET.geometries[0], SW["idvd"], "typical", 25, image_pdk))
    assert "1e-06" in text
    with pytest.raises(SpiceError, match="timed out after 2 s"):
        xyce.run_xyce(text, tmp_path, plan=bias_plan(NFET, SW["idvd"]))
