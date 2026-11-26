# SPDX-License-Identifier: Apache-2.0
"""Charon input decks for the junction cross-sections of structure.py.

Pure Python, no simulator needed. A deck is the text charonInterpreter.py turns into the
XML charon_mp.exe reads. Three stages share one description of the device:

  "nlp"    nonlinear Poisson at equilibrium, from the mesh file
  "dd0"    drift-diffusion at 0 V, started from the nlp result
  "sweep"  drift-diffusion with avalanche, the well contact swept by LOCA continuation,
           started from the dd0 result (or from one plane of an earlier sweep)

The device description (see describe_params and describe_diode):

  blocks    [(element block, "Si" or "Oxide")]
  doping    list of analytic profiles in micrometres:
              {"kind": "uniform", "type", "value"[, "ymin", "ymax"]}
              {"kind": "box", "type", "peak", "x0", "x1", "sx", "rp", "sy"}
  ohmic     {"well": block, "sub": block}; the well is the swept contact
  plates    {name: (block, "well" or "sub")} fixed-potential boundaries on the oxide

Lengths in a deck are micrometres, concentrations cm^-3, as Charon expects.
"""

from __future__ import annotations

import math

import ionize

# The same constants dd.py gives DEVSIM.
EPS_SI, EPS_OX = 11.7, 3.9
NI = 1.0e10
MU_N, MU_P = 1000.0, 400.0
TAU_N, TAU_P = 1.0e-5, 1.0e-5
# Lifetime the sweep uses unless told otherwise. Charon works in double precision; with
# DEVSIM's 1e-5 s the generation current and the depleted-region densities (1e-18 of the
# doping) are below what its Newton solve resolves, and the sweep then wanders between
# spurious solutions with negative densities. 1e-9 s raises the leakage 1e4 times. The
# breakdown voltage does not depend on the size of the current that is multiplied.
SEED_TAU = 1.0e-9
T = 300.0

# The plate work function is Charon's reference energy, so that a plate at bias V sits at
# potential V on DEVSIM's scale (potential zero where the silicon is intrinsic). The
# reference is the intrinsic level of Charon's default silicon: affinity 4.17 eV plus half
# the 1.12 eV gap, less 7.198 mV; the last figure is measured (a plate given 4.73 eV
# came out at V - 7.198 mV).
PLATE_WORK_FUNCTION = 4.17 + 0.5 * 1.12 - 0.007198

AVALANCHE_MIN_FIELD = 1.0e4  # V/cm; below it Charon sets alpha to zero
WORKSET = 500  # elements assembled together


def describe_params(p, blocks):
    """Device description of a structure.py parameter dictionary.

    blocks: [(name, material)] as the mesh dump lists them. The doping repeats
    structure.net_doping_expr term by term: uniform acceptors, then one box per well
    (donors) and per pfield entry (acceptors).
    """
    doping = [{"kind": "uniform", "type": "acceptor", "value": p["sub"]}]
    for w in p["wells"]:
        doping.append({"kind": "box", "type": "donor", **_box(w)})
    for w in p.get("pfield", []):
        doping.append({"kind": "box", "type": "acceptor", **_box(w)})
    plates = {f"plate{k}": ("ox", pl["tie"]) for k, pl in enumerate(p.get("plates", []))}
    return {"blocks": [tuple(b) for b in blocks], "doping": doping,
            "ohmic": {"well": "si", "sub": "si"}, "plates": plates}  # fmt: skip


def _box(w):
    return {k: w[k] for k in ("peak", "x0", "x1", "sx", "rp", "sy")}


def describe_diode(na, nd=1e19, xj_um=0.5, length_um=8.0):
    """The abrupt N+/P strip of charon_mesh.dump_diode: donors above xj, acceptors below."""
    # Charon's ranges include their ends. The donors stop just short of xj so that the node
    # at xj is P, as DEVSIM's "y < xj" makes it.
    doping = [
        {"kind": "uniform", "type": "donor", "value": nd, "ymin": -1.0, "ymax": xj_um - 1e-6},
        {"kind": "uniform", "type": "acceptor", "value": na, "ymin": xj_um - 1e-7,
         "ymax": length_um + 1.0},
    ]
    return {"blocks": [("si", "Si")], "doping": doping,
            "ohmic": {"well": "si", "sub": "si"}, "plates": {}}  # fmt: skip


