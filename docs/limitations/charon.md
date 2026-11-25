# Charon: what the experiments found

This page answers the open questions of the design spec's
{repo}`section 12.1 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#121-dual-backend-cross-comparison-devsim-and-charon>`
for the 1D MOS capacitor, from experiments B1 to B7 of the
{repo}`Charon plan, Task B <docs/superpowers/plans/2026-10-27-phase4-charon-backend.md#task-b-backendscharon-behind-the-task-15-seam>`.
Each experiment is a script in {repo}`tools/charon-experiments/`, run in the pinned
{repo}`Charon image <docker/CHARON_IMAGE>` through {repo}`tools/sandbox-run`.

```{note}
Work in progress: this page is filled in as each experiment finishes (draft pull request).
```

## The test structure

Every experiment uses the committed DEVSIM 1D job of `nfet_05v0` at the calibrated values
({repo}`its meta file <results/tcad/moscap1d/nfet_05v0/calibrated/per_area.meta.json>`):
0.2 µm of n+ poly at 1e20 cm⁻³, 16.05 nm of oxide and 1 µm of p body at 8.81e16 cm⁻³, on the
same 686 nodes as DEVSIM. Charon has no 1D mode, so the node list is extruded into a strip one
element wide and 1 µm deep.

## Findings so far

- **A side set may not share a name with an element block.** A side set named `body` on the
  block `body` makes `charon_mp.exe` abort with MPI error code 14 and no message. Renaming the
  side set to `body_contact` fixes it.
- **A uniform doping block must be named `Function1`, `Function2` and so on.** Any other name is
  accepted by the interpreter and then ignored: the nodal `Doping` field is zero everywhere.
- **The interpreter cannot select a direct solver, but `Direct input` can.** The tpetra block
  offers only `aztecOO` and `belos`. Three `Direct input` lines rooted at `Charon->Solution
  Control` select Amesos2 KLU2, which then runs.
- **The default status test accepts a failed linear solve.** NOX's `Rescue Bad Newton Solve` is
  on, so a Newton step uses an unconverged GMRES solution.
- **Zero-current drift-diffusion stalls in double precision at the onset of inversion.** At
  WRMS tolerances of 1e-10 relative and 1e-12 absolute, the sweep stops at 0.35 V device bias:
  the residual stays at 2e-6 and the WRMS norm at 18 for 50 iterations. Both KLU2 and Belos stop
  there. Looser tolerances are being measured.
- **The LOCA sweep keeps the grid.** With a fixed step it lands on every grid voltage and ends
  with one extra state of zero length on the bound.
