"""Two things a farm-twin usually cannot do.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

1. Time machine — "your field's last ten years, read from space".
   MODIS NDVI (250 m) shows, season by season, whether this field was green (cropped) or bare.
   Each detected season is replayed on that year's real NASA POWER weather for the farmer's own
   crops, and for the suggested rotation. Result: what the field actually used and earned, what
   the alternative would have, and the running difference since 2015.

2. Canal mode — neighbours on one canal plan together.
   Delta canals deliver water on a rotation; the shared constraint is the canal's peak weekly
   demand in summer. For each farm we take its best few rotations (all within 10 % of its own
   best score), build each one's average daily irrigation profile from the replay, scale it by
   the farm's area, and pick the combination that minimises the canal's peak 7-day demand.
   No farmer gives up more than the tolerance; the canal gets a lower peak.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import econ
import replay as rp
import waterbalance as wb
from crops import CROPS, FALLOW, MM_TO_M3_PER_FEDDAN

FEDDAN_HA = 0.42


# ---------------------------------------------------------------------------
# 1. Time machine
# ---------------------------------------------------------------------------

def _season_flags(ndvi: pd.Series, y: int) -> dict:
    """Was the field green in the winter (Dec–Apr) and summer (Jun–Oct) of agricultural year y?"""
    out = {}
    for name, a, b in (("winter", pd.Timestamp(y, 12, 1), pd.Timestamp(y + 1, 4, 30)),
                       ("summer", pd.Timestamp(y + 1, 6, 1), pd.Timestamp(y + 1, 10, 15))):
        seg = ndvi[(ndvi.index >= a) & (ndvi.index <= b)].dropna()
        if len(seg) < 4:
            out[name] = dict(peak=None, cropped=None)
            continue
        peak, low = float(seg.max()), float(seg.min())
        out[name] = dict(peak=round(peak, 3), amplitude=round(peak - low, 3),
                         cropped=bool(peak >= 0.45 and (peak - low) >= 0.12),
                         peak_date=str(seg.idxmax().date()))
    return out


def time_machine(weather_raw: pd.DataFrame, ndvi: pd.Series, existing: tuple, suggested: tuple,
                 soil_class: str, irrigated: bool, prices: dict, overrides: dict) -> dict:
    if ndvi is None or len(ndvi.dropna()) < 40:
        return dict(available=False, reason="no MODIS NDVI history for this point yet")
    years = [y for y in wb.windows(weather_raw) if y >= ndvi.dropna().index[0].year]
    if len(years) < 3:
        return dict(available=False, reason="too few seasons with both NDVI and weather")
    wx = wb.weather_matrices(weather_raw, years)
    sim = wb.simulate([existing, suggested], wx, soil_class, irrigated)
    eco = econ.slot_economics(sim, prices, 1.0, overrides)
    rows, cw, cp = [], 0.0, 0.0
    for k, y in enumerate(years):
        fl = _season_flags(ndvi, y)
        seasons = []
        act_w = act_p = alt_w = alt_p = 0.0
        for j, sname in ((0, "winter"), (1, "summer")):
            crop_e, crop_s = existing[j], suggested[j]
            seen = fl[sname]["cropped"]
            # What the field did: the farmer's crop where the satellite saw green, bare where it didn't.
            used = crop_e != FALLOW and seen is not False
            if used:
                act_w += sim["irr_gross"][0, k, j] * MM_TO_M3_PER_FEDDAN
                act_p += eco["profit"][0, k, j]
            if crop_s != FALLOW:
                alt_w += sim["irr_gross"][1, k, j] * MM_TO_M3_PER_FEDDAN
                alt_p += eco["profit"][1, k, j]
            seasons.append(dict(season=sname, satellite=fl[sname], your_crop=crop_e if used else FALLOW,
                                suggested_crop=crop_s))
        cw += act_w - alt_w
        cp += alt_p - act_p
        rows.append(dict(year=f"{y}/{str(y + 1)[2:]}", seasons=seasons,
                         actual=dict(water_m3=round(act_w), profit=round(act_p)),
                         suggested=dict(water_m3=round(alt_w), profit=round(alt_p)),
                         cum_water_saved_m3=round(cw), cum_extra_profit=round(cp)))
    detected = sum(1 for r in rows for s in r["seasons"] if s["satellite"]["cropped"])
    total = sum(1 for r in rows for s in r["seasons"] if s["satellite"]["cropped"] is not None)
    return dict(available=True, years=rows, seasons_seen=total, seasons_green=detected,
                per_feddan=True, first=rows[0]["year"], last=rows[-1]["year"],
                source="nasa:MODIS MOD13Q1 (green or bare, per season) + nasa:POWER weather replayed through the FAO-56 model",
                caveat="The satellite sees whether the field was green, not which crop; your crop names come from what you told us.")


# ---------------------------------------------------------------------------
# 2. Canal mode
# ---------------------------------------------------------------------------

def daily_profile(rotation: tuple, wx: dict, soil_class: str, irrigated: bool) -> np.ndarray:
    """Average gross irrigation per day (mm) over the first 365 days of the season, across all past years."""
    sim = wb.simulate([rotation], wx, soil_class, irrigated, keep_wetness_days=365)
    gross = sim["irr_trace"][0] / 0.6          # net → gross with the irrigation-efficiency assumption
    return gross.mean(0)


def weekly_peak(m3_per_day: np.ndarray) -> tuple[float, int]:
    wk = np.convolve(m3_per_day, np.ones(7), mode="valid")
    i = int(np.argmax(wk))
    return float(wk[i]), i


SHIFTS = (-14, 0, 14)   # days: stagger summer sowing inside the planting window (assumption:canal_shift_days)


def _shift_summer(prof: np.ndarray, rot: tuple, shift: int) -> np.ndarray:
    """Move the summer crop's irrigation by `shift` days (first-year summer slot only).
    Approximation: the same water, two weeks earlier or later; small changes in weather ignored."""
    if shift == 0:
        return prof
    cal = wb.calendar(rot)
    summer = next(((s, e) for j, c, s, e in cal if j == 1), None)
    if not summer:
        return prof
    s0 = max(summer[0] - 5, 0)
    out = prof.copy()
    seg = prof[s0:].copy()
    out[s0:] = 0
    dst = s0 + shift
    if dst < 0:
        seg, dst = seg[-dst:], 0
    n = min(len(seg), len(out) - dst)
    out[dst:dst + n] += seg[:n]
    return out


def canal(farms: list[dict], site_runs: dict, tolerance: float = 10.0, options: int = 3) -> dict:
    """farms: [{id, name, area_feddan, wx, soil_class, irrigated}]. Current vs each-alone vs coordinated."""
    per_farm = []
    for f in farms:
        res = site_runs[f["id"]]
        pool = sorted(res["_all"], key=lambda m: -m["total"])
        best = pool[0]["total"]
        ex = res["_all"][0]
        cands, seen = [], set()
        for m in pool:
            key = tuple(m["seq"])
            if key in seen or m["total"] < best - tolerance:
                continue
            seen.add(key)
            cands.append(m)
            if len(cands) >= options:
                break
        base = {}
        for m in [ex] + cands:
            key = tuple(m["seq"])
            if key not in base:
                base[key] = daily_profile(key, f["wx"], f["soil_class"], f["irrigated"]) * MM_TO_M3_PER_FEDDAN * f["area_feddan"]
        opts = [(ci, sh, _shift_summer(base[tuple(cands[ci]["seq"])], tuple(cands[ci]["seq"]), sh))
                for ci in range(len(cands)) for sh in SHIFTS]
        per_farm.append(dict(farm=f, existing=ex, cands=cands, base=base, opts=opts))

    now = sum(p["base"][tuple(p["existing"]["seq"])] for p in per_farm)
    alone = sum(p["base"][tuple(p["cands"][0]["seq"])] for p in per_farm)
    # greedy coordinate descent on the canal's peak 7-day demand
    choice = [next(i for i, o in enumerate(p["opts"]) if o[0] == 0 and o[1] == 0) for p in per_farm]
    total = alone.copy()
    for _ in range(4):
        improved = False
        for fi, p in enumerate(per_farm):
            rest = total - p["opts"][choice[fi]][2]
            scores = [weekly_peak(rest + o[2])[0] + 1e-6 * abs(o[1]) for o in p["opts"]]
            j = int(np.argmin(scores))
            if j != choice[fi]:
                choice[fi], total, improved = j, rest + p["opts"][j][2], True
        if not improved:
            break
    days = len(total)
    start = pd.Timestamp(pd.Timestamp.today().year if pd.Timestamp.today().month >= 10 else pd.Timestamp.today().year - 1, 10, 1)
    weeks = lambda arr: [round(float(x)) for x in np.add.reduceat(arr, np.arange(0, days, 7))]
    pk_now, i_now = weekly_peak(now)
    pk_alone, i_alone = weekly_peak(alone)
    pk_coord, i_coord = weekly_peak(total)
    farms_out = []
    for p, ci in zip(per_farm, choice):
        c_i, sh, _ = p["opts"][ci]
        ch, own = p["cands"][c_i], p["cands"][0]
        sow = None
        cal = wb.calendar(tuple(ch["seq"]))
        summer = next(((c, s) for j, c, s, e in cal if j == 1), None)
        if summer:
            sow = dict(crop=summer[0], date=str((start + pd.Timedelta(days=summer[1] + sh)).date()), shift_days=sh)
        farms_out.append(dict(
            id=p["farm"]["id"], name=p["farm"]["name"], area_feddan=round(p["farm"]["area_feddan"], 2),
            current=dict(seq=p["existing"]["seq"], total=p["existing"]["total"], water_m3=p["existing"]["water_m3"]["median"]),
            own_best=dict(seq=own["seq"], total=own["total"], water_m3=own["water_m3"]["median"]),
            coordinated=dict(seq=ch["seq"], total=ch["total"], water_m3=ch["water_m3"]["median"],
                             profit=ch["profit"]["median"], gives_up=round(own["total"] - ch["total"], 1), summer_sowing=sow)))
    return dict(
        farms=farms_out, tolerance=tolerance, shifts_days=list(SHIFTS), week_start=str(start.date()),
        weekly_m3=dict(current=weeks(now), each_alone=weeks(alone), coordinated=weeks(total)),
        peak_week_m3=dict(current=round(pk_now), each_alone=round(pk_alone), coordinated=round(pk_coord)),
        peak_date=dict(current=str((start + pd.Timedelta(days=i_now)).date()), each_alone=str((start + pd.Timedelta(days=i_alone)).date()),
                       coordinated=str((start + pd.Timedelta(days=i_coord)).date())),
        season_total_m3=dict(current=round(float(now.sum())), each_alone=round(float(alone.sum())), coordinated=round(float(total.sum()))),
        method="options: rotations within the tolerance of each farm's own best score × summer sowing moved −14/0/+14 days "
               "(inside the planting window); greedy search for the lowest canal peak 7-day demand",
        source="computed: replayed daily irrigation (FAO-56 on nasa:POWER, climate-adjusted) × farm area")


DEMO_CANAL = [
    dict(id="demo_a", name="Abu Hassan", lat=31.25, lon=30.95, area_feddan=3.0, existing=["wheat", "rice"]),
    dict(id="demo_b", name="Umm Mahmoud", lat=31.25, lon=30.95, area_feddan=1.5, existing=["wheat", "maize"]),
    dict(id="demo_c", name="El-Sayed brothers", lat=31.25, lon=30.95, area_feddan=6.0, existing=["wheat", "rice"]),
    dict(id="demo_d", name="Fathi", lat=31.25, lon=30.95, area_feddan=2.0, existing=["berseem", "maize"]),
    dict(id="demo_e", name="Coop plot", lat=31.25, lon=30.95, area_feddan=4.5, existing=["sugarbeet", "maize"]),
]
