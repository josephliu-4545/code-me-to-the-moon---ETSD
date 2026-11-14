from datetime import date

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import create_app
from app.services.imerg_region_service import ImergRegionService, RegionBox
from app.services.imerg_service import ImergRetrievalError


class FakeManager:
    ee = None

    def initialize(self) -> None:
        pass


def months(start: date, end: date) -> list[str]:
    out, y, m = [], start.year, start.month
    while date(y, m, 1) < end:
        out.append(date(y, m, 1).isoformat())
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def loader(rate=0.5, valid=1.0, total=1.0, low_coverage_months=()):
    def load(box, s, e):
        rows = []
        for i, m in enumerate(months(s, e)):
            v = valid * (0.5 if m in low_coverage_months else 1.0)
            rows.append([m, rate * v * 1e8, v * 1e8, total * 1e8])
        return rows
    return load


def service(**kw) -> ImergRegionService:
    return ImergRegionService(FakeManager(), row_loader=kw.pop("row_loader", loader()), **kw)


BOX = RegionBox(96.0, 16.6, 96.4, 17.0)


@pytest.mark.parametrize(
    "args, message",
    [
        ((97, 16, 96, 17), "west must be less than east"),
        ((170, 0, -170, 1), "antimeridian"),
        ((0, 10, 1, 5), "south must be less than north"),
        ((0, float("nan"), 1, 1), "finite"),
    ],
)
def test_region_box_validation(args, message) -> None:
    with pytest.raises(ValueError, match=message):
        RegionBox(*args)


def test_area_weighted_mean_and_accumulation() -> None:
    region = service().fetch_region(BOX, date(2020, 1, 1), date(2020, 3, 1))
    jan, feb = region.series.observations
    assert jan.mean_rate_mm_per_hour == pytest.approx(0.5)
    assert jan.accumulation_mm == pytest.approx(0.5 * 24 * 31)
    assert feb.accumulation_mm == pytest.approx(0.5 * 24 * 29)
    assert region.coverage[0].valid_area_fraction == 1.0 and region.coverage[0].accepted
    assert region.series.grid_cell_id.startswith("imerg-v07-region:")


def test_months_below_area_threshold_are_missing_not_zero() -> None:
    region = service(row_loader=loader(low_coverage_months={"2020-02-01"})).fetch_region(BOX, date(2020, 1, 1), date(2020, 4, 1))
    feb = region.series.observations[1]
    assert feb.mean_rate_mm_per_hour is None and feb.accumulation_mm is None
    assert region.coverage[1].valid_area_fraction == pytest.approx(0.5)
    assert region.coverage[1].accepted is False


def test_fully_masked_month_is_missing() -> None:
    rows = lambda box, s, e: [[s.isoformat(), None, None, 1e8]]
    region = service(row_loader=rows).fetch_region(BOX, date(2020, 1, 1), date(2020, 2, 1))
    assert region.series.observations[0].accumulation_mm is None


def test_threshold_is_configurable_and_validated() -> None:
    region = service(row_loader=loader(low_coverage_months={"2020-02-01"}), min_valid_area_fraction=0.4).fetch_region(
        BOX, date(2020, 1, 1), date(2020, 4, 1))
    assert region.coverage[1].accepted
    with pytest.raises(ValueError):
        ImergRegionService(FakeManager(), min_valid_area_fraction=0)


@pytest.mark.parametrize(
    "rows, message",
    [
        ("bad", "malformed"),
        ([["2020-01-01", 1, 1]], "malformed IMERG region row"),
        ([["2020-01-01", -1, 1, 1]], "invalid IMERG region sums"),
        ([["2020-01-01", 1, 2, 1]], "inconsistent"),
        ([["2020-01-01", 1, 1, 0]], "inconsistent"),
        ([["2020-01-01", 1, 1, 1], ["2020-01-01", 1, 1, 1]], "duplicate"),
    ],
)
def test_malformed_region_rows_are_rejected(rows, message) -> None:
    with pytest.raises(ImergRetrievalError, match=message):
        service(row_loader=lambda box, s, e: rows).fetch_region(BOX, date(2020, 1, 1), date(2020, 2, 1))


def test_ten_years_use_five_year_windows_and_results_are_cached() -> None:
    calls = []
    def rec(box, s, e):
        calls.append((s, e))
        return loader()(box, s, e)
    svc = service(row_loader=rec)
    svc.fetch_region(BOX, date(2015, 1, 1), date(2025, 1, 1))
    svc.fetch_region(BOX, date(2015, 1, 1), date(2025, 1, 1))
    assert calls == [(date(2015, 1, 1), date(2020, 1, 1)), (date(2020, 1, 1), date(2025, 1, 1))]


# --- route --------------------------------------------------------------------------


def client(row_loader=None) -> TestClient:
    app = create_app(Settings(_env_file=None, ee_project_id="test"),
                     imerg_region_service=ImergRegionService(FakeManager(), row_loader=row_loader or loader()))
    return TestClient(app)


Q = {"west": 96.0, "south": 16.6, "east": 96.4, "north": 17.0, "start_date": "2015-01-01", "end_date": "2025-01-01"}


def test_region_trend_route_reports_area_weighted_support() -> None:
    body = client().get("/api/v1/precipitation/region/trend", params=Q).json()
    assert body["spatial_support"]["type"] == "bbox_area_weighted_mean"
    assert body["spatial_support"]["single_cell_substituted"] is False
    assert body["spatial_support"]["bbox"] == {"west": 96.0, "south": 16.6, "east": 96.4, "north": 17.0}
    assert len(body["monthly_coverage"]) == 120
    assert len(body["annual_summaries"]) == 10
    assert body["annual_summaries"][0]["annual_accumulation_mm"] == pytest.approx(0.5 * 24 * 365)
    assert body["trend"]["result_level"] in {"descriptive_slope", "statistical_inference"}


def test_region_with_low_coverage_month_makes_year_ineligible() -> None:
    body = client(loader(low_coverage_months={"2018-07-01"})).get("/api/v1/precipitation/region/trend", params=Q).json()
    y2018 = next(s for s in body["annual_summaries"] if s["year"] == 2018)
    assert not y2018["eligible_for_trend_inference"]
    assert body["coverage"]["months_meeting_area_threshold"] == 119


@pytest.mark.parametrize(
    "patch, fragment",
    [
        ({"west": 97.0}, "west must be less than east"),
        ({"east": 102.0}, "at most 5"),
        ({"east": 96.05}, "at least 0.1"),
        ({"start_date": "2025-01-01"}, "before"),
        ({"start_date": "2005-01-01"}, "exceeds"),
    ],
)
def test_region_route_validation(patch, fragment) -> None:
    r = client().get("/api/v1/precipitation/region/trend", params={**Q, **patch})
    assert r.status_code == 422 and fragment in r.json()["detail"]


def test_region_route_maps_provider_errors_to_502() -> None:
    r = client(lambda box, s, e: "garbage").get("/api/v1/precipitation/region/trend", params=Q)
    assert r.status_code == 502
