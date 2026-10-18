# SPDX-License-Identifier: Apache-2.0
"""Known, explained results shared by the tests and the docs.

Kept outside :data:`gf180tcad.reference.GENERATOR_MODULES` on purpose: it only labels results
and does not shape the SPICE reference, so editing it does not change the provenance hash.
"""

# (device, sweep) pairs where ngspice and Xyce differ by more than the 0.5 % threshold because
# the nfet card declares BSIM4 version 4.5 (ngspice runs BSIM4v5) while Xyce's oldest BSIM4 is
# 4.6.1. Explained, and proven by a forced-4.6 ngspice run, in
# docs/limitations/engine-cross-check.md. tests/spice/test_xyce.py marks exactly these cases
# strict xfail, and gf180tcad.docgen labels them "(known)".
KNOWN_ENGINE_DIFFS = frozenset({("nfet_05v0", "idvg_sat"), ("nfet_05v0", "idvg_lin")})
