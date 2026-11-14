from datetime import date, timedelta

import pytest

from app.core.earth_engine import EarthEngineInitializationError
from app.services.soil_moisture_provider import (
    EarthEngineSoilMoistureProvider,
    SoilMoistureRetrievalError,
    UnsupportedLocationError,
    check_supported,
    native_cell,
)
from app.soil_moisture.datasets import get_dataset


GLDAS = get_dataset("gldas_2_1_noah_0_10cm")
SMAP6 = get_dataset("smap_l3e_v006_am")


class FakeManager:
    ee = None

    def __init__(self) -> None:
        self.initialized = 0

    def initialize(self) -> None:
        self.initialized += 1


def month_starts(start: date, end: date) -> list[date]:
    out, m = [], start
    while m < end:
        out.append(m)
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def gldas_rows(start, end, mean=24.0, early=()):
    rows = []
    for m in month_starts(start, end):
        n = 248
        permanent = 0 if m in early else n
        rows.append([m.isoformat(), n, permanent, n, n, n, mean, 290.0])
    return rows


class Recorder:
    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def __call__(self, *args):
        self.calls.append(args)
        return self.fn(*args)


def provider(gldas=None, smap=None, avail=("2000-01-01", "2026-10-15"), neighbours=9, **kw):
    gldas = gldas or Recorder(lambda d, c, s, e: gldas_rows(s, e))
    smap = smap or Recorder(lambda d, c, s, e: {"images": [], "rows": []})
    return EarthEngineSoilMoistureProvider(
        FakeManager(),
        gldas_loader=gldas,
        smap_loader=smap,
        availability_loader=lambda d: list(avail),
        neighbourhood_loader=lambda d, c, m: neighbours,
        **kw,
    )


# --- native cells and coverage -------------------------------------------------


def test_gldas_native_cell_for_yangon() -> None:
    cell = native_cell(GLDAS, 16.8661, 96.1951)
    assert (cell.center_latitude, cell.center_longitude) == (16.875, 96.125)
    assert (cell.south, cell.north, cell.west, cell.east) == (16.75, 17.0, 96.0, 96.25)
    assert cell.crs_transform == [0.25, 0, -180.0, 0, -0.25, 90.0]


def test_smap_native_cell_uses_ee_grid_origin() -> None:
    cell = native_cell(SMAP6, 38.5, -98.5)
    assert cell.cell_size_degrees == 0.08
    assert cell.crs_transform[5] == pytest.approx(85.04450187981062)
    assert cell.south <= 38.5 < cell.north and cell.west <= -98.5 < cell.east


def test_longitude_180_stays_inside_the_grid() -> None:
    assert native_cell(GLDAS, 0.0, 180.0).east == 180.0


def test_unsupported_locations_are_refused_with_reasons() -> None:
    with pytest.raises(UnsupportedLocationError) as exc:
        check_supported(GLDAS, -75.0, 0.0)
    assert exc.value.reason == "outside_dataset_coverage"
    with pytest.raises(UnsupportedLocationError) as exc:
        check_supported(GLDAS, 72.0, -40.0)
    assert exc.value.reason == "unsupported_land_cover_region"
    with pytest.raises(UnsupportedLocationError):
        check_supported(SMAP6, 86.0, 0.0)
    check_supported(SMAP6, -75.0, 0.0)  # SMAP grid itself covers this latitude


# --- GLDAS normalisation ---------------------------------------------------------


def test_gldas_rows_become_monthly_samples() -> None:
    result = provider().fetch(GLDAS, 16.8661, 96.1951, date(2020, 1, 1), date(2020, 4, 1))
    assert [s.month for s in result.samples] == month_starts(date(2020, 1, 1), date(2020, 4, 1))
    first = result.samples[0]
    assert (first.available_images, first.valid_values, first.mean_native, first.nonpermanent_images) == (
        248, 248, 24.0, 0)
    assert result.valid_cells_in_3x3 == 9
    assert result.cell.cell_id == "gldas:292:1104"


