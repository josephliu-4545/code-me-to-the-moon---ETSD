"""Catalog of datasets per environmental variable, with provenance and comparability.

Every collection ID, band, unit and date below was checked against the live Earth
Engine catalog and the provider documentation on 2026-11-14. Primary datasets
are analysed by the existing, validated /api/v1 pipelines; alternative datasets use
the generic monthly Earth Engine pipeline in app/comparison/providers.py.
"""

from dataclasses import dataclass, field
from typing import Literal


Backend = Literal["v1", "ee_monthly"]
Method = Literal["subdaily_mean", "monthly_value", "daily_sum", "monthly_sum"]


@dataclass(frozen=True)
class DatasetEntry:
    key: str
    variable: str
    name: str
    provider: str
    collection_id: str
    version: str
    measurement: str
    product_type: str                 # reanalysis | model | satellite | satellite_gauge_merge | ...
    native_units: str
    units: str                        # units of the annual value returned
    slope_units: str
    temporal_resolution: str
    spatial_resolution: str
    available_from: str
    available_to: str | None          # None = ongoing (read live where possible)
    coverage_note: str
    quality_control: str
    processing: str
    lineage: str
    shared_inputs: tuple[str, ...]
    limitations: tuple[str, ...]
    citation: str
    doi: str | None
    license: str
    comparable_quantity: str          # datasets with the same value may be compared numerically
    is_primary: bool = False
    modes: tuple[str, ...] = ("point",)
    backend: Backend = "v1"
    # v1-backed datasets
    v1_variable: str | None = None
    v1_dataset: str | None = None
    # ee_monthly datasets
    method: Method | None = None
    band: str | None = None
    crs_transform: tuple[float, ...] | None = None
    scale: float = 1.0                # canonical = native * scale + offset
    offset: float = 0.0
    valid_range: tuple[float, float] | None = None   # canonical units, per sample
    latitude_limits: tuple[float, float] = (-90.0, 90.0)
    status_property: str | None = None
    min_month_coverage: float = 1.0
    max_years: int = 30
    annual_rule: Literal["mean", "sum"] = "mean"
    extra: dict = field(default_factory=dict)


REANALYSIS_OBS = "global observing system assimilated by reanalyses (radiosondes, satellites, surface stations)"

