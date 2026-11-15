"""Field Pulse — a hybrid physics + machine-learning model of field greenness.

What it does
    Forecasts the field's MODIS NDVI 16 and 32 days ahead as a range (10th, 50th, 90th percentile),
    and checks the newest satellite image against what the model expected from the weather.

How
    Features per MODIS composite (16-day, 250 m):
      - the field's own recent NDVI (last four composites) and its slope
      - the field's own seasonal normal for this date and the target date (leave-one-year-out in training)
      - NASA POWER weather of the last 16–90 days: rain, reference ET (FAO-56 Penman-Monteith), heat, GWETROOT
      - physics: an FAO-56 single-bucket water balance driven by an NDVI-derived crop coefficient
        (Kc = 1.25·NDVI − 0.10, assumption:ndvi_kc) → crop water demand and water-stress factor Ks
    Model: gradient-boosted trees with quantile loss (scikit-learn), one per horizon and percentile,
    predicting the change in NDVI. Trained and tested by qa/pulse_train.py → qa/PULSE.md.

Why it matters
    If the newest image is below the model's 10th percentile, the drop is not explained by the weather
    or the field's usual season: something on the field (pests, salinity, a missed irrigation) — the
    place to send the Verdex Scout.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_PATH = Path(__file__).resolve().parent / "models" / "pulse.pkl"
QUANTILES = (0.1, 0.5, 0.9)
HORIZONS = (1, 2)            # composites ahead (16 and 32 days)
KC_A, KC_B = 1.25, -0.10     # assumption:ndvi_kc (linear NDVI→Kc, FAO-56 ch. 9 style)
TAW, P_DEP = 100.0, 0.5      # assumption:pulse_bucket (generic root zone, mm; depletion fraction)

FEATURES = ["n0", "n1", "n2", "n3", "slope1", "slope2", "c0", "ch", "a0", "cdelta", "cmax", "camp",
            "sin_t", "cos_t", "rain16", "rain60", "et0_16", "tmax16", "tmax_anom", "heat16", "gwet",
            "deficit30", "etc16", "ks16", "ks_min60", "rain_annual", "lat", "h"]

def _composites(ndvi: pd.Series) -> pd.Series:
    s = ndvi.sort_index()
    s = s[~s.index.duplicated()]
    return s.interpolate(limit=2, limit_area="inside")

def _climatology(s: pd.Series, loyo: bool) -> pd.DataFrame:
    """Mean NDVI per composite day-of-year. With loyo, each year's own value is left out."""
    df = pd.DataFrame({"v": s.values, "doy": s.index.day_of_year, "yr": s.index.year}, index=s.index)
    g = df.groupby("doy")["v"]
    tot, cnt = g.transform("sum"), g.transform("count")
    if loyo:
        own = df["v"].fillna(0)
        n = cnt - df["v"].notna()
        df["clim"] = np.where(n > 0, (tot - own) / n.replace(0, np.nan), np.nan)
    else:
        df["clim"] = tot / cnt
    by_doy = g.mean()
    return df, by_doy

def _bucket(weather: pd.DataFrame, kc_daily: pd.Series) -> pd.DataFrame:
    """FAO-56 single bucket, rain only (what the sky alone would do for this canopy)."""
    et0 = weather["ET0"].fillna(0).values
    rain = weather["PRECTOTCORR"].fillna(0).values
    kc = kc_daily.reindex(weather.index).ffill().bfill().fillna(0.3).values
    dr, ks_out, etc_out = 0.0, np.empty(len(et0)), np.empty(len(et0))
    raw = P_DEP * TAW
    for i in range(len(et0)):
        ks = 1.0 if dr <= raw else max(0.0, (TAW - dr) / (TAW - raw))
        etc = kc[i] * et0[i]
        dr = min(TAW, max(0.0, dr - rain[i] + ks * etc))
        ks_out[i], etc_out[i] = ks, etc
    return pd.DataFrame({"ks": ks_out, "etc": etc_out}, index=weather.index)

def _window(cum: np.ndarray, end: np.ndarray, n: int) -> np.ndarray:
    """Sum of the n days ending at index `end` (inclusive), from a cumulative-sum array."""
    lo = np.clip(end - n, -1, None)
    return cum[end] - np.where(lo >= 0, cum[np.maximum(lo, 0)], 0.0)