def net_doping(dev, x_um, y_um):
    """Donors minus acceptors (cm^-3) of the description at points in micrometres.

    The formula the deck asks Charon for, in numpy, to compare with Charon's output and
    with DEVSIM's NetDoping.
    """
    import numpy as np
    from scipy.special import erfc

    x, y = np.asarray(x_um, dtype=float), np.asarray(y_um, dtype=float)
    net = np.zeros(np.broadcast(x, y).shape)
    for f in dev["doping"]:
        sign = 1.0 if f["type"] == "donor" else -1.0
        if f["kind"] == "uniform":
            inside = (y >= f.get("ymin", -math.inf)) & (y <= f.get("ymax", math.inf))
            net = net + sign * f["value"] * inside
        else:
            wx = math.sqrt(2.0) * f["sx"]
            lateral = 0.5 * (erfc((x - f["x1"]) / wx) - erfc((x - f["x0"]) / wx))
            net = net + sign * f["peak"] * np.exp(-0.5 * ((y - f["rp"]) / f["sy"]) ** 2) * lateral
    return net


def _doping_lines(dev):
    """Uniform functions, and MGauss functions for the boxes.

    Charon's MGauss along an axis with "erfc" is 0.5*(erfc((x-max)/w) - erfc((x-min)/w)),
    and without it exp(-((y-max)/w)^2) beyond the range [min, max]. With w = sqrt(2)*sigma
    and min = max = rp in y this is the expression of structure._gauss_box.
    """
    out = []
    for k, f in enumerate(dev["doping"]):
        if f["kind"] == "uniform":
            out += [f"  start uniform doping named Function{k}",
                    f"    type is {f['type']}",
                    f"    concentration = {f['value']:.17g}"]  # fmt: skip
            if "ymin" in f:
                out.append(f"    spatial range is {f['ymin']:.17g} to {f['ymax']:.17g} in y")
            out.append("  end uniform doping")
        else:
            wx, wy = math.sqrt(2.0) * f["sx"], math.sqrt(2.0) * f["sy"]
            out += [f"  start mgauss doping named Function{k}",
                    f"    type is {f['type']}",
                    f"    concentration range is 0.0 to {f['peak']:.17g}",
                    "    erfc in x",
                    f"    spatial range is {f['x0']:.17g} to {f['x1']:.17g} in x",
                    f"    gradient width = {wx:.17g} in x",
                    f"    spatial range is {f['rp']:.17g} to {f['rp']:.17g} in y",
                    f"    gradient width = {wy:.17g} in y",
                    "  end mgauss doping"]  # fmt: skip
    return out


def _avalanche_lines(scheme):
    """Impact ionisation with the coefficients of ionize.py, set explicitly.

    The finite-element schemes take Charon's van Overstraeten model, which has the two
    field ranges of ionize.py. The control-volume scheme has no such model; it takes
    Selberherr's, alpha = a0*exp(-(E0/F)^delta), with delta = 1 and a fixed critical
    field: the same electron coefficient, and for holes the low-field branch at every
    field (above 4e5 V/cm it is larger than ionize.alpha_p).
    """
    if scheme == "cvfem":
        return [
            "  start avalanche generation",
            "    threshold behavior model is selberherr",
            "    driving force is gradient potential J",
            f"    minimum field = {AVALANCHE_MIN_FIELD:g}",
            "    start selberherr parameters",
            "      critical field is fixed",
            f"      electron a0 = {ionize.AN:g}",
            "      electron a1 = 0.0",
            "      electron a2 = 0.0",
            "      electron delta = 1.0",
            f"      electron E0 = {ionize.BN:g}",
            f"      hole a0 = {ionize.AP_LO:g}",
            "      hole a1 = 0.0",
            "      hole a2 = 0.0",
            "      hole delta = 1.0",
            f"      hole E0 = {ionize.BP_LO:g}",
            "    end selberherr parameters",
            "  end avalanche generation",
        ]
    return [
        "  start avalanche generation",
        "    threshold behavior model is van overstraeten",
        "    driving force is gradient potential J",
        f"    minimum field = {AVALANCHE_MIN_FIELD:g}",
        "    start van overstraeten parameters",
        f"      electron alow = {ionize.AN:g}",
        f"      electron blow = {ionize.BN:g}",
        f"      electron ahigh = {ionize.AN:g}",
        f"      electron bhigh = {ionize.BN:g}",
        f"      electron E0 = {ionize.E_SWITCH:g}",
        f"      hole alow = {ionize.AP_LO:g}",
        f"      hole blow = {ionize.BP_LO:g}",
        f"      hole ahigh = {ionize.AP_HI:g}",
        f"      hole bhigh = {ionize.BP_HI:g}",
        f"      hole E0 = {ionize.E_SWITCH:g}",
        "    end van overstraeten parameters",
        "  end avalanche generation",
    ]


