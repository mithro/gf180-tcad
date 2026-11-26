# SPDX-License-Identifier: Apache-2.0
"""Carry a DEVSIM mesh into Charon: dump it from DEVSIM, write it as Exodus II.

    python charon_mesh.py dump PARAMS.json MESH.npz        (DEVSIM image)
    python charon_mesh.py diode NA LENGTH_UM MESH.npz      (DEVSIM image)
    python charon_mesh.py exodus MESH.npz MESH.exo [--quads]   (Charon image, has netCDF4)

`dump` builds the device with structure.build(p); `diode` builds a narrow strip with the
node spacing of diode1d.py along y. Both store, per region, the node coordinates in cm
exactly as DEVSIM holds them, the triangles, and per contact the boundary edges.

`exodus` writes one TRI3 element block per meshed region (the conductor "plate" regions
are holes: DEVSIM meshes them, Charon gets no elements there; insulator blocks are named
"ins_" + region, see block_name), merges the interface nodes
DEVSIM duplicates per region, and writes one side set per contact. Charon works in
micrometres, so coordinates are multiplied by 1e4. Next to MESH.exo it writes
MESH.exo.map.npz: for every region the global (0-based) Exodus node of each DEVSIM node,
so that a Charon field can be put back on DEVSIM's nodes in DEVSIM's order.
"""

from __future__ import annotations

import json
import sys

import numpy as np

CM_TO_UM = 1.0e4
SKIP_MATERIALS = ("metal",)  # conductor regions: boundaries only, no elements


def block_name(region, material):
    """Exodus element block of a DEVSIM region.

    Charon sets the initial potential block by block in the order of the block names, and
    a node shared by two blocks keeps the last value. The silicon ("si") must come after
    every insulator: a trench block named "sti0" would overwrite the equilibrium potential
    of the silicon on the trench walls with 0, and with 1e20 doping there the first Newton
    step of the equilibrium solve is 1e10 kT/q and the residual overflows.
    """
    return region if material == "Si" else "ins_" + region


def dump_device(device, contacts, path, extra=None):
    """Store the mesh of a DEVSIM device. contacts: {name: region}."""
    import devsim as ds

    out, meta = {}, {"regions": [], "contacts": dict(contacts), "extra": extra or {}}
    for region in ds.get_region_list(device=device):
        material = ds.get_material(device=device, region=region)
        if material in SKIP_MATERIALS:
            continue
        meta["regions"].append([region, material])
        x = ds.get_node_model_values(device=device, region=region, name="x")
        y = ds.get_node_model_values(device=device, region=region, name="y")
        out[f"xy_{region}"] = np.stack([np.array(x), np.array(y)], axis=1)
        tri = np.array(ds.get_element_node_list(device=device, region=region), dtype=np.int64)
        out[f"tri_{region}"] = tri.reshape(-1, 3)
    for name, region in contacts.items():
        edges = ds.get_element_node_list(device=device, region=region, contact=name)
        out[f"contact_{name}"] = np.array(edges, dtype=np.int64).reshape(-1, 2)
    np.savez_compressed(path, meta=json.dumps(meta), **out)
    return meta


def dump_params(p, path):
    """Build the cross-section of structure.py and dump its mesh."""
    import structure

    names = structure.build(p)
    contacts = {**names["si_contacts"], **names["ox_contacts"]}
    return dump_device(names["device"], contacts, path, extra={"params": p})


def diode_lines(length_um, xj_um=0.5):
    """Mesh lines {pos_cm: spacing_cm} along the diode, the ones diode1d.py uses."""
    length = length_um * 1e-4
    return {0.0: 5e-7, xj_um * 1e-4: 1e-7, length: length / 400}


def dump_diode(na, length_um, path, width_um=0.1, xj_um=0.5):
    """A strip `width_um` wide, uniform along x, N+ (1e19) above y = xj and P (na) below.

    Contacts: "well" on the N+ end (y = 0), "sub" on the P end (y = length).
    """
    import devsim as ds

    mesh, dev, w = "strip_mesh", "strip", width_um * 1e-4
    ds.create_2d_mesh(mesh=mesh)
    for pos in (0.0, w):
        ds.add_2d_mesh_line(mesh=mesh, dir="x", pos=pos, ps=w / 2)
    lines = diode_lines(length_um, xj_um)
    for pos, ps in sorted(lines.items()):
        ds.add_2d_mesh_line(mesh=mesh, dir="y", pos=pos, ps=ps)
    length = max(lines)
    # DEVSIM finds contact nodes only where the region meets another one: pad both ends
    # with a conductor region, which the dump leaves out.
    pad = 1e-6
    for pos in (-pad, length + pad):
        ds.add_2d_mesh_line(mesh=mesh, dir="y", pos=pos, ps=pad)
    ds.add_2d_region(mesh=mesh, material="Si", region="si", xl=0, xh=w, yl=0, yh=length)
    ds.add_2d_region(mesh=mesh, material="metal", region="pad0", xl=0, xh=w, yl=-pad, yh=0)
    ds.add_2d_region(mesh=mesh, material="metal", region="pad1", xl=0, xh=w,
                     yl=length, yh=length + pad)  # fmt: skip
    eps = 1e-10
    ds.add_2d_contact(mesh=mesh, name="well", region="si", material="metal",
                      xl=0, xh=w, yl=-eps, yh=eps, bloat=eps)  # fmt: skip
    ds.add_2d_contact(mesh=mesh, name="sub", region="si", material="metal",
                      xl=0, xh=w, yl=length - eps, yh=length + eps, bloat=eps)  # fmt: skip
    ds.finalize_mesh(mesh=mesh)
    ds.create_device(mesh=mesh, device=dev)
    extra = {"diode": {"na": na, "nd": 1e19, "xj_um": xj_um, "length_um": length_um,
                       "width_um": width_um}}  # fmt: skip
    return dump_device(dev, {"well": "si", "sub": "si"}, path, extra=extra)