def build_rows(ndvi: pd.Series, weather: pd.DataFrame, lat: float, loyo: bool = True,
               with_target: bool = True) -> pd.DataFrame:
    """Vectorised feature builder: one row per (composite, horizon). Same features as v1."""
    s = _composites(ndvi)
    cdf, by_doy = _climatology(s, loyo)
    clim_all = by_doy
    w = weather.loc[weather.index >= s.index[0] - pd.Timedelta(days=120)].copy()
    if len(w) < 200:
        return pd.DataFrame()
    kc = (KC_A * s + KC_B).clip(0.15, 1.2)
    kc_daily = kc.resample("D").interpolate()
    phys = _bucket(w, kc_daily)
    tnorm = weather["T2M_MAX"].groupby(weather.index.day_of_year).mean()
    rain_annual = float(weather["PRECTOTCORR"].resample("YE").sum().iloc[-11:-1].mean())
    didx = w.index
    rain = w["PRECTOTCORR"].fillna(0).to_numpy(); et0 = w["ET0"].fillna(0).to_numpy()
    tmax = w["T2M_MAX"].ffill().bfill().to_numpy(); gw = w["GWETROOT"].ffill().bfill().to_numpy()
    tanom = tmax - tnorm.reindex(didx.day_of_year).to_numpy()
    heat = (tmax > 35).astype(float)
    ks, etc = phys["ks"].to_numpy(), phys["etc"].to_numpy()
    C = {k: np.cumsum(v) for k, v in dict(rain=rain, et0=et0, tmax=tmax, gw=gw, tanom=tanom, heat=heat, etc=etc, ks=ks, def_=et0 - rain).items()}
    vals, idx = s.to_numpy(), s.index
    t_end = idx + pd.Timedelta(days=15)
    pos = didx.get_indexer(t_end)
    ok = (pos >= 60) & np.isfinite(vals)
    ok[:3] = False
    for k in (1, 2, 3):
        ok[k:] &= np.isfinite(vals[:-k])
    ii = np.where(ok)[0]
    if not len(ii):
        return pd.DataFrame()
    e = pos[ii]
    n = np.stack([vals[ii - k] for k in range(4)], 1)
    ks60 = np.array([ks[max(0, x - 59):x + 1].min() for x in e])
    c0 = cdf["clim"].to_numpy()[ii] if loyo else clim_all.reindex(idx[ii].day_of_year).to_numpy()
    base = dict(
        date=idx[ii], n0=n[:, 0], n1=n[:, 1], n2=n[:, 2], n3=n[:, 3], slope1=n[:, 0] - n[:, 1], slope2=n[:, 1] - n[:, 2],
        c0=c0, cmax=float(clim_all.max()), camp=float(clim_all.max() - clim_all.min()),
        rain16=_window(C["rain"], e, 16), rain60=_window(C["rain"], e, 60), et0_16=_window(C["et0"], e, 16),
        tmax16=_window(C["tmax"], e, 16) / 16, tmax_anom=_window(C["tanom"], e, 16) / 16, heat16=_window(C["heat"], e, 16),
        gwet=_window(C["gw"], e, 16) / 16, deficit30=_window(C["def_"], e, 30), etc16=_window(C["etc"], e, 16),
        ks16=_window(C["ks"], e, 16) / 16, ks_min60=ks60, rain_annual=rain_annual, lat=lat)
    base["a0"] = base["n0"] - base["c0"]
    frames = []
    for h in HORIZONS:
        tgt_i = ii + h
        has = tgt_i < len(s)
        if with_target:
            keep = has & np.isfinite(np.where(has, vals[np.minimum(tgt_i, len(s) - 1)], np.nan))
        else:
            keep = np.ones(len(ii), bool)
        if not keep.any():
            continue
        tdate = pd.DatetimeIndex([idx[t] if t < len(s) else idx[i] + pd.Timedelta(days=16 * h) for t, i in zip(tgt_i, ii)])
        if loyo:
            ch = np.where(has, cdf["clim"].to_numpy()[np.minimum(tgt_i, len(s) - 1)], np.nan)
            miss = ~has | ~np.isfinite(ch)
            ch[miss] = np.interp(tdate.day_of_year[miss], clim_all.index, clim_all.values, period=366)
        else:
            ch = np.interp(tdate.day_of_year, clim_all.index, clim_all.values, period=366)
        f = pd.DataFrame({k: (v[keep] if isinstance(v, np.ndarray) else (v[keep] if hasattr(v, "__len__") and not isinstance(v, str) else v)) for k, v in base.items()})
        f["h"] = h; f["target_date"] = tdate[keep]; f["ch"] = ch[keep]; f["cdelta"] = f["ch"] - f["c0"]
        f["sin_t"] = np.sin(2 * np.pi * tdate[keep].day_of_year / 365.25); f["cos_t"] = np.cos(2 * np.pi * tdate[keep].day_of_year / 365.25)
        if with_target:
            f["y"] = vals[tgt_i[keep]]
        frames.append(f)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return out.dropna(subset=[c for c in FEATURES if c in out.columns]) if len(out) else out

