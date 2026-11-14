from datetime import date

from app.schemas.ndvi import NDVIQuery
from app.services.modis_service import ModisService


class FakeValue:
    def __init__(self, value: object) -> None:
        self.value = value

    def getInfo(self) -> object:
        return self.value


class FakeDictionary:
    def __init__(self, value: float | None) -> None:
        self.value = value

    def get(self, key: str) -> float | None:
        assert key == "ndvi"
        return self.value


class FakeImage:
    def __init__(self, mean: float | None = 0.52) -> None:
        self.mean = mean
        self.actions: list[tuple[object, ...]] = []
        self.properties: dict[str, object] = {}

    def select(self, band: str) -> "FakeImage":
        self.actions.append(("select", band))
        return self

    def eq(self, value: int) -> "FakeImage":
        self.actions.append(("eq", value))
        return self

    def updateMask(self, mask: "FakeImage") -> "FakeImage":
        self.actions.append(("updateMask",))
        return self

    def multiply(self, value: float) -> "FakeImage":
        self.actions.append(("multiply", value))
        return self

    def rename(self, name: str) -> "FakeImage":
        self.actions.append(("rename", name))
        return self

    def reduceRegion(self, **kwargs: object) -> FakeDictionary:
        self.actions.append(("reduceRegion", kwargs))
        return FakeDictionary(self.mean)

    def get(self, name: str) -> int:
        assert name == "system:time_start"
        return 1_577_836_800_000

    def set(self, properties: dict[str, object]) -> "FakeImage":
        self.properties.update(properties)
        return self


class FakeCollection:
    def __init__(self, ee: "FakeEE") -> None:
        self.ee = ee

    def filterDate(self, start: str, end: str) -> "FakeCollection":
        self.ee.filtered_dates = (start, end)
        return self

    def map(self, transform: object) -> "FakeCollection":
        transform(self.ee.image)
        return self

    def filter(self, filter_value: object) -> "FakeCollection":
        self.ee.applied_filter = filter_value
        return self

    def reduceColumns(self, reducer: object, selectors: list[str]) -> FakeDictionary:
        self.ee.column_reduction = (reducer, selectors)
        return _ListDictionary(self.ee.rows)


class _ListDictionary:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows

    def get(self, key: str) -> FakeValue:
        assert key == "list"
        return FakeValue(self.rows)


class FakeGeometry:
    def __init__(self, ee: "FakeEE", coordinates: list[float]) -> None:
        self.ee = ee
        self.coordinates = coordinates

    def buffer(self, metres: float) -> "FakeGeometry":
        self.ee.buffer_metres = metres
        return self


class FakeEE:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows
        self.image = FakeImage()
        self.dataset: str | None = None
        self.filtered_dates: tuple[str, str] | None = None
        self.point: list[float] | None = None
        self.buffer_metres: float | None = None
        self.applied_filter: object = None
        self.column_reduction: tuple[object, list[str]] | None = None
        self.Geometry = _GeometryFactory(self)
        self.Reducer = _ReducerFactory()
        self.Filter = _FilterFactory()

    def ImageCollection(self, dataset: str) -> FakeCollection:
        self.dataset = dataset
        return FakeCollection(self)

    def Date(self, timestamp: int) -> "FakeDate":
        return FakeDate(timestamp)


class _GeometryFactory:
    def __init__(self, ee: FakeEE) -> None:
        self.ee = ee

    def Point(self, coordinates: list[float]) -> FakeGeometry:
        self.ee.point = coordinates
        return FakeGeometry(self.ee, coordinates)


class _ReducerFactory:
    def mean(self) -> str:
        return "mean-reducer"

    def toList(self, count: int) -> tuple[str, int]:
        return ("list-reducer", count)


class _FilterFactory:
    def notNull(self, properties: list[str]) -> tuple[str, tuple[str, ...]]:
        return ("not-null", tuple(properties))


class FakeDate:
    def __init__(self, timestamp: int) -> None:
        self.timestamp = timestamp

    def format(self, pattern: str) -> str:
        assert pattern == "YYYY-MM-dd"
        return "2020-01-01"


class FakeManager:
    def __init__(self, ee: FakeEE) -> None:
        self.ee = ee
        self.initialized = 0

    def initialize(self) -> None:
        self.initialized += 1


def test_fetch_ndvi_builds_correct_modis_processing_request() -> None:
    fake_ee = FakeEE(rows=[["2020-01-17", 0.61], ["2020-01-01", 0.52]])
    manager = FakeManager(fake_ee)
    service = ModisService(manager)
    query = NDVIQuery(
        latitude=16.8661,
        longitude=96.1951,
        start_date=date(2020, 1, 1),
        end_date=date(2021, 1, 1),
        radius_km=5,
    )

    response = service.fetch_ndvi(query)

    assert manager.initialized == 1
    assert fake_ee.dataset == "MODIS/061/MOD13Q1"
    assert fake_ee.point == [96.1951, 16.8661]
    assert fake_ee.buffer_metres == 5000
    assert fake_ee.filtered_dates == ("2020-01-01", "2021-01-01")
    assert ("select", "SummaryQA") in fake_ee.image.actions
    assert ("eq", 0) in fake_ee.image.actions
    assert ("select", "NDVI") in fake_ee.image.actions
    assert ("multiply", 0.0001) in fake_ee.image.actions
    reduction = next(action[1] for action in fake_ee.image.actions if action[0] == "reduceRegion")
    assert reduction["scale"] == 250
    assert fake_ee.column_reduction == (("list-reducer", 2), ["date", "ndvi"])
    assert [item.model_dump(mode="json") for item in response.observations] == [
        {"date": "2020-01-01", "ndvi": 0.52},
        {"date": "2020-01-17", "ndvi": 0.61},
    ]


def test_fetch_ndvi_drops_null_non_finite_and_malformed_rows() -> None:
    fake_ee = FakeEE(
        rows=[
            ["2020-01-01", None],
            ["2020-01-17", float("nan")],
            ["2020-02-02", float("inf")],
            ["bad-date", 0.4],
            ["2020-02-18", 0.44],
            ["missing-value"],
        ]
    )
    service = ModisService(FakeManager(fake_ee))
    query = NDVIQuery(
        latitude=0,
        longitude=0,
        start_date=date(2020, 1, 1),
        end_date=date(2020, 3, 1),
        radius_km=1,
    )

    response = service.fetch_ndvi(query)

    assert response.observation_count == 1
    assert response.observations[0].ndvi == 0.44