def test_gldas_early_images_are_counted_as_nonpermanent() -> None:
    p = provider(gldas=Recorder(lambda d, c, s, e: gldas_rows(s, e, early={date(2020, 2, 1)})))
    samples = p.fetch(GLDAS, 0, 0, date(2020, 1, 1), date(2020, 4, 1)).samples
    assert [s.nonpermanent_images for s in samples] == [0, 248, 0]


def test_gldas_unknown_status_gives_none() -> None:
    rows = lambda d, c, s, e: [[s.isoformat(), 248, 0, 0, 248, 248, 24.0, 290.0]]
    sample = provider(gldas=Recorder(rows)).fetch(GLDAS, 0, 0, date(2020, 1, 1), date(2020, 2, 1)).samples[0]
    assert sample.nonpermanent_images is None


def test_gldas_values_outside_physical_range_are_a_provider_error() -> None:
    rows = lambda d, c, s, e: [[s.isoformat(), 248, 248, 248, 248, 247, 24.0, 290.0]]
    with pytest.raises(SoilMoistureRetrievalError, match="outside"):
        provider(gldas=Recorder(rows)).fetch(GLDAS, 0, 0, date(2020, 1, 1), date(2020, 2, 1))


def test_gldas_masked_cell_yields_no_mean_not_zero() -> None:
    rows = lambda d, c, s, e: [[s.isoformat(), 248, 248, 248, None, None, None, None]]
    sample = provider(gldas=Recorder(rows)).fetch(GLDAS, 0, 0, date(2020, 1, 1), date(2020, 2, 1)).samples[0]
    assert sample.valid_values == 0 and sample.mean_native is None


@pytest.mark.parametrize(
    "rows, message",
    [
        ("not a list", "malformed"),
        ([["2020-01-01", 248]], "malformed"),
        ([["2020-13-01", 248, 248, 248, 248, 248, 24.0, 290.0]], "invalid GLDAS month"),
        ([["2020-01-01", 248, 248, 248, 248, 248, 24.0, 290.0]] * 2, "duplicate"),
        ([["2020-01-01", -1, 0, 0, 0, 0, None, None]], "counts"),
        ([["2020-01-01", 248, 248, 248, 248, 248, float("nan"), 290.0]], "non-finite"),
    ],
)
def test_gldas_malformed_responses_are_rejected(rows, message) -> None:
    with pytest.raises(SoilMoistureRetrievalError, match=message):
        provider(gldas=Recorder(lambda d, c, s, e: rows)).fetch(GLDAS, 0, 0, date(2020, 1, 1), date(2020, 2, 1))


def test_gldas_frozen_months_are_reported_as_diagnostic_only() -> None:
    rows = lambda d, c, s, e: [[m.isoformat(), 248, 248, 248, 248, 248, 30.0, 260.0 if m.month == 1 else 280.0]
                               for m in month_starts(s, e)]
    result = provider(gldas=Recorder(rows)).fetch(GLDAS, 50, 10, date(2020, 1, 1), date(2020, 3, 1))
    assert result.frozen_months == (date(2020, 1, 1),)
    assert result.samples[0].mean_native == 30.0


# --- SMAP quality control --------------------------------------------------------


def smap_payload(start, end, rows):
    days, d = [], start
    while d < end:
        days.append(d.isoformat())
        d += timedelta(days=1)
    return {"images": days, "rows": rows}


