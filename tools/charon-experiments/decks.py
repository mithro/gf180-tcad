"""Charon interpreter decks for the 1D/2D MOS capacitor experiments."""

from __future__ import annotations


def silicon_block(name, *, eps, dopant, conc, ni=None, nc_nv_eg=None, mun, mup, taun, taup,
                  affinity=4.05):
    """A Silicon material block with every model parameter set explicitly."""
    lines = [
        f"start Material Block {name}",
        "  material name is Silicon",
        f"  relative permittivity = {eps!r}",
        f"  electron affinity = {affinity!r}",
    ]
    if ni is not None:
        lines.append(f"  constant intrinsic concentration = {ni!r}")
    if nc_nv_eg is not None:
        nc, nv, eg = nc_nv_eg
        lines += [
            f"  constant bandgap = {eg!r}",
            "  start Effective DOS",
            f"    Nc300 = {nc!r}",
            f"    Nv300 = {nv!r}",
            "    Nc_F = 0.0",
            "    Nv_F = 0.0",
            "  end Effective DOS",
        ]
    lines += [
        f"  fixed mobility for electrons is {mun!r} holes is {mup!r}",
        "  start Carrier Lifetime Block",
        f"    electron lifetime is constant = {taun!r}",
        f"    hole lifetime is constant = {taup!r}",
        "  end Carrier Lifetime Block",
        f"  start uniform doping named Function1",
        f"    concentration = {conc!r}",
        f"    type is {dopant}",
        f"  end uniform doping named Function1",
        f"end Material Block {name}",
    ]
    return "\n".join(lines)


def oxide_block(name, eps):
    return "\n".join([
        f"start Material Block {name}",
        "  material name is SiO2",
        f"  relative permittivity = {eps!r}",
        f"end Material Block {name}",
    ])


def physics(block, disc, material, *, srh=True):
    lines = [
        f"start Physics Block {block}",
        f"  geometry block is {block}",
        f"  standard discretization type is {disc}",
        f"  material model is {material}",
    ]
    if srh:
        lines.append("  SRH Recombination is on")
    lines.append(f"end Physics Block {block}")
    return "\n".join(lines)


def solver(problem, *, rel=1e-10, abs_=1e-12, lin_tol=1e-12, maxit=50, linear="belos",
           extra=()):
    return "\n".join([
        "start solver block",
        "  start tpetra block",
        f"    problem type is {problem}",
        f"    linear solver is {linear}",
        f"    linear solver tolerance = {lin_tol!r}",
        f"    maximum number nonlinear iterations = {maxit}",
        "    verbosity level is high",
        *extra,
        "    start nonlinear solver wrms block",
        f"      relative tolerance = {rel!r}",
        f"      absolute tolerance = {abs_!r}",
        "    end nonlinear solver wrms block",
        "  end tpetra block",
        "end solver block",
    ])


def moscap_deck(job, *, mesh, out, disc="drift diffusion cvfem", ox_disc="laplace cvfem",
                gate_bc="fixed at 0.0", ni_mode="ni", problem="steady state", sweep=None,
                init="equilibrium", srh=True, rel=1e-10, abs_=1e-12, lin_tol=1e-12,
                linear="belos", extra_solver=(), import_index=None, extra=(),
                conc_scaling=None, nodal_out=None):
    """The 1D MOS capacitor deck of a Job1D (strip mesh file `mesh`)."""
    st = job.meta["stack"]
    c = job.meta["constants"]
    pol = st["polarity"]
    ni = c["n_i_cm3"]
    kw = dict(eps=c["eps_si"], mun=c["mu_n_cm2_per_vs"], mup=c["mu_p_cm2_per_vs"],
              taun=c["tau_n_s"], taup=c["tau_p_s"])
    if ni_mode == "ni":
        kw["ni"] = ni
    elif ni_mode == "dos":
        import math
        eg = 1.12
        vt = c["vt_v"]
        nc = ni * math.exp(eg / (2 * vt))
        kw["nc_nv_eg"] = (nc, nc, eg)
    elif ni_mode == "both":
        import math
        eg = 1.12
        vt = c["vt_v"]
        nc = ni * math.exp(eg / (2 * vt))
        kw["nc_nv_eg"] = (nc, nc, eg)
        kw["ni"] = ni
    gate_dop = "donor" if pol == "n" else "acceptor"
    body_dop = "acceptor" if pol == "n" else "donor"
    imp = f"Import State File {mesh}" + (f" at Index {import_index}" if import_index else "")
    lines = [
        imp,
        "tpetra is on",
        f"lattice temperature = {c['t_k']!r}",
    ]
    if conc_scaling:
        lines.append(f"concentration scaling = {conc_scaling!r}")
    lines += [
        "start output parameters",
        f"  Output State File {out}",
        "  Unscale Variables is on",
    ]
    if nodal_out:
        for blk, names in nodal_out:
            lines.append(f'  Output nodal variables in {blk} for "{names}"')
    lines += [
        "end output parameters",
        physics("gate_poly", disc, "polyParameter", srh=srh and "drift" in disc),
        physics("body", disc, "bodyParameter", srh=srh and "drift" in disc),
        physics("oxide", ox_disc, "oxideParameter", srh=False),
        silicon_block("polyParameter", dopant=gate_dop, conc=st["ngate_cm3"], **kw),
        silicon_block("bodyParameter", dopant=body_dop, conc=st["n_ch_cm3"], **kw),
        oxide_block("oxideParameter", st["eps_ox"]),
    ]
    if init == "equilibrium":
        for b in ("gate_poly", "body"):
            lines.append(f"initial conditions for ELECTRIC_POTENTIAL in {b} is equilibrium potential")
            if "drift" in disc:
                lines.append(f"initial conditions for ELECTRON_DENSITY in {b} is equilibrium density")
                lines.append(f"initial conditions for HOLE_DENSITY in {b} is equilibrium density")
        lines.append("initial conditions for ELECTRIC_POTENTIAL in oxide is uninitialized")
    elif init == "exodus":
        for b in ("gate_poly", "body"):
            lines.append(f"initial conditions for ELECTRIC_POTENTIAL in {b} is exodus file")
            if "drift" in disc:
                lines.append(f"initial conditions for ELECTRON_DENSITY in {b} is exodus file")
                lines.append(f"initial conditions for HOLE_DENSITY in {b} is exodus file")
        lines.append("initial conditions for ELECTRIC_POTENTIAL in oxide is exodus file")
    lines += [
        "BC is ohmic for body on body fixed at 0.0",
        f"BC is ohmic for gate on gate_poly {gate_bc}",
    ]
    if sweep:
        lines += ["start sweep options", *[f"  {s}" for s in sweep], "end sweep options"]
    lines += list(extra)
    lines.append(solver(problem, rel=rel, abs_=abs_, lin_tol=lin_tol, linear=linear,
                        extra=extra_solver))
    return "\n".join(lines) + "\n"
