from datetime import date, timedelta

from app.extremes.hot_days import HotDayPolicy
from app.power.models import PowerParameter, PowerPayload, PowerPointQuery
from app.services.extreme_heat_service import ExtremeHeatService


def _values(start, end, warming=0.0):
    values={}; day=start
    while day<end:
        values[day.strftime("%Y%m%d")]=25+day.month/2+(day.year-1991)*warming
        day+=timedelta(days=1)
    return values


class FakeClient:
    def __init__(self): self.queries=[]
    def fetch_daily_point(self, query, parameter):
        assert parameter==PowerParameter.T2M_MAX; self.queries.append(query)
        return PowerPayload(_values(query.start_date,query.end_date,.05),"C",-999,"LST",parameter)


def test_reference_is_retrieved_independently_and_outputs_are_separate() -> None:
    client=FakeClient(); service=ExtremeHeatService(client,HotDayPolicy(bootstrap_repetitions=3))
    result=service.analyze(PowerPointQuery(16.8661,96.1951,date(2020,1,1),date(2022,1,1),"LST"))
    assert client.queries[0].start_date==date(1991,1,1)
    assert client.queries[0].end_date==date(2021,1,1)
    assert client.queries[1].start_date==date(2020,1,1)
    y2020=result.annual_summaries[0]
    assert isinstance(y2020.raw_hot_day_count,int)
    assert y2020.valid_exposure_days==366
    assert y2020.bootstrap_adjusted_percentage is not None
    assert y2020.primary_trend_percentage==y2020.bootstrap_adjusted_percentage
    y2021=result.annual_summaries[1]
    assert y2021.bootstrap_adjusted_percentage is None
    assert y2021.primary_trend_percentage==y2021.raw_hot_day_percentage


def test_reference_cache_avoids_second_thirty_year_download() -> None:
    client=FakeClient(); service=ExtremeHeatService(client,HotDayPolicy(bootstrap_repetitions=2))
    query=PowerPointQuery(1,2,date(2021,1,1),date(2022,1,1),"LST")
    service.analyze(query); service.analyze(query)
    assert sum(q.start_date==date(1991,1,1) and q.end_date==date(2021,1,1) for q in client.queries)==1
