from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import math
from statistics import mean

from app.power.client import PowerClient, PowerResponseError
from app.power.models import PowerParameter, PowerPointQuery
from app.statistics.models import AnnualSummary, TimedValue, TrendAnalysisResult
from app.statistics.policies import TrendPolicy
from app.statistics.trend import analyze_trend


class TemperatureDataError(PowerResponseError): pass


@dataclass(frozen=True)
class TemperatureSeries:
    observations: tuple[TimedValue, ...]
    expected_count: int
    returned_count: int
    missing_dates: tuple[date, ...]
    time_standard: str
    temporal_resolution: str = "daily"


@dataclass(frozen=True)
class TemperatureAnalysis:
    series: TemperatureSeries
    annual_summaries: tuple[AnnualSummary, ...]
    trend: TrendAnalysisResult


class TemperatureService:
    def __init__(self, client: PowerClient, min_annual_coverage: float = .90, min_monthly_coverage: float = .80, trend_policy: TrendPolicy | None = None):
        self._client, self._annual, self._monthly = client, min_annual_coverage, min_monthly_coverage
        self._trend_policy = trend_policy or TrendPolicy()

    @staticmethod
    def _units(units):
        if units not in {"C", "°C", "degC"}: raise TemperatureDataError("T2M units must be Celsius")

    def fetch_daily(self, query):
        payload = self._client.fetch_daily_point(query, PowerParameter.T2M); self._units(payload.units)
        expected=[]; d=query.start_date
        while d < query.end_date: expected.append(d); d += timedelta(days=1)
        expected_set=set(expected)
        returned=set(); observations=[]; sentinels={-999.0}
        if payload.fill_value is not None:
            try: sentinels.add(float(payload.fill_value))
            except (TypeError, ValueError): pass
        for key, raw in payload.values.items():
            try: day=date(int(key[:4]), int(key[4:6]), int(key[6:8]))
            except (ValueError, TypeError): raise TemperatureDataError("invalid date") from None
            if day not in expected_set or day in returned: raise TemperatureDataError("duplicate or out-of-range date")
            returned.add(day)
            try: value=float(raw)
            except (ValueError, TypeError): raise TemperatureDataError("non-numeric temperature") from None
            if value in sentinels: continue
            if not math.isfinite(value) or not -100 <= value <= 70: raise TemperatureDataError("temperature outside plausible range")
            observations.append(TimedValue(day, value))
        valid={x.date for x in observations}
        return TemperatureSeries(tuple(sorted(observations,key=lambda x:x.date)),len(expected),len(returned),tuple(x for x in expected if x not in valid),payload.time_standard or query.time_standard)

    def fetch_monthly(self, query):
        payload=self._client.fetch_monthly_point(query, PowerParameter.T2M); self._units(payload.units); observations=[]
        for key, raw in payload.values.items():
            if len(key)!=6 or not key.isdigit() or not 1 <= int(key[4:]) <= 12: continue
            day=date(int(key[:4]),int(key[4:]),1)
            if query.start_date <= day < query.end_date and float(raw) != -999: observations.append(TimedValue(day,float(raw)))
        return TemperatureSeries(tuple(observations),len(observations),len(observations),(),payload.time_standard or query.time_standard,"monthly")

    def analyze(self, query):
        series=self.fetch_daily(query); by_year=defaultdict(list)
        for x in series.observations: by_year[x.date.year].append(x)
        summaries=[]
        for year in range(query.start_date.year,(query.end_date-timedelta(days=1)).year+1):
            ys,ye=date(year,1,1),date(year+1,1,1); start=max(ys,query.start_date); end=min(ye,query.end_date); expected=(end-start).days
            items=by_year[year]; months=defaultdict(list)
            for x in items: months[x.date.month].append(x.value)
            monthly=tuple((m,mean(v)) for m,v in sorted(months.items())); represented=[]; inadequate=[]
            for m in range(1,13):
                ms=date(year,m,1); me=date(year+(m==12),1 if m==12 else m+1,1); exp=max(0,(min(end,me)-max(start,ms)).days)
                if exp and len(months[m])/exp >= self._monthly: represented.append(m)
                elif exp: inadequate.append(m)
            reasons=[]; complete=start==ys and end==ye; coverage=len(items)/expected if expected else 0
            if not complete: reasons.append("partial_calendar_year")
            if len(represented)<12: reasons.append("insufficient_represented_months")
            if inadequate: reasons.append("insufficient_monthly_coverage")
            if coverage<self._annual: reasons.append("insufficient_annual_coverage")
            summaries.append(AnnualSummary(year,mean(v for _,v in monthly) if monthly else None,"°C",monthly,tuple(represented),tuple(m for m in range(1,13) if m not in represented),tuple(sorted({(m-1)//3+1 for m in represented})),(),len(items),len(items),expected,len(items),coverage*100,coverage*100,complete,not reasons,tuple(reasons),None,None,None,None))
        summaries=tuple(summaries); return TemperatureAnalysis(series,summaries,analyze_trend(summaries,"°C",self._trend_policy))
