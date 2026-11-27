"""The two deck traps of issue #224, on the nfet calibrated strip at equilibrium (0 V).

- side_set_named_body: the body's side set keeps the name of its element block, `body` (the
  scripts rename it `body_contact`);
- doping_block_misnamed: the body's uniform doping block is named `BodyDoping`, not `Function1`
  (the poly's keeps `Function1`).

Each deck is B5's deck otherwise (nodal Doping written). Records per deck the interpreter's and
charon_mp.exe's exit codes, whether Charon completed, the log tails, and when an Exodus file was
written the nodal Doping (cm^-3, scaled back by C0) against the description, per block.
Writes traps.json.
"""

import json
import re
import subprocess
from pathlib import Path

import cx
import decks
import numpy as np
import opts

NAMES = "Doping,Acceptor Concentration,Donor Concentration,Intrinsic Concentration"
TAIL = 1500


def run(inp: str) -> dict:
    """The interpreter, then charon_mp.exe, as cx.run, with both exit codes kept."""
    r = subprocess.run(
        ["python3", "-W", "ignore", cx.INTERP, "-i", inp],
        check=False,
        capture_output=True,
        text=True,
    )
    rec = {
        "interpreter_exit": r.returncode,
        "interpreter_tail": (r.stdout + r.stderr)[-TAIL:],
        "xml_written": Path(inp + ".xml").is_file(),
    }
    if r.returncode != 0 or not rec["xml_written"]:
        return rec
    # stdbuf: charon_mp.exe buffers stdout, and an MPI_ABORT loses the buffered tail
    r = subprocess.run(
        ["stdbuf", "-o0", "-e0", cx.CHARON, f"--i={inp}.xml"],
        check=False,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    out = r.stdout + r.stderr
    Path(inp + ".log").write_text(out)
    rec.update(
        charon_exit=r.returncode,
        completed="Charon run completed." in out,
        tail=out[-TAIL:],
        log=out,
    )
    return rec


def doping(job, exo: str, log: str) -> dict:
    """The nodal Doping per block against the description (the B5 check, per block)."""
    c0 = float(re.search(r"Concentration Scaling C0 = (\S+)", log).group(1))
    st = cx.read_states(exo)
    xs, bn = job.stack.node_positions_um()
    stk = job.meta["stack"]
    gate_net = stk["ngate_cm3"] if stk["polarity"] == "n" else -stk["ngate_cm3"]
    body_net = -stk["n_ch_cm3"] if stk["polarity"] == "n" else stk["n_ch_cm3"]
    dop = st.nodal["Doping"][0, 0::2] * c0
    # the interface nodes belong to two blocks; each block's interior nodes only
    poly, body = np.r_[0 : bn[1]], np.r_[bn[2] + 1 : len(xs)]
    return {
        "c0": c0,
        "doping_cm3": dop.tolist(),
        "x_um": list(map(float, xs)),
        "poly_description_cm3": gate_net,
        "body_description_cm3": body_net,
        "poly_max_rel": float(np.max(np.abs(dop[poly] / gate_net - 1))),
        "body_max_abs_cm3": float(np.max(np.abs(dop[body]))),
        "body_max_rel": float(np.max(np.abs(dop[body] / body_net - 1))),
    }


def main() -> int:
    job = cx.job1d("nfet_05v0", "calibrated")
    _, xy, blocks, ss = cx.stack_strip(job.stack)
    assert [s[0] for s in ss] == ["gate", "body"], ss
    cx.write_exodus("strip_body.exo", xy, blocks, ss)
    cx.write_exodus("strip.exo", xy, blocks, [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])])

    def deck(mesh, out):
        return decks.moscap_deck(
            job,
            mesh=mesh,
            out=out,
            gate_bc="fixed at 0.0",
            nodal_out=[("gate_poly", NAMES), ("body", NAMES)],
            rel=opts.REL,
            abs_=opts.ABS,
            extra=opts.EXTRA,
        )

    # the side set keeps the block's name: the deck's BC names the side set `body` as it is
    side = deck("strip_body.exo", "side_set_named_body.exo")
    assert "BC is ohmic for body on body fixed at 0.0" in side
    # the body's doping block renamed; the poly's keeps Function1
    misnamed = deck("strip.exo", "doping_block_misnamed.exo").replace(
        "BC is ohmic for body on body", "BC is ohmic for body_contact on body"
    )
    head, body_block = misnamed.split("start Material Block bodyParameter")
    assert body_block.count("uniform doping named Function1") == 2, body_block
    misnamed = (
        head
        + "start Material Block bodyParameter"
        + body_block.replace("uniform doping named Function1", "uniform doping named BodyDoping")
    )
    rec = {}
    for name, text in (("side_set_named_body", side), ("doping_block_misnamed", misnamed)):
        Path(f"{name}.inp").write_text(text)
        r = run(f"{name}.inp")
        log = r.pop("log", "")
        r["exodus_written"] = Path(f"{name}.exo").is_file()
        r["doping"] = doping(job, f"{name}.exo", log) if r.get("completed") else None
        rec[name] = r
        print(
            name,
            {k: v for k, v in r.items() if "tail" not in k and k != "doping"},
            None
            if r["doping"] is None
            else {k: v for k, v in r["doping"].items() if not isinstance(v, list)},
            flush=True,
        )
    Path("traps.json").write_text(json.dumps(rec, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
