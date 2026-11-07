(limitations-corners)=

# Corner fits of the 1D MOS capacitor

The {term}`corner` fits give each fitted number of the 1D {term}`MOS capacitor <MOSCAP>` a
lowest and a highest value. They span the five {term}`SPICE` corners
({ref}`explained-calibration-corners`, {ref}`reproduce-corners`). This page sets out what those
fits cannot see, which fits stop on a limit, and how their shifts compare with the
{term}`model card`'s. The fits are in {repo}`results/tcad/corners`.

(limitations-corners-unseen)=

## What the 1D corner fits cannot see

Each corner fit tunes one 1D stack, the same for every gate length. A corner's change that
depends on the gate length cannot enter that stack. It shows up as a gap that moves with the
length.
{numref}`fig-corner-crossing` shows that shift at the {term}`depletion` crossing for every fit.

```{figure} /_generated/explained/corner-crossing-light.svg
:figclass: only-light
:name: fig-corner-crossing
:alt: Two panels, nfet above pfet, of the depletion crossing shift in millivolts against gate length on a log axis, one line per corner: a solid typical line, dashed ff and ss lines in colour, dotted and dash-dotted fs and sf lines in grey.

The depletion crossing shift, simulated minus SPICE, at every W = 10 µm gate of each fit. Solid is
the typical fit, dashed the ff and ss fits, grey the fs and sf fits. Fitted and held-out gates
are both drawn. Read from the corner files in {repo}`results/tcad/corners` and the typical
calibration and validation files.
```

```{figure} /_generated/explained/corner-crossing-dark.svg
:figclass: only-dark
:alt: Two panels, nfet above pfet, of the depletion crossing shift in millivolts against gate length on a log axis, one line per corner: a solid typical line, dashed ff and ss lines in colour, dotted and dash-dotted fs and sf lines in grey.

The depletion crossing shift, simulated minus SPICE, at every W = 10 µm gate of each fit. Solid is
the typical fit, dashed the ff and ss fits, grey the fs and sf fits. Fitted and held-out gates
are both drawn. Read from the corner files in {repo}`results/tcad/corners` and the typical
calibration and validation files.
```

The nfet's lines lie close together, near zero at every gate length. At every corner the pfet's
shift is positive at its shortest gate and negative at its longest. The typical fit shows the same
({ref}`the pfet mismatch <cv-agreement-mismatch>`). {{ x_corner_verdicts }}.

These corner inputs do not enter a corner fit at all:

- **VSAT and its binning.** The saturation velocity acts on drain current, not on a {term}`C–V` curve.
- **TOXM.** The card's oxide thickness for parameter extraction, which the C–V model never reads.
- **The pfet's PVTH0 line.** It adds a threshold shift that grows as the gate shrinks. At the
  worst calibration gate it moves VTH0 by {{ x_corner_pvth0_dv }}
  ({ref}`reproduce-corners`, {math:numref}`eq-corner-pvth0`).

A corner is one deterministic extreme of the global process variation. The corners give no
statistical spread: no mean, standard deviation or percentiles. That needs the Monte Carlo of
the card's statistical section ([issue #57](https://github.com/mithro/gf180-tcad/issues/57)).

(limitations-corners-limits)=

## Fits that stop on a limit

Each fit keeps its numbers between limits set before it runs. A corner fit moves the oxide limits
by the corner's TOXE offset. It moves the shift limits by its VTH0 offset
({math:numref}`eq-corner-bounds`). A fit that stops on a shift limit runs again with a wider
window, as {math:numref}`eq-corner-flatband-window` gives:

$$
V_{\mathrm{lo}} = V_s - h - k \, |\Delta V_c|, \qquad V_{\mathrm{hi}} = V_s + h + k \, |\Delta V_c|
$$ (eq-corner-flatband-window)

where

- $V_{\mathrm{lo}}$, $V_{\mathrm{hi}}$ are the lower and upper shift limits of the fit at corner $c$, in V;
- $V_s$ is the fit's start value, the typical start plus $\Delta V_c$, in V;
- $h$ is the half-width of the typical shift window, {{ x_flatband_half_width }}, in V;
- $k$ is how many times the window was widened, dimensionless;
- $\Delta V_c$ is the card's VTH0 offset at corner $c$, in V.

