# SPDX-License-Identifier: Apache-2.0
"""Device, geometry and bias-sweep matrix for the GF180MCU 5 V transistors.

All bias values are non-negative magnitudes (except the ``cv`` gate sweep, which spans
-5..5 V as specified); the netlister applies device polarity later.
"""

from dataclasses import dataclass
from typing import Literal

_ROLES = ("calibration", "validation")
_KINDS = ("idvg", "idvd", "cv")


@dataclass(frozen=True)
class Geometry:
    w_um: float
    l_um: float
    role: Literal["calibration", "validation"]

    def __post_init__(self) -> None:
        if not self.w_um > 0 or not self.l_um > 0:
            raise ValueError(f"w and l must be > 0, got w={self.w_um} l={self.l_um}")
        if self.role not in _ROLES:
            raise ValueError(f"role must be one of {_ROLES}, got {self.role!r}")


@dataclass(frozen=True)
class Device:
    name: str
    polarity: Literal[1, -1]
    spice_model: str
    geometries: tuple[Geometry, ...]

    def __post_init__(self) -> None:
        if self.polarity not in (1, -1):
            raise ValueError(f"polarity must be 1 or -1, got {self.polarity!r}")
        if not isinstance(self.geometries, tuple):
            raise TypeError("geometries must be a tuple")
        if not self.geometries:
            raise ValueError("geometries must be non-empty")


@dataclass(frozen=True)
class Sweep:
    name: str
    kind: Literal["idvg", "idvd", "cv"]
    vds: tuple[float, ...]
    vgs: tuple[float, ...]
    vbs: tuple[float, ...]
    freq_hz: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"kind must be one of {_KINDS}, got {self.kind!r}")
        for field in ("vds", "vgs", "vbs"):
            if not isinstance(getattr(self, field), tuple):
                raise TypeError(f"{field} must be a tuple")
            if not getattr(self, field):
                raise ValueError(f"{field} must be non-empty")


def geometry_id(g: Geometry) -> str:
    """Return a filename-safe id such as ``w10p0_l0p60``."""
    return f"w{g.w_um:.1f}_l{g.l_um:.2f}".replace(".", "p")


def _device(name: str, polarity: Literal[1, -1], lmin: float) -> Device:
    cal, val = "calibration", "validation"
    return Device(
        name=name,
        polarity=polarity,
        spice_model=name,
        geometries=(
            Geometry(10, lmin, cal),
            Geometry(10, 0.7, val),
            Geometry(10, 1, val),
            Geometry(10, 2, cal),
            Geometry(10, 10, cal),
            Geometry(1.6, 0.7, val),
        ),
    )


DEVICES: dict[str, Device] = {
    "nfet_05v0": _device("nfet_05v0", 1, 0.6),
    "pfet_05v0": _device("pfet_05v0", -1, 0.5),
}

# Grids are built from integers so each point is the correctly rounded decimal.
_V_0_5 = tuple(i / 100 for i in range(501))  # 0..5 V, 10 mV step
_V_CV = tuple((i - 100) / 20 for i in range(201))  # -5..5 V, 50 mV step

SWEEPS: tuple[Sweep, ...] = (
    Sweep("idvg_lin", "idvg", vds=(0.1,), vgs=_V_0_5, vbs=(0.0, 1.0, 2.0)),
    Sweep("idvg_sat", "idvg", vds=(5.0,), vgs=_V_0_5, vbs=(0.0, 1.0, 2.0)),
    Sweep("idvd", "idvd", vds=_V_0_5, vgs=(1.0, 2.0, 3.0, 4.0, 5.0), vbs=(0.0,)),
    Sweep("cv", "cv", vds=(0.0,), vgs=_V_CV, vbs=(0.0,), freq_hz=1e6),
    Sweep("ioff", "idvg", vds=(5.5,), vgs=(0.0,), vbs=(0.0,)),
)

CORNERS = ("typical", "ff", "ss", "fs", "sf")
TEMPS_C = (25.0,)
