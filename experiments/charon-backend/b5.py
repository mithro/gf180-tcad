"""B5: Charon's nodal doping against the description's node values, both devices, start and
calibrated; also n*p/n_i^2 in the neutral bulk (the n_i check of B2) and the scaling C0.

Charon writes non-DOF nodal fields scaled by its concentration scaling C0 (read from the log).
"""

import json
import re
from pathlib import Path

import cx
import decks
import numpy as np
import opts

names = "Doping,Acceptor Concentration,Donor Concentration,Intrinsic Concentration"
out = {}
for dev in ("nfet_05v0", "pfet_05v0"):
    for params in ("start", "calibrated"):
        job = cx.job1d(dev, params)
        xs, xy, blocks, ss = cx.stack_strip(job.stack)
        ss = [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])]
        cx.write_exodus("strip.exo", xy, blocks, ss)
        tag = f"{dev}_{params}"
        d = decks.moscap_deck(
            job,
            mesh="strip.exo",
            out=f"{tag}.exo",
            gate_bc="fixed at 0.0",
            nodal_out=[("gate_poly", names), ("body", names)],
            rel=opts.REL,
            abs_=opts.ABS,
            extra=opts.EXTRA,
        )
        d = d.replace("BC is ohmic for body on body", "BC is ohmic for body_contact on body")
        Path(f"{tag}.inp").write_text(d)
        ok, log, dt = cx.run(f"{tag}.inp")
        rec = {"ok": ok}
        if not ok:
            rec["tail"] = log[-1500:]
            out[tag] = rec
            print(tag, "failed")
            continue
        c0 = float(re.search(r"Concentration Scaling C0 = (\S+)", log).group(1))
        st = cx.read_states(f"{tag}.exo")
        bn = job.stack.node_positions_um()[1]
        stk = job.meta["stack"]
        pol = stk["polarity"]
        gate_net = stk["ngate_cm3"] if pol == "n" else -stk["ngate_cm3"]
        body_net = -stk["n_ch_cm3"] if pol == "n" else stk["n_ch_cm3"]
        dop = st.nodal["Doping"][0, 0::2] * c0
        want = np.zeros(len(xs))
        want[: bn[1] + 1] = gate_net
        want[bn[2] :] = body_net
        semi = np.r_[0 : bn[1] + 1, bn[2] : len(xs)]
        rel = np.abs(dop[semi] - want[semi]) / np.abs(want[semi])
        # the oxide nodes: interface nodes belong to two blocks
        rec.update(
            c0=c0,
            max_rel_doping=float(np.max(rel)),
            poly_doping_cm3=float(dop[0]),
            body_doping_cm3=float(dop[-1]),
            interface_doping_cm3=[float(dop[bn[1]]), float(dop[bn[2]])],
            ni_cm3=float(st.nodal["Intrinsic Concentration"][0, 0] * c0),
            ni_want=job.meta["constants"]["n_i_cm3"],
            x_um=list(map(float, xs)),
            doping_cm3=dop.tolist(),
            description_cm3=want.tolist(),
            semiconductor_nodes=semi.tolist(),
        )
        nn = st.nodal["ELECTRON_DENSITY"][0, 0::2]
        pp = st.nodal["HOLE_DENSITY"][0, 0::2]
        ni = job.meta["constants"]["n_i_cm3"]
        rec["np_over_ni2_poly_bulk"] = float(nn[0] * pp[0] / ni**2)
        rec["np_over_ni2_body_bulk"] = float(nn[-1] * pp[-1] / ni**2)
        rec["max_abs_np_over_ni2_minus_1"] = float(np.max(np.abs(nn[semi] * pp[semi] / ni**2 - 1)))
        out[tag] = rec
        print(tag, rec, flush=True)
Path("b5.json").write_text(json.dumps(out, indent=1))
