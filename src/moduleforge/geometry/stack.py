"""Layer stack of a DBC/AMB power-module substrate.

Conventions (mf-conventions): SI units, float64, z = 0 at the *bottom of the baseplate*, layers are
listed bottom-up. The default values below are *typical* datasheet/design-guide values, intended as
cited defaults, and must be replaced by vendor data for a real customer module:

* Copper electrical conductivity 5.8e7 S/m: International Annealed Copper Standard (IEC 60028).
* Copper thermal conductivity ~385 W/(m K): CRC Handbook of Chemistry and Physics (401 W/mK for pure Cu
  at 300 K; ~385 typical for DBC/baseplate copper).
* Al2O3 (96 %) DBC ceramic: 0.38 mm thick, k ~ 24 W/(m K); Rogers/curamik and CeramTec DBC datasheets.
* Si3N4 AMB ceramic: 0.32 mm thick, k ~ 90 W/(m K); Rogers/curamik and Kyocera Si3N4 AMB datasheets.
* Substrate Cu: 0.30 mm on both faces (standard DBC/AMB copper thickness).
* Baseplate: 3 mm Cu (typical module baseplate).
* SAC305 solder: 0.1 mm, sigma ~ 7.7e6 S/m (rho ~ 13 uOhm cm), k ~ 58 W/(m K); Lead-free solder handbooks.
* Aluminium bond wire: pure Al rho = 2.65e-8 Ohm m -> 3.77e7 S/m (CRC); alloy bond wire is lower, 3.5e7 used.
"""
from __future__ import annotations

from dataclasses import dataclass

SIGMA_CU = 5.8e7  # S/m, IACS
SIGMA_AL_WIRE = 3.5e7  # S/m, Al bond wire (CRC pure Al 3.77e7, alloy lower)
SIGMA_SOLDER = 7.7e6  # S/m, SAC305

LAYER_ORDER = ("baseplate", "solder", "backside_cu", "ceramic", "top_cu")


@dataclass(frozen=True)
class Layer:
    """One layer: thickness [m], electrical conductivity sigma [S/m], thermal conductivity k [W/(m K)]."""

    name: str
    material: str
    thickness: float
    sigma: float
    k: float


@dataclass(frozen=True)
class LayerStack:
    """Bottom-up layer stack; z = 0 at the bottom of the first (baseplate) layer."""

    layers: tuple[Layer, ...]
    kind: str = "custom"

    def __post_init__(self):
        names = tuple(la.name for la in self.layers)
        if names != LAYER_ORDER:
            raise ValueError(f"layers must be {LAYER_ORDER} bottom-up, got {names}")
        if any(la.thickness <= 0 for la in self.layers):
            raise ValueError("layer thicknesses must be positive")

    def layer(self, name: str) -> Layer:
        for la in self.layers:
            if la.name == name:
                return la
        raise KeyError(name)

    def z_bottom(self, name: str) -> float:
        z = 0.0
        for la in self.layers:
            if la.name == name:
                return z
            z += la.thickness
        raise KeyError(name)

    def z_top(self, name: str) -> float:
        return self.z_bottom(name) + self.layer(name).thickness

    @property
    def total_thickness(self) -> float:
        return sum(la.thickness for la in self.layers)

    @property
    def conductive_plane_names(self) -> tuple[str, ...]:
        """Extended conductive planes that carry image currents (backside Cu and baseplate)."""
        return ("baseplate", "backside_cu")


def _stack(kind: str, ceramic: Layer) -> LayerStack:
    return LayerStack(
        (
            Layer("baseplate", "Cu", 3.0e-3, SIGMA_CU, 385.0),
            Layer("solder", "SAC305", 0.1e-3, SIGMA_SOLDER, 58.0),
            Layer("backside_cu", "Cu", 0.3e-3, SIGMA_CU, 385.0),
            ceramic,
            Layer("top_cu", "Cu", 0.3e-3, SIGMA_CU, 385.0),
        ),
        kind=kind,
    )


def default_dbc_stack() -> LayerStack:
    """Al2O3 DBC: 0.38 mm ceramic, k = 24 W/mK (see module docstring for sources)."""
    return _stack("DBC", Layer("ceramic", "Al2O3", 0.38e-3, 0.0, 24.0))


def default_amb_stack() -> LayerStack:
    """Si3N4 AMB: 0.32 mm ceramic, k = 90 W/mK (see module docstring for sources)."""
    return _stack("AMB", Layer("ceramic", "Si3N4", 0.32e-3, 0.0, 90.0))
