from dataclasses import FrozenInstanceError, replace
from datetime import date

import pytest

from app.soil_moisture.datasets import (
    DATASETS,
    DEPRECATED_COLLECTIONS,
    DatasetDescriptor,
    DepthSemantics,
    ProductType,
    UnknownDatasetError,
    get_dataset,
    primary_dataset,
)
from app.soil_moisture.units import QuantityKind


GLDAS = "gldas_2_1_noah_0_10cm"
SMAP_V005 = "smap_l3e_v005_am"
SMAP_V006 = "smap_l3e_v006_am"


# --- registry shape -----------------------------------------------------------


def test_registry_contains_exactly_the_milestone_one_datasets() -> None:
    assert set(DATASETS) == {GLDAS, SMAP_V005, SMAP_V006}


def test_registry_keys_match_descriptor_keys() -> None:
    for key, descriptor in DATASETS.items():
        assert descriptor.key == key


def test_registry_is_read_only() -> None:
    with pytest.raises(TypeError):
        DATASETS["new_dataset"] = DATASETS[GLDAS]  # type: ignore[index]


def test_descriptors_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        DATASETS[GLDAS].band = "SoilMoi10_40cm_inst"  # type: ignore[misc]


def test_exactly_one_primary_dataset_and_it_is_gldas() -> None:
    primaries = [d for d in DATASETS.values() if d.is_primary]
    assert len(primaries) == 1
    assert primary_dataset().key == GLDAS


def test_every_descriptor_has_complete_provenance() -> None:
    for d in DATASETS.values():
        assert d.variable == "soil_moisture"
        for field in (d.title, d.version, d.band, d.native_units, d.native_grid,
                      d.temporal_sampling, d.doi, d.citation):
            assert isinstance(field, str) and field.strip()
        assert d.collection_ids and all(c.strip() for c in d.collection_ids)
        assert d.limitations and all(text.strip() for text in d.limitations)
        assert d.nominal_scale_m > 0
        assert d.expected_slots_per_day >= 1
        assert d.availability_as_of == date(2026, 11, 13)


# --- lookup and rejection -----------------------------------------------------


def test_get_dataset_returns_registered_descriptor() -> None:
    assert get_dataset(SMAP_V006) is DATASETS[SMAP_V006]


@pytest.mark.parametrize(
    "bad_key",
    [
        "smap_l3e_am",               # concatenated key is out of scope (D3)
        "smap_l4_v008",              # milestone 2 (D4)
        "gldas_2_1_noah_10_40cm",    # deeper layers deferred (D11)
        "smap_l3e_v006_pm",          # PM overpass not in milestone 1 (D10)
        "GLDAS_2_1_NOAH_0_10CM",     # keys are case-sensitive
        " gldas_2_1_noah_0_10cm",    # no whitespace normalisation
        "",
        "NASA/GLDAS/V021/NOAH/G025/T3H",  # collection id is not a dataset key
    ],
)
def test_unknown_dataset_keys_are_rejected(bad_key: str) -> None:
    with pytest.raises(UnknownDatasetError, match="unknown soil moisture dataset"):
        get_dataset(bad_key)


@pytest.mark.parametrize("bad_key", [None, 1, b"smap_l3e_v005_am"])
def test_non_string_dataset_keys_are_rejected(bad_key: object) -> None:
    with pytest.raises(UnknownDatasetError):
        get_dataset(bad_key)  # type: ignore[arg-type]


def test_unknown_dataset_error_is_a_value_error_listing_valid_keys() -> None:
    with pytest.raises(ValueError) as excinfo:
        get_dataset("nope")
    for key in (GLDAS, SMAP_V005, SMAP_V006):
        assert key in str(excinfo.value)


# --- GLDAS-2.1 Noah -----------------------------------------------------------


def test_gldas_identity_and_provenance() -> None:
    d = get_dataset(GLDAS)
    assert d.collection_ids == ("NASA/GLDAS/V021/NOAH/G025/T3H",)
    assert d.version == "2.1"
    assert d.band == "SoilMoi0_10cm_inst"
    assert d.product_type is ProductType.LAND_SURFACE_MODEL_OPEN_LOOP
    assert d.is_model and not d.is_satellite
    assert d.doi == "10.5067/E7TYRXPJKWOQ"
    assert d.qc_band is None


