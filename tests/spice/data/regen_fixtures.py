# SPDX-License-Identifier: Apache-2.0
"""Regenerate the tiny ngspice binary raw fixtures in this directory (needs Docker + the image).

    uv run python tests/spice/data/regen_fixtures.py

ngspice runs in the sandbox on two resistor/capacitor netlists (no PDK models), so the expected
values are analytic (see tests/spice/test_rawfile.py):

- ``rc_dc.raw``: real plot, ``.dc`` sweep of a 1k/1k divider, 3 points.
- ``rc_ac.raw``: complex plot, ``.ac`` of a 1k / 1n RC low-pass at 100, 200 and 300 kHz.

The raw files carry a ``Date:`` header line, so regenerating changes their bytes but not the
values the tests check.
"""

import shutil
import tempfile
from pathlib import Path

from gf180tcad import sandbox

HERE = Path(__file__).resolve().parent

NETLISTS = {
    "rc_dc": """\
* gf180tcad raw fixture: real dc sweep
V1 in 0 dc 0
R1 in out 1k
R2 out 0 1k
.dc V1 0 2 1
.control
set filetype=binary
run
write rc_dc.raw v(in) v(out) i(v1)
.endc
.end
""",
    "rc_ac": """\
* gf180tcad raw fixture: complex ac sweep
V1 in 0 dc 0 ac 1
R1 in out 1k
C1 out 0 1n
.ac lin 3 1e5 3e5
.control
set filetype=binary
run
write rc_ac.raw v(out) i(v1)
.endc
.end
""",
}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="gf180tcad-fixture-") as tmp:
        work = Path(tmp)
        for name, text in NETLISTS.items():
            (work / f"{name}.cir").write_text(text, encoding="utf-8")
            res = sandbox.run(["ngspice", "-b", f"{name}.cir"], out_dir=work, mem="1g", cpus=1)
            print(res.stdout, res.stderr)
            shutil.copyfile(work / f"{name}.raw", HERE / f"{name}.raw")
            print(f"wrote {HERE / f'{name}.raw'}")


if __name__ == "__main__":
    main()
