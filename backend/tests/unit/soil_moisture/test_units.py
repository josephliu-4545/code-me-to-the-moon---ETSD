import math

import pytest

from app.soil_moisture.units import (
    WATER_DENSITY_KG_PER_M3,
    QuantityKind,
    layer_thickness_m,
    storage_to_volumetric,
    volumetric_to_storage,
)


def test_water_density_is_reference_value() -> None:
    assert WATER_DENSITY_KG_PER_M3 == 1000.0


def test_gldas_top_layer_thickness_is_ten_centimetres() -> None:
    assert layer_thickness_m(0, 10) == pytest.approx(0.10, abs=1e-15)
    assert layer_thickness_m(10, 40) == pytest.approx(0.30, abs=1e-15)


def test_storage_to_volumetric_for_gldas_top_layer() -> None:
    theta = storage_to_volumetric(
        25.0, 0, 10, quantity_kind=QuantityKind.LAYER_WATER_STORAGE
    )
    assert theta == pytest.approx(0.25, abs=1e-12)


def test_zero_storage_is_a_real_value_not_missing() -> None:
    assert storage_to_volumetric(
        0.0, 0, 10, quantity_kind=QuantityKind.LAYER_WATER_STORAGE
    ) == 0.0


@pytest.mark.parametrize("storage", [0.0, 1e-9, 12.345, 25.0, 47.5, 100.0])
def test_round_trip_within_tolerance(storage: float) -> None:
    theta = storage_to_volumetric(
        storage, 0, 10, quantity_kind=QuantityKind.LAYER_WATER_STORAGE
    )
    assert volumetric_to_storage(theta, 0, 10) == pytest.approx(storage, abs=1e-12)


@pytest.mark.parametrize("top, bottom", [(10, 10), (10, 0), (5, 4.999)])
def test_zero_or_negative_thickness_is_rejected(top: float, bottom: float) -> None:
    with pytest.raises(ValueError, match="thickness"):
        layer_thickness_m(top, bottom)
    with pytest.raises(ValueError, match="thickness"):
        storage_to_volumetric(
            10.0, top, bottom, quantity_kind=QuantityKind.LAYER_WATER_STORAGE
        )
    with pytest.raises(ValueError, match="thickness"):
        volumetric_to_storage(0.2, top, bottom)


def test_negative_top_depth_is_rejected() -> None:
    with pytest.raises(ValueError, match="depth"):
        layer_thickness_m(-1, 10)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_inputs_are_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        storage_to_volumetric(
            bad, 0, 10, quantity_kind=QuantityKind.LAYER_WATER_STORAGE
        )
    with pytest.raises(ValueError, match="finite"):
        volumetric_to_storage(bad, 0, 10)
    with pytest.raises(ValueError, match="finite"):
        layer_thickness_m(bad, 10)
    with pytest.raises(ValueError, match="finite"):
        layer_thickness_m(0, bad)


def test_negative_storage_is_rejected_not_clamped() -> None:
    with pytest.raises(ValueError, match="negative"):
        storage_to_volumetric(
            -0.001, 0, 10, quantity_kind=QuantityKind.LAYER_WATER_STORAGE
        )


def test_negative_volumetric_content_is_rejected_not_clamped() -> None:
    with pytest.raises(ValueError, match="negative"):
        volumetric_to_storage(-0.01, 0, 10)


def test_storage_above_layer_capacity_is_rejected() -> None:
    # 0-10 cm holds at most 100 kg/m2 of water (theta = 1).
    with pytest.raises(ValueError, match="capacity"):
        storage_to_volumetric(
            100.01, 0, 10, quantity_kind=QuantityKind.LAYER_WATER_STORAGE
        )


def test_volumetric_content_above_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="capacity"):
        volumetric_to_storage(1.0001, 0, 10)


def test_volumetric_dataset_cannot_use_storage_conversion() -> None:
    with pytest.raises(ValueError, match="layer_water_storage"):
        storage_to_volumetric(
            0.25, 0, 5, quantity_kind=QuantityKind.VOLUMETRIC_WATER_CONTENT
        )


def test_quantity_kind_must_be_given_explicitly() -> None:
    with pytest.raises(TypeError):
        storage_to_volumetric(25.0, 0, 10)  # type: ignore[call-arg]


def test_boolean_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="number"):
        storage_to_volumetric(
            True, 0, 10, quantity_kind=QuantityKind.LAYER_WATER_STORAGE
        )


def test_quantity_kind_values_are_stable_strings() -> None:
    assert QuantityKind.LAYER_WATER_STORAGE == "layer_water_storage"
    assert QuantityKind.VOLUMETRIC_WATER_CONTENT == "volumetric_water_content"
