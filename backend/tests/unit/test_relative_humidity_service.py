from datetime import date, timedelta

import pytest

from app.power.models import PowerPayload, PowerPointQuery
from app.services.relative_humidity_service import (
    RelativeHumidityDataError,
    RelativeHumidityPolicy,
    RelativeHumidityService,
)


class FakePowerClient:
    def __init__(self, payload: PowerPayload) -> None:
        self.payload = payload

    def fetch_daily_point(self, query: PowerPointQuery, parameter=None) -> PowerPayload:
        return self.payload

    def fetch_monthly_point(self, query: PowerPointQuery, parameter=None) -> PowerPayload:
        return self.payload


def test_parser_keeps_missing_dates_and_removes_fill_values() -> None:
    payload = PowerPayload({"20200101": 70.0, "20200102": -999, "20200103": 72.0}, "%", -999)
    service = RelativeHumidityService(FakePowerClient(payload))
    series = service.fetch_daily(PowerPointQuery(0, 0, date(2020, 1, 1), date(2020, 1, 4)))
    assert [item.value for item in series.observations] == [70.0, 72.0]
    assert series.expected_count == 3
    assert series.returned_count == 3
    assert series.valid_count == 2
    assert series.missing_dates == (date(2020, 1, 2),)


@pytest.mark.parametrize("units", ["C", None, "g/kg"])
def test_parser_rejects_unexpected_units(units: str | None) -> None:
    service = RelativeHumidityService(FakePowerClient(PowerPayload({"20200101": 50.0}, units)))
    with pytest.raises(RelativeHumidityDataError, match="units"):
        service.fetch_daily(PowerPointQuery(0, 0, date(2020, 1, 1), date(2020, 1, 2)))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 100.1, "bad"])
def test_parser_rejects_invalid_physical_values(value: object) -> None:
    service = RelativeHumidityService(FakePowerClient(PowerPayload({"20200101": value}, "%")))
    with pytest.raises(RelativeHumidityDataError):
        service.fetch_daily(PowerPointQuery(0, 0, date(2020, 1, 1), date(2020, 1, 2)))


def _year_payload(year: int, missing: set[date] | None = None, value: float = 60.0) -> PowerPayload:
    missing = missing or set()
    cursor = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    values: dict[str, float] = {}
    while cursor < end:
        if cursor not in missing:
            values[cursor.strftime("%Y%m%d")] = value + cursor.month / 10
        cursor += timedelta(days=1)
    return PowerPayload(values, "%")


def test_annual_aggregation_handles_leap_year_and_equal_month_weights() -> None:
    service = RelativeHumidityService(FakePowerClient(_year_payload(2020)))
    result = service.analyze(PowerPointQuery(0, 0, date(2020, 1, 1), date(2021, 1, 1)))
    summary = result.annual_summaries[0]
    assert summary.expected_observations == 366
    assert summary.valid_observations == 366
    assert summary.represented_months == tuple(range(1, 13))
    assert summary.annual_value == pytest.approx(sum(60 + month / 10 for month in range(1, 13)) / 12)
    assert summary.eligible_for_trend_inference is True


def test_month_failure_is_stable_even_when_annual_coverage_passes() -> None:
    missing = {date(2021, 2, day) for day in range(1, 8)}
    service = RelativeHumidityService(FakePowerClient(_year_payload(2021, missing)))
    summary = service.analyze(PowerPointQuery(0, 0, date(2021, 1, 1), date(2022, 1, 1))).annual_summaries[0]
    assert summary.valid_coverage_percentage > 90
    assert summary.eligible_for_trend_inference is False
    assert "insufficient_monthly_coverage" in summary.eligibility_reasons


def test_partial_year_remains_descriptive() -> None:
    payload = PowerPayload({"20210101": 50.0, "20210102": 52.0}, "%")
    service = RelativeHumidityService(FakePowerClient(payload), RelativeHumidityPolicy())
    summary = service.analyze(PowerPointQuery(0, 0, date(2021, 1, 1), date(2021, 1, 3))).annual_summaries[0]
    assert summary.annual_value == 51.0
    assert summary.eligible_for_trend_inference is False
    assert "partial_calendar_year" in summary.eligibility_reasons


def test_returned_fill_values_are_counted_per_year_but_not_valid() -> None:
    payload = PowerPayload({"20201231": -999, "20210101": 55.0, "20210102": -999}, "%", -999)
    service = RelativeHumidityService(FakePowerClient(payload))
    result = service.analyze(PowerPointQuery(0, 0, date(2020, 12, 31), date(2021, 1, 3)))
    assert result.annual_summaries[0].available_images == 1
    assert result.annual_summaries[0].valid_observations == 0
    assert result.annual_summaries[1].available_images == 2
    assert result.annual_summaries[1].valid_observations == 1


def test_completely_missing_month_reports_both_month_failures() -> None:
    missing = {date(2021, 2, day) for day in range(1, 29)}
    service = RelativeHumidityService(FakePowerClient(_year_payload(2021, missing)))
    summary = service.analyze(PowerPointQuery(0, 0, date(2021, 1, 1), date(2022, 1, 1))).annual_summaries[0]
    assert "insufficient_represented_months" in summary.eligibility_reasons
    assert "insufficient_monthly_coverage" in summary.eligibility_reasons
