"""B1: does Charon accept TRI3 element blocks?

(a) the 1D strip of the nfet calibrated job with every quad split into two TRI3 against the
QUAD4 strip: the same LOCA sweep (vg from -2 V to +2 V, 0.25 V steps, at vg +- 1 mV) on both, the
oxide-flux gate charge and the C per area compared point by point;
(b) a 2D gmsh triangle mesh of the uniform stack (stack.uniform, L = 0.2 um, a coarse MeshSpec)
written as TRI3 blocks per region with the contact lines as side sets: an equilibrium solve and
a two-point C-V at vg = 0 V.
"""
import json
import re
import shutil
import sys

import numpy as np

import cx
import decks
import opts

job = cx.job1d("nfet_05v0", "calibrated")
DV = 1e-3
STEP = 0.25
V0, V1 = -2.0, 0.25  # inversion (device bias above 0.30 V) does not converge (B2)
NPTS = int(round((V1 - V0) / STEP)) + 1
out = {}


def deck(mesh, name, gate_bc, problem, init, sweep=None, gate_ss="gate", body_ss="body_contact",
         job=job):
    d = decks.moscap_deck(job, mesh=mesh, out=f"{name}.exo", gate_bc=gate_bc, problem=problem,
                          init=init, sweep=sweep, rel=opts.REL, abs_=opts.ABS, extra=opts.EXTRA)
    d = d.replace("BC is ohmic for body on body", f"BC is ohmic for {body_ss} on body")
    d = d.replace("BC is ohmic for gate on gate_poly", f"BC is ohmic for {gate_ss} on gate_poly")
    return d


def sweep_pair(mesh, tag, **kw):
    """Equilibrium, then sweeps at vg - dv_fb -+ DV over the grid; returns per-side states."""
    open(f"{tag}_eq.inp", "w").write(deck(mesh, f"{tag}_eq", f"fixed at {V0 - job.dv_fb - DV!r}",
                                          "steady state", "equilibrium", **kw))
    ok, log, dt = cx.run(f"{tag}_eq.inp")
    if not ok:
        return None, f"{tag} equilibrium failed"
    res = {}
    for side, sgn in (("A", -1), ("B", 1)):
        a = V0 - job.dv_fb + sgn * DV
        b = a + (NPTS - 1) * STEP
        sweep = [f"initial step size = {STEP!r}", f"minimum step size = {STEP!r}",
                 f"maximum step size = {STEP!r}", f"maximum number of steps = {NPTS + 5}",
                 "hit continuation bound = false", "step size aggressiveness = 0.0",
                 "predictor method is secant"]
        if side == "A":
            start = f"{tag}_eq.exo"
        else:
            # B starts from a ramp of 2*DV from the A start
            open(f"{tag}_rB.inp", "w").write(deck(mesh, f"{tag}_rB", f"fixed at {a!r}",
                                                  "steady state", "exodus", **kw))
            ok, log, dt = cx.run(f"{tag}_rB.inp")
            if not ok:
                return None, f"{tag} ramp B failed"
            start = f"{tag}_rB.exo"
        txt = deck(start, f"{tag}_{side}", f"swept from {a!r} to {b!r}", "parameter sweep",
                   "exodus", sweep, **kw)
        open(f"{tag}_{side}.inp", "w").write(txt)
        ok, log, dt = cx.run(f"{tag}_{side}.inp")
        fails = re.findall(r"Value of continuation parameter at failed step = (\S+)", log)
        if not ok:
            return None, f"{tag} sweep {side} failed at {fails[:3]}"
        shutil.copy("currents-loca.dat", f"{tag}_{side}.dat")
        res[side] = (cx.read_states(f"{tag}_{side}.exo"), fails, dt)
    return res, "ok"


