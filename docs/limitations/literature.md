# Literature

The papers, books and manuals the design and these pages cite, grouped by what they are used
for ({repo}`design spec, section 11 <docs/superpowers/specs/2026-10-18-gf180-tcad-design.md#11-literature-initial-verify-items-to-be-checked-before-citing>`).
Each DOI resolves to a record whose title, authors, volume, issue and year match the entry.
Each annotation names what the project uses the item for. The last section is the record of a
search: its items are the hits, not sources the project uses.

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
  Its §7.1 and §7.5.2 give the gate-bias-dependent overlap capacitance with the lightly doped
  source and drain region, CGDL.
- Its ch. 7, "Capacitance Model", gives the equations of the {term}`SPICE` gate capacitance that
  {ref}`explained-cv-curve` compares with the simulated stack.
- The BSIM4.5.0 manual, in the
  [BSIM450.zip package](https://web.archive.org/web/20260420023056/https://bsim.berkeley.edu/BSIM4/BSIM450.zip)
  (archived copy), matches the {term}`model card`'s
  [`version=4.5`](https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/4e132a23aea61dc035b9dbcd5f081dee23a7b691/models/ngspice/sm141064.spice#L37330).
  Its §8.1 and appendix A give the switches
  ACNQSMOD and TRNQSMOD of the non-quasi-static model: the value 0, the default, turns it off.

The project models no {term}`LDD`: its modelled source/drain doping under the gate edge is in {numref}`Figure %s of The 2D MOS capacitor and the C/Cox > 1 artefact <fig-moscap2d-sd>`.

## Physics models

(lit-sze)=

- Sze and Ng, *Physics of Semiconductor Devices*, 3rd ed., Wiley, 2006,
  {doi}`10.1002/0470068329`: ch. 2, the p-n junction ({term}`built-in potential`, the
  {term}`depletion approximation`, the {term}`ideality factor`); ch. 1, carrier statistics
  ({term}`Boltzmann statistics`); ch. 3, metal-semiconductor and {term}`ohmic contacts <ohmic contact>`.
- Its ch. 1, "Physics and Properties of Semiconductors—A Review": the explainer pages'
  carriers, {term}`dopants <dopant>`, the mass-action law and Fermi–Dirac statistics ({ref}`explained-silicon`).
- Its ch. 4, the ideal MIS capacitor: {term}`accumulation`, {term}`depletion`, {term}`inversion`,
  {term}`flat band` and the threshold of strong inversion ({ref}`explained-regions`).

(lit-ioffe)=

- Ioffe Physico-Technical Institute, NSM archive of semiconductor properties, silicon,
  [band structure and carrier concentration](https://web.archive.org/web/20261009101141/https://www.ioffe.ru/SVA/NSM/Semicond/Si/bandstr.html)
  (archived copy of 2026-10-09). It gives the {term}`band gap` of silicon at 300 K that the
  explainer's band diagrams draw ({ref}`explained-bands`). It also gives the band gap's
  temperature dependence and the band-edge densities of states with their masses
  ({ref}`display-values`).

(lit-ioffe-basic)=

- Ioffe Physico-Technical Institute, NSM archive of semiconductor properties, silicon,
  [basic parameters](https://web.archive.org/web/20260930073143/https://www.ioffe.ru/SVA/NSM/Semicond/Si/basic.html)
  (archived copy of 2026-09-30). Its table "Basic Parameters at 300 K" gives the number of atoms
  in 1 cm³ of silicon, 5·10²², that the explainer compares with the doping
  ({ref}`explained-dopants`).

(lit-wikipedia-mobility)=

- Wikipedia, "[Electron mobility](https://en.wikipedia.org/w/index.php?title=Electron_mobility&oldid=1383366442)".
  Its section "Relation to conductivity" gives the conductivity from the carrier densities and
  their mobilities. The explainer uses it for the resistivity of doped and pure silicon
  ({ref}`explained-conduction`).
- The same article gives a majority-carrier mobility fit for silicon doped 10¹⁸ cm⁻³ and up.
  It cites that range and the fit's form to Anderson and Anderson, *Fundamentals of
  Semiconductor Devices*, 2005. It cites the fit's parameters to
  {ref}`Caughey and Thomas <lit-caughey>`.

(lit-colorado-constants)=

- University of Colorado Boulder, Electrical, Computer and Energy Engineering, constants sheet
  "[Si material parameters](https://www.colorado.edu/ecee/sites/default/files/attached-files/sd_constants_sheet.pdf)".
  It lists silicon's band gap at 300 K and its band-edge densities of states with their masses
  ({ref}`display-values`).

(lit-wikipedia-band-gap)=

- Wikipedia, "[Band gap](https://en.wikipedia.org/w/index.php?title=Band_gap&oldid=1380816580)",
  the table of band gaps at 302 K. It gives 1.14 eV for silicon. For that value it cites Streetman
  and Banerjee, *Solid State Electronic Devices*, 5th ed., p. 524. It also cites Pankove,
  *Optical Processes in Semiconductors*, 1971 ({ref}`display-values`).
- The same table gives 9 eV for SiO₂. It cites Vella et al., Phys. Rev. B 83, 174201, 2011,
  {doi}`10.1103/PhysRevB.83.174201`. Its title is "Unraveling exciton dynamics in amorphous
  silicon dioxide: Interpretation of the optical features from 8 to 11 eV".

(lit-wikipedia-effective-mass)=

- Wikipedia, "[Effective mass (solid-state physics)](https://en.wikipedia.org/w/index.php?title=Effective_mass_%28solid-state_physics%29&oldid=1383927910)",
  table "Density of states effective mass in various semiconductors". It
  gives silicon's masses at 300 K, 1.09 for {term}`electrons <electron>` and 1.15 for {term}`holes <hole>`, in units of the free
  electron mass. The table cites four references. One of them is Green, "Intrinsic concentration, effective densities of states, and effective mass in
  silicon", J. Appl. Phys. 67(6), 2944-2954, 1990, {doi}`10.1063/1.345414`. The two masses set the band-edge densities of states
  N_c and N_v in {repo}`data/render/display.toml`.

(lit-alkauskas)=

- Alkauskas, Broqvist, Devynck and Pasquarello, "[Band offsets at semiconductor-oxide interfaces
  from hybrid density functional calculations](https://arxiv.org/abs/0809.3119)", Phys. Rev.
  Lett. 101, 106802, 2008. Its tables give the measured band gap of SiO₂, 8.9 eV. They give the
  measured Si/SiO₂ band offsets too: 4.4 eV for the {term}`valence band`, 3.4 eV for the {term}`conduction band`.
  The render band diagrams draw them ({repo}`data/render/display.toml`).

(lit-shaltaf)=

- Shaltaf, Rignanese, Gonze, Giustino and Pasquarello, "[Band offsets at the Si/SiO₂ interface
  from many-body perturbation theory](https://arxiv.org/abs/0805.0212)", Phys. Rev. Lett. 100,
  186401, 2008. Its measured offsets are 4.3 eV for the valence band and 3.1 eV for the
  conduction band. Its measured gaps are 8.9 eV for SiO₂ and 1.2 eV for silicon
  ({ref}`display-values`).

(lit-altermatt)=

- Altermatt, Schenk, Geelhaar and Heiser, "[Reassessment of the intrinsic carrier density in
  crystalline silicon in view of band-gap narrowing](https://doi.org/10.1063/1.1529297)".
  J. Appl. Phys. 93(3), 1598-1604, 2003. It gives the {term}`intrinsic carrier density` of
  silicon at 300 K. The simulations start from its value, 9.65×10⁹ cm⁻³ ({ref}`explained-silicon`).

(lit-misiakos)=

- Misiakos and Tsamakis, "[Accurate measurements of the silicon intrinsic carrier density from
  78 to 340 K](https://doi.org/10.1063/1.354551)", J. Appl. Phys. 74(5), 3293-3297, 1993: the intrinsic
  carrier density measured from 78 to 340 K. The code cites it for the temperature scaling of
  n_i ({py:attr}`gf180tcad.tcad.process.Constants.n_i_cm3`).

(lit-shockley)=

- Shockley, "The theory of p-n junctions in semiconductors and p-n junction transistors", Bell
  Syst. Tech. J. 28(3), 435-489, 1949, {doi}`10.1002/j.1538-7305.1949.tb03645.x`: the ideal
  diode law, {term}`ideality factor` 1.

(lit-sah)=

- Sah, Noyce and Shockley, "Carrier generation and recombination in p-n junctions and p-n
  junction characteristics", Proc. IRE 45(9), 1228-1243, 1957,
  {doi}`10.1109/JRPROC.1957.278528`: recombination in the {term}`depletion` region, {term}`ideality factor`
  near 2.

(lit-caughey)=

- Caughey and Thomas, "Carrier mobilities in silicon empirically related to doping and
  field", Proc. IEEE 55(12), 2192-2193, 1967, {doi}`10.1109/PROC.1967.6123`: velocity
  saturation, and mobility against doping ({ref}`explained-conduction`).

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

A simulated p-n junction and its built-in potential are in {numref}`Figure %s of The gplugins DEVSIM plugin: it once worked <fig-plugin-history-pn>`.

## Textbooks for the explainer pages

Each chapter below is named from the Crossref record of the edition cited, with its title.

- {ref}`Sze and Ng, 3rd ed. <lit-sze>`: ch. 4, "Metal-Insulator-Semiconductor Capacitors", and
  ch. 6, "MOSFETs".

(lit-taur)=

- Taur and Ning, *Fundamentals of Modern VLSI Devices*, 3rd ed., Cambridge University Press,
  2021, {doi}`10.1017/9781108847087`. The explainer pages use its ch. 2, "Basic Device
  Physics", ch. 4, "{term}`MOS Capacitors <MOSCAP>`", and ch. 5, "MOSFETs".

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

The doping of each part of the simulated cell is in {numref}`Figure %s of Definition of agreement <fig-agreement-cell>`.

## Simulators

(lit-devsim)=

- Sanchez, {{ DEVSIM }}, JOSS 7(70), 3898, 2022, {doi}`10.21105/joss.03898`.

(lit-charon)=

- {{ Charon }} User Manual v2.2 (SAND 2022), {doi}`10.2172/1871374`.

(lit-shadid)=

- Shadid, Hoekstra, Hennigan, Castro and Fixel, "Simulation of neutron radiation damage in
  silicon semiconductor devices", Sandia National Laboratories report SAND2007-7157, 2007,
  {doi}`10.2172/934581`. It describes the {{ Charon }} code: a stabilized finite-element
  discretization of the {term}`drift-diffusion` equations.

(lit-bochev)=

- Bochev, Peterson and Gao, Comput. Methods Appl. Mech. Eng. 254, 2013,
  {doi}`10.1016/j.cma.2012.10.009`: a control-volume finite-element method for the
  drift–diffusion equations on unstructured grids.

(lit-search-bsim)=

## Comparisons of DEVSIM or Charon with foundry SPICE models

A search on 2026-11-26 looked for a published comparison of {{ DEVSIM }} or {{ Charon }}
results with a foundry's {term}`BSIM4` {term}`model card`. It found OpenTCAD, a {term}`TCAD` project on
GitHub. OpenTCAD calibrates a DEVSIM transistor to the SkyWater SKY130 card.
{numref}`tab-lit-search-bsim-queries` lists every query.

~~~{table} The queries of the search on 2026-11-26, one row per query, with the relevant hit each found.
:name: tab-lit-search-bsim-queries

| Where | Query | Relevant hit |
|---|---|---|
| Web search | `devsim bsim comparison` | none |
| Web search | `charon tcad bsim comparison` | none |
| Web search | `open-source tcad compact model validation` | none |
| Web search | `devsim mosfet calibration` | none |
| Web search | `"charon" sandia semiconductor device simulator validation` | none |
| Web search | `sky130 tcad` | none |
| Web search | `gf180 tcad` | none |
| Web search, extended | `DEVSIM simulation compared with BSIM4 SPICE model foundry PDK` | none |
| Web search, extended | `open-source TCAD SkyWater sky130 device simulation DEVSIM ngspice comparison` | devphys |
| Web search, extended | `gf180mcu TCAD device simulation paper` | none |
| Web search, extended | `Charon Sandia TCAD compact model SPICE comparison Xyce MOSFET` | none |
| Web search | `devphys github devsim sky130 calibrated measured silicon 77 K` | devphys |
| Web search, arxiv.org only | `DEVSIM TCAD MOSFET BSIM` | none |
| Web search, ieeexplore.ieee.org only | `DEVSIM open-source TCAD MOSFET compact model comparison` | none |
| Web search, ieeexplore.ieee.org and osti.gov only | `Charon TCAD Sandia MOSFET compact model` | none |
| Web search, extended | `FOSS TCAD open PDK sky130 gf180 MOS-AK devsim BSIM verification` | OpenTCAD |
| Web search, extended | `"GF180MCU" OR "gf180mcu" TCAD Sentaurus OR DEVSIM OR Charon simulation transistor doping profile` | none |
| Web search, extended | `open-source TCAD calibrated against foundry SPICE model card BSIM4 ngspice reference curves github` | none |
| arXiv API | `all:devsim` | none |
| arXiv API | `all:charon AND all:TCAD` | none |
| arXiv API | `abs:charon AND abs:semiconductor` | none |
| arXiv API | `all:gf180mcu` | none |
| arXiv API | `all:GF180MCU AND all:TCAD` | none |
| arXiv API | `all:sky130 AND all:TCAD` | none |
| arXiv API | `abs:"open-source TCAD"` | none |
| arXiv API | `abs:TCAD AND abs:BSIM` | none |
| GitHub topic `tcad` | first page of repositories | devphys |
| Google Scholar | `"devsim" "bsim"` | none: the site answered HTTP 403 |
~~~

These are the hits about DEVSIM and the SKY130 process, from the queries:

- **OpenTCAD's check.** Its [SKY130 `nfet_01v8` check](https://github.com/abhineet-agarwal/opentcad/blob/0ea3326ed1dffb760ee0186ab914ed48115251c0/validation/sky130/README.md)
  simulates a 1 µm nMOS in DEVSIM. It compares the result with {{ ngspice }} 44.2 curves of
  SKY130's typical-corner BSIM4 card. The version committed on 2026-11-05 compared the
  threshold voltage only. {numref}`fig-lit-opentcad-vth-check` is the check's figure at the pinned
  commit, before the calibration.
- **OpenTCAD's calibration.** Commits on 2026-11-18 fit the device's implant dose, drive-in and
  Lombardi mobility coefficients to the card. They compare the threshold at five back biases,
  the subthreshold swing, the peak transconductance, the on-current and the {term}`linear Id`–Vgs
  curves. The comparison is a fit to the card.

```{figure} images/opentcad-sky130-vth-check.png
:name: fig-lit-opentcad-vth-check
:alt: Two plots. Left: acceptor concentration against depth below the silicon surface, from 0 to 900 nm on a log axis from 1e14 to 1e19 per cubic centimetre, with mesh points on a design line peaking near 30 nm and again near 420 nm. Right: drain current per micrometre against gate voltage from 0 to 1.8 V on a log axis, with a dashed line at 0.592 V, a shaded band of 20 percent around it and a dotted line at 0.697 V.

OpenTCAD's threshold check of a 1 µm SKY130 `nfet_01v8`, before its calibration to the card. Left, the channel doping of the DEVSIM device. Right, its drain current against gate voltage at a drain voltage of 50 mV, beside the card's threshold ([OpenTCAD](https://github.com/abhineet-agarwal/opentcad/blob/0ea3326ed1dffb760ee0186ab914ed48115251c0/validation/sky130/README.md), Apache License).
```

The list continues with the other hits from the queries:

- **devphys.** Its [README](https://github.com/joaln27/devphys/blob/bcae3beebcaaeb15a1937af996f43e0bc15bcdb4/README.md)
  compares DEVSIM simulations of SKY130 `nfet_01v8` with measured silicon at 300 K and 77 K. It
  sets its 77 K error beside the error the dataset's authors give for their own BSIM4 fits. It
  compares its extracted `toxe` with the card's.
- **devphys's inverter.** Its inverter stage compares a DEVSIM-derived inverter's drive
  resistance with a Liberty file characterised with BSIM. The file comes from a standard-cell
  repository. It prints the DEVSIM saturation current beside BSIM's.
- **The 2021 request.** [DEVSIM issue 74](https://github.com/devsim/devsim/issues/74) asked in
  August 2021 for an open TCAD flow matched to the SKY130 {term}`PDK`. It was closed in April 2022 with
  no comments.

The search also read the two simulators' own publication lists. These are the hits from those
lists and the papers they lead to:

- **DEVSIM's list of papers.** The [DEVSIM introduction](https://devsim.org/introduction.html)
  links a spreadsheet of papers that cite DEVSIM. On 2026-11-26 it held 50 titles. None names
  BSIM, a compact model, SPICE, a PDK or a foundry process.
- **A DEVSIM radiation study.** Julson et al.,
  [arXiv:2605.16597](https://arxiv.org/abs/2605.16597), couple DEVSIM with Geant4 for a 90 nm
  NOR flash chip. They compare simulated threshold shifts with measured ones. The paper names no
  BSIM model.
- **Charon's list of publications.** The [Charon publications page](https://charon.sandia.gov/publications-and-documents/)
  held 16 items on 2026-11-26. No title names a compact model, SPICE or BSIM.
- **Charon and compact models.** Huang et al.,
  SAND2021-2473C, {doi}`10.2172/1854316`, fit a graph-network compact
  model of a p-n diode to Charon results. BSIM appears in their software list only. Gao et al.,
  ACM TODAES 2026, {doi}`10.1145/3766551`, calibrate Charon to measured dose effects in a
  commercial SiC power MOSFET. Their abstract names no BSIM card.

## Tooling

(lit-dmt)=

- {{ SemiMod }} {{ DMT_core }}, JOSS 2022, {doi}`10.21105/joss.04298`.