def _silicon_material(dev, stage, scheme, tau):
    out = ["start Material Block siliconParameter",
           "  material name is Silicon",
           f"  relative permittivity = {EPS_SI}",
           f"  constant intrinsic concentration = {NI:g}"]  # fmt: skip
    if stage != "nlp":
        out += [f"  fixed mobility for electrons is {MU_N}",
                f"  fixed mobility for holes is {MU_P}",
                "  start carrier lifetime block",
                f"    electron lifetime is constant = {tau:g}",
                f"    hole lifetime is constant = {tau:g}",
                "  end carrier lifetime block"]  # fmt: skip
    if stage == "sweep":
        out += _avalanche_lines(scheme)
    return out + _doping_lines(dev) + ["end Material Block siliconParameter", ""]


# Discretisations: (nonlinear Poisson, drift-diffusion, Laplace in the oxide). Charon's
# van Overstraeten model exists for the finite-element schemes only; the Scharfetter-
# Gummel control-volume scheme ("cvfem") offers Selberherr and Crowell-Sze.
SCHEMES = {
    "effpg": ("nlp gfem", "drift diffusion effpg", "laplace gfem"),
    "supg": ("nlp gfem", "drift diffusion gfem", "laplace gfem"),
    "cvfem": ("nlp cvfem", "drift diffusion cvfem", "laplace cvfem"),
}


def _physics(dev, stage, avalanche, scheme):
    nlp, dd, laplace = SCHEMES[scheme]
    kind = nlp if stage == "nlp" else dd
    out = []
    for name, material in dev["blocks"]:
        out.append(f"start Physics Block {name}Physics")
        out.append(f"  geometry block is {name}")
        if material == "Si":
            out += [f"  standard discretization type is {kind}",
                    "  material model is siliconParameter"]  # fmt: skip
            if stage != "nlp":
                out.append("  srh recombination is on")
            if stage == "sweep" and avalanche:
                out += ["  avalanche is on", "  driving force is gradient potential"]
        else:
            out += [f"  standard discretization type is {laplace}",
                    "  material model is oxideParameter"]  # fmt: skip
        out += [f"end Physics Block {name}Physics", ""]
    return out


def _initial(dev, stage):
    out = []
    for name, material in dev["blocks"]:
        if stage == "nlp":
            how = "equilibrium potential" if material == "Si" else "uninitialized"
            out.append(f"initial conditions for ELECTRIC_POTENTIAL in {name} is {how}")
            continue
        out.append(f"initial conditions for ELECTRIC_POTENTIAL in {name} is exodus file")
        if material == "Si":
            how = "equilibrium density" if stage == "dd0" else "exodus file"
            out += [f"initial conditions for ELECTRON_DENSITY in {name} is {how}",
                    f"initial conditions for HOLE_DENSITY in {name} is {how}"]  # fmt: skip
    return out + [""]


def _boundaries(dev, stage, v0, v1):
    """Ohmic contacts on the silicon, plates as contacts on the insulator.

    In the sweep the well and every plate tied to it take the same LOCA parameter.
    """
    work = PLATE_WORK_FUNCTION
    swept = f"swept from {v0:.10g} to {v1:.10g}" if stage == "sweep" else "fixed at 0"
    out = [f"BC is ohmic for well on {dev['ohmic']['well']} {swept}",
           f"BC is ohmic for sub on {dev['ohmic']['sub']} fixed at 0"]  # fmt: skip
    for name, (block, tie) in dev["plates"].items():
        how = swept if tie == "well" else "fixed at 0"
        out.append(f"BC is contact on insulator for {name} on {block} "
                   f"with work function {work:.7g} {how}")
    return out + [""]


NEWTON = "Charon->Solution Control->NOX->Direction->Newton"
STRATIMIKOS = NEWTON + "->Stratimikos Linear Solver->Stratimikos"

