"""Immutable registry of soil moisture datasets (milestone 1).

Each dataset is retrieved, summarised, and trend-tested on its own. The registry
never merges datasets, never spans more than one Earth Engine collection per key,
and keeps SMAP versions 005 and 006 as separate keys (decision D3).

Documented availability is a snapshot of the Earth Engine catalog taken on
``availability_as_of``. Providers must read live availability at runtime; these
dates are for documentation and tests, not for deciding which months exist.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from app.soil_moisture.units import QuantityKind, layer_thickness_m, volumetric_to_storage


class ProductType(StrEnum):
    LAND_SURFACE_MODEL_OPEN_LOOP = "land_surface_model_open_loop"
    SATELLITE_RETRIEVAL = "satellite_retrieval"


class DepthSemantics(StrEnum):
    MODEL_LAYER = "model_layer"
    APPROXIMATE_SENSING_DEPTH = "approximate_sensing_depth"


class UnknownDatasetError(ValueError):
    """Raised for any dataset key that is not in the registry."""


DEPRECATED_COLLECTIONS: frozenset[str] = frozenset({"NASA/SMAP/SPL4SMGP/007"})

_UNITS_BY_QUANTITY: Mapping[QuantityKind, str] = MappingProxyType(
    {
        QuantityKind.LAYER_WATER_STORAGE: "kg m-2",
        QuantityKind.VOLUMETRIC_WATER_CONTENT: "m3 m-3",
    }
)

_AVAILABILITY_AS_OF = date(2026, 11, 13)


@dataclass(frozen=True)
class DatasetDescriptor:
    key: str
    variable: str
    title: str
    product_type: ProductType
    quantity_kind: QuantityKind
    native_units: str
    depth_top_cm: float
    depth_bottom_cm: float
    depth_semantics: DepthSemantics
    collection_ids: tuple[str, ...]
    version: str
    band: str
    qc_band: str | None
    native_grid: str
    nominal_scale_m: float
    temporal_sampling: str
    expected_slots_per_day: int
    documented_first_date: date
    documented_last_date: date | None  # None = ongoing at availability_as_of
    availability_as_of: date
    doi: str
    citation: str
    valid_range: tuple[float, float]
    supports_derived_volumetric: bool
    is_primary: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("key", "variable", "title", "native_units", "version", "band",
                     "native_grid", "temporal_sampling", "doi", "citation"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

        if len(self.collection_ids) != 1 or not self.collection_ids[0].strip():
            raise ValueError("a dataset must reference exactly one collection")
        if set(self.collection_ids) & DEPRECATED_COLLECTIONS:
            raise ValueError(f"collection is deprecated: {self.collection_ids[0]}")

        if self.native_units != _UNITS_BY_QUANTITY[self.quantity_kind]:
            raise ValueError(
                f"units {self.native_units!r} do not match {self.quantity_kind.value}"
            )

        layer_thickness_m(self.depth_top_cm, self.depth_bottom_cm)

        low, high = self.valid_range
        if self.quantity_kind is QuantityKind.LAYER_WATER_STORAGE:
            ceiling = volumetric_to_storage(1.0, self.depth_top_cm, self.depth_bottom_cm)
        else:
            ceiling = 1.0
        if not 0.0 <= low < high <= ceiling:
            raise ValueError(f"valid range must lie within [0, {ceiling}] {self.native_units}")

        if self.product_type is ProductType.SATELLITE_RETRIEVAL and not self.qc_band:
            raise ValueError("satellite retrievals require a qc band")

        if (self.supports_derived_volumetric
                and self.quantity_kind is not QuantityKind.LAYER_WATER_STORAGE):
            raise ValueError("derived volumetric values are only defined for layer water storage")

        if self.nominal_scale_m <= 0:
            raise ValueError("nominal scale must be positive")
        if self.expected_slots_per_day < 1:
            raise ValueError("expected slots per day must be at least 1")

        if (self.documented_last_date is not None
                and self.documented_last_date < self.documented_first_date):
            raise ValueError("documented availability ends before it starts")

        if not self.limitations or not all(t.strip() for t in self.limitations):
            raise ValueError("limitations must be non-empty")

    @property
    def is_model(self) -> bool:
        return self.product_type is ProductType.LAND_SURFACE_MODEL_OPEN_LOOP

    @property
    def is_satellite(self) -> bool:
        return self.product_type is ProductType.SATELLITE_RETRIEVAL


_SMAP_COMMON_LIMITATIONS = (
    "Satellite retrieval from L-band brightness temperature; values are retrieved "
    "volumetric content of roughly the top 5 cm, an approximate sensing depth rather "
    "than a sharp layer boundary.",
    "Not equivalent to GLDAS 0-10 cm soil moisture, including GLDAS values converted "
    "to m3 m-3: depth, footprint (9 km vs 0.25 degree), and method (retrieval vs "
    "model) all differ.",
    "Missing data are non-random: no retrieval outside the daily swath, and retrievals "
    "are skipped or fail quality control over frozen ground, open water, dense "
    "vegetation, urban areas, and radio-frequency interference.",
    "Monthly values are means of valid sampled days, not true monthly means.",
    "AM (06:00 descending) overpass only; AM and PM are never averaged.",
    "Mission accuracy requirement is 0.04 m3 m-3, which can be comparable to "
    "multi-year changes.",
)


_GLDAS = DatasetDescriptor(
    key="gldas_2_1_noah_0_10cm",
    variable="soil_moisture",
    title="GLDAS-2.1 Noah land surface model, 0-10 cm soil moisture (3-hourly, 0.25 degree)",
    product_type=ProductType.LAND_SURFACE_MODEL_OPEN_LOOP,
    quantity_kind=QuantityKind.LAYER_WATER_STORAGE,
    native_units="kg m-2",
    depth_top_cm=0.0,
    depth_bottom_cm=10.0,
    depth_semantics=DepthSemantics.MODEL_LAYER,
    collection_ids=("NASA/GLDAS/V021/NOAH/G025/T3H",),
    version="2.1",
    band="SoilMoi0_10cm_inst",
    qc_band=None,
    native_grid="0.25 degree",
    nominal_scale_m=27830.0,
    temporal_sampling="3-hourly instantaneous (00, 03, ..., 21 UTC)",
    expected_slots_per_day=8,
    documented_first_date=date(2000, 1, 1),  # first image 2000-01-01T03Z
    documented_last_date=None,
    availability_as_of=_AVAILABILITY_AS_OF,
    doi="10.5067/E7TYRXPJKWOQ",
    citation=(
        "Beaudoing, H. and M. Rodell, NASA/GSFC/HSL (2020), GLDAS Noah Land Surface "
        "Model L4 3 hourly 0.25 x 0.25 degree V2.1, Greenbelt, Maryland, USA, Goddard "
        "Earth Sciences Data and Information Services Center (GES DISC). "
        "https://doi.org/10.5067/E7TYRXPJKWOQ"
    ),
    valid_range=(0.0, 100.0),
    supports_derived_volumetric=True,
    is_primary=True,
    limitations=(
        "Land surface model output driven by meteorological forcing; not an observation.",
        "Layer water storage in kg m-2 (1 kg m-2 = 1 mm of water in the 0-10 cm layer).",
        "The derived m3 m-3 value (storage / 100) is a 0-10 cm model layer mean. It is "
        "not equivalent to SMAP's approximately 0-5 cm satellite retrieval.",
        "Forcing changes can create artificial trends: an unexplained shift in AGRMET "
        "climatology after 2011, and a radiation-forcing switch to GALWEM on 2025-06-09.",
        "Recent months may be Early-stream products without GPCP precipitation that are "
        "later superseded; they are provisional and excluded from trend inference.",
        "Whether soil moisture includes frozen water is not stated in the product "
        "documentation (unverified).",
        "Coverage is 60S-90N over modelled land; ocean, inland water, Antarctica, and "
        "ice sheets are not supported.",
        "Errors are largest where forcing is uncertain: high latitudes, high altitudes, "
        "and regions with sparse rain gauges.",
    ),
)

_SMAP_V005 = DatasetDescriptor(
    key="smap_l3e_v005_am",
    variable="soil_moisture",
    title=(
        "SMAP Enhanced L3 Radiometer Global and Polar Grid Daily 9 km EASE-Grid Soil "
        "Moisture, Version 5 (AM overpass)"
    ),
    product_type=ProductType.SATELLITE_RETRIEVAL,
    quantity_kind=QuantityKind.VOLUMETRIC_WATER_CONTENT,
    native_units="m3 m-3",
    depth_top_cm=0.0,
    depth_bottom_cm=5.0,
    depth_semantics=DepthSemantics.APPROXIMATE_SENSING_DEPTH,
    collection_ids=("NASA/SMAP/SPL3SMP_E/005",),
    version="005",
    band="soil_moisture_am",
    qc_band="retrieval_qual_flag_am",
    native_grid="9 km EASE-Grid 2.0 (EE geographic)",
    nominal_scale_m=9000.0,
    temporal_sampling="daily overpass (06:00 local solar time, descending), when retrieved",
    expected_slots_per_day=1,
    documented_first_date=date(2015, 3, 31),
    documented_last_date=date(2023, 12, 2),
    availability_as_of=_AVAILABILITY_AS_OF,
    doi="10.5067/4DQ54OUIJ9DL",
    citation=(
        "O'Neill, P. E., Chan, S., Njoku, E. G., Jackson, T., Bindlish, R., Chaubell, "
        "J. & Colliander, A. (2021). SMAP Enhanced L3 Radiometer Global and Polar Grid "
        "Daily 9 km EASE-Grid Soil Moisture. (SPL3SMP_E, Version 5). Boulder, Colorado "
        "USA. NASA National Snow and Ice Data Center Distributed Active Archive Center. "
        "https://doi.org/10.5067/4DQ54OUIJ9DL"
    ),
    valid_range=(0.0, 1.0),
    supports_derived_volumetric=False,
    is_primary=False,
    limitations=_SMAP_COMMON_LIMITATIONS + (
        "Version 005 only. Months after this collection ends are never filled from "
        "version 006, and the two versions are never concatenated or averaged.",
        "Version 005 is retired at NSIDC; the record ends in December 2023.",
    ),
)

_SMAP_V006 = DatasetDescriptor(
    key="smap_l3e_v006_am",
    variable="soil_moisture",
    title=(
        "SMAP Enhanced L3 Radiometer Global and Polar Grid Daily 9 km EASE-Grid Soil "
        "Moisture, Version 6 (AM overpass)"
    ),
    product_type=ProductType.SATELLITE_RETRIEVAL,
    quantity_kind=QuantityKind.VOLUMETRIC_WATER_CONTENT,
    native_units="m3 m-3",
    depth_top_cm=0.0,
    depth_bottom_cm=5.0,
    depth_semantics=DepthSemantics.APPROXIMATE_SENSING_DEPTH,
    collection_ids=("NASA/SMAP/SPL3SMP_E/006",),
    version="006",
    band="soil_moisture_am",
    qc_band="retrieval_qual_flag_am",
    native_grid="9 km EASE-Grid 2.0 (EE geographic)",
    nominal_scale_m=9000.0,
    temporal_sampling="daily overpass (06:00 local solar time, descending), when retrieved",
    expected_slots_per_day=1,
    documented_first_date=date(2015, 3, 31),
    documented_last_date=None,
    availability_as_of=_AVAILABILITY_AS_OF,
    doi="10.5067/M20OXIZHY3RJ",
    citation=(
        "O'Neill, P. E., Chan, S., Njoku, E. G., Jackson, T., Bindlish, R., Chaubell, "
        "J. & Colliander, A. (2023). SMAP Enhanced L3 Radiometer Global and Polar Grid "
        "Daily 9 km EASE-Grid Soil Moisture. (SPL3SMP_E, Version 6). Boulder, Colorado "
        "USA. NASA National Snow and Ice Data Center Distributed Active Archive Center. "
        "https://doi.org/10.5067/M20OXIZHY3RJ"
    ),
    valid_range=(0.0, 1.0),
    supports_derived_volumetric=False,
    is_primary=False,
    limitations=_SMAP_COMMON_LIMITATIONS + (
        "Version 006 only. Gaps are never filled from version 005, and the two "
        "versions are never concatenated or averaged.",
        "Version 006 was reprocessed back to 2015-03-31 (NSIDC and Earth Engine), so it "
        "overlaps Version 005 for 2015-2023; earlier Earth Engine releases started on "
        "2023-12-04. Values in the overlap can differ between versions.",
    ),
)


DATASETS: Mapping[str, DatasetDescriptor] = MappingProxyType(
    {d.key: d for d in (_GLDAS, _SMAP_V005, _SMAP_V006)}
)


def get_dataset(key: str) -> DatasetDescriptor:
    if not isinstance(key, str) or key not in DATASETS:
        raise UnknownDatasetError(
            f"unknown soil moisture dataset {key!r}; valid keys: {', '.join(sorted(DATASETS))}"
        )
    return DATASETS[key]


def primary_dataset() -> DatasetDescriptor:
    (primary,) = (d for d in DATASETS.values() if d.is_primary)
    return primary
