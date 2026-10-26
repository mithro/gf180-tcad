# SPDX-License-Identifier: Apache-2.0
"""Calibration of the :term:`TCAD` against the :term:`SPICE` reference.

:mod:`gf180tcad.calibrate.cv` fits the 1D :term:`MOS capacitor <MOSCAP>` to the :term:`TT`
ngspice :term:`Cgg`–Vg and validates the frozen fit; ``python -m gf180tcad.calibrate``
(:mod:`gf180tcad.calibrate.__main__`) runs both in the TCAD image. Results:
:repo:`results/tcad/calibration` and :repo:`results/tcad/validation`.
"""

from gf180tcad.calibrate.cv import (
    CalibrationLeak,
    CalibrationResult,
    NotFrozen,
    ValidationResult,
    calibrate_cv,
    envelope_cv,
    load_frozen,
    validate_cv,
)

__all__ = [
    "CalibrationLeak",
    "CalibrationResult",
    "NotFrozen",
    "ValidationResult",
    "calibrate_cv",
    "envelope_cv",
    "load_frozen",
    "validate_cv",
]
