"""DEVSIM drift-diffusion set-up for reverse-biased junctions with oxide and plates.

Runs inside the gf180-tcad DEVSIM image (see run.py). Lengths are in cm inside DEVSIM.
One silicon region carries the whole doping (wells and rings are doping only), so a
floating ring needs no contact: its potential comes from the carrier balance.
"""

from __future__ import annotations

import devsim as ds
from devsim.python_packages import model_create as mc
from devsim.python_packages import simple_physics as sp

Q = 1.602176634e-19
KB = 1.380649e-23
EPS0 = 8.8541878128e-14  # F/cm
EPS_SI = 11.7
EPS_OX = 3.9
NI = 1.0e10  # cm^-3 at 300 K
T = 300.0


def use_extended_precision(on=True):
    """128-bit floats. Reverse bias leaves minority densities far below 1e-16 of the doping."""
    for name in ("extended_solver", "extended_model", "extended_equation"):
        ds.set_parameter(name=name, value=on)


def silicon_parameters(device, region, taun=1e-5, taup=1e-5, mu_n=1000.0, mu_p=400.0):
    sp.SetSiliconParameters(device, region, T)
    put = lambda n, v: ds.set_parameter(device=device, region=region, name=n, value=v)
    put("Permittivity", EPS_SI * EPS0)
    put("ElectronCharge", Q)
    put("n_i", NI)
    put("kT", KB * T)
    put("V_t", KB * T / Q)
    put("mu_n", mu_n)
    put("mu_p", mu_p)
    put("taun", taun)
    put("taup", taup)


def oxide_parameters(device, region, eps_r=EPS_OX):
    ds.set_parameter(device=device, region=region, name="Permittivity", value=eps_r * EPS0)
    ds.set_parameter(device=device, region=region, name="ElectronCharge", value=Q)


def set_doping(device, region, net_doping_expr):
    """net_doping_expr: DEVSIM expression in x, y (cm) of donors minus acceptors, cm^-3."""
    mc.CreateNodeModel(device, region, "NetDoping", net_doping_expr)


def potential_only(device, si_regions, ox_regions, si_contacts, ox_contacts, interfaces):
    """Equilibrium Poisson solve; the starting point of the drift-diffusion solve."""
    for r in si_regions:
        sp.CreateSiliconPotentialOnly(device, r)
    for r in ox_regions:
        sp.CreateOxidePotentialOnly(device, r, "log_damp")
    for c, r in si_contacts.items():
        ds.set_parameter(device=device, name=sp.GetContactBiasName(c), value=0.0)
        sp.CreateSiliconPotentialOnlyContact(device, r, c)
    for c, r in ox_contacts.items():
        ds.set_parameter(device=device, name=sp.GetContactBiasName(c), value=0.0)
        sp.CreateOxideContact(device, r, c)
    for i in interfaces:
        sp.CreateSiliconOxideInterface(device, i)


def add_interface_charge(device, region, qf_cm2):
    """Fixed oxide charge qf_cm2 (charges/cm^2, positive) as a node charge on the silicon side.

    SurfaceArea/NodeVolume turns the sheet charge into a volume charge on the surface nodes
    only, so the total charge does not depend on the mesh. SurfaceArea is non-zero on contact
    nodes too, where the Dirichlet condition overrides the Poisson equation.
    """
    ds.set_parameter(device=device, region=region, name="Qf", value=qf_cm2)
    mc.CreateNodeModel(device, region, "QfDensity", "Qf*SurfaceArea/NodeVolume")


def undamp_oxide(device, ox_regions):
    """Plain Newton updates in the dielectric once the equilibrium solve is done."""
    for r in ox_regions:
        ds.equation(device=device, region=r, name="PotentialEquation", variable_name="Potential",
                    edge_model="PotentialEdgeFlux", variable_update="default")


def drift_diffusion(device, si_regions, si_contacts, with_qf=False, update="default"):
    """update: Newton update of the potential. "log_damp" limits each update to a few
    kT/q, which needs hundreds of iterations for a reverse-bias step of volts."""
    for r in si_regions:
        mc.CreateSolution(device, r, "Electrons")
        mc.CreateSolution(device, r, "Holes")
        ds.set_node_values(device=device, region=r, name="Electrons", init_from="IntrinsicElectrons")
        ds.set_node_values(device=device, region=r, name="Holes", init_from="IntrinsicHoles")
        sp.CreateSiliconDriftDiffusion(device, r)
        if with_qf:
            pne = "-ElectronCharge*(kahan3(Holes, -Electrons, NetDoping) + QfDensity)"
            mc.CreateNodeModel(device, r, "PotentialNodeCharge", pne)
            mc.CreateNodeModelDerivative(device, r, "PotentialNodeCharge", pne, "Electrons")
            mc.CreateNodeModelDerivative(device, r, "PotentialNodeCharge", pne, "Holes")
        ds.equation(device=device, region=r, name="PotentialEquation", variable_name="Potential",
                    node_model="PotentialNodeCharge", edge_model="PotentialEdgeFlux",
                    time_node_model="", variable_update=update)
    for c, r in si_contacts.items():
        sp.CreateSiliconDriftDiffusionAtContact(device, r, c)


def solve(rel=1e-6, abs_=1e10, iters=30):
    """rel is DEVSIM's relative update limit for every equation. In double precision the
    continuity equations of a depleted region stall near 3e-7 while the potential is
    converged to 1e-13, so a limit of 1e-8 stopped sweeps that had not broken down."""
    # maximum_divergence: give up after the error has grown this many times. A diverging
    # Newton iteration is very slow to factorise, and the default of 20 kept a step that
    # was going to be halved anyway busy for an hour.
    ds.solve(type="dc", absolute_error=abs_, relative_error=rel, maximum_iterations=iters,
             maximum_divergence=4)


def ramp(device, contacts, target, step, on_point, min_step=None):
    """Move the bias of every contact in `contacts` together from its present value to
    `target` (up or down), halving the step when a solve fails.

    on_point(v) is called after each converged point; it may return True to stop the ramp.
    Returns the last voltage reached.
    """
    names = [sp.GetContactBiasName(c) for c in contacts]
    v = ds.get_parameter(device=device, name=names[0])
    min_step = min_step if min_step is not None else abs(step) / 64
    dv = abs(step) / 8  # a small first step, growing to `step`: floating rings need it
    sign = 1.0 if target >= v else -1.0

    def put(val):
        for n in names:
            ds.set_parameter(device=device, name=n, value=val)

    while sign * (target - v) > 1e-9:
        nxt = v + sign * min(dv, abs(target - v))
        put(nxt)
        try:
            solve()
        except ds.error as exc:
            put(v)
            dv /= 2
            if dv < min_step:
                print(f"ramp: gave up at {v:.3f} V ({str(exc)[:80]})", flush=True)
                return v
            continue
        v = nxt
        if on_point(v):
            return v
        dv = min(dv * 1.5, abs(step))
    return v
