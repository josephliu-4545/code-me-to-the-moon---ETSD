from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from threading import Lock

from app.extremes.hot_days import HotDayPolicy, HotDayThresholdSet, bootstrap_base_year, build_thresholds, classify_year
from app.power.client import PowerClient, PowerResponseError
from app.power.models import PowerParameter, PowerPointQuery
from app.statistics.models import AnnualSummary, TimedValue, TrendAnalysisResult
from app.statistics.policies import TrendPolicy
from app.statistics.trend import analyze_trend


@dataclass(frozen=True)
class ExtremeHeatAnnualSummary:
    year: int
    raw_hot_day_count: int
    valid_exposure_days: int
    raw_hot_day_percentage: float
    bootstrap_adjusted_percentage: float | None
    bootstrap_confidence_interval: tuple[float,float] | None
    primary_trend_percentage: float | None
    expected_days: int
    annual_coverage_percentage: float
    eligible_for_trend_inference: bool
    eligibility_reasons: tuple[str,...]


@dataclass(frozen=True)
class ExtremeHeatAnalysis:
    annual_summaries: tuple[ExtremeHeatAnnualSummary,...]
    trend: TrendAnalysisResult
    reference_complete: bool
    reference_valid_days: int
    reference_expected_days: int
    thresholds: HotDayThresholdSet


@dataclass(frozen=True)
class _ReferenceData:
    observations: tuple[TimedValue,...]
    thresholds: HotDayThresholdSet
    complete: bool
    expected: int


class ExtremeHeatService:
    def __init__(self,client:PowerClient,policy:HotDayPolicy|None=None,trend_policy:TrendPolicy|None=None,cache_max_entries:int=16):
        self._client=client; self._policy=policy or HotDayPolicy(); self._trend_policy=trend_policy or TrendPolicy()
        self._cache: dict[tuple, _ReferenceData] = {}
        self._cache_lock=Lock()
        self._reference_build_lock=Lock()
        self._cache_max_entries=cache_max_entries

    def _parse(self,payload,query):
        if payload.units not in {"C","°C","degC"}: raise PowerResponseError("T2M_MAX units must be Celsius")
        observations=[]
        for key,raw in payload.values.items():
            day=date(int(key[:4]),int(key[4:6]),int(key[6:8])); value=float(raw)
            if value == -999 or value == payload.fill_value: continue
            if query.start_date <= day < query.end_date: observations.append(TimedValue(day,value))
        return tuple(sorted(observations,key=lambda x:x.date))

    def _reference(self,query):
        key=(round(query.latitude,6),round(query.longitude,6),"NASA_POWER","T2M_MAX","LST",self._policy.reference_start_year,self._policy.reference_end_year,self._policy.percentile,self._policy.window_days,self._policy.minimum_window_fraction,"tx90p-v1")
        with self._reference_build_lock:
            with self._cache_lock:
                cached=self._cache.get(key)
            if cached: return cached
            rq=PowerPointQuery(query.latitude,query.longitude,date(self._policy.reference_start_year,1,1),date(self._policy.reference_end_year+1,1,1),"LST")
            obs=self._parse(self._client.fetch_daily_point(rq,PowerParameter.T2M_MAX),rq); thresholds=build_thresholds(obs,self._policy)
            expected=(rq.end_date-rq.start_date).days; counts=Counter(x.date.year for x in obs)
            complete=all(counts[y]/(date(y+1,1,1)-date(y,1,1)).days >= self._policy.minimum_window_fraction for y in range(self._policy.reference_start_year,self._policy.reference_end_year+1)) and all(x is not None for x in thresholds.values.values())
            data=_ReferenceData(obs,thresholds,complete,expected)
            with self._cache_lock:
                if len(self._cache)>=self._cache_max_entries: self._cache.pop(next(iter(self._cache)))
                self._cache[key]=data
            return data

    def analyze(self,query):
        ref=self._reference(query)
        obs=self._parse(self._client.fetch_daily_point(query,PowerParameter.T2M_MAX),query); summaries=[]; trend_summaries=[]
        for year in range(query.start_date.year,(query.end_date-timedelta(days=1)).year+1):
            ys,ye=date(year,1,1),date(year+1,1,1); start=max(ys,query.start_date); end=min(ye,query.end_date); expected=(end-start).days
            annual=tuple(x for x in obs if x.date.year==year); classified=classify_year(annual,ref.thresholds); valid=[x for x in classified if x.is_hot_day is not None]; raw=sum(x.is_hot_day is True for x in valid); raw_pct=100*raw/len(valid) if valid else 0
            missing_months=Counter(x.date.month for x in annual); reasons=[]
            if start!=ys or end!=ye: reasons.append("partial_calendar_year")
            if expected-len(annual)>self._policy.maximum_missing_days_per_year: reasons.append("insufficient_annual_daily_coverage")
            for month in range(1,13):
                ms=date(year,month,1); me=date(year+(month==12),1 if month==12 else month+1,1)
                if (me-ms).days-missing_months[month]>self._policy.maximum_missing_days_per_month: reasons.append("insufficient_monthly_daily_coverage"); break
            if len(valid)!=len(annual): reasons.append("threshold_unavailable_for_observation")
            if not ref.complete: reasons.append("reference_period_incomplete")
            adjusted=None; ci=None
            if self._policy.reference_start_year <= year <= self._policy.reference_end_year and ref.complete:
                boot=bootstrap_base_year(ref.observations,year,self._policy); adjusted=boot.adjusted_percentage; ci=boot.confidence_interval
            primary=adjusted if adjusted is not None else raw_pct
            summary=ExtremeHeatAnnualSummary(year,raw,len(valid),raw_pct,adjusted,ci,primary,expected,100*len(annual)/expected if expected else 0,not reasons,tuple(dict.fromkeys(reasons))); summaries.append(summary)
            trend_summaries.append(AnnualSummary(year,primary,"percentage points",(),(),(),(),(),len(valid),len(valid),expected,len(annual),summary.annual_coverage_percentage,summary.annual_coverage_percentage,start==ys and end==ye,not reasons,summary.eligibility_reasons,None,None,None,None))
        trend=analyze_trend(tuple(trend_summaries),"percentage points",self._trend_policy)
        return ExtremeHeatAnalysis(tuple(summaries),trend,ref.complete,len(ref.observations),ref.expected,ref.thresholds)
