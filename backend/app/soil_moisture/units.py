"""Pure conversion between layer water storage and layer-mean volumetric content.

theta = S / (rho_w * dz), with S in kg m-2, rho_w = 1000 kg m-3, dz in m.

The conversion is exact arithmetic, not scientific equivalence: a converted GLDAS
value is a model layer mean, not a satellite retrieval or a point measurement.
Invalid inputs raise ValueError; nothing is clamped or substituted.
"""

from enum import StrEnum
import math


WATER_DENSITY_KG_PER_M3 = 1000.0


class QuantityKind(StrEnum):
    LAYER_WATER_STORAGE = "layer_water_storage"
    VOLUMETRIC_WATER_CONTENT = "volumetric_water_content"


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def layer_thickness_m(top_cm: float, bottom_cm: float) -> float:
    top = _finite(top_cm, "top depth")
    bottom = _finite(bottom_cm, "bottom depth")
    if top < 0:
        raise ValueError("top depth must not be negative")
    if bottom <= top:
        raise ValueError("layer thickness must be positive")
    return (bottom - top) / 100.0


def storage_to_volumetric(
    storage_kg_m2: float,
    top_cm: float,
    bottom_cm: float,
    *,
    quantity_kind: QuantityKind,
) -> float:
    if quantity_kind is not QuantityKind.LAYER_WATER_STORAGE:
        raise ValueError(
            f"storage conversion requires {QuantityKind.LAYER_WATER_STORAGE.value}, "
            f"got {QuantityKind(quantity_kind).value}"
        )
    storage = _finite(storage_kg_m2, "storage")
    thickness = layer_thickness_m(top_cm, bottom_cm)
    if storage < 0:
        raise ValueError("storage must not be negative")
    theta = storage / (WATER_DENSITY_KG_PER_M3 * thickness)
    if theta > 1.0:
        raise ValueError("storage exceeds the physical capacity of the layer")
    return theta


def volumetric_to_storage(theta_m3_m3: float, top_cm: float, bottom_cm: float) -> float:
    theta = _finite(theta_m3_m3, "volumetric water content")
    thickness = layer_thickness_m(top_cm, bottom_cm)
    if theta < 0:
        raise ValueError("volumetric water content must not be negative")
    if theta > 1.0:
        raise ValueError("volumetric water content exceeds the physical capacity of the layer")
    return theta * WATER_DENSITY_KG_PER_M3 * thickness
