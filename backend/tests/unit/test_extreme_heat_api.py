from datetime import date, timedelta

import httpx
import pytest

from app.core.operation_runner import BoundedOperationRunner
from app.extremes.hot_days import HotDayPolicy
from app.main import create_app
from app.power.models import PowerPayload
from app.services.extreme_heat_service import ExtremeHeatService


class FakeClient:
    def fetch_daily_point(self, query, parameter):
        values={}; d=query.start_date
        while d<query.end_date: values[d.strftime("%Y%m%d")]=30+d.month/10; d+=timedelta(days=1)
        return PowerPayload(values,"C",-999,"LST",parameter)


@pytest.mark.anyio
async def test_extreme_heat_contract_distinguishes_counts_and_adjusted_frequency() -> None:
    runner=BoundedOperationRunner(1,"NASA POWER","power-heat-test")
    service=ExtremeHeatService(FakeClient(),HotDayPolicy(bootstrap_repetitions=2))
    app=create_app(extreme_heat_service=service,power_operation_runner=runner)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            response=await client.get("/api/v1/extreme-heat/trend",params={"latitude":16.8661,"longitude":96.1951,"start_date":"2020-01-01","end_date":"2022-01-01"})
    finally: runner.shutdown()
    assert response.status_code==200
    body=response.json(); annual=body["annual_summaries"][0]
    assert isinstance(annual["raw_hot_day_count"],int)
    assert "bootstrap_adjusted_percentage" in annual
    assert body["trend_basis"]=="bootstrap-adjusted exceedance percentage where applicable"
    assert "not heatwave" in " ".join(body["limitations"]).lower()
    assert body["reference_period"]["start_year"]==1991
    assert app.openapi()["paths"]["/api/v1/extreme-heat/trend"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("ExtremeHeatResponse")
