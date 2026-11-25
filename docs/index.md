# gf180-tcad

**Can open-source physics simulation, given only public data, reproduce a chip maker's own
transistor models?**

This project tests that for the 5 V transistors of the open
{term}`GF180MCU` chip process from GlobalFoundries.

## The question

Chip designers simulate a circuit before it is made. Each transistor in that simulation is a
{term}`SPICE` model: equations the chip maker fits to its own measurements. GlobalFoundries
publishes these models for GF180MCU in an open {term}`process design kit <PDK>`
({{ gf180mcu_pdk }}).

{term}`TCAD` takes another route. It simulates the physics inside the transistor: its layers,
their thickness, their doping, and the electrons and holes that move in them. This project
builds a TCAD model of the GF180MCU transistors from public sources. It then measures how
closely the TCAD curves match the PDK's SPICE curves ({numref}`index-flow-figure`).

```{figure} /_generated/explained/project-flow-light.svg
:figclass: only-light
:name: index-flow-figure
:alt: Two columns of boxes joined by arrows. Left, grey: the PDK's SPICE models, a circuit simulator, reference curves. Right, green: public process data and the PDK's layouts, the TCAD, TCAD curves. Both feed one comparison box at the bottom.

The two routes to the same curves. The grey column is the reference, the green column is what
is tested, and every pair of curves is compared at the bottom.
```

```{figure} /_generated/explained/project-flow-dark.svg
:figclass: only-dark
:alt: Two columns of boxes joined by arrows. Left, grey: the PDK's SPICE models, a circuit simulator, reference curves. Right, green: public process data and the PDK's layouts, the TCAD, TCAD curves. Both feed one comparison box at the bottom.

The two routes to the same curves. The grey column is the reference, the green column is what
is tested, and every pair of curves is compared at the bottom.
```

## How the comparison works

The PDK's SPICE models are the {term}`reference <SPICE reference results>`, and the TCAD is what
is tested. A circuit simulator runs the SPICE models to give the reference curves. The TCAD
simulates a slice through the same transistor ({numref}`index-cell-figure`) to give its own
curves. Each pair is judged {term}`Agree`, {term}`Same process` or {term}`Disagree`. Same
process means the TCAD lies inside the range the PDK specifies, not at its typical point.

```{figure} /_generated/explained/parts-cell-light.svg
:figclass: only-light
:name: index-cell-figure
:alt: Cross-section of the transistor: a gate on a thin oxide in the middle, a source on the left and a drain on the right at the surface, a large body below, contacts drawn as dark bars.

The simulated slice of the {term}`nfet_05v0`, 10 µm wide with a 0.7 µm gate, cut along the
gate's length. Blue parts are n-type and the orange body is p-type.
{{ x_fig_parts_cell_scale }}
```

```{figure} /_generated/explained/parts-cell-dark.svg
:figclass: only-dark
:alt: Cross-section of the transistor: a gate on a thin oxide in the middle, a source on the left and a drain on the right at the surface, a large body below, contacts drawn as dark bars.

The simulated slice of the {term}`nfet_05v0`, 10 µm wide with a 0.7 µm gate, cut along the
gate's length. Blue parts are n-type and the orange body is p-type.
{{ x_fig_parts_cell_scale }}
```

## Why it matters

A TCAD model that matches the SPICE models explains them from physics. It can also reach sizes
and devices the models do not cover, once it has earned confidence here. Every mismatch is
listed with its cause and the evidence for it. Every input, script and result is in the
repository, under an open licence. No published comparison of {{ DEVSIM }} or {{ Charon }} with
the {term}`BSIM` models of any open PDK was found ({doc}`limitations/literature`).

## Where it stands

- **The reference is complete.** The SPICE curves are committed and rebuild byte for byte on a
  second computer.
- **The TCAD covers the gate only.** It simulates how much charge the gate holds as its voltage
  changes, the {term}`C–V` curve. It has no result for the transistor's current.
- **In 1D the nfet matches and the pfet does not.** The nfet agrees at every size. The pfet
  disagrees at the sizes it was fitted to ({numref}`index-cv-figure`).
- **The 2D slices are mixed.** Each calibrated 2D slice is Same process or Disagree.
- **No chip has been measured.** No silicon data exists to check either model against.

{doc}`limitations/status` lists every committed result, its folder and its verdict.

```{figure} /_generated/explained/cv-overview-light.svg
:figclass: only-light
:name: index-cv-figure
:alt: Gate capacitance against gate voltage, nfet above and pfet below: SPICE curves in a grey band, with dotted and dashed 1D lines and dash-dot 2D lines.

The gate's capacitance against its voltage at the shortest gate, nfet above and pfet below. The
solid line is the SPICE model, inside the grey band of its {{ x_corner_count }}
{term}`corners <corner>`. The dotted and dashed lines are the 1D TCAD before and after fitting.
The dash-dot lines are the 2D slice before (orange) and after (blue).
```

```{figure} /_generated/explained/cv-overview-dark.svg
:figclass: only-dark
:alt: Gate capacitance against gate voltage, nfet above and pfet below: SPICE curves in a grey band, with dotted and dashed 1D lines and dash-dot 2D lines.

The gate's capacitance against its voltage at the shortest gate, nfet above and pfet below. The
solid line is the SPICE model, inside the grey band of its {{ x_corner_count }}
{term}`corners <corner>`. The dotted and dashed lines are the 1D TCAD before and after fitting.
The dash-dot lines are the 2D slice before (orange) and after (blue).
```

## Should you read on?

- **You design circuits on GF180MCU:** {doc}`comparison/index` shows how far the transistor
  models can be rebuilt from physics.
- **You work on open-source TCAD:** {doc}`reproduce/index` rebuilds every result, and
  {doc}`limitations/index` lists what is missing.
- **You are learning how transistors work:** {doc}`explained/index` explains each part with this
  process's numbers.

## The documentation

The documentation has five sections, plus a glossary and the API reference:

- {doc}`explained/index`: how a transistor works, with this project's numbers.
- {doc}`reproduce/index`: how to rebuild every result.
- {doc}`results/index`: the SPICE reference and the TCAD results.
- {doc}`comparison/index`: the TCAD against the PDK, with each verdict.
- {doc}`limitations/index`: what is missing, and the project status.

Planned work, each item with its issue, is on the {doc}`roadmap`. The {doc}`glossary` defines
every term.

```{toctree}
:maxdepth: 2
:hidden:

explained/index
reproduce/index
results/index
comparison/index
limitations/index
roadmap
glossary
api/index
```
