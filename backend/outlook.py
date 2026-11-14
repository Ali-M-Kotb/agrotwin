"""Looking ahead: 16-day irrigation planner and 6-month seasonal outlook.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

Non-NASA data, disclosed as such on screen:
  Open-Meteo forecast API   16-day daily FAO-56 ET0, rain, Tmax (ECMWF/GFS blend), no key
  Open-Meteo seasonal API   ECMWF SEAS5 ensemble, ~6 months ahead, no key

Planner: the field's water balance is run on real NASA POWER weather from the start of this
season to the last POWER day, then continued on the 16-day forecast, so "irrigate on day X"
comes from the same FAO-56 model as everything else.
Outlook: each SEAS5 member's 3-month rain and mean Tmax is placed in the site's 30-year POWER
distribution for the same months. Shown as context only; never used in the scores (seasonal
skill cannot be backtested without archived forecasts).
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

import data_sources as ds
import waterbalance as wb
from config import A

TTL = 6 * 3600


def _cached(name: str, url: str, params: dict, offline: bool) -> dict | None:
    p = ds.CACHE / f"openmeteo_{name}_{params['latitude']:.3f}_{params['longitude']:.3f}.json"
    if p.exists() and (offline or time.time() - p.stat().st_mtime < TTL):
        return json.loads(p.read_text())
    if offline:
        return None
    try:
        r = requests.get(url, params=params, timeout=25, headers=ds.UA)
        r.raise_for_status()
        d = r.json()
        p.write_text(json.dumps(d))
        return d
    except Exception:
        return json.loads(p.read_text()) if p.exists() else None


def forecast16(lat: float, lon: float, offline: bool = False) -> pd.DataFrame | None:
    d = _cached("fc16", "https://api.open-meteo.com/v1/forecast",
                dict(latitude=round(lat, 3), longitude=round(lon, 3), forecast_days=16, timezone="GMT",
                     daily="et0_fao_evapotranspiration,precipitation_sum,temperature_2m_max,temperature_2m_min"), offline)
    if not d or "daily" not in d:
        return None
    dd = d["daily"]
    f = pd.DataFrame({"ET0": dd["et0_fao_evapotranspiration"], "PRECTOTCORR": dd["precipitation_sum"],
                      "T2M_MAX": dd["temperature_2m_max"], "T2M_MIN": dd["temperature_2m_min"]},
                     index=pd.to_datetime(dd["time"]))
    f["T2M"] = (f["T2M_MAX"] + f["T2M_MIN"]) / 2
    return f.astype(float)


def irrigation_plan(site: dict, rotation: tuple, soil_class: str, irrigated: bool, offline: bool = False) -> dict:
    fc = forecast16(site["lat"], site["lon"], offline)
    if fc is None:
        return dict(available=False, reason="forecast unavailable (offline and no cached forecast)")
    w = site["weather"][["ET0", "PRECTOTCORR", "T2M_MAX"]]
    today = pd.Timestamp(date.today())
    fc = fc[fc.index > w.index[-1]]
    gap = pd.date_range(w.index[-1] + pd.Timedelta(days=1), fc.index[0] - pd.Timedelta(days=1)) if len(fc) else []
    # days between the last POWER day and the first forecast day: use the 10-year normal for that date
    normal = w[w.index.year >= w.index[-1].year - 10]
    fill = pd.DataFrame({c: [normal[normal.index.day_of_year == d.day_of_year][c].mean() for d in gap] for c in w.columns}, index=gap) \
        if len(gap) else None
    joined = pd.concat([w] + ([fill] if fill is not None else []) + [fc[["ET0", "PRECTOTCORR", "T2M_MAX"]]])
    # pad far ahead with the normal so the window has room (only the next 16 days are reported)
    start = pd.Timestamp(today.year if today.month >= 10 else today.year - 1, 10, 1)
    need_end = start + pd.Timedelta(days=wb.T_DAYS)
    if joined.index[-1] < need_end:
        pad_idx = pd.date_range(joined.index[-1] + pd.Timedelta(days=1), need_end)
        clim = w.groupby(w.index.day_of_year).mean()
        joined = pd.concat([joined, pd.DataFrame({c: clim[c].reindex(pad_idx.day_of_year).values for c in w.columns}, index=pad_idx)])
    wx = wb.weather_matrices(joined, [start.year])
    sim = wb.simulate([rotation], wx, soil_class, irrigated, None, keep_wetness_days=400)
    days = [(start + timedelta(days=i)).date() for i in range(400)]
    wet, irr = sim["wet"][0, 0], sim["irr_trace"][0, 0]
    i_today = (today - start).days
    horizon = range(max(i_today, 0), min(i_today + 16, len(days)))
    events = [dict(date=str(days[i]), net_mm=round(float(irr[i]), 1),
                   gross_m3_per_feddan=round(float(irr[i]) / A["irrigation_efficiency"] * 4.2))
              for i in horizon if irr[i] > 1.0]
    rain = [str(days[i]) for i in horizon if float(joined["PRECTOTCORR"].get(pd.Timestamp(days[i]), 0) or 0) > 10]
    cal = wb.calendar(rotation)
    crop_now = next((c for j, c, s, e in cal if s <= i_today < e), None)
    nxt = next(((c, s) for j, c, s, e in cal if s >= i_today), None)
    next_crop = dict(crop=nxt[0], sow=str(days[nxt[1]]) if nxt[1] < len(days) else None) if nxt else None
    return dict(available=True, crop_now=crop_now, next_crop=next_crop, start=str(days[horizon.start]) if len(horizon) else None,
                wetness=[dict(date=str(days[i]), value=round(float(wet[i]), 3),
                              forecast=bool(pd.Timestamp(days[i]) >= fc.index[0]) if len(fc) else False) for i in horizon],
                irrigate_on=events if irrigated else [], rain_refills=rain,
                forecast_rain_mm=round(float(fc["PRECTOTCORR"].sum()), 1), forecast_et0_mm=round(float(fc["ET0"].sum()), 1),
                source="computed: FAO-56 balance on nasa:POWER to " + str(w.index[-1].date()) + ", then Open-Meteo 16-day forecast (non-NASA)")


def seasonal(site: dict, offline: bool = False) -> dict:
    d = _cached("seas5", "https://seasonal-api.open-meteo.com/v1/seasonal",
                dict(latitude=round(site["lat"], 3), longitude=round(site["lon"], 3), forecast_days=183,
                     daily="temperature_2m_max,precipitation_sum"), offline)
    if not d or "daily" not in d:
        return dict(available=False)
    dd = d["daily"]
    idx = pd.to_datetime(dd["time"])
    rain_m = [k for k in dd if k.startswith("precipitation_sum_member")]
    tmax_m = [k for k in dd if k.startswith("temperature_2m_max_member")]
    w = site["weather"]
    first = idx[0] + pd.Timedelta(days=1)
    out = []
    for months in (3, 6):
        end = first + pd.DateOffset(months=months)
        sel = (idx >= first) & (idx < end)
        if sel.sum() < 25:
            continue
        r_mem = np.array([np.nansum(np.array(dd[k], dtype=float)[sel]) for k in rain_m])
        t_mem = np.array([np.nanmean(np.array(dd[k], dtype=float)[sel]) for k in tmax_m])
        # 30-year POWER distribution for the same calendar window
        clim_r, clim_t = [], []
        for y in range(w.index[-1].year - 31, w.index[-1].year - 1):
            a = pd.Timestamp(y, first.month, min(first.day, 28))
            b = a + pd.DateOffset(months=months)
            seg = w.loc[a:b - pd.Timedelta(days=1)]
            if len(seg) > 25:
                clim_r.append(seg["PRECTOTCORR"].sum())
                clim_t.append(seg["T2M_MAX"].mean())
        terc = lambda mem, clim: dict(
            below=float(np.mean(mem < np.quantile(clim, 1 / 3))), normal=float(np.mean((mem >= np.quantile(clim, 1 / 3)) & (mem <= np.quantile(clim, 2 / 3)))),
            above=float(np.mean(mem > np.quantile(clim, 2 / 3))))
        out.append(dict(months=months, start=str(first.date()), end=str((end - pd.Timedelta(days=1)).date()),
                        members=len(rain_m),
                        rain=dict(member_median_mm=round(float(np.median(r_mem)), 1), normal_mm=round(float(np.median(clim_r)), 1), **terc(r_mem, clim_r)),
                        tmax=dict(member_median_c=round(float(np.median(t_mem)), 2), normal_c=round(float(np.median(clim_t)), 2), **terc(t_mem, clim_t))))
    return dict(available=bool(out), periods=out, used_in_scores=False,
                caveat="ECMWF SEAS5 via Open-Meteo (non-NASA), compared with the site's 30-year NASA POWER record without bias "
                       "correction. Context only: not used in any score.",
                source="Open-Meteo seasonal API (ECMWF SEAS5)")
