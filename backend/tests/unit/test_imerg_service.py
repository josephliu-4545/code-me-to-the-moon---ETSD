from datetime import date

import pytest

from app.precipitation.models import PrecipitationQuery
from app.services.imerg_service import ImergRetrievalError, ImergService


class Manager:
    def __init__(self) -> None:
        self.initialized = 0
    def initialize(self) -> None:
        self.initialized += 1


def test_adapter_normalizes_rows_and_uses_bounded_windows() -> None:
    calls = []
    def loader(query, start, end):
        calls.append((start, end))
        return [["2020-01-01", 1.0], ["2020-02-01", None]]
    manager = Manager()
    service = ImergService(manager, window_years=5, row_loader=loader)
    result = service.fetch_monthly(PrecipitationQuery(16.8661, 96.1951, date(2020, 1, 1), date(2021, 1, 1)))
    assert manager.initialized == 1
    assert calls == [(date(2020, 1, 1), date(2021, 1, 1))]
    assert result.observations[0].accumulation_mm == 744
    assert result.observations[1].accumulation_mm is None
    assert result.grid_cell_center == pytest.approx((16.85, 96.15))


def test_adapter_rejects_duplicate_and_negative_rows() -> None:
    query = PrecipitationQuery(0, 0, date(2020, 1, 1), date(2021, 1, 1))
    duplicate = lambda *_: [["2020-01-01", 1], ["2020-01-01", 2]]
    with pytest.raises(ImergRetrievalError, match="duplicate"):
        ImergService(Manager(), row_loader=duplicate).fetch_monthly(query)
    negative = lambda *_: [["2020-01-01", -1]]
    with pytest.raises(ImergRetrievalError, match="invalid"):
        ImergService(Manager(), row_loader=negative).fetch_monthly(query)


def test_adapter_cache_avoids_repeat_download() -> None:
    calls = 0
    def loader(*_):
        nonlocal calls
        calls += 1
        return []
    service = ImergService(Manager(), row_loader=loader)
    query = PrecipitationQuery(0, 0, date(2020, 1, 1), date(2021, 1, 1))
    service.fetch_monthly(query)
    service.fetch_monthly(query)
    assert calls == 1


def test_adapter_cache_expires_deterministically() -> None:
    calls = 0
    now = [0.0]
    def loader(*_):
        nonlocal calls
        calls += 1
        return []
    service = ImergService(Manager(), row_loader=loader, cache_ttl_seconds=10, clock=lambda: now[0])
    query = PrecipitationQuery(0, 0, date(2020, 1, 1), date(2021, 1, 1))
    service.fetch_monthly(query)
    now[0] = 11
    service.fetch_monthly(query)
    assert calls == 2