# Newton stops when the scaled residual norm is below RESIDUAL_TOL and the weighted update
# norm (update / (REL_TOL*|x| + ABS_TOL), root mean square) is below 1. Densities are in
# units of the concentration scaling; in a depleted region they are about 1e-14 with the
# seed lifetime, so the absolute tolerance sits far below Charon's default of 1e-14. With
# that default the densities there are never tested and the sweep leaves the physical
# solution; with 1e-26 the test never passes (round-off).
RESIDUAL_TOL, REL_TOL, ABS_TOL = 1.0e-9, 1.0e-4, 1.0e-18
MAX_NEWTON = 20
# NOX by default carries on after a Newton step whose linear solve failed. Switched off,
# such a step aborts charon_mp.exe, so the sweep cannot halve its step and ends there (a
# 4 V first step on the 2D case did this). Left on: a bias point still counts only when
# the residual norm, evaluated after the step, passes RESIDUAL_TOL.
RESCUE_BAD_NEWTON_SOLVE = True


def _solver(stage, step, min_step, max_steps, tol):
    """Solver settings. The linear solver is the direct one (Amesos2, KLU2): the default
    GMRES with its 1e-6 tolerance leaves the depleted-region densities as noise."""
    out = []
    residual_tol, rel_tol, abs_tol = tol
    if stage == "sweep":
        out += ["start sweep options",
                "  continuation method is natural",
                "  predictor method is constant",
                f"  initial step size = {step:g}",
                f"  maximum step size = {step:g}",
                f"  minimum step size = {min_step:g}",
                "  step size aggressiveness = 0.5",
                "  failed step reduction factor = 0.5",
                "  successful step increase factor = 2.0",
                f"  maximum number of steps = {max_steps}",
                "end sweep options", ""]  # fmt: skip
    problem = "parameter sweep" if stage == "sweep" else "steady state"
    out += ["start solver block",
            "  start tpetra block",
            f"    problem type is {problem}",
            "    verbosity level is high",
            f"    nonlinear solver residual tolerance = {residual_tol:g}",
            f"    maximum number nonlinear iterations = {MAX_NEWTON}",
            "    start nonlinear solver wrms block",
            f"      absolute tolerance = {abs_tol:g}",
            f"      relative tolerance = {rel_tol:g}",
            "    end nonlinear solver wrms block",
            "  end tpetra block",
            "end solver block", "",
            f'direct input "{STRATIMIKOS},Linear Solver Type,string,Amesos2"',
            f'direct input "{STRATIMIKOS},Preconditioner Type,string,None"', ""]  # fmt: skip
    if not RESCUE_BAD_NEWTON_SOLVE:
        out += [f'direct input "{NEWTON},Rescue Bad Newton Solve,bool,false"', ""]
    return out


def deck(dev, stage, state_in, state_out, v0=0.0, v1=0.0, step=1.0, min_step=1e-3,
         max_steps=1000, avalanche=True, index=None, currents="currents.dat", extra=(),
         scheme="cvfem", tol=None, tau=SEED_TAU):  # fmt: skip
    """Text of the deck of one stage. `extra`: more lines, e.g. "Direct input" overrides."""
    scale = max(f.get("value", f.get("peak", 0.0)) for f in dev["doping"])
    tol = tol if tol is not None else (RESIDUAL_TOL, REL_TOL, ABS_TOL)
    at = f" at index {index}" if index is not None else ""
    # Without this line Charon assembles one element at a time: minutes of set-up and
    # about 140 kB of memory per element.
    out = [f"import state file {state_in}{at}", "tpetra is on",
           f"assembly workset = {WORKSET}", "",
           "start output parameters",
           f"  output state file {state_out}"]  # fmt: skip
    if stage == "sweep":
        out.append(f"  output tabulated parameter currents to {currents}")
    out += ["end output parameters", "",
            f"concentration scaling = {scale:g}",
            f"lattice temperature = {T}", ""]  # fmt: skip
    out += _physics(dev, stage, avalanche, scheme)
    out += _silicon_material(dev, stage, scheme, tau)
    if any(m != "Si" for _, m in dev["blocks"]):
        out += ["start Material Block oxideParameter", "  material name is SiO2",
                f"  relative permittivity = {EPS_OX}",
                "end Material Block oxideParameter", ""]  # fmt: skip
    out += _initial(dev, stage)
    out += _boundaries(dev, stage, v0, v1)
    out += _solver(stage, step, min_step, max_steps, tol)
    out += list(extra)
    return "\n".join(out) + "\n"
