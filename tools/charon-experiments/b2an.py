"""B2/B6 analysis of the sweeps written by b2.py: grid alignment, C-V, charge checks.

usage: python3 b2an.py DEVICE PARAMS TAG
"""
import json
import sys

import numpy as np

import cx

dev, params, tag = sys.argv[1], sys.argv[2], sys.argv[3]
job = cx.job1d(dev, params)
DV = 1e-3
n = len(job.vg)
xs = np.array(job.stack.node_positions_um()[0])
bn = job.stack.node_positions_um()[1]
c = job.stack.constants
q_e = c.q_c
eps0 = c.eps0_f_per_cm
res = {"device": dev, "params": params, "tag": tag, "n": n}

sides = {}
for side, sgn in (("A", -1), ("B", 1)):
    head, rows = cx.read_currents(f"currents-sweep{side}.dat")
    v = rows[:, head.index("gate_Voltage")]
    want = np.array(job.vg) - job.dv_fb + sgn * DV
    # LOCA ends with a tiny step onto the exact bound when the accumulated value falls short
    extra = v[n:]
    res[f"extra_states_{side}"] = len(extra)
    res[f"extra_max_dev_{side}"] = float(np.max(np.abs(extra - want[-1]))) if len(extra) else 0.0
    res[f"align_{side}"] = float(np.max(np.abs(v[:n] - want)))
    st = cx.read_states(f"sweep{side}.exo")
    res[f"exo_times_first_{side}"] = [float(t) for t in st.times[:3]]
    res[f"exo_globals_{side}"] = sorted(st.globals_)
    if len(st.times) >= n:
        res[f"align_exo_time_{side}"] = float(np.max(np.abs(np.asarray(st.times[:n]) - want)))
    psi = st.nodal["ELECTRIC_POTENTIAL"][:n, 0::2]
    has_np = "ELECTRON_DENSITY" in st.nodal
    nn = st.nodal["ELECTRON_DENSITY"][:n, 0::2] if has_np else None
    pp = st.nodal["HOLE_DENSITY"][:n, 0::2] if has_np else None
    res[f"nodal_vars_{side}"] = sorted(st.nodal)
    # y = w nodes must equal y = 0 nodes (a 1D solution on the strip)
    res[f"strip_y_asym_{side}"] = float(np.max(np.abs(
        st.nodal["ELECTRIC_POTENTIAL"][:n, 1::2] - psi)))
    x = xs * 1e-4
    i0, i1 = bn[1], bn[2]  # oxide nodes i0..i1
    # flux through each oxide interval (C/cm^2), positive for the gate charge
    e = c.eps_ox * eps0 * (psi[:, i0:i1] - psi[:, i0 + 1:i1 + 1]) / np.diff(x[i0:i1 + 1])
    q_gate = e[:, 0]
    res[f"oxide_flux_spread_{side}"] = float(np.max(np.abs(e - e[:, :1]) / np.max(np.abs(e))))
    # space charge over the CVFEM control volumes (1D median dual: half of each neighbour interval)
    st_ = job.meta["stack"]
    pol = st_["polarity"]
    net = np.zeros(len(xs))
    gate_net = st_["ngate_cm3"] if pol == "n" else -st_["ngate_cm3"]
    body_net = -st_["n_ch_cm3"] if pol == "n" else st_["n_ch_cm3"]

    def region_charge(lo, hi, dnet):
        h = np.diff(x[lo:hi + 1])
        vol = np.zeros(hi - lo + 1)
        vol[:-1] += h / 2
        vol[1:] += h / 2
        rho = q_e * (pp[:, lo:hi + 1] - nn[:, lo:hi + 1] + dnet)
        return rho @ vol

    if not has_np:
        sides[side] = q_gate
        continue
    q_poly = region_charge(0, i0, gate_net)
    q_body = region_charge(i1, len(xs) - 1, body_net)
    scale = np.max(np.abs(q_gate))
    res[f"poly_vs_gate_{side}"] = float(np.max(np.abs(q_poly - q_gate)) / scale)
    res[f"body_vs_gate_{side}"] = float(np.max(np.abs(q_body + q_gate)) / scale)
    # n*p/ni^2 in the neutral bulk (last body node and first poly node)
    ni = c.n_i_cm3
    res[f"np_over_ni2_body_{side}"] = [float(nn[0, -1] * pp[0, -1] / ni**2),
                                       float(nn[-1, -1] * pp[-1, -1] / ni**2)]
    res[f"np_over_ni2_poly_{side}"] = [float(nn[0, 0] * pp[0, 0] / ni**2),
                                       float(nn[-1, 0] * pp[-1, 0] / ni**2)]
    sides[side] = q_gate
cc = (sides["B"] - sides["A"]) / (2 * DV) * 1e7
dv = np.array(job.c_devsim)
rel = (cc - dv) / dv
res["c_ff_um2"] = cc.tolist()
res["rel_vs_devsim"] = rel.tolist()
res["max_abs_rel_vs_devsim"] = float(np.max(np.abs(rel)))
res["argmax_vg"] = job.vg[int(np.argmax(np.abs(rel)))]
for k, val in res.items():
    if not isinstance(val, list) or len(val) < 5:
        print(k, val)
for i in range(0, n, 10):
    print(f"vg={job.vg[i]:+.2f} C={cc[i]:.7f} devsim={dv[i]:.7f} rel={rel[i]:+.3e}")
json.dump(res, open(f"b2an_{tag}.json", "w"), indent=1)
