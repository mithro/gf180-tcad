"""Charon experiment helpers (Task B, experiments B1-B7): Exodus writer, decks, runner, readers.

Runs inside the Charon image (numpy, netCDF4, gplugins and gf180tcad on the path).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import netCDF4
import numpy as np

REPO = Path(os.environ.get("GF180TCAD_REPO", "/work/src"))
CHARON = "/opt/charon/bin/charon_mp.exe"
INTERP = "/opt/charon/bin/charonInterpreter.py"

# --------------------------------------------------------------------------------------------
# The 1D job of the committed DEVSIM tree
# --------------------------------------------------------------------------------------------


@dataclass
class Job1D:
    device: str
    params: str
    stack: object  # gplugins Stack1D
    meta: dict
    vg: list[float]
    c_devsim: list[float]  # fF/um^2
    dv_fb: float


def job1d(device: str, params: str, *, mesh_spacing: dict | None = None) -> Job1D:
    """The Stack1D of a committed DEVSIM 1D job, built from its meta as the DEVSIM job built it."""
    from gplugins.devsim import Contact, InterfaceRef, Layer1D, Mesh1D, doping
    from gplugins.devsim.constants import Constants
    from gplugins.devsim.device_description import Stack1D

    d = REPO / "results/tcad/moscap1d" / device / params
    meta = json.loads((d / "per_area.meta.json").read_text())
    st = meta["stack"]
    body_dopant = "acceptor" if st["polarity"] == "n" else "donor"
    gate_dopant = "donor" if st["polarity"] == "n" else "acceptor"
    layers = [
        Layer1D(
            "gate_poly", "silicon", st["poly_um"], doping.constant(st["ngate_cm3"]), gate_dopant
        ),
        Layer1D("oxide", "oxide", st["t_ox_nm"] * 1e-3, None),
        Layer1D("body", "silicon", st["body_um"], doping.constant(st["n_ch_cm3"]), body_dopant),
    ]
    contacts = [
        Contact("gate", InterfaceRef("gate_poly", None), "ohmic"),
        Contact("body", InterfaceRef("body", None), "ohmic"),
    ]
    spacing = mesh_spacing or {k: tuple(v) for k, v in meta["mesh_1d_spacing_um"].items()}
    c = {k: v for k, v in meta["constants"].items() if k not in ("n_i_cm3", "vt_v")}
    consts = Constants(**c, eps_ox=st["eps_ox"])
    stack = Stack1D(
        f"moscap1d_{device}",
        layers,
        contacts,
        Mesh1D(spacing, max_ratio=meta["mesh"]["grading"]),
        consts,
    )
    vg, cs = [], []
    for line in (d / "per_area.csv").read_text().splitlines():
        if line.startswith(("#", "vg")):
            continue
        f = line.split(",")
        vg.append(float(f[0]))
        cs.append(float(f[1]))
    dv_fb = meta["tunables"]["dv_fb_v"]["value"]
    return Job1D(device, params, stack, meta, vg, cs, dv_fb)


# --------------------------------------------------------------------------------------------
# Exodus II writer (netCDF classic), nodes never reordered
# --------------------------------------------------------------------------------------------

LEN_NAME = 33


def _chars(names, width=LEN_NAME):
    a = np.zeros((len(names), width), dtype="S1")
    for i, n in enumerate(names):
        b = n.encode()
        assert len(b) < width, n
        a[i, : len(b)] = np.frombuffer(b, dtype="S1")
    return a


def write_exodus(path, xy_um, blocks, sidesets, title="gf180tcad"):
    """Write a 2D Exodus II file.

    xy_um: (N, 2) float64 node coordinates (um). blocks: list of (name, elem_type, conn) with
    conn an (E, k) array of 0-based node indices; elements are numbered block by block from 1.
    sidesets: list of (name, elem_ids 1-based, local side ids 1-based).
    """
    xy = np.asarray(xy_um, dtype=np.float64)
    ds = netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET")
    try:
        ds.setncattr("api_version", np.float32(8.03))
        ds.setncattr("version", np.float32(8.03))
        ds.setncattr("floating_point_word_size", np.int32(8))
        ds.setncattr("file_size", np.int32(1))
        ds.setncattr("maximum_name_length", np.int32(32))
        ds.setncattr("int64_status", np.int32(0))
        ds.setncattr("title", title)
        nelem = sum(len(c) for _, _, c in blocks)
        ds.createDimension("len_string", 33)
        ds.createDimension("len_line", 81)
        ds.createDimension("four", 4)
        ds.createDimension("len_name", LEN_NAME)
        ds.createDimension("time_step", None)
        ds.createDimension("num_dim", 2)
        ds.createDimension("num_nodes", len(xy))
        ds.createDimension("num_elem", nelem)
        ds.createDimension("num_el_blk", len(blocks))
        ds.createDimension("num_side_sets", len(sidesets))
        ds.createVariable("time_whole", "f8", ("time_step",))
        v = ds.createVariable("coordx", "f8", ("num_nodes",))
        v[:] = xy[:, 0]
        v = ds.createVariable("coordy", "f8", ("num_nodes",))
        v[:] = xy[:, 1]
        v = ds.createVariable("coor_names", "S1", ("num_dim", "len_name"))
        v[:] = _chars(["x", "y"])
        v = ds.createVariable("eb_status", "i4", ("num_el_blk",))
        v[:] = 1
        v = ds.createVariable("eb_prop1", "i4", ("num_el_blk",))
        v.setncattr("name", "ID")
        v[:] = np.arange(1, len(blocks) + 1)
        v = ds.createVariable("eb_names", "S1", ("num_el_blk", "len_name"))
        v[:] = _chars([b[0] for b in blocks])
        for k, (name, etype, conn) in enumerate(blocks, 1):
            conn = np.asarray(conn, dtype=np.int64)
            ds.createDimension(f"num_el_in_blk{k}", conn.shape[0])
            ds.createDimension(f"num_nod_per_el{k}", conn.shape[1])
            v = ds.createVariable(f"connect{k}", "i4", (f"num_el_in_blk{k}", f"num_nod_per_el{k}"))
            v.setncattr("elem_type", etype)
            v[:] = conn + 1
        if sidesets:
            v = ds.createVariable("ss_status", "i4", ("num_side_sets",))
            v[:] = 1
            v = ds.createVariable("ss_prop1", "i4", ("num_side_sets",))
            v.setncattr("name", "ID")
            v[:] = np.arange(1, len(sidesets) + 1)
            v = ds.createVariable("ss_names", "S1", ("num_side_sets", "len_name"))
            v[:] = _chars([s[0] for s in sidesets])
            for k, (name, elems, sides) in enumerate(sidesets, 1):
                ds.createDimension(f"num_side_ss{k}", len(elems))
                v = ds.createVariable(f"elem_ss{k}", "i4", (f"num_side_ss{k}",))
                v[:] = np.asarray(elems)
                v = ds.createVariable(f"side_ss{k}", "i4", (f"num_side_ss{k}",))
                v[:] = np.asarray(sides)
        ds.createDimension("num_qa_rec", 1)
        v = ds.createVariable("qa_records", "S1", ("num_qa_rec", "four", "len_string"))
        v[0] = _chars(["gf180tcad", "1", "", ""], 33)
    finally:
        ds.close()


STRIP_WIDTH_UM = 1.0  # the strip width (um) the 1D nodes are extruded to


def strip_mesh(x_um, layer_of_interval, layer_names, w_um=STRIP_WIDTH_UM, *, tri=False):
    """A 1D node list extruded into a strip of width w_um: (xy, blocks, sidesets).

    Node i of the 1D list is node 2*i (y = 0) and 2*i + 1 (y = w). Interval j between nodes j
    and j+1 is one QUAD4 (or two TRI3). Side set 'left' is the x = x[0] edge, 'right' x = x[-1].
    """
    n = len(x_um)
    xy = np.zeros((2 * n, 2))
    xy[0::2, 0] = x_um
    xy[1::2, 0] = x_um
    xy[1::2, 1] = w_um
    blocks = []
    eid = 0
    first = last = None
    for name in layer_names:
        js = [j for j in range(n - 1) if layer_of_interval[j] == name]
        conn = []
        for j in js:
            a, b, c, d = 2 * j, 2 * (j + 1), 2 * (j + 1) + 1, 2 * j + 1
            if tri:
                conn += [(a, b, c), (a, c, d)]
            else:
                conn.append((a, b, c, d))
        ids = list(range(eid + 1, eid + len(conn) + 1))
        if 0 in js:
            # left edge (nodes d-a) of the interval-0 element: QUAD4 side 4; TRI3 (a,c,d) side 3
            first = (ids[js.index(0) * (2 if tri else 1) + (1 if tri else 0)], 3 if tri else 4)
        if n - 2 in js:
            # right edge (b-c): QUAD4 side 2; TRI3 (a,b,c) side 2
            last = (ids[js.index(n - 2) * (2 if tri else 1)], 2)
        eid += len(conn)
        blocks.append((name, "TRI3" if tri else "QUAD4", np.array(conn)))
    sidesets = [("left", [first[0]], [first[1]]), ("right", [last[0]], [last[1]])]
    return xy, blocks, sidesets


def stack_strip(stack, w_um=STRIP_WIDTH_UM, *, tri=False):
    """The strip of a Stack1D: blocks named as layers, side sets named as the two contacts."""
    xs, bnodes = stack.node_positions_um()
    layer_of = []
    for i, layer in enumerate(stack.layers):
        layer_of += [layer.name] * (bnodes[i + 1] - bnodes[i])
    xy, blocks, ss = strip_mesh(xs, layer_of, [l.name for l in stack.layers], w_um, tri=tri)
    ends = stack.contact_ends()
    names = {v: k for k, v in ends.items()}
    ss = [(names[0], *ss[0][1:]), (names[len(stack.layers)], *ss[1][1:])]
    return np.array(xs), xy, blocks, ss


# --------------------------------------------------------------------------------------------
# Running Charon
# --------------------------------------------------------------------------------------------


def run(inp: str, *, current=True, log=None, timeout=3600):
    """charonInterpreter.py -i inp (writes inp.xml), then charon_mp.exe --i=inp.xml [--current]."""
    Path("currents-loca.dat").unlink(missing_ok=True)
    t0 = time.time()
    r = subprocess.run(  # the interpreter exit code is checked below
        check=False,
        args=["python3", "-W", "ignore", INTERP, "-i", inp],
        capture_output=True,
        text=True,
    )
    out = r.stdout + r.stderr
    if r.returncode != 0 or not Path(inp + ".xml").exists():
        raise RuntimeError(f"interpreter failed ({r.returncode}):\n{out}")
    cmd = [CHARON, f"--i={inp}.xml"] + (["--current"] if current else [])
    r = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
    out = r.stdout + r.stderr
    Path(log or (inp + ".log")).write_text(out)
    ok = "Charon run completed." in out
    return ok, out, time.time() - t0


# --------------------------------------------------------------------------------------------
# Reading Exodus states
# --------------------------------------------------------------------------------------------


def _names(var):
    a = var[:]
    return ["".join(c.decode() for c in row if c) for row in a]


@dataclass
class States:
    x: np.ndarray
    y: np.ndarray
    times: np.ndarray
    nodal: dict  # name -> (T, N)
    blocks: dict  # name -> conn (0-based)
    globals_: dict


def read_states(path) -> States:
    ds = netCDF4.Dataset(path)
    ds.set_auto_mask(False)
    try:
        if "coordx" in ds.variables:
            x = ds["coordx"][:]
            y = ds["coordy"][:]
        else:
            x, y = ds["coord"][0], ds["coord"][1]
        times = ds["time_whole"][:] if "time_whole" in ds.variables else np.zeros(0)
        nodal = {}
        if "name_nod_var" in ds.variables:
            for k, n in enumerate(_names(ds["name_nod_var"]), 1):
                if f"vals_nod_var{k}" in ds.variables:
                    nodal[n] = ds[f"vals_nod_var{k}"][:]
                elif "vals_nod_var" in ds.variables:
                    nodal[n] = ds["vals_nod_var"][:, k - 1, :]
        blocks = {}
        bnames = _names(ds["eb_names"]) if "eb_names" in ds.variables else []
        for k, n in enumerate(bnames, 1):
            blocks[n] = ds[f"connect{k}"][:] - 1
        gl = {}
        if "name_glo_var" in ds.variables:
            for k, n in enumerate(_names(ds["name_glo_var"])):
                gl[n] = ds["vals_glo_var"][:, k]
        return States(x, y, times, nodal, blocks, gl)
    finally:
        ds.close()


def read_currents(path):
    """currents-loca.dat: (header names, rows)."""
    lines = Path(path).read_text().splitlines()
    head = lines[0].split()
    rows = [[float(v) for v in l.split()] for l in lines[1:] if l.strip()]
    return head, np.array(rows)


# --------------------------------------------------------------------------------------------
# Charge extraction on the strip
# --------------------------------------------------------------------------------------------


def oxide_flux_charge(st: States, k: int, x_nodes, ox_lo, ox_hi, eps_ox, eps0, *, w_um=1.0):
    """Gate charge per area (C/cm^2) at state k from the oxide potential drop of the strip.

    On the strip the CVFEM/FEM Laplace flux through the oxide is eps*(psi(lo)-psi(hi))/t_ox on
    every oxide element when psi is linear across x; we return the flux at both oxide faces
    (from the first and the last oxide interval) to check conservation.
    """
    psi = st.nodal["ELECTRIC_POTENTIAL"][k]
    # node index 2*i is the y=0 node of 1D node i
    p = psi[0::2]
    x = np.asarray(x_nodes) * 1e-4  # cm
    f_lo = eps_ox * eps0 * (p[ox_lo] - p[ox_lo + 1]) / (x[ox_lo + 1] - x[ox_lo])
    f_hi = eps_ox * eps0 * (p[ox_hi - 1] - p[ox_hi]) / (x[ox_hi] - x[ox_hi - 1])
    return f_lo, f_hi


# --------------------------------------------------------------------------------------------
# gmsh MSH 2.2 (ASCII) to Exodus parts
# --------------------------------------------------------------------------------------------


def read_msh22(path):
    """Nodes (tag -> (x, y)), physical names ((dim, tag) -> name), elements (type, phys, nodes)."""
    lines = Path(path).read_text().splitlines()
    i = 0
    nodes, phys, elems = {}, {}, []
    fmt = None
    while i < len(lines):
        s = lines[i].strip()
        if s == "$MeshFormat":
            fmt = lines[i + 1].split()[0]
            i += 2
        elif s == "$PhysicalNames":
            n = int(lines[i + 1])
            for line in lines[i + 2 : i + 2 + n]:
                d, t, name = line.split(maxsplit=2)
                phys[(int(d), int(t))] = name.strip('"')
            i += 2 + n
        elif s == "$Nodes":
            n = int(lines[i + 1])
            for line in lines[i + 2 : i + 2 + n]:
                f = line.split()
                nodes[int(f[0])] = (float(f[1]), float(f[2]))
            i += 2 + n
        elif s == "$Elements":
            n = int(lines[i + 1])
            for line in lines[i + 2 : i + 2 + n]:
                f = [int(v) for v in line.split()]
                etype, ntags = f[1], f[2]
                tags = f[3 : 3 + ntags]
                elems.append((etype, tags[0], f[3 + ntags :]))
            i += 2 + n
        else:
            i += 1
    if fmt != "2.2":
        raise ValueError(f"MSH format {fmt}, want 2.2")
    return {
        "nodes": nodes,
        "physical": {f"{d}:{t}": n for (d, t), n in phys.items()},
        "phys": phys,
        "elems": elems,
    }


TRI_SIDES = {(0, 1): 1, (1, 2): 2, (2, 0): 3}


def msh_to_exodus_parts(m, *, regions, contacts):
    """TRI3 blocks per region (in `regions` order) and side sets per contact.

    contacts: {side set name: (electrode region, semiconductor region)}; the contact line is the
    gmsh physical line named electrode___region (or region___electrode). Nodes used by no block
    are dropped; the rest keep their gmsh order.
    """
    phys = m["phys"]
    by_name = {}
    for (d, t), n in phys.items():
        by_name.setdefault((d, n), t)
    tris = {r: [] for r in regions}
    for etype, ptag, ns in m["elems"]:
        if etype == 2:
            name = phys.get((2, ptag))
            if name in tris:
                tris[name].append(ns)
    used = sorted({n for r in regions for t in tris[r] for n in t})
    index = {tag: k for k, tag in enumerate(used)}
    xy = np.array([m["nodes"][t] for t in used])
    blocks, eid0, elem_ids = [], 0, {}
    for r in regions:
        conn = np.array([[index[n] for n in t] for t in tris[r]])
        # orient counter-clockwise
        p = xy[conn]
        area = (p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1]) - (p[:, 2, 0] - p[:, 0, 0]) * (
            p[:, 1, 1] - p[:, 0, 1]
        )
        flip = area < 0
        conn[flip] = conn[flip][:, [0, 2, 1]]
        for k, tri in enumerate(conn):
            elem_ids.setdefault(r, []).append((eid0 + k + 1, tuple(tri)))
        eid0 += len(conn)
        blocks.append((r, "TRI3", conn))
    sidesets = []
    info = {
        "nodes": len(xy),
        "triangles": {r: len(tris[r]) for r in regions},
        "dropped_nodes": len(m["nodes"]) - len(used),
        "contacts": {},
    }
    for ss_name, (electrode, region) in contacts.items():
        names = {f"{electrode}___{region}", f"{region}___{electrode}"}
        segs = [ns for etype, ptag, ns in m["elems"] if etype == 1 and phys.get((1, ptag)) in names]
        lookup = {}
        for eid, tri in elem_ids[region]:
            for (a, b), side in TRI_SIDES.items():
                lookup[frozenset((tri[a], tri[b]))] = (eid, side)
        el, sd = [], []
        for a, b in segs:
            eid, side = lookup[frozenset((index[a], index[b]))]
            el.append(eid)
            sd.append(side)
        sidesets.append((ss_name, el, sd))
        info["contacts"][ss_name] = len(el)
    return xy, blocks, sidesets, info


def truncate_grid(job, vgmax=None, vgmin=None):
    """Keep only the leading grid points with vg <= vgmax and vg >= vgmin (env CX_VGMAX and
    CX_VGMIN when None). The nfet grid ascends, so CX_VGMAX cuts its end; the pfet grid descends
    from +5 V, so CX_VGMIN cuts its end."""
    if vgmax is None:
        v = os.environ.get("CX_VGMAX")
        vgmax = float(v) if v else None
    if vgmin is None:
        v = os.environ.get("CX_VGMIN")
        vgmin = float(v) if v else None
    k = 0
    for v in job.vg:
        if (vgmax is not None and v > vgmax + 1e-12) or (vgmin is not None and v < vgmin - 1e-12):
            break
        k += 1
    job.vg, job.c_devsim = job.vg[:k], job.c_devsim[:k]
    return job