# (a) QUAD4 vs TRI3 strip --------------------------------------------------------------------
xs1d = np.array(job.stack.node_positions_um()[0])
bn = job.stack.node_positions_um()[1]
c = job.stack.constants
charges = {}
for kind, tri in (() if "--only2d" in sys.argv else (("quad4", False), ("tri3", True))):
    _, xy, blocks, ss = cx.stack_strip(job.stack, tri=tri)
    ss = [("gate", *ss[0][1:]), ("body_contact", *ss[1][1:])]
    cx.write_exodus(f"strip_{kind}.exo", xy, blocks, ss)
    res, msg = sweep_pair(f"strip_{kind}.exo", kind)
    out[f"strip_{kind}"] = msg
    print(kind, msg, flush=True)
    if res is None:
        continue
    q = {}
    for side, (st, fails, dt) in res.items():
        q[side] = np.array([cx.oxide_flux_charge(st, k, xs1d, bn[1], bn[2], c.eps_ox,
                                                 c.eps0_f_per_cm)[0]
                            for k in range(NPTS)])
        out[f"strip_{kind}_{side}_time_s"] = dt
        out[f"strip_{kind}_{side}_failed_steps"] = fails
    charges[kind] = q
if len(charges) == 2:
    cq = {k: (v["B"] - v["A"]) / (2 * DV) * 1e7 for k, v in charges.items()}
    rel = np.abs(cq["tri3"] - cq["quad4"]) / np.abs(cq["quad4"])
    out["strip_c_quad4"] = cq["quad4"].tolist()
    out["strip_c_tri3"] = cq["tri3"].tolist()
    out["strip_max_rel_c_tri3_vs_quad4"] = float(np.max(rel))
    out["strip_max_rel_q_tri3_vs_quad4"] = float(max(
        np.max(np.abs(charges["tri3"][s] - charges["quad4"][s]) / np.max(np.abs(charges["quad4"][s])))
        for s in "AB"))
    print("max rel C tri3 vs quad4", out["strip_max_rel_c_tri3_vs_quad4"])

# (b) a 2D gmsh triangle mesh -------------------------------------------------------------
if "--no2d" not in sys.argv:
    from gf180tcad.tcad import moscap2d, process
    from gf180tcad.tcad import stack as stack_mod
    from gf180tcad.tcad.mesh import MeshSpec

    proc = process.load("nfet_05v0")
    xs = stack_mod.uniform(proc, 0.2)
    spec = MeshSpec(h_poly_nm=2.0, h_ox_nm=4.0, h_si_surface_nm=2.0, h_si_bulk_nm=100.0,
                    grading=1.3)
    dd = moscap2d.build_device(xs, spec, mesh_file="b1.msh")
    dd.delete_device()
    m = cx.read_msh22("b1.msh")
    out["msh_physical"] = m["physical"]
    xy, blocks, ss, info = cx.msh_to_exodus_parts(
        m, regions=["gate_poly", "oxide", "body"],
        contacts={"gate": ("gate_contact", "gate_poly"), "body_contact": ("body_contact", "body")})
    out["mesh2d"] = info
    # the plugin writes the gmsh file in cm (mesh_scaling_factor 1e-4); Charon reads um
    xy = xy * 1e4
    cx.write_exodus("mesh2d.exo", xy, blocks, ss)
    job2 = cx.job1d("nfet_05v0", "start")  # process.load gives the start values
    print("2D mesh", info, flush=True)
    # equilibrium and a two-point C at vg = 0 (gate at -dv_fb -+ DV)
    vals = {}
    for side, sgn in (("A", -1), ("B", 1)):
        v = 0.0 - job2.dv_fb + sgn * DV
        open(f"m2d_{side}.inp", "w").write(deck("mesh2d.exo", f"m2d_{side}", f"fixed at {v!r}",
                                                "steady state", "equilibrium", job=job2))
        ok, log, dt = cx.run(f"m2d_{side}.inp")
        out[f"mesh2d_{side}_ok"] = ok
        out[f"mesh2d_{side}_time_s"] = dt
        if not ok:
            out[f"mesh2d_{side}_tail"] = log[-2000:]
            print("2D", side, "failed")
            break
        gl = cx.read_states(f"m2d_{side}.exo")
        vals[side] = gl
    print(json.dumps({k: v for k, v in out.items() if "mesh2d" in k and "tail" not in k}))
json.dump(out, open("b1.json", "w"), indent=1, default=float)
