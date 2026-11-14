"""Independent validation helper; xclim is installed only in .validation_xclim."""
from datetime import date
import json
import sys
from pathlib import Path

sys.path.insert(0, ".validation_xclim")
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import xarray as xr
from xclim.core.calendar import percentile_doy
from xclim.indices import tx90p

from app.extremes.hot_days import HotDayPolicy, bootstrap_base_year, build_thresholds
from app.power.client import PowerClient
from app.power.models import PowerParameter, PowerPointQuery
from app.statistics.models import TimedValue


query = PowerPointQuery(16.8661, 96.1951, date(1991, 1, 1), date(2022, 1, 1), "LST")
payload = PowerClient(window_years=5).fetch_daily_point(query, PowerParameter.T2M_MAX)
observations = tuple(
    TimedValue(date(int(key[:4]), int(key[4:6]), int(key[6:8])), float(value))
    for key, value in payload.values.items()
    if float(value) != -999
)
reference = tuple(item for item in observations if item.date.year <= 2020)
ours = build_thresholds(reference, HotDayPolicy())

no_leap = tuple(item for item in observations if not (item.date.month == 2 and item.date.day == 29))
times = xr.date_range("1991-01-01", periods=len(no_leap), freq="D", calendar="noleap", use_cftime=True)
data = xr.DataArray([item.value for item in no_leap], coords={"time": times}, dims="time", attrs={"units": "degC"})
ref_da = data.sel(time=slice("1991-01-01", "2020-12-31"))
per = percentile_doy(ref_da, window=5, per=90).sel(percentiles=90)
xresult = tx90p(tasmax=data, tasmax_per=per, freq="YS", bootstrap=True)
x2020 = float(xresult.sel(time="2020").values.item())
x2021 = float(xresult.sel(time="2021").values.item())
our2020 = bootstrap_base_year(reference, 2020, HotDayPolicy())

threshold_diffs = []
for doy in range(1, 366):
    threshold_diffs.append(abs(ours.values[doy] - float(per.sel(dayofyear=doy).values)))

print(json.dumps({
    "xclim_version": __import__("xclim").__version__,
    "xclim_2020_days": x2020,
    "ours_2020_adjusted_days": our2020.adjusted_percentage / 100 * our2020.valid_days,
    "xclim_2021_days": x2021,
    "ours_2020_replacements": our2020.repetitions,
    "threshold_max_abs_difference_c": float(np.max(threshold_diffs)),
    "threshold_mean_abs_difference_c": float(np.mean(threshold_diffs)),
}, indent=2))