def load_dump(path):
    """Returns (meta, arrays) of a dump written by dump_device."""
    z = np.load(path)
    return json.loads(str(z["meta"])), {k: z[k] for k in z.files if k != "meta"}


def _anticlockwise(xy, tri, region):
    """Triangles with positive area in the (x, y) plane, as Exodus wants them."""
    a, b, c = xy[tri[:, 0]], xy[tri[:, 1]], xy[tri[:, 2]]
    area2 = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    if np.any(area2 == 0.0):
        raise ValueError(f"degenerate triangle in region {region}")
    tri = tri.copy()
    flip = area2 < 0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return tri


def _quads(xy, tri, region, tol_cm):
    """The rectangles of the tensor grid that the triangles of one region cover.

    DEVSIM splits every grid cell into two triangles; each pair becomes one QUAD4,
    numbered anticlockwise in the (x, y) plane.
    """
    kx = np.round(xy[:, 0] / tol_cm).astype(np.int64)
    ky = np.round(xy[:, 1] / tol_cm).astype(np.int64)
    ux, uy = np.unique(kx), np.unique(ky)
    grid = np.full((len(ux), len(uy)), -1, dtype=np.int64)
    grid[np.searchsorted(ux, kx), np.searchsorted(uy, ky)] = np.arange(len(xy))
    cen = xy[tri].mean(axis=1) / tol_cm
    i = np.searchsorted(ux, cen[:, 0]) - 1
    j = np.searchsorted(uy, cen[:, 1]) - 1
    cells, count = np.unique(np.stack([i, j], axis=1), axis=0, return_counts=True)
    if np.any(count != 2):
        raise ValueError(f"region {region}: the triangles do not pair up into grid cells")
    i, j = cells[:, 0], cells[:, 1]
    quad = np.stack([grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1]], axis=1)
    if np.any(quad < 0):
        raise ValueError(f"region {region}: a grid cell has a corner without a node")
    return quad


def merge(meta, arrays, tol_cm=1e-11, quads=False):
    """Global numbering: nodes at the same position in different regions become one.

    Returns a dictionary with
      xy_cm        (N, 2) global node coordinates, cm
      blocks       [(name, material, connectivity, 0-based global, anticlockwise)];
                   (M, 3) triangles, or (M, 4) rectangles with quads=True
      node_map     {region: global node of each DEVSIM node}
      sides        {contact: (block index, element in block, side 0..)} arrays
    """
    regions = [r for r, _ in meta["regions"]]
    allxy = np.concatenate([arrays[f"xy_{r}"] for r in regions])
    key = np.round(allxy / tol_cm).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)
    # number global nodes in order of first appearance, so the first region keeps its order
    order = np.argsort(first)
    rank = np.empty(len(order), dtype=np.int64)
    rank[order] = np.arange(len(order))
    glob = rank[inverse]
    xy = allxy[first[order]]
    node_map, blocks, start = {}, [], 0
    for r, material in meta["regions"]:
        n = len(arrays[f"xy_{r}"])
        node_map[r] = glob[start : start + n]
        start += n
        tri = node_map[r][arrays[f"tri_{r}"]]
        conn = _quads(xy, tri, r, tol_cm) if quads else _anticlockwise(xy, tri, r)
        blocks.append((block_name(r, material), material, conn))
    sides = {}
    nn = len(xy)
    for name, region in meta["contacts"].items():
        bi = regions.index(region)
        tri = blocks[bi][2]
        edges = node_map[region][arrays[f"contact_{name}"]]
        lo, hi = np.minimum(edges[:, 0], edges[:, 1]), np.maximum(edges[:, 0], edges[:, 1])
        want = set((lo * nn + hi).tolist())
        elems, locs = [], []
        nper = tri.shape[1]
        for s in range(nper):
            n0, n1 = tri[:, s], tri[:, (s + 1) % nper]
            k = np.minimum(n0, n1) * nn + np.maximum(n0, n1)
            hit = np.nonzero(np.isin(k, np.fromiter(want, dtype=np.int64)))[0]
            elems.append(hit)
            locs.append(np.full(len(hit), s))
        elems, locs = np.concatenate(elems), np.concatenate(locs)
        if len(elems) != len(want):
            raise ValueError(f"contact {name}: {len(want)} edges but {len(elems)} element sides")
        sides[name] = (bi, elems, locs)
    return {"xy_cm": xy, "blocks": blocks, "node_map": node_map, "sides": sides}