The card's VTH0 offset is the size of the corner's own threshold move. Each widening gives the
fit one more move of that size on each side, so the window favours neither direction. A fit
still on its limit is widened again. {{ x_corner_widened }}
([first ff fit](https://github.com/mithro/gf180-tcad/blob/f60ca2d28138751903df564d3f98faf9a7671d61/results/tcad/corners/pfet_05v0/ff.json),
[first sf fit](https://github.com/mithro/gf180-tcad/blob/f60ca2d28138751903df564d3f98faf9a7671d61/results/tcad/corners/pfet_05v0/sf.json)).

{numref}`fig-corner-limits` shows every fit within its limits.

```{figure} /_generated/explained/corner-limits-light.svg
:figclass: only-light
:name: fig-corner-limits
:alt: Three panels side by side, one per fitted number, with ten rows, the nfet and pfet at each of five corners. Each row has a grey bar between two tick marks and a diamond, green inside the bar and orange on its end.

Each fitted number of every fit: one row per transistor and corner. The grey bar runs between
the fit's limits. The diamond is the fitted value, orange where it sits on a limit. Read from the
typical calibration files and the corner files in {repo}`results/tcad/corners`.
```

```{figure} /_generated/explained/corner-limits-dark.svg
:figclass: only-dark
:alt: Three panels side by side, one per fitted number, with ten rows, the nfet and pfet at each of five corners. Each row has a grey bar between two tick marks and a diamond, green inside the bar and orange on its end.

Each fitted number of every fit: one row per transistor and corner. The grey bar runs between
the fit's limits. The diamond is the fitted value, orange where it sits on a limit. Read from the
typical calibration files and the corner files in {repo}`results/tcad/corners`.
```

{{ x_corner_fit_hits }}. {{ x_corner_nearest_limit }}. A value on its limit is set by the limit,
not by the SPICE curve. A table marks such a value with †, and a figure rings it in orange.

The body doping has no card offset, so its corner range shows the fit trading doping against the
other two numbers, not a process spread.

(limitations-corners-card)=

## The card cross-check

The oxide thickness and the gate voltage shift each have a model-card counterpart: the corner's
TOXE and VTH0 offsets. The cross-check sets the fit's shift beside the card's. For the oxide,
{math:numref}`eq-corner-crosscheck-tox` gives the difference:

$$
d_{t,c} = (t_c - t_t) - \Delta t_c
$$ (eq-corner-crosscheck-tox)

where

- $d_{t,c}$ is the oxide difference at corner $c$, in nm;
- $t_c$ is the fitted oxide thickness at corner $c$, in nm;
- $t_t$ is the fitted oxide thickness at the {term}`typical corner`, in nm;
- $\Delta t_c$ is the card's TOXE offset at corner $c$, in nm.

For the gate voltage shift, {math:numref}`eq-corner-crosscheck-vfb` gives it:

$$
d_{V,c} = (V_c - V_t) - \Delta V_c
$$ (eq-corner-crosscheck-vfb)

where

- $d_{V,c}$ is the shift difference at corner $c$, in V;
- $V_c$ is the fitted gate voltage shift at corner $c$, in V;
- $V_t$ is the fitted gate voltage shift at the typical corner, in V;
- $\Delta V_c$ is the card's VTH0 offset at corner $c$, in V.

{numref}`fig-corner-crosscheck` plots the fit's shift against the card's for every corner.

```{figure} /_generated/explained/corner-crosscheck-light.svg
:figclass: only-light
:name: fig-corner-crosscheck
:alt: Two square panels, oxide thickness shift and gate voltage shift, each plotting fitted shift against card shift: circles for the nfet and squares for the pfet, coloured by corner, and a dashed diagonal line where the two are equal.

The fit's shift from the typical fit against the card's offset, for the oxide (left) and the
gate voltage shift (right). Circles are the nfet, squares the pfet, coloured by corner. A point
on the dashed line has a difference of zero. Read from the corner summaries
({repo}`nfet_05v0 <results/tcad/corners/nfet_05v0/summary.json>`,
{repo}`pfet_05v0 <results/tcad/corners/pfet_05v0/summary.json>`).
```

```{figure} /_generated/explained/corner-crosscheck-dark.svg
:figclass: only-dark
:alt: Two square panels, oxide thickness shift and gate voltage shift, each plotting fitted shift against card shift: circles for the nfet and squares for the pfet, coloured by corner, and a dashed diagonal line where the two are equal.

The fit's shift from the typical fit against the card's offset, for the oxide (left) and the
gate voltage shift (right). Circles are the nfet, squares the pfet, coloured by corner. A point
on the dashed line has a difference of zero. Read from the corner summaries
({repo}`nfet_05v0 <results/tcad/corners/nfet_05v0/summary.json>`,
{repo}`pfet_05v0 <results/tcad/corners/pfet_05v0/summary.json>`).
```

For the nfet the largest oxide difference is {{ x_crosscheck_tox_gap_nfet }}, at
{{ x_crosscheck_tox_corner_nfet }}. Its largest shift difference is
{{ x_crosscheck_vfb_gap_nfet }}, at {{ x_crosscheck_vfb_corner_nfet }}. For the pfet the largest
oxide difference is {{ x_crosscheck_tox_gap_pfet }}, at {{ x_crosscheck_tox_corner_pfet }}. Its
largest shift difference is {{ x_crosscheck_vfb_gap_pfet }}, at
{{ x_crosscheck_vfb_corner_pfet }}. Each corner's values are in the tables on {ref}`cv-agreement-corners`.