# ---------------------------------------------------------------------------
# inference
# ---------------------------------------------------------------------------

_MODEL = None

def load():
    global _MODEL
    if _MODEL is None and MODEL_PATH.exists():
        with open(MODEL_PATH, "rb") as f:
            _MODEL = pickle.load(f)
    return _MODEL

def predict(rows: pd.DataFrame) -> pd.DataFrame:
    m = load()
    out = rows.copy()
    X = rows[FEATURES].astype(float).values
    for q in QUANTILES:
        out[f"q{int(q * 100)}"] = rows["n0"].values + m["models"][q].predict(X)
    qs = np.sort(out[["q10", "q50", "q90"]].values, axis=1)   # no quantile crossing
    wd = m.get("widen", 0.0)                                   # split-conformal widening (qa/pulse_train.py)
    out["q10"], out["q50"], out["q90"] = (qs[:, 0] - wd).clip(-0.2, 1), qs[:, 1], (qs[:, 2] + wd).clip(-0.2, 1)
    return out

def field_pulse(ndvi: pd.Series, weather: pd.DataFrame, lat: float) -> dict:
    m = load()
    if m is None:
        return dict(available=False, reason="model not trained yet (python qa/pulse_train.py)")
    if ndvi is None or len(ndvi.dropna()) < 60:
        return dict(available=False, reason="not enough MODIS NDVI history for this field yet")
    s = _composites(ndvi).dropna()
    # 1) check the newest images against what the model expected one and two composites earlier
    hist = build_rows(s, weather, lat, loyo=False, with_target=True)
    hist = hist[hist["date"] >= s.index[-1] - pd.Timedelta(days=400)]
    hist = predict(hist) if len(hist) else hist
    checks = []
    for _, r in hist.iterrows():
        if r["h"] != 1:
            continue
        status = "below" if r["y"] < r["q10"] else ("above" if r["y"] > r["q90"] else "expected")
        checks.append(dict(date=str(r["target_date"].date()), observed=round(r["y"], 3), expected=round(r["q50"], 3),
                           low=round(r["q10"], 3), high=round(r["q90"], 3), status=status))
    latest = checks[-1] if checks else None
    # 2) forecast from the newest composite
    fut = build_rows(s, weather, lat, loyo=False, with_target=False)
    fut = fut[fut["date"] == fut["date"].max()] if len(fut) else fut
    forecast = []
    if len(fut):
        fut = predict(fut)
        for _, r in fut.iterrows():
            forecast.append(dict(date=str(r["target_date"].date()), days_ahead=int(16 * r["h"]),
                                 low=round(r["q10"], 3), mid=round(r["q50"], 3), high=round(r["q90"], 3),
                                 normal=round(float(r["ch"]), 3)))
    recent_below = sum(c["status"] == "below" for c in checks[-4:])
    clim = s.groupby(s.index.day_of_year).mean()
    return dict(
        available=True, latest_image=str(s.index[-1].date()), latest_ndvi=round(float(s.iloc[-1]), 3),
        normal_now=round(float(clim.get(s.index[-1].day_of_year, np.nan)), 3),
        latest_check=latest, checks=checks, forecast=forecast,
        send_scout=bool(latest and latest["status"] == "below") or recent_below >= 2,
        skill=m.get("summary"), trained_on=m.get("trained_on"),
        source="computed: Field Pulse (gradient-boosted quantile trees) trained on nasa:MODIS MOD13Q1 + nasa:POWER; qa/PULSE.md",
        caveat="NDVI is greenness, not yield. A 'below' image means the weather does not explain the drop; it does not say why.")