_TEMPERATURE = (
    DatasetEntry(
        key="nasa_power_t2m", variable="temperature", name="NASA POWER 2 m air temperature (T2M)",
        provider="NASA Langley Research Center (POWER project)", collection_id="POWER API daily point T2M (AG community)",
        version="POWER API v2 (MERRA-2 based)",
        measurement="Daily mean 2 m air temperature; annual value = mean of 12 monthly means",
        product_type="reanalysis-based model estimate", native_units="°C", units="°C", slope_units="°C/year",
        temporal_resolution="daily", spatial_resolution="0.5° × 0.625° grid cell", available_from="1981-01-01", available_to=None,
        coverage_note="global",
        quality_control="POWER fill values removed; months need ≥80% of days and years ≥90% of days, 12 of 12 months",
        processing="NASA POWER daily point series; existing validated pipeline (/api/v1/temperature/trend)",
        lineage="NASA GMAO MERRA-2 reanalysis",
        shared_inputs=(REANALYSIS_OBS,),
        limitations=("Model/reanalysis estimate for a coarse grid cell, not a weather station.",),
        citation="NASA POWER Project, NASA Langley Research Center (https://power.larc.nasa.gov/)", doi=None,
        license="NASA open data policy", comparable_quantity="air_temperature_2m", is_primary=True,
        v1_variable="temperature",
    ),
    DatasetEntry(
        key="gldas_2_1_tair", variable="temperature", name="GLDAS-2.1 forcing air temperature (Tair_f_inst)",
        provider="NASA GSFC Hydrological Sciences Laboratory / GES DISC", collection_id="NASA/GLDAS/V021/NOAH/G025/T3H",
        version="2.1",
        measurement="Near-surface air temperature forcing (K, instantaneous every 3 h); annual value = mean of 12 monthly means of 3-hourly states",
        product_type="land-model forcing from an operational atmospheric analysis", native_units="K", units="°C", slope_units="°C/year",
        temporal_resolution="3-hourly instantaneous", spatial_resolution="0.25° native grid cell", available_from="2000-01-01", available_to=None,
        coverage_note="modelled land only, 60°S–90°N; ocean and inland water masked",
        quality_control="unmasked values in 200–335 K; a month needs ≥90% of its 3-hourly states; months containing any non-'permanent' (Early-stream) image are provisional and excluded from trends; 12 of 12 months",
        processing="Earth Engine: monthly mean of 3-hourly values at the native 0.25° cell containing the point; K → °C (−273.15)",
        lineage="NOAA/NCEP GDAS atmospheric analysis (GLDAS-2.1 forcing)",
        shared_inputs=(REANALYSIS_OBS,),
        limitations=(
            "Forcing field for a land model, derived from the GDAS operational analysis; not an observation.",
            "Mean of eight instantaneous states per day approximates, but is not identical to, a daily mean.",
            "Cells over water or ice sheets have no values.",
        ),
        citation="Beaudoing, H. and M. Rodell, NASA/GSFC/HSL (2020), GLDAS Noah Land Surface Model L4 3 hourly 0.25 x 0.25 degree V2.1, GES DISC",
        doi="10.5067/E7TYRXPJKWOQ", license="NASA open data policy", comparable_quantity="air_temperature_2m",
        backend="ee_monthly", method="subdaily_mean", band="Tair_f_inst",
        crs_transform=(0.25, 0, -180.0, 0, -0.25, 90.0), offset=-273.15, valid_range=(200 - 273.15, 335 - 273.15),
        latitude_limits=(-60.0, 90.0), status_property="status", min_month_coverage=0.90, max_years=27,
        extra={"expected_slots_per_day": 8, "record_start_missing_slots": {"2000-01": 1}},
    ),
    DatasetEntry(
        key="era5_land_t2m", variable="temperature", name="ERA5-Land monthly 2 m air temperature",
        provider="ECMWF / Copernicus Climate Change Service (via Google Earth Engine)", collection_id="ECMWF/ERA5_LAND/MONTHLY_AGGR",
        version="ERA5-Land (monthly aggregates of hourly data)",
        measurement="Monthly mean of hourly 2 m air temperature (K); annual value = mean of 12 monthly means",
        product_type="reanalysis (land component)", native_units="K", units="°C", slope_units="°C/year",
        temporal_resolution="monthly (mean of hourly)", spatial_resolution="0.1° native grid cell", available_from="1950-01-01", available_to=None,
        coverage_note="global grid; values over the sampled cell",
        quality_control="unmasked monthly values in 180–340 K; 12 of 12 months",
        processing="Earth Engine: monthly value at the native 0.1° cell containing the point; K → °C (−273.15)",
        lineage="ECMWF ERA5 reanalysis forcing a land-surface model (ERA5-Land)",
        shared_inputs=(REANALYSIS_OBS,),
        limitations=(
            "Reanalysis estimate (not NASA); temperature is interpolated from the lowest model level.",
            "Use requires the notice 'Generated using Copernicus Climate Change Service information'.",
        ),
        citation="Muñoz Sabater, J. (2019): ERA5-Land monthly averaged data from 1981 to present. Copernicus Climate Change Service (C3S) Climate Data Store",
        doi="10.24381/cds.68d2bb30", license="Copernicus C3S/CAMS licence (attribution required)", comparable_quantity="air_temperature_2m",
        backend="ee_monthly", method="monthly_value", band="temperature_2m",
        crs_transform=(0.1, 0, -180.05, 0, -0.1, 90.05), offset=-273.15, valid_range=(180 - 273.15, 340 - 273.15), max_years=50,
    ),
)