def test_smap_quality_control_and_diagnostics() -> None:
    rows = [
        ["2020-06-02", 0.21, 0],      # valid
        ["2020-06-03", 0.65, 0],      # valid but implausible: counted, kept
        ["2020-06-04", 0.30, 1],      # QC rejected
        ["2020-06-05", -9999.0, 0],   # fill-value leak
        ["2020-06-06", 1.5, 0],       # out of physical range
        ["2020-06-07", None, 0],      # no value
    ]
    smap = Recorder(lambda d, c, s, e: smap_payload(s, e, rows))
    result = provider(smap=smap, avail=("2015-03-31", "2026-11-10")).fetch(
        SMAP6, 38.5, -98.5, date(2020, 6, 1), date(2020, 7, 1))
    (sample,) = result.samples
    assert sample.available_images == 30
    assert sample.valid_dates == (date(2020, 6, 2), date(2020, 6, 3))
    assert sample.mean_native == pytest.approx((0.21 + 0.65) / 2)
    d = result.diagnostics
    assert d["qc_rejected_retrievals"] == 1
    assert d["fill_value_leaks"] == 1
    assert d["out_of_range_values"] == 1
    assert d["values_above_0_6"] == 1
    assert d["observation_opportunities"] == 6
    assert result.frozen_months == ()


def test_smap_month_without_retrievals_has_zero_valid_values() -> None:
    smap = Recorder(lambda d, c, s, e: smap_payload(s, e, []))
    (sample,) = provider(smap=smap, avail=("2015-03-31", "2026-11-10")).fetch(
        SMAP6, 16.8661, 96.1951, date(2020, 6, 1), date(2020, 7, 1)).samples
    assert sample.valid_values == 0 and sample.mean_native is None and sample.valid_dates == ()


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"images": ["2020-06-01", "2020-06-01"], "rows": []}, "duplicate SMAP image"),
        ({"images": ["2020-06-01"], "rows": [["2020-06-02", 0.2, 0]]}, "orphan"),
        ({"images": ["2020-06-01"], "rows": [["2020-06-01", 0.2]]}, "malformed SMAP row"),
        ({"rows": []}, "malformed SMAP response"),
        ({"images": [17], "rows": []}, "invalid SMAP date"),
    ],
)
def test_smap_malformed_responses_are_rejected(payload, message) -> None:
    p = provider(smap=Recorder(lambda d, c, s, e: payload), avail=("2015-03-31", "2026-11-10"))
    with pytest.raises(SoilMoistureRetrievalError, match=message):
        p.fetch(SMAP6, 0, 0, date(2020, 6, 1), date(2020, 7, 1))


# --- windows, availability clipping, caching, errors ------------------------------


def test_ten_year_request_uses_five_year_windows() -> None:
    gldas = Recorder(lambda d, c, s, e: gldas_rows(s, e))
    provider(gldas=gldas).fetch(GLDAS, 0, 0, date(2010, 1, 1), date(2020, 1, 1))
    assert [(c[2], c[3]) for c in gldas.calls] == [
        (date(2010, 1, 1), date(2015, 1, 1)), (date(2015, 1, 1), date(2020, 1, 1))]


def test_requests_are_clipped_to_catalog_availability() -> None:
    gldas = Recorder(lambda d, c, s, e: gldas_rows(s, e))
    result = provider(gldas=gldas).fetch(GLDAS, 0, 0, date(1999, 1, 1), date(2000, 3, 1))
    assert gldas.calls[0][2] == date(2000, 1, 1)
    assert [s.month for s in result.samples] == [date(2000, 1, 1), date(2000, 2, 1)]


def test_request_entirely_outside_availability_makes_no_data_calls() -> None:
    gldas = Recorder(lambda d, c, s, e: gldas_rows(s, e))
    result = provider(gldas=gldas).fetch(GLDAS, 0, 0, date(1990, 1, 1), date(1995, 1, 1))
    assert gldas.calls == [] and result.samples == () and result.valid_cells_in_3x3 is None


def test_historical_results_are_cached() -> None:
    gldas = Recorder(lambda d, c, s, e: gldas_rows(s, e))
    p = provider(gldas=gldas)
    a = p.fetch(GLDAS, 16.8661, 96.1951, date(2015, 1, 1), date(2016, 1, 1))
    b = p.fetch(GLDAS, 16.87, 96.20, date(2015, 1, 1), date(2016, 1, 1))  # same native cell
    assert a is b and len(gldas.calls) == 1


