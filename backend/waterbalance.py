"""Daily FAO-56 root-zone water balance, run for many rotations × many past years at once.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

FAO-56 chapter 8 (single crop coefficient):
    TAW = 1000 (θFC − θWP) Zr            RAW = p · TAW,  p = p_table + 0.04 (5 − ETc)
    Ks  = 1                 if Dr ≤ RAW
        = (TAW − Dr) / ((1 − p) TAW)     otherwise
    ETa = Ks · Kc · ET0
    Dr,i = Dr,i−1 − (P − RO) − I + ETa + DP      (clamped to 0 … TAW; excess = deep percolation)

Runoff: NRCS curve number, S = 25400/CN − 254, Ia = 0.2·S, RO = (P − Ia)² / (P − Ia + S) for P > Ia,
with CN by soil class and by whether the day is cropped or bare (USDA TR-55). Adopted from the
AgroTwin engine by Yaseen Abdelal (single CN there; per-soil, per-cover here).

A rotation is 6 slots over 3 agricultural years (Oct 1 → Sep 30): winter, summer,
winter, summer, winter, summer; a slot holds a crop or 'fallow'. Every rotation is
simulated on every replay window (start year y uses the real weather of y, y+1, y+2)
in one vectorised loop over days: state arrays are (rotations, windows).

Irrigated fields refill to field capacity at sowing and whenever depletion passes RAW,
until the season's water cap runs out. Rain-fed fields never irrigate.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from config import A
from crops import CROPS, FALLOW, total_days
from soil import taw_per_m

YEARS = 3
SLOTS = 2 * YEARS
T_DAYS = 365 * YEARS + 75          # room for the last summer crop to finish
SEASON_OF_SLOT = ["winter", "summer"] * YEARS


# Sowing-date shift by season (days), used by the planner to stagger or adapt sowing inside the planting window.
SOW_SHIFT = {"winter": 0, "summer": 0}


def sow_offset(crop: str) -> int:
    m, d = CROPS[crop]["sow"]
    return (date(2001 if m >= 10 else 2002, m, d) - date(2001, 10, 1)).days + SOW_SHIFT.get(CROPS[crop]["season"], 0)


def calendar(rotation: tuple[str, ...]) -> list[tuple[int, str, int, int]] | None:
    """[(slot, crop, start_day, end_day)] counted from Oct 1 of year 1, or None if infeasible."""
    out, prev_end = [], -10_000
    for j, crop in enumerate(rotation):
        if crop == FALLOW:
            continue
        if CROPS[crop]["season"] != SEASON_OF_SLOT[j]:
            return None
        start = 365 * (j // 2) + sow_offset(crop)
        end = start + total_days(crop)
        if start < prev_end + A["gap_days"] or end > T_DAYS:
            return None
        out.append((j, crop, start, end))
        prev_end = end
    return out


def _calendar_arrays(cal, zr_min: float, bare_zr: float):
    kc = np.zeros(T_DAYS)
    zr = np.full(T_DAYS, bare_zr)
    pt = np.full(T_DAYS, 0.5)
    slot = np.full(T_DAYS, -1, dtype=int)
    crit = np.zeros(T_DAYS, dtype=bool)
    thr = np.full(T_DAYS, np.inf)
    flooded = np.zeros(T_DAYS, dtype=bool)
    sow = np.zeros(T_DAYS, dtype=bool)
    for j, crop, s, e in cal:
        c = CROPS[crop]
        ini, dev, mid, late = c["stages"]
        k0, k1, k2 = c["kc"]
        kc[s:e] = np.concatenate([np.full(ini, k0), np.linspace(k0, k1, dev, endpoint=False),
                                  np.full(mid, k1), np.linspace(k1, k2, late)])
        root = np.concatenate([np.linspace(zr_min, c["root_m"], ini + dev, endpoint=False),
                               np.full(mid + late, c["root_m"])])
        zr[s:e] = root
        pt[s:e] = c["p"]
        slot[s:e] = j
        a, b = c["critical"]
        crit[s + a:s + b] = True
        thr[s:e] = c["heat_tmax"]
        flooded[s:e] = bool(c.get("flooded"))
        sow[s] = True
    return kc, zr, pt, slot, crit, thr, flooded, sow


def windows(weather: pd.DataFrame, first_year: int | None = None) -> list[int]:
    """Start years whose full window (spin-up + 3 years + tail) has weather."""
    first_year = first_year or A["replay_first_year"]
    last = weather.index[-1]
    ys = []
    for y in range(first_year, last.year + 1):
        start = pd.Timestamp(y, 10, 1) - pd.Timedelta(days=A["spinup_days"])
        end = pd.Timestamp(y, 10, 1) + pd.Timedelta(days=T_DAYS - 1)
        if start >= weather.index[0] and end <= last:
            ys.append(y)
    return ys


def weather_matrices(weather: pd.DataFrame, years: list[int]) -> dict:
    spin = A["spinup_days"]
    idx0 = weather.index.get_indexer([pd.Timestamp(y, 10, 1) for y in years]) - spin
    rng = idx0[:, None] + np.arange(spin + T_DAYS)[None, :]
    get = lambda col: weather[col].to_numpy(dtype=float)[rng]
    et0 = np.nan_to_num(get("ET0"), nan=4.0)
    rain = np.nan_to_num(get("PRECTOTCORR"), nan=0.0)
    tmax = np.nan_to_num(get("T2M_MAX"), nan=25.0)
    return dict(et0=et0, rain=rain, tmax=tmax, years=list(years))


def site_warming_trend(weather: pd.DataFrame) -> float:
    """°C per year: linear trend of annual mean Tmax over the full POWER record (complete years)."""
    ann = weather["T2M_MAX"].groupby(weather.index.year).agg(["mean", "count"])
    ann = ann[ann["count"] >= 360]["mean"]
    return float(np.polyfit(ann.index.values.astype(float), ann.values, 1)[0])


def weather_matrices_adjusted(weather: pd.DataFrame, years: list[int], lat: float, elev: float,
                              target_year: int, trend: float | None = None) -> dict:
    """Climate-adjusted replay: each past window is warmed to target_year's climate by the site's
    own measured Tmax trend (all three temperatures shifted, ET0 recomputed with FAO-56).
    Backtest (qa/BACKTEST.md): improves irrigation CRPS by ~29% and profit coverage 70% → 78%."""
    import data_sources as ds
    trend = site_warming_trend(weather) if trend is None else trend
    spin = A["spinup_days"]
    cols = {"et0": [], "rain": [], "tmax": []}
    for y in years:
        i0 = weather.index.get_loc(pd.Timestamp(y, 10, 1)) - spin
        sl = weather.iloc[i0:i0 + spin + T_DAYS].drop(columns=["ET0"], errors="ignore").copy()
        dT = trend * (target_year - y)
        for c in ("T2M", "T2M_MAX", "T2M_MIN"):
            sl[c] = sl[c] + dT
        sl = ds.add_et0(sl, lat, elev)
        cols["et0"].append(np.nan_to_num(sl["ET0"].to_numpy(float), nan=4.0))
        cols["rain"].append(np.nan_to_num(sl["PRECTOTCORR"].to_numpy(float), nan=0.0))
        cols["tmax"].append(np.nan_to_num(sl["T2M_MAX"].to_numpy(float), nan=25.0))
    return dict(et0=np.stack(cols["et0"]), rain=np.stack(cols["rain"]), tmax=np.stack(cols["tmax"]),
                years=list(years), adjusted_to=target_year, trend_per_decade=round(trend * 10, 3))


def simulate(rotations: list[tuple[str, ...]], wx: dict, soil_class: str, irrigated: bool,
             cap_net_mm: dict | None = None, irrigation_days: np.ndarray | None = None,
             keep_wetness_days: int = 0) -> dict:
    """Run every rotation on every window.

    cap_net_mm: {"winter": mm, "summer": mm} net irrigation allowed per season (None = no cap).
    irrigation_days: optional bool array over calendar days of year 1; when given, irrigation
        in year 1 happens only on those days (the farmer's log), used by fusion.
    Returns per-slot arrays shaped (R, W, SLOTS) and per-rotation arrays (R, W).
    """
    cals = [calendar(r) for r in rotations]
    if any(c is None for c in cals):
        bad = [r for r, c in zip(rotations, cals) if c is None]
        raise ValueError(f"infeasible rotation(s): {bad}")
    R, W = len(rotations), len(wx["years"])
    spin = A["spinup_days"]
    taw_m = taw_per_m(soil_class)
    bare_zr = A["bare_root_m"]
    arrs = [_calendar_arrays(c, A["zr_min_m"], bare_zr) for c in cals]
    KC, ZR, PT, SL, CR, TH, FL, SW = (np.stack([a[i] for a in arrs]) for i in range(8))

    heavy = A["heavy_rain_mm"]
    def _cn_s(cn):
        return 25400.0 / cn - 254.0
    S_crop, S_bare = _cn_s(A["runoff_cn_crop"][soil_class]), _cn_s(A["runoff_cn_bare"][soil_class])

    def runoff(P, S):
        ia = 0.2 * S
        return np.where(P > ia, (P - ia) ** 2 / (P - ia + S), 0.0)
    kbare = A["bare_evap_coef"]
    perc, puddle = A["rice_percolation_mm_day"], A["rice_puddling_mm"]

    cap = np.full((R, W, SLOTS), np.inf)
    if irrigated and cap_net_mm:
        for j in range(SLOTS):
            cap[:, :, j] = cap_net_mm[SEASON_OF_SLOT[j]]

    acc = {k: np.zeros((R, W, SLOTS)) for k in
           ("etc", "eta", "irr", "irr_gross", "deficit_days", "severe_days", "heat_days", "rain", "transp_days")}
    bare_days = np.zeros((R, W))
    erosion = np.zeros((R, W))
    dp_sum = np.zeros((R, W))
    ro_sum = np.zeros((R, W))
    in_sum = np.zeros((R, W))
    et_sum = np.zeros((R, W))
    clamp_loss = np.zeros((R, W))
    keep = min(keep_wetness_days, T_DAYS)
    wet_trace = np.zeros((R, W, keep)) if keep else None
    irr_trace = np.zeros((R, W, keep)) if keep else None

    ar = np.arange(R)
    aw = np.arange(W)
    Dr = np.zeros((R, W))
    Dr0 = None

    for t in range(spin + T_DAYS):
        et0, P, tmax = wx["et0"][:, t], wx["rain"][:, t], wx["tmax"][:, t]
        if t < spin:                                    # bare-soil spin-up
            taw = taw_m * bare_zr
            Dr = np.minimum(Dr, taw)
            E = kbare * (1 - Dr / taw) * et0[None, :]
            ro = runoff(P, S_bare)[None, :]
            Dr = Dr - (P[None, :] - ro) + E
            Dr = np.clip(Dr, 0, taw)
            continue
        if Dr0 is None:
            Dr0 = Dr.copy()
        c = t - spin
        kc, zr, pt, sl = KC[:, c], ZR[:, c], PT[:, c], SL[:, c]
        crop = (sl >= 0)[:, None]
        taw = (taw_m * zr)[:, None]
        over = np.maximum(Dr - taw, 0)                  # root zone shrank after harvest
        clamp_loss += over
        Dr = Dr - over

        etc = kc[:, None] * et0[None, :]
        p = np.clip(pt[:, None] + 0.04 * (5 - etc), 0.1, 0.8)
        raw = p * taw

        I = np.zeros((R, W))
        if irrigated:
            fl = FL[:, c][:, None]
            sow = SW[:, c][:, None]
            if irrigation_days is not None and c < len(irrigation_days):
                want = crop & (irrigation_days[c] | fl)
            else:
                want = crop & (sow | fl | (Dr > raw))
            need = np.where(want, Dr + np.where(fl, perc, 0.0) + np.where(fl & sow, puddle, 0.0), 0.0)
            slc = np.maximum(sl, 0)
            left = cap[ar[:, None], aw[None, :], slc[:, None]]
            I = np.where(crop, np.minimum(need, left), 0.0)
            cap[ar[:, None], aw[None, :], slc[:, None]] = left - I
            Dr = Dr - I

        ks = np.where(Dr <= raw, 1.0, np.clip((taw - Dr) / ((1 - p) * taw), 0, 1))
        eta = ks * etc
        E = kbare * np.clip(1 - Dr / taw, 0, 1) * et0[None, :]
        ET = np.where(crop, eta, E)

        ro = np.where(crop, runoff(P, S_crop)[None, :], runoff(P, S_bare)[None, :])
        inf = P[None, :] - ro
        # Flooded rice loses water below the root zone every day (and the puddling water
        # at transplanting): forced deep percolation, so it cannot feed ET.
        forced = 0.0
        if irrigated:
            forced = np.where(crop & FL[:, c][:, None], perc + np.where(SW[:, c][:, None], puddle, 0.0), 0.0)
        Dr = Dr - inf + ET + forced
        dp = np.maximum(-Dr, 0) + forced
        Dr = np.maximum(Dr, 0)
        Dr = np.minimum(Dr, taw)

        dp_sum += dp
        et_sum += ET
        ro_sum += ro
        in_sum += P[None, :] + I
        if keep and c < keep:
            wet_trace[:, :, c] = 1 - Dr / taw
            irr_trace[:, :, c] = I

        if crop.any():
            ii = (ar[:, None], aw[None, :], np.maximum(sl, 0)[:, None])
            m = crop.astype(float)
            acc["etc"][ii] += etc * m
            acc["eta"][ii] += eta * m
            acc["irr"][ii] += I * m
            # Flooded rice: percolation and puddling are modelled explicitly, so the
            # application-efficiency factor is not applied on top of them.
            acc["irr_gross"][ii] += np.where(FL[:, c][:, None], I, I / A["irrigation_efficiency"]) * m
            acc["deficit_days"][ii] += (ks < 1) * m
            acc["severe_days"][ii] += (ks <= 0.0) * m          # root zone at wilting point
            acc["transp_days"][ii] += m
            acc["rain"][ii] += P[None, :] * m
            acc["heat_days"][ii] += (CR[:, c][:, None] & (tmax[None, :] > TH[:, c][:, None])) * m
        bare = ~crop
        bare_days += bare
        erosion += np.where(bare & (P[None, :] > heavy), P[None, :], 0.0)

    return dict(
        rotations=rotations, years=wx["years"], calendars=cals,
        etc=acc["etc"], eta=acc["eta"], irr_net=acc["irr"], irr_gross=acc["irr_gross"],
        transp_days=acc["transp_days"], deficit_days=acc["deficit_days"], severe_days=acc["severe_days"], heat_days=acc["heat_days"], rain_in_season=acc["rain"],
        bare_days=bare_days, erosion=erosion,
        # mass balance terms (tests): inputs − ET − DP − RO − clamp = Δstorage
        _in=in_sum, _et=et_sum, _dp=dp_sum, _ro=ro_sum, _clamp=clamp_loss, _Dr0=Dr0, _Dr1=Dr,
        wet=wet_trace, irr_trace=irr_trace,
    )
