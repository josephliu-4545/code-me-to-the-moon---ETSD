from datetime import date, timedelta

import pytest

from app.power.models import PowerParameter, PowerPayload, PowerPointQuery
from app.services.temperature_service import TemperatureDataError, TemperatureService


class FakeClient:
    def __init__(self, payload): self.payload = payload; self.parameters = []
    def fetch_daily_point(self, query, parameter): self.parameters.append(parameter); return self.payload
    def fetch_monthly_point(self, query, parameter): self.parameters.append(parameter); return self.payload


def _year(year: int, base: float) -> PowerPayload:
    values = {}
    day, end = date(year, 1, 1), date(year + 1, 1, 1)
    while day < end:
        values[day.strftime("%Y%m%d")] = base + day.month
        day += timedelta(days=1)
    return PowerPayload(values, "C", -999, "LST", PowerParameter.T2M)


def test_temperature_uses_t2m_and_equal_month_means() -> None:
    client = FakeClient(_year(2020, 20))
    service = TemperatureService(client)
    result = service.analyze(PowerPointQuery(0, 0, date(2020, 1, 1), date(2021, 1, 1)))
    assert client.parameters == [PowerParameter.T2M]
    assert result.annual_summaries[0].annual_value == pytest.approx(26.5)
    assert result.annual_summaries[0].expected_observations == 366
    assert result.annual_summaries[0].value_units == "°C"


@pytest.mark.parametrize("unit", ["%", None, "K"])
def test_temperature_rejects_unexpected_units(unit) -> None:
    service = TemperatureService(FakeClient(PowerPayload({"20200101": 25}, unit)))
    with pytest.raises(TemperatureDataError):
        service.fetch_daily(PowerPointQuery(0, 0, date(2020, 1, 1), date(2020, 1, 2)))


def test_temperature_trend_reports_celsius_per_year() -> None:
    values = {}
    for year in range(2010, 2020):
        values.update(_year(year, float(year - 2010)).values)
    service = TemperatureService(FakeClient(PowerPayload(values, "C", -999, "LST", PowerParameter.T2M)))
    result = service.analyze(PowerPointQuery(0, 0, date(2010, 1, 1), date(2020, 1, 1)))
    assert result.trend.theil_sen.slope == pytest.approx(1.0)
    assert result.trend.theil_sen.slope_units == "°C/year"


# --- fetch_daily validation and performance regression (Phase 1, fix 1) -------


def _query(start: date, end: date) -> PowerPointQuery:
    return PowerPointQuery(0, 0, start, end)


def test_fetch_daily_rejects_duplicate_dates() -> None:
    # Two keys that parse to the same calendar day (the parser reads the first 8 characters).
    payload = PowerPayload({"20200101": 25.0, "20200101Z": 26.0}, "C", -999, "LST", PowerParameter.T2M)
    with pytest.raises(TemperatureDataError, match="duplicate or out-of-range date"):
        TemperatureService(FakeClient(payload)).fetch_daily(_query(date(2020, 1, 1), date(2020, 1, 3)))


@pytest.mark.parametrize("key", ["20191231", "20200103", "20210101"])
def test_fetch_daily_rejects_dates_outside_the_half_open_query(key) -> None:
    payload = PowerPayload({"20200101": 25.0, key: 26.0}, "C", -999, "LST", PowerParameter.T2M)
    with pytest.raises(TemperatureDataError, match="duplicate or out-of-range date"):
        TemperatureService(FakeClient(payload)).fetch_daily(_query(date(2020, 1, 1), date(2020, 1, 3)))


def test_fetch_daily_reports_absent_and_fill_days_as_missing_in_order() -> None:
    payload = PowerPayload(
        {"20200228": 25.0, "20200229": -999.0, "20200302": 27.5},  # 2020-03-01 absent; leap day filled
        "C", -999, "LST", PowerParameter.T2M,
    )
    series = TemperatureService(FakeClient(payload)).fetch_daily(_query(date(2020, 2, 28), date(2020, 3, 3)))
    assert [(o.date, o.value) for o in series.observations] == [(date(2020, 2, 28), 25.0), (date(2020, 3, 2), 27.5)]
    assert series.expected_count == 4
    assert series.returned_count == 3
    assert series.missing_dates == (date(2020, 2, 29), date(2020, 3, 1))
    assert series.time_standard == "LST"


def test_fetch_daily_honours_a_declared_non_default_fill_value() -> None:
    payload = PowerPayload({"20200101": -9999.0, "20200102": 21.0}, "C", -9999.0, "LST", PowerParameter.T2M)
    series = TemperatureService(FakeClient(payload)).fetch_daily(_query(date(2020, 1, 1), date(2020, 1, 3)))
    assert [o.date for o in series.observations] == [date(2020, 1, 2)]
    assert series.missing_dates == (date(2020, 1, 1),)


def test_fetch_daily_scales_linearly_for_a_45_year_record() -> None:
    # Regression guard for the former O(days^2) membership check (about 10 s for
    # 1981-2025). Linear parsing takes well under a second; the bound is generous.
    import time

    values: dict[str, float] = {}
    day = date(1981, 1, 1)
    while day < date(2026, 1, 1):
        values[day.strftime("%Y%m%d")] = 20.0 + day.month
        day += timedelta(days=1)
    service = TemperatureService(FakeClient(PowerPayload(values, "C", -999, "LST", PowerParameter.T2M)))
    started = time.perf_counter()
    series = service.fetch_daily(_query(date(1981, 1, 1), date(2026, 1, 1)))
    elapsed = time.perf_counter() - started
    assert series.expected_count == len(values) == 16436
    assert series.missing_dates == ()
    assert elapsed < 2.0, f"fetch_daily took {elapsed:.2f} s for 45 years"
