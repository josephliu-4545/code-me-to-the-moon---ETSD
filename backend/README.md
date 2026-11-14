# NASA Earth System Trend Detective Backend

FastAPI backend for retrieving quality-filtered NASA MODIS MOD13Q1.061 NDVI
observations through Google Earth Engine.

## Setup (PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Set `EE_PROJECT_ID` in `.env` or in the process environment. Existing Google
Earth Engine credentials are reused; the application does not run
`ee.Authenticate()`.

## Run

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the generated API documentation.

## Example requests

```text
GET http://127.0.0.1:8000/
GET http://127.0.0.1:8000/health
GET http://127.0.0.1:8000/api/v1/ndvi?latitude=16.8661&longitude=96.1951&start_date=2020-01-01&end_date=2021-01-01&radius_km=5
GET http://127.0.0.1:8000/api/v1/ndvi/trend?latitude=16.8661&longitude=96.1951&start_date=2015-01-01&end_date=2025-01-01&radius_km=5
```

The end date is exclusive. Raw NDVI observations (`/api/v1/ndvi`) are limited to
10 years; NDVI trends (fetched one calendar year at a time) and precipitation
are limited to 30 years (`NDVI_TREND_MAX_DATE_RANGE_YEARS`,
`PRECIPITATION_MAX_DATE_RANGE_YEARS`). Radii are limited to 100 km by default.

## Annual summaries and trends

`/api/v1/ndvi/trend` keeps nominal MODIS slots, catalog image availability,
quality-filtered regional values, and per-observation spatial pixel support as
separate coverage concepts. Annual NDVI is the equal-weight mean of represented
monthly means.

Default inference eligibility requires at least 9 represented months, 70% of
nominal slots with valid regional values, all four calendar quarters, and a
complete calendar year. These are configurable policy choices, not universal
scientific standards. Ineligible and partial years still receive descriptive
annual summaries with explicit exclusion reasons.

A descriptive Theil–Sen slope requires 3 eligible years. Standard two-sided
Mann–Kendall inference is attempted only with at least 8 eligible years and
adequate serial-dependence diagnostics. A nonsignificant autocorrelation
diagnostic is not presented as proof of independence.

## Tests

Run mocked tests without Earth Engine access:

```powershell
python -m pytest -m "not integration"
```

Run the opt-in live test using existing credentials:

```powershell
$env:RUN_EE_INTEGRATION = "1"
$env:EE_PROJECT_ID = "your-google-cloud-project-id"
python -m pytest -m integration -v
```

# NASA POWER relative humidity

The backend exposes `GET /api/v1/relative-humidity` for daily or monthly NASA
POWER `RH2M` point estimates and `GET /api/v1/relative-humidity/trend` for
annual trend analysis. Trend retrieval always explicitly requests daily Local
Solar Time (`LST`) values. LST is solar time, not the location's civil time
zone.

POWER RH2M values are 2 m gridded meteorological estimates at the native
0.5 by 0.625 degree source resolution. They are not station observations,
5 km buffer means, or administrative-region averages. Missing observations
are excluded without interpolation.

Monthly means are calculated from valid daily observations. Annual means are
the equal-weighted mean of the monthly means. Initial configurable screening
requires a complete calendar year, all 12 months, at least 90% valid days in
the year, and at least 80% valid days in every month. These are application
policies, not universal scientific standards. Ineligible years remain in the
response as descriptive summaries with stable reason codes.

Relevant settings include `POWER_BASE_URL`, `POWER_HTTP_TIMEOUT_SECONDS`,
`POWER_REQUEST_TIMEOUT_SECONDS`, `POWER_MAX_CONCURRENT_OPERATIONS`,
`POWER_MAX_DATE_RANGE_YEARS`, `POWER_WINDOW_YEARS`,
`RH_MIN_ANNUAL_COVERAGE`, and `RH_MIN_MONTHLY_COVERAGE`.

Live POWER tests are opt-in and require no credentials:

```powershell
$env:RUN_POWER_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -m power_integration -v
```