def test_gldas_units_and_depth() -> None:
    d = get_dataset(GLDAS)
    assert d.quantity_kind is QuantityKind.LAYER_WATER_STORAGE
    assert d.native_units == "kg m-2"
    assert (d.depth_top_cm, d.depth_bottom_cm) == (0.0, 10.0)
    assert d.depth_semantics is DepthSemantics.MODEL_LAYER
    assert d.valid_range == (0.0, 100.0)  # 0-10 cm layer holds at most 100 kg/m2


def test_gldas_spatial_and_temporal_resolution() -> None:
    d = get_dataset(GLDAS)
    assert d.native_grid == "0.25 degree"
    assert d.nominal_scale_m == 27830.0
    assert d.expected_slots_per_day == 8
    assert "3-hourly" in d.temporal_sampling and "instantaneous" in d.temporal_sampling


def test_gldas_documented_availability_is_open_ended() -> None:
    d = get_dataset(GLDAS)
    assert d.documented_first_date == date(2000, 1, 1)
    assert d.documented_last_date is None


def test_gldas_offers_a_derived_volumetric_value_labelled_as_layer_mean() -> None:
    d = get_dataset(GLDAS)
    assert d.supports_derived_volumetric is True
    text = " ".join(d.limitations).lower()
    assert "layer mean" in text
    assert "not equivalent" in text and "smap" in text


def test_gldas_limitations_carry_forcing_and_provisional_caveats() -> None:
    text = " ".join(get_dataset(GLDAS).limitations).lower()
    assert "not an observation" in text
    assert "2011" in text and "2025-06-09" in text
    assert "early" in text


# --- SMAP L3 Enhanced 005 / 006 ----------------------------------------------


@pytest.mark.parametrize(
    "key, collection, version, doi",
    [
        (SMAP_V005, "NASA/SMAP/SPL3SMP_E/005", "005", "10.5067/4DQ54OUIJ9DL"),
        (SMAP_V006, "NASA/SMAP/SPL3SMP_E/006", "006", "10.5067/M20OXIZHY3RJ"),
    ],
)
def test_smap_identity_and_provenance(key: str, collection: str, version: str, doi: str) -> None:
    d = get_dataset(key)
    assert d.collection_ids == (collection,)
    assert d.version == version
    assert d.doi == doi
    assert d.band == "soil_moisture_am"
    assert d.qc_band == "retrieval_qual_flag_am"
    assert d.product_type is ProductType.SATELLITE_RETRIEVAL
    assert d.is_satellite and not d.is_model
    assert not d.is_primary


@pytest.mark.parametrize("key", [SMAP_V005, SMAP_V006])
def test_smap_units_depth_and_resolution(key: str) -> None:
    d = get_dataset(key)
    assert d.quantity_kind is QuantityKind.VOLUMETRIC_WATER_CONTENT
    assert d.native_units == "m3 m-3"
    assert (d.depth_top_cm, d.depth_bottom_cm) == (0.0, 5.0)
    assert d.depth_semantics is DepthSemantics.APPROXIMATE_SENSING_DEPTH
    assert d.valid_range == (0.0, 1.0)
    assert d.native_grid == "9 km EASE-Grid 2.0 (EE geographic)"
    assert d.nominal_scale_m == 9000.0
    assert d.expected_slots_per_day == 1
    assert "06:00" in d.temporal_sampling and "descending" in d.temporal_sampling
    assert d.supports_derived_volumetric is False


def test_smap_versions_have_distinct_keys_collections_and_dois() -> None:
    v5, v6 = get_dataset(SMAP_V005), get_dataset(SMAP_V006)
    assert v5.key != v6.key
    assert set(v5.collection_ids).isdisjoint(v6.collection_ids)
    assert v5.doi != v6.doi
    assert v5.version != v6.version


def test_smap_versions_overlap_but_stay_separate_keys() -> None:
    # V006 was reprocessed back to 2015 (live catalog check 2026-11-13).
    v5, v6 = get_dataset(SMAP_V005), get_dataset(SMAP_V006)
    assert v5.documented_first_date == date(2015, 3, 31)
    assert v5.documented_last_date == date(2023, 12, 2)
    assert v6.documented_first_date == date(2015, 3, 31)
    assert v6.documented_last_date is None
    assert v5.key != v6.key and v5.collection_ids != v6.collection_ids


