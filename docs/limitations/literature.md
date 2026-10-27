# Literature

The papers, books and manuals the design and these pages cite, grouped by what they are used
for ({repo}`design spec, section 11 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#11-literature-initial-verify-items-to-be-checked-before-citing>`).
Each DOI resolves to a record whose title, authors, volume, issue and year match the entry.
Each annotation names what the project uses the item for.

## Tolerances

(lit-itrs)=

- [ITRS 2007](https://www.semiconductors.org/resources/2007-international-technology-roadmap-for-semiconductors-itrs/)
  (International Technology Roadmap for Semiconductors),
  Modeling and Simulation chapter, Table MS3:
  the {term}`tolerance` numbers in {ref}`tolerances`.

## Model benchmark tests

(lit-tsividis)=

- Tsividis and Suyama, "MOSFET modeling for analog circuit CAD: problems and prospects", IEEE
  JSSC 29(3), 1994, {doi}`10.1109/4.278342`: a set of benchmark tests for MOSFET models.

(lit-mcandrew)=

- McAndrew, "Validation of MOSFET model source-drain symmetry", IEEE Trans. Electron Devices
  53(9), 2006, {doi}`10.1109/TED.2006.881005`. Its dc and ac tests check a model's symmetry under
  a source-drain reversal, the property the {term}`Gummel symmetry test` checks.

## Compact model

(lit-bsim4)=

- {{ BSIM4_site }} manual (UC Berkeley): the meaning of TOXE, TOXP, {term}`NGATE` and LPE0.

## Physics models

(lit-sze)=

- Sze and Ng, *Physics of Semiconductor Devices*, 3rd ed., Wiley, 2006,
  {doi}`10.1002/0470068329`: ch. 2, the p-n junction ({term}`built-in potential`, the
  {term}`depletion approximation`, the {term}`ideality factor`); ch. 1, carrier statistics
  ({term}`Boltzmann statistics`); ch. 3, metal-semiconductor and {term}`ohmic contacts <ohmic contact>`.
- Its ch. 4 and appendices G and H: the Si and SiO₂ band values the render band diagrams draw
  ({repo}`data/render/display.toml`).
- Its ch. 1, "Physics and Properties of Semiconductors—A Review": the explainer pages'
  carriers, {term}`dopants <dopant>`, the mass-action law and Fermi–Dirac statistics ({ref}`explained-silicon`).

(lit-shockley)=

- Shockley, "The theory of p-n junctions in semiconductors and p-n junction transistors", Bell
  Syst. Tech. J. 28(3), 435-489, 1949, {doi}`10.1002/j.1538-7305.1949.tb03645.x`: the ideal
  diode law, {term}`ideality factor` 1.

(lit-sah)=

- Sah, Noyce and Shockley, "Carrier generation and recombination in p-n junctions and p-n
  junction characteristics", Proc. IRE 45(9), 1228-1243, 1957,
  {doi}`10.1109/JRPROC.1957.278528`: recombination in the depletion region, {term}`ideality factor`
  near 2.

(lit-caughey)=

- Caughey and Thomas, Proc. IEEE 55(12), 1967, {doi}`10.1109/PROC.1967.6123`: velocity
  saturation.

(lit-masetti)=

- Masetti, Severi and Solmi, IEEE Trans. Electron Devices 30(7), 1983,
  {doi}`10.1109/T-ED.1983.21207`: mobility versus doping.

(lit-lombardi)=

- Lombardi et al., IEEE Trans. Computer-Aided Design 7(11), 1988, {doi}`10.1109/43.9186`:
  surface mobility.

(lit-darwish)=

- Darwish et al. (CVT), IEEE Trans. Electron Devices 44(9), 1997, {doi}`10.1109/16.622611`:
  surface mobility, a transverse-field dependent mobility model for MOS transistors.

(lit-klaassen)=

- Klaassen, "A unified mobility model for device simulation—I", Solid-State Electronics 35(7),
  1992, {doi}`10.1016/0038-1101(92)90325-7`: mobility, the alternative named in the
  {ref}`mismatch taxonomy <mismatch-taxonomy>`.

(lit-ancona)=

- Ancona and Iafrate, Phys. Rev. B 39, 9536, 1989, {doi}`10.1103/PhysRevB.39.9536`:
  {term}`density-gradient` quantum correction.

## Textbooks for the explainer pages

The chapter titles below come from the Crossref record of the edition cited.

- {ref}`Sze and Ng, 3rd ed. <lit-sze>`: ch. 4, "Metal-Insulator-Semiconductor Capacitors", and
  ch. 6, "MOSFETs".

(lit-taur)=

- Taur and Ning, *Fundamentals of Modern VLSI Devices*, 3rd ed., Cambridge University Press,
  2021, {doi}`10.1017/9781108847087`: its chapters on basic device physics, the
  {term}`MOS capacitor <MOSCAP>` and the MOSFET.

## Mismatch

(lit-pelgrom)=

- Pelgrom, Duinmaijer and Welbers, "Matching properties of MOS transistors", IEEE JSSC 24(5),
  1989, {doi}`10.1109/JSSC.1989.572629`: the mismatch scale ({term}`σ_mismatch`). It covers the
  matching of {term}`threshold voltage`, substrate factor and current factor.

## Inverse modelling of doping from I-V and C-V (the calibration method)

(lit-khalil)=

- Khalil, Faricelli, Bell and Selberherr, IEEE Electron Device Letters 16(1), 1995,
  {doi}`10.1109/55.363213`: the 2D doping of a MOSFET by inverse modelling. Its data are
  source/drain diode and gate capacitance.

(lit-lee)=

- Lee, McIlrath and Antoniadis, IEEE Trans. Electron Devices 46(8), 1999,
  {doi}`10.1109/16.777152`: the 2D doping of a MOSFET by inverse modelling of its subthreshold
  I-V characteristics.

## Simulators

(lit-devsim)=

- Sanchez, {{ DEVSIM }}, JOSS 7(70), 3898, 2022, {doi}`10.21105/joss.03898`.

(lit-charon)=

- {{ Charon }} User Manual v2.2 (SAND 2022), {doi}`10.2172/1871374`.

(lit-bochev)=

- Bochev, Peterson and Gao, Comput. Methods Appl. Mech. Eng. 254, 2013,
  {doi}`10.1016/j.cma.2012.10.009`: a control-volume finite-element method for the
  drift–diffusion equations on unstructured grids.

## Tooling

(lit-dmt)=

- {{ SemiMod }} {{ DMT_core }}, JOSS 2022, {doi}`10.21105/joss.04298`.