Recent near-real-time POWER meteorology may later be replaced by improved
climate-quality products. Annual means can also conceal important seasonal
humidity changes, and short annual series provide weak autocorrelation
diagnostics.

## Air temperature and unusually hot days

`GET /api/v1/temperature` and `/api/v1/temperature/trend` use NASA POWER
`T2M`. Trends are built from daily LST values; annual values are equal-weighted
means of valid monthly means. Slopes are returned in °C/year with a direct
°C/decade conversion.

`GET /api/v1/extreme-heat` and `/api/v1/extreme-heat/trend` use daily
`T2M_MAX`. Hot days exceed a calendar-day 90th-percentile threshold calculated
from 1991–2020 with a centered five-day window and Type-8 quantiles. In-base
years use the exhaustive Zhang-style bootstrap over all 29 replacement years.
Raw counts remain separate from adjusted exceedance percentages. This metric
is not a heatwave definition.

Reference thresholds are cached per application service using a bounded cache
keyed by location, dataset/parameter, LST, baseline, and method version. The
75% reference-window availability threshold and annual/monthly missing-day
limits are configurable.

# Precipitation (NASA GPM IMERG V07)

The additive endpoints `GET /api/v1/precipitation` and `GET /api/v1/precipitation/trend` use the explicitly pinned Earth Engine collection `NASA/GPM_L3/IMERG_MONTHLY_V07`. They sample the native 0.1° grid cell containing the requested coordinate; no 5 km spatial resolution is implied.

The monthly product supplies a calendar-month mean rate in mm/hour. The service converts it to mm/month using 24 multiplied by the actual number of calendar days, including leap-year February. Annual totals require all twelve valid Final monthly values. Partial years and missing months remain descriptive and include stable exclusion reasons; values are never interpolated or silently treated as zero.

Run ordinary tests with `python -m pytest -m "not integration" -q`. Live Earth Engine tests are opt-in with `RUN_EE_INTEGRATION=1` and `EE_PROJECT_ID`; existing local Earth Engine authentication is reused. The implementation does not call `ee.Authenticate()` or expose credentials.

The trend endpoint reuses the shared Theil–Sen, Mann–Kendall, tie, confidence-interval, and serial-dependence safeguards. A slope is reported as mm/year²: change in the annual accumulated total per calendar year. Monthly accumulation is not precipitation intensity, and the gridded satellite–gauge estimate is not a station observation or administrative-region average.


# Soil moisture (GLDAS-2.1 Noah, SMAP L3 Enhanced V005 / V006)

Three separate datasets that are never merged or gap-filled from each other. They are listed by `GET /api/v1/soil-moisture/datasets`.

* `GET /api/v1/soil-moisture?dataset=…&latitude=…&longitude=…&start_date=YYYY-MM-01&end_date=YYYY-MM-01` returns monthly records and annual summaries; `/trend` adds the Theil–Sen / Mann–Kendall result. For GLDAS it also adds a derived layer-mean m³ m⁻³ trend.
* `GET /api/v1/soil-moisture/compare?datasets=a,b[,c]&…` returns a descriptive comparison only: anomaly correlation (needs ≥ 36 common months), mean difference labelled "not error", and slope-sign agreement.
* Values come from the exact native grid cell containing the point (0.25° GLDAS, 9 km SMAP). A masked or quality-failing cell is reported as `no_valid_land_values`, with no substitution. GLDAS months containing any non-`permanent` catalog image are provisional and excluded from trends. SMAP months need ≥ 8 quality-passing AM days, including one in each third of the month.

# Unified API (v2) and regions

`/api/v2/variables`, `/api/v2/analysis`, `/api/v2/relationships` and `/api/v2/geocode` serve the frontend. They call the v1 endpoints in-process, normalise them into one envelope that keeps each variable's own definition, and cache results (labelled `cached_nasa_retrieval` with the retrieval time). `GET /api/v1/precipitation/region/trend?west&south&east&north&start_date&end_date` computes area-weighted IMERG regional means over valid pixels. Months below the valid-area threshold (default 95%) are missing, never zero.