_PRECIPITATION = (
    DatasetEntry(
        key="gpm_imerg_v07", variable="precipitation", name="GPM IMERG V07 Final, monthly",
        provider="NASA GSFC (GPM mission)", collection_id="NASA/GPM_L3/IMERG_MONTHLY_V07", version="V07 Final",
        measurement="Monthly mean precipitation rate → monthly accumulation; annual value = sum of 12 months",
        product_type="satellite–gauge merged estimate", native_units="mm/hour", units="mm/year", slope_units="mm/year²",
        temporal_resolution="monthly", spatial_resolution="0.1° native grid cell", available_from="2000-06-01", available_to=None,
        coverage_note="global grid",
        quality_control="12 valid monthly products in a complete calendar year",
        processing="existing validated pipeline (/api/v1/precipitation/trend)",
        lineage="passive-microwave and infrared satellite constellation, calibrated with GPCC monthly gauge analyses",
        shared_inputs=("geostationary infrared imagery", "rain-gauge analyses"),
        limitations=("Satellite–gauge estimate for a 0.1° cell, not a gauge reading.",),
        citation="Huffman, G. J. et al., GPM IMERG Final Precipitation L3 1 month 0.1 degree V07, GES DISC",
        doi="10.5067/GPM/IMERG/3B-MONTH/07", license="NASA open data policy", comparable_quantity="precipitation_total",
        is_primary=True, modes=("point", "region"), v1_variable="precipitation", annual_rule="sum", max_years=30,
    ),
    DatasetEntry(
        key="chirps_v2_daily", variable="precipitation", name="CHIRPS daily precipitation",
        provider="UCSB Climate Hazards Center (via Google Earth Engine)", collection_id="UCSB-CHG/CHIRPS/DAILY", version="2.0",
        measurement="Daily precipitation (mm/day) summed to monthly totals; annual value = sum of 12 months",
        product_type="infrared satellite–station blend", native_units="mm/day", units="mm/year", slope_units="mm/year²",
        temporal_resolution="daily", spatial_resolution="0.05° native grid cell", available_from="1981-01-01", available_to=None,
        coverage_note="quasi-global land, 50°S–50°N only",
        quality_control="unmasked daily values ≥0; a month counts only if every day has a value; 12 of 12 months",
        processing="Earth Engine: sum of daily values per month at the native 0.05° cell containing the point",
        lineage="thermal-infrared cold-cloud duration with CHPclim climatology, blended with station rain gauges",
        shared_inputs=("geostationary infrared imagery", "rain-gauge analyses"),
        limitations=(
            "Not a NASA product. Available only between 50°S and 50°N.",
            "Infrared-based estimates can be weaker for warm-cloud or orographic rain; gauge density varies by region.",
        ),
        citation="Funk, C. et al. (2015). The climate hazards infrared precipitation with stations—a new environmental record for monitoring extremes. Scientific Data 2, 150066",
        doi="10.1038/sdata.2015.66", license="public domain (CC0 waiver)", comparable_quantity="precipitation_total",
        backend="ee_monthly", method="daily_sum", band="precipitation",
        crs_transform=(0.05, 0, -180.0, 0, -0.05, 50.0), valid_range=(0.0, 2000.0), latitude_limits=(-50.0, 50.0),
        annual_rule="sum", max_years=30,
    ),
    DatasetEntry(
        key="era5_land_tp", variable="precipitation", name="ERA5-Land monthly total precipitation",
        provider="ECMWF / Copernicus Climate Change Service (via Google Earth Engine)", collection_id="ECMWF/ERA5_LAND/MONTHLY_AGGR",
        version="ERA5-Land (monthly sums)",
        measurement="Monthly accumulated precipitation (m) → mm; annual value = sum of 12 months",
        product_type="reanalysis model output (precipitation not assimilated)", native_units="m/month", units="mm/year", slope_units="mm/year²",
        temporal_resolution="monthly (sum of hourly accumulations)", spatial_resolution="0.1° native grid cell", available_from="1950-01-01", available_to=None,
        coverage_note="global grid",
        quality_control="unmasked monthly totals; negative totals (documented GRIB packing artefact) are rejected as invalid, never clipped; 12 of 12 months",
        processing="Earth Engine: monthly total at the native 0.1° cell containing the point; m → mm (×1000)",
        lineage="ECMWF ERA5 reanalysis model precipitation (forecast field, no precipitation assimilation)",
        shared_inputs=(REANALYSIS_OBS,),
        limitations=(
            "Model-generated precipitation; biases are common in convective and mountainous regions.",
            "Not a NASA product. Use requires the notice 'Generated using Copernicus Climate Change Service information'.",
        ),
        citation="Muñoz Sabater, J. (2019): ERA5-Land monthly averaged data from 1981 to present. Copernicus Climate Change Service (C3S) Climate Data Store",
        doi="10.24381/cds.68d2bb30", license="Copernicus C3S/CAMS licence (attribution required)", comparable_quantity="precipitation_total",
        backend="ee_monthly", method="monthly_sum", band="total_precipitation_sum",
        crs_transform=(0.1, 0, -180.05, 0, -0.1, 90.05), scale=1000.0, valid_range=(0.0, 5000.0),
        annual_rule="sum", max_years=50,
    ),
)