def test_smap_limitations_state_version_separation_and_missingness() -> None:
    for key, other in ((SMAP_V005, "006"), (SMAP_V006, "005")):
        text = " ".join(get_dataset(key).limitations).lower()
        assert "never filled" in text and other in text
        assert "frozen" in text
        assert "not equivalent" in text and "gldas" in text


def test_smap_v006_documents_reprocessing_and_overlap() -> None:
    text = " ".join(get_dataset(SMAP_V006).limitations)
    assert "NSIDC" in text and "2015-03-31" in text and "overlaps Version 005" in text


# --- cross-dataset guarantees -------------------------------------------------


def test_no_descriptor_spans_more_than_one_collection() -> None:
    for d in DATASETS.values():
        assert len(d.collection_ids) == 1


def test_no_collection_is_shared_between_datasets() -> None:
    collections = [c for d in DATASETS.values() for c in d.collection_ids]
    assert len(collections) == len(set(collections))


def test_no_descriptor_references_a_deprecated_collection() -> None:
    assert "NASA/SMAP/SPL4SMGP/007" in DEPRECATED_COLLECTIONS
    for d in DATASETS.values():
        assert not set(d.collection_ids) & DEPRECATED_COLLECTIONS


def test_gldas_and_smap_are_not_presented_as_the_same_quantity_or_layer() -> None:
    gldas, smap = get_dataset(GLDAS), get_dataset(SMAP_V005)
    assert gldas.quantity_kind is not smap.quantity_kind
    assert gldas.native_units != smap.native_units
    assert (gldas.depth_top_cm, gldas.depth_bottom_cm) != (smap.depth_top_cm, smap.depth_bottom_cm)
    assert gldas.depth_semantics is not smap.depth_semantics
    assert gldas.product_type is not smap.product_type


def test_enum_values_are_stable_strings() -> None:
    assert ProductType.LAND_SURFACE_MODEL_OPEN_LOOP == "land_surface_model_open_loop"
    assert ProductType.SATELLITE_RETRIEVAL == "satellite_retrieval"
    assert DepthSemantics.MODEL_LAYER == "model_layer"
    assert DepthSemantics.APPROXIMATE_SENSING_DEPTH == "approximate_sensing_depth"


# --- descriptor invariants (construction-time validation) ---------------------


def _base() -> DatasetDescriptor:
    return get_dataset(GLDAS)


def test_descriptor_rejects_multiple_collections() -> None:
    with pytest.raises(ValueError, match="exactly one collection"):
        replace(_base(), collection_ids=("A/B", "C/D"))


def test_descriptor_rejects_empty_collection_tuple() -> None:
    with pytest.raises(ValueError, match="exactly one collection"):
        replace(_base(), collection_ids=())


def test_descriptor_rejects_deprecated_collection() -> None:
    with pytest.raises(ValueError, match="deprecated"):
        replace(_base(), collection_ids=("NASA/SMAP/SPL4SMGP/007",))


def test_descriptor_rejects_units_that_do_not_match_quantity_kind() -> None:
    with pytest.raises(ValueError, match="units"):
        replace(_base(), native_units="m3 m-3")


def test_descriptor_rejects_invalid_depths_using_task_one_rules() -> None:
    with pytest.raises(ValueError, match="thickness"):
        replace(_base(), depth_top_cm=10.0, depth_bottom_cm=10.0)


def test_descriptor_rejects_valid_range_above_layer_capacity() -> None:
    with pytest.raises(ValueError, match="valid range"):
        replace(_base(), valid_range=(0.0, 150.0))


def test_satellite_descriptor_requires_qc_band() -> None:
    with pytest.raises(ValueError, match="qc band"):
        replace(get_dataset(SMAP_V005), qc_band=None)


def test_derived_volumetric_only_allowed_for_storage_quantities() -> None:
    with pytest.raises(ValueError, match="derived volumetric"):
        replace(get_dataset(SMAP_V005), supports_derived_volumetric=True)


def test_descriptor_rejects_inverted_availability() -> None:
    with pytest.raises(ValueError, match="availability"):
        replace(_base(), documented_first_date=date(2020, 1, 1),
                documented_last_date=date(2019, 12, 31))


def test_descriptor_rejects_blank_required_text() -> None:
    with pytest.raises(ValueError, match="doi"):
        replace(_base(), doi=" ")


def test_descriptor_rejects_empty_limitations() -> None:
    with pytest.raises(ValueError, match="limitations"):
        replace(_base(), limitations=())