def test_recent_or_provisional_results_are_not_cached() -> None:
    gldas = Recorder(lambda d, c, s, e: gldas_rows(s, e))
    p = provider(gldas=gldas)
    p.fetch(GLDAS, 0, 0, date(2026, 1, 1), date(2026, 11, 1))
    p.fetch(GLDAS, 0, 0, date(2026, 1, 1), date(2026, 11, 1))
    assert len(gldas.calls) == 2


def test_availability_is_cached() -> None:
    calls = []
    p = EarthEngineSoilMoistureProvider(
        FakeManager(), availability_loader=lambda d: calls.append(1) or ["2000-01-01", "2026-10-15"])
    p.availability(GLDAS)
    p.availability(GLDAS)
    assert len(calls) == 1


@pytest.mark.parametrize("raw", [None, ["2000-01-01"], ["x", "2026-10-15"], [1, 2]])
def test_malformed_availability_is_rejected(raw) -> None:
    p = EarthEngineSoilMoistureProvider(FakeManager(), availability_loader=lambda d: raw)
    with pytest.raises(SoilMoistureRetrievalError, match="availability"):
        p.availability(GLDAS)


def test_unexpected_loader_errors_are_wrapped_and_sanitised() -> None:
    def boom(*args):
        raise RuntimeError("secret project details")
    p = provider(gldas=Recorder(boom))
    with pytest.raises(SoilMoistureRetrievalError) as exc:
        p.fetch(GLDAS, 0, 0, date(2020, 1, 1), date(2020, 2, 1))
    assert "secret" not in str(exc.value)


def test_earth_engine_errors_pass_through() -> None:
    def fail(*args):
        raise EarthEngineInitializationError("Earth Engine initialization failed")
    p = provider(gldas=Recorder(fail))
    with pytest.raises(EarthEngineInitializationError):
        p.fetch(GLDAS, 0, 0, date(2020, 1, 1), date(2020, 2, 1))


def test_malformed_neighbourhood_count_is_rejected() -> None:
    with pytest.raises(SoilMoistureRetrievalError, match="neighbourhood"):
        provider(neighbours=12).fetch(GLDAS, 0, 0, date(2020, 1, 1), date(2020, 2, 1))


def test_unsupported_location_is_refused_before_any_retrieval() -> None:
    gldas = Recorder(lambda d, c, s, e: gldas_rows(s, e))
    with pytest.raises(UnsupportedLocationError):
        provider(gldas=gldas).fetch(GLDAS, -80, 0, date(2020, 1, 1), date(2021, 1, 1))
    assert gldas.calls == []


def test_parallel_windows_give_identical_ordered_results() -> None:
    import threading, time as _t
    seen_threads = set()

    def slow(d, c, s, e):
        seen_threads.add(threading.get_ident())
        _t.sleep(0.05)
        return gldas_rows(s, e)

    serial = provider(gldas=Recorder(slow), max_parallel_windows=1).fetch(GLDAS, 0, 0, date(2005, 1, 1), date(2020, 1, 1))
    parallel = provider(gldas=Recorder(slow), max_parallel_windows=3).fetch(GLDAS, 0, 0, date(2005, 1, 1), date(2020, 1, 1))
    assert parallel.samples == serial.samples
    assert [s.month for s in parallel.samples] == sorted(s.month for s in parallel.samples)
    assert len(seen_threads) >= 2


def test_parallel_window_error_propagates() -> None:
    def fail_second(d, c, s, e):
        if s.year >= 2010:
            raise RuntimeError("boom")
        return gldas_rows(s, e)
    with pytest.raises(SoilMoistureRetrievalError):
        provider(gldas=Recorder(fail_second)).fetch(GLDAS, 0, 0, date(2005, 1, 1), date(2020, 1, 1))