_SOIL = tuple(
    DatasetEntry(
        key=k, variable="soil_moisture", name=n, provider=p, collection_id=c, version=v, measurement=m,
        product_type=pt, native_units=u, units=u, slope_units=f"{u}/year", temporal_resolution=tr,
        spatial_resolution=sr, available_from=af, available_to=at, coverage_note=cov,
        quality_control=qc, processing="existing validated pipeline (/api/v1/soil-moisture/trend)",
        lineage=lin, shared_inputs=si, limitations=lim, citation=cit, doi=doi, license="NASA open data policy",
        comparable_quantity=cq, is_primary=primary, v1_variable="soil_moisture", v1_dataset=k, max_years=27,
    )
    for (k, n, p, c, v, m, pt, u, tr, sr, af, at, cov, qc, lin, si, lim, cit, doi, cq, primary) in (
        ("gldas_2_1_noah_0_10cm", "GLDAS-2.1 Noah 0–10 cm soil moisture", "NASA GSFC HSL / GES DISC",
         "NASA/GLDAS/V021/NOAH/G025/T3H", "2.1", "Water stored in the 0–10 cm model layer", "land surface model (open loop)",
         "kg m-2", "3-hourly", "0.25° native grid cell", "2000-01-01", None, "modelled land, 60°S–90°N",
         "≥90% of 3-hourly states per month; provisional months excluded; 12 of 12 months",
         "Noah land model forced by GDAS, GPCP precipitation and AGRMET radiation", ("GPCP precipitation", REANALYSIS_OBS),
         ("Model state, not an observation; forcing changes after 2011 and on 2025-06-09 can create artificial trends.",),
         "Beaudoing & Rodell (2020), GLDAS Noah L4 3-hourly 0.25° V2.1", "10.5067/E7TYRXPJKWOQ", "soil_moisture_layer_storage_0_10cm", True),
        ("smap_l3e_v006_am", "SMAP L3 Enhanced V006 (AM) soil moisture", "NASA JPL / NSIDC DAAC",
         "NASA/SMAP/SPL3SMP_E/006", "006", "Retrieved volumetric water content of roughly the top 5 cm", "satellite retrieval",
         "m3 m-3", "daily overpass", "9 km native grid cell", "2015-03-31", None, "global land; no retrieval over water, ice or frozen ground",
         "recommended-quality flag; ≥8 valid days per month spread across the month; 12 of 12 months",
         "SMAP L-band radiometer brightness temperature (Version 6 processing)", ("SMAP L-band radiometer",),
         ("Gappy and non-random missingness (frozen ground, dense vegetation, urban, RFI).",),
         "O'Neill et al. (2023), SPL3SMP_E Version 6, NSIDC DAAC", "10.5067/M20OXIZHY3RJ", "soil_moisture_volumetric_surface", False),
        ("smap_l3e_v005_am", "SMAP L3 Enhanced V005 (AM) soil moisture", "NASA JPL / NSIDC DAAC",
         "NASA/SMAP/SPL3SMP_E/005", "005", "Retrieved volumetric water content of roughly the top 5 cm", "satellite retrieval",
         "m3 m-3", "daily overpass", "9 km native grid cell", "2015-03-31", "2023-12-02", "global land; record ends 2023-12-02",
         "recommended-quality flag; ≥8 valid days per month spread across the month; 12 of 12 months",
         "SMAP L-band radiometer brightness temperature (Version 5 processing)", ("SMAP L-band radiometer",),
         ("Retired version; same instrument as V006 with different processing.",),
         "O'Neill et al. (2021), SPL3SMP_E Version 5, NSIDC DAAC", "10.5067/4DQ54OUIJ9DL", "soil_moisture_volumetric_surface", False),
    )
)

CATALOG: dict[str, tuple[DatasetEntry, ...]] = {
    "temperature": _TEMPERATURE,
    "precipitation": _PRECIPITATION,
    "soil_moisture": _SOIL,
}

# Variables with a single implemented dataset, and why alternatives are not offered yet.
NOT_YET_COMPARABLE: dict[str, str] = {
    "relative_humidity": "Candidate alternatives (ERA5-Land dewpoint, GLDAS specific humidity) need a documented humidity conversion; planned.",
    "extreme_heat": "The percentile method needs daily maximum temperature; GLDAS has no daily maximum and ERA5-Land daily maxima are not yet integrated; planned.",
    "ndvi": "Candidates verified in Earth Engine (MODIS Aqua MYD13Q1 — same algorithm, related lineage; VIIRS VNP13A1 — different sensor, from 2012) need the NDVI regional pipeline extended; planned.",
}

# Pairs whose relationship is known to be stronger than shared inputs alone suggest.
SAME_LINEAGE: dict[frozenset[str], str] = {
    frozenset({"smap_l3e_v005_am", "smap_l3e_v006_am"}):
        "Same instrument and algorithm family, different processing versions: not independent evidence.",
}


def entries(variable: str) -> tuple[DatasetEntry, ...]:
    return CATALOG.get(variable, ())


def find(variable: str, key: str) -> DatasetEntry | None:
    return next((e for e in entries(variable) if e.key == key), None)


def relationship(a: DatasetEntry, b: DatasetEntry) -> tuple[str, str]:
    """Classify product lineage: same_lineage, partially_related or independent."""
    same = SAME_LINEAGE.get(frozenset({a.key, b.key}))
    if same:
        return "same_lineage", same
    shared = sorted(set(a.shared_inputs) & set(b.shared_inputs))
    if shared:
        return "partially_related", ("Different production systems that share inputs (" + "; ".join(shared)
                                     + "). Agreement is supporting but not fully independent evidence.")
    return "independent", "No shared primary inputs identified in the documentation."
