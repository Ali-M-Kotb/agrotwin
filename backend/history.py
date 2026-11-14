"""Field diagnosis: climate trend, NDVI seasons, danger windows.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

Danger windows (plan 5.6): for each day-of-year, median and MAD over a ±7-day window across
all years; robust z = (x − median) / (1.4826 · MAD). A danger window is |z| > 2 for 5 or more
consecutive days (assumption:danger_rule). Rain uses 30-day totals (daily rain is mostly zero).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import A
from crops import CROPS, total_days


def climate_summary(weather: pd.DataFrame) -> dict:
    full = weather.groupby(weather.index.year).filter(lambda g: len(g) >= 360)
    yr = full.groupby(full.index.year)
    annual = pd.DataFrame({
        "tmax": yr["T2M_MAX"].mean(),
        "hot_days": yr["T2M_MAX"].apply(lambda s: int((s > 35).sum())),
        "rain": yr["PRECTOTCORR"].sum(),
        "et0": yr["ET0"].sum(),
    })
    x = annual.index.values.astype(float)
    trend = {k: float(np.polyfit(x, annual[k].values, 1)[0] * 10) for k in annual}
    return dict(years=annual.index.tolist(), tmax=annual["tmax"].round(2).tolist(),
                hot_days=annual["hot_days"].tolist(), rain=annual["rain"].round(1).tolist(),
                et0=annual["et0"].round(0).tolist(),
                trend_per_decade={k: round(v, 2) for k, v in trend.items()},
                source="nasa:POWER", first=str(weather.index[0].date()), last=str(weather.index[-1].date()))


def robust_z(series: pd.Series, half_window: int = 7) -> pd.Series:
    s = series.dropna()
    doy = s.index.day_of_year.values
    vals = s.values
    z = np.full(len(s), np.nan)
    for d in range(1, 367):
        near = np.abs(((doy - d + 183) % 366) - 183) <= half_window
        if near.sum() < 10:
            continue
        med = np.median(vals[near])
        mad = np.median(np.abs(vals[near] - med)) * 1.4826
        if mad <= 1e-9:   # e.g. a dry month where most days are 0 mm: use the mean deviation (as in Yaseen's danger.py)
            mad = np.mean(np.abs(vals[near] - med))
        sel = doy == d
        z[sel] = (vals[sel] - med) / mad if mad > 1e-9 else 0.0
    return pd.Series(z, index=s.index)


def _runs(z: pd.Series, thr: float, min_len: int, sign: int) -> list[dict]:
    flag = (z * sign > thr).fillna(False).values
    out, start = [], None
    for i, f in enumerate(np.append(flag, False)):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                seg = z.iloc[start:i]
                out.append(dict(start=str(seg.index[0].date()), end=str(seg.index[-1].date()),
                                days=int(i - start), peak_z=round(float(seg.abs().max()), 1)))
            start = None
    return out


def danger_windows(weather: pd.DataFrame, ndvi: pd.Series | None = None, months: int = 24) -> dict:
    thr, min_len = A["danger_rule"]
    since = weather.index[-1] - pd.Timedelta(days=30 * months)
    series = {
        "heat": (weather["T2M_MAX"], +1, "nasa:POWER T2M_MAX"),
        "dry_spell": (weather["PRECTOTCORR"].rolling(30, min_periods=20).sum(), -1, "nasa:POWER PRECTOTCORR (30-day total)"),
        "wet_spell": (weather["PRECTOTCORR"].rolling(30, min_periods=20).sum(), +1, "nasa:POWER PRECTOTCORR (30-day total)"),
        "dry_soil": (weather["GWETROOT"], -1, "nasa:POWER GWETROOT"),
    }
    out = {}
    for name, (s, sign, src) in series.items():
        z = robust_z(s)
        ws = [w for w in _runs(z, thr, min_len, sign) if pd.Timestamp(w["start"]) >= since]
        out[name] = dict(windows=ws, source=src)
    if ndvi is not None and len(ndvi.dropna()) > 40:
        daily = ndvi.resample("D").interpolate(limit=20)
        z = robust_z(daily)
        ws = [w for w in _runs(z, thr, min_len, -1) if pd.Timestamp(w["start"]) >= since]
        out["low_greenness"] = dict(windows=ws, source="nasa:MODIS MOD13Q1 NDVI")
    return dict(rule=f"|robust z| > {thr} for {min_len}+ days", rule_source="assumption:danger_rule",
                since=str(since.date()), until=str(weather.index[-1].date()), kinds=out)


def ndvi_seasons(ndvi: pd.Series) -> dict:
    """Green-up peaks → which seasons the field was cropped, and crops whose peak timing fits."""
    s = ndvi.dropna()
    if len(s) < 20:
        return dict(peaks=[], suggestion=[])
    sm = s.rolling(3, center=True, min_periods=1).mean()
    v = sm.values
    peaks = []
    for i in range(1, len(v) - 1):
        if v[i] >= v[i - 1] and v[i] > v[i + 1] and v[i] >= 0.45:
            lo = max(v[max(0, i - 6):i].min(), v[i + 1:i + 7].min())
            if v[i] - lo >= 0.15:
                d = sm.index[i]
                season = "winter" if d.month in (12, 1, 2, 3, 4) else "summer" if d.month in (6, 7, 8, 9, 10) else "transition"
                peaks.append(dict(date=str(d.date()), ndvi=round(float(v[i]), 2), season=season))
    sugg = []
    for season in ("winter", "summer"):
        p = [x for x in peaks if x["season"] == season]
        if not p:
            continue
        last = pd.Timestamp(p[-1]["date"])
        cands = []
        for k, c in CROPS.items():
            if c["season"] != season:
                continue
            ini, dev, mid, _ = c["stages"]
            y = last.year if (season == "summer" or c["sow"][0] < 6) else last.year - 1
            peak = pd.Timestamp(y, *c["sow"]) + pd.Timedelta(days=ini + dev + mid // 2)
            cands.append((abs((peak - last).days), k))
        cands.sort()
        sugg.append(dict(season=season, peak=p[-1]["date"], crops=[k for _, k in cands[:3]]))
    years = sorted({x["date"][:4] for x in peaks})
    per_year = {y: sum(1 for x in peaks if x["date"].startswith(y)) for y in years}
    return dict(peaks=peaks, suggestion=sugg, peaks_per_year=per_year, source="nasa:MODIS MOD13Q1")