def _put_names(ds_, var, dim, names):
    v = ds_.createVariable(var, "S1", (dim, "len_name"))
    for k, name in enumerate(names):
        row = np.zeros(33, dtype="S1")
        row[: len(name)] = list(name)
        v[k, :] = row


def write_exodus(m, path, title="hv-junction"):
    """Write the merged mesh `m` (see merge) as an Exodus II file in micrometres."""
    import netCDF4

    xy = m["xy_cm"] * CM_TO_UM
    blocks, sides = m["blocks"], m["sides"]
    d = netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET")
    d.setncatts({"api_version": np.float32(8.15), "version": np.float32(8.15),
                 "floating_point_word_size": np.int32(8), "file_size": np.int32(1),
                 "maximum_name_length": np.int32(32), "int64_status": np.int32(0),
                 "title": title})  # fmt: skip
    nelem = sum(len(b[2]) for b in blocks)
    for name, size in (("len_string", 33), ("len_line", 81), ("len_name", 33), ("four", 4),
                       ("num_dim", 2), ("num_nodes", len(xy)), ("num_elem", nelem),
                       ("num_el_blk", len(blocks)), ("num_side_sets", len(sides))):  # fmt: skip
        d.createDimension(name, size)
    d.createDimension("time_step", None)
    d.createVariable("time_whole", "f8", ("time_step",))
    d.createVariable("coordx", "f8", ("num_nodes",))[:] = xy[:, 0]
    d.createVariable("coordy", "f8", ("num_nodes",))[:] = xy[:, 1]
    _put_names(d, "coor_names", "num_dim", ["x", "y"])
    d.createVariable("node_num_map", "i4", ("num_nodes",))[:] = np.arange(1, len(xy) + 1)
    d.createVariable("elem_num_map", "i4", ("num_elem",))[:] = np.arange(1, nelem + 1)
    d.createVariable("eb_status", "i4", ("num_el_blk",))[:] = 1
    v = d.createVariable("eb_prop1", "i4", ("num_el_blk",))
    v.setncattr("name", "ID")
    v[:] = np.arange(1, len(blocks) + 1)
    _put_names(d, "eb_names", "num_el_blk", [b[0] for b in blocks])
    offsets = np.concatenate([[0], np.cumsum([len(b[2]) for b in blocks])])
    for k, (_, _, tri) in enumerate(blocks, start=1):
        d.createDimension(f"num_el_in_blk{k}", len(tri))
        d.createDimension(f"num_nod_per_el{k}", tri.shape[1])
        v = d.createVariable(f"connect{k}", "i4", (f"num_el_in_blk{k}", f"num_nod_per_el{k}"))
        v.setncattr("elem_type", "TRI3" if tri.shape[1] == 3 else "QUAD4")
        v[:] = tri + 1
    d.createVariable("ss_status", "i4", ("num_side_sets",))[:] = 1
    v = d.createVariable("ss_prop1", "i4", ("num_side_sets",))
    v.setncattr("name", "ID")
    v[:] = np.arange(1, len(sides) + 1)
    _put_names(d, "ss_names", "num_side_sets", list(sides))
    for k, (bi, elems, locs) in enumerate(sides.values(), start=1):
        d.createDimension(f"num_side_ss{k}", len(elems))
        d.createVariable(f"elem_ss{k}", "i4", (f"num_side_ss{k}",))[:] = elems + offsets[bi] + 1
        d.createVariable(f"side_ss{k}", "i4", (f"num_side_ss{k}",))[:] = locs + 1
    d.close()
    np.savez_compressed(path + ".map.npz", xy_cm=m["xy_cm"],
                        **{f"map_{r}": g for r, g in m["node_map"].items()})  # fmt: skip


def summary(meta, m):
    """Counts for the log: nodes, elements per block, sides per contact."""
    return {
        "nodes": len(m["xy_cm"]),
        "blocks": {b[0]: len(b[2]) for b in m["blocks"]},
        "region_nodes": {r: len(g) for r, g in m["node_map"].items()},
        "sides": {c: [meta["contacts"][c], len(s[1])] for c, s in m["sides"].items()},
    }


def main(argv):
    mode = argv[0]
    if mode == "dump":
        meta = dump_params(json.load(open(argv[1])), argv[2])
    elif mode == "diode":
        meta = dump_diode(float(argv[1]), float(argv[2]), argv[3])
    elif mode == "exodus":
        meta, arrays = load_dump(argv[1])
        m = merge(meta, arrays, quads="--quads" in argv)
        write_exodus(m, argv[2])
        print("MESH", json.dumps(summary(meta, m)), flush=True)
        return 0
    else:
        sys.exit(f"unknown mode {mode}")
    print("DUMP", json.dumps(meta["regions"]), json.dumps(meta["contacts"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
