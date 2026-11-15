"""NASA and soil data access, with an on-disk cache.

Every source here is real and public:

  NASA POWER (no login)         daily weather since 1981 + MERRA-2 root-zone
                                soil wetness (GWETROOT), used until SMAP is on
  MODIS via ORNL DAAC (no login) MOD13Q1 NDVI (250 m, 16-day) and
                                MOD16A2GF evapotranspiration (500 m, 8-day)
  SoilGrids / ISRIC (no login)  clay, sand, silt, organic carbon, pH
  Earthdata (login needed)      SMAP L4 and GPM IMERG — see scripts/fetch_earthdata.py;
                                their output lands in the same cache and is picked
                                up automatically when present

The app never calls a remote service during a demo if the cache has the data,
so a dead venue Wi-Fi does not kill the pitch.
"""
from __future__ import annotations

import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
from paths import DATA
CACHE = DATA / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "verdex-planner/1.0 (NASA Space Apps prototype)"}

POWER_PARAMS = [
    "T2M", "T2M_MAX", "T2M_MIN", "RH2M", "PRECTOTCORR",
    "ALLSKY_SFC_SW_DWN", "WS2M", "PS", "GWETROOT", "GWETTOP",
]
POWER_START = "19810101"

def _key(lat: float, lon: float) -> str:
    return f"{lat:.3f}_{lon:.3f}"

def _read(path: Path):
    return json.loads(path.read_text()) if path.exists() else None

def _write(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(path)

def _get(url: str, params: dict, timeout: int = 90, tries: int = 3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = RuntimeError(f"{r.status_code}: {r.text[:200]}")
        except requests.RequestException as exc:
            last = exc
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"request failed: {url} ({last})")

# ---------------------------------------------------------------------------
# NASA POWER
# ---------------------------------------------------------------------------

def power_daily(lat: float, lon: float, offline: bool = False) -> tuple[pd.DataFrame, float]:
    """Daily weather 1981 → latest. Returns (frame indexed by date, elevation m)."""
    path = CACHE / f"power_{_key(lat, lon)}.json"
    raw = _read(path)
    if raw is None:
        if offline:
            raise FileNotFoundError(f"no cached POWER data for {lat},{lon}")
        end = date.today().strftime("%Y%m%d")
        raw = _get(
            "https://power.larc.nasa.gov/api/temporal/daily/point",
            {
                "parameters": ",".join(POWER_PARAMS),
                "community": "AG",
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "start": POWER_START,
                "end": end,
                "format": "JSON",
            },
            timeout=60,
        )
        _write(path, raw)

    par = raw["properties"]["parameter"]
    df = pd.DataFrame(par)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(-999.0, np.nan).astype(float)
    # POWER publishes recent days with a lag; drop trailing rows with no temperature.
    df = df.loc[: df["T2M"].last_valid_index()]
    elev = float(raw["geometry"]["coordinates"][2])
    return df, elev

# ---------------------------------------------------------------------------
# MODIS through the ORNL DAAC web service (no login required)
# ---------------------------------------------------------------------------

ORNL = "https://modis.ornl.gov/rst/api/v1"

def _modis_series(product: str, band: str, lat: float, lon: float,
                  start: str, scale: float, valid: tuple[float, float],
                  offline: bool, workers: int = 6, progress: dict | None = None) -> pd.Series:
    """MODIS point series. ORNL serves 10 dates per request, so chunks run in
    parallel (`workers`) and `progress` (if given) is updated as they land."""
    path = CACHE / f"modis_{product}_{_key(lat, lon)}.json"
    cached = _read(path) or {"points": {}}
    pts: dict = cached["points"]

    if not offline:
        dates = _get(f"{ORNL}/{product}/dates", {"latitude": lat, "longitude": lon}, timeout=60)["dates"]
        todo = [d["modis_date"] for d in dates
                if d["calendar_date"] >= start and d["calendar_date"] not in pts]
        chunks = [todo[i:i + 10] for i in range(0, len(todo), 10)]
        if progress is not None:
            progress.update(done=0, total=len(chunks))

        def fetch(chunk):
            return _get(f"{ORNL}/{product}/subset", {
                "latitude": lat, "longitude": lon, "band": band,
                "startDate": chunk[0], "endDate": chunk[-1],
                "kmAboveBelow": 0, "kmLeftRight": 0,
            }, timeout=90)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for n, res in enumerate(pool.map(fetch, chunks), 1):
                for row in res.get("subset", []):
                    pts[row["calendar_date"]] = row["data"][0]
                if progress is not None:
                    progress["done"] = n
                if n % 5 == 0 or n == len(chunks):
                    _write(path, {"product": product, "band": band, "points": pts})

    if not pts:
        return pd.Series(dtype=float)
    ser = pd.Series(pts, dtype=float)
    ser.index = pd.to_datetime(ser.index)
    ser = ser.sort_index() * scale
    return ser.where((ser >= valid[0]) & (ser <= valid[1]))

def modis_cached(product: str, lat: float, lon: float) -> int:
    raw = _read(CACHE / f"modis_{product}_{_key(lat, lon)}.json")
    return len(raw["points"]) if raw else 0

def modis_ndvi(lat, lon, start="2015-01-01", offline=False, progress=None) -> pd.Series:
    return _modis_series("MOD13Q1", "250m_16_days_NDVI", lat, lon, start,
                         0.0001, (-0.2, 1.0), offline, progress=progress)

def modis_et(lat, lon, start="2020-01-01", offline=False, progress=None) -> pd.Series:
    """MOD16A2GF actual evapotranspiration, mm per 8-day composite."""
    return _modis_series("MOD16A2GF", "ET_500m", lat, lon, start,
                         0.1, (0, 3000), offline, progress=progress)

# ---------------------------------------------------------------------------
# SoilGrids
# ---------------------------------------------------------------------------

# Used while SoilGrids is still loading (it can take over a minute) or if it is
# down: the average of SoilGrids at the four cached Delta fields. Labelled in the UI.
SOIL_FALLBACK = {"clay": 33.5, "sand": 31.0, "silt": 35.5, "soc": 30.0,
                 "phh2o": 7.6, "source": "regional default (Delta average): SoilGrids not loaded for this point",
                 "fallback": True}

def soil_cached(lat: float, lon: float) -> dict | None:
    return _read(CACHE / f"soil_{_key(lat, lon)}.json")

def soilgrids(lat: float, lon: float, offline: bool = False, timeout: int = 150) -> dict:
    path = CACHE / f"soil_{_key(lat, lon)}.json"
    hit = _read(path)
    if hit:
        return hit
    if offline:
        return dict(SOIL_FALLBACK)
    try:
        raw = _get("https://rest.isric.org/soilgrids/v2.0/properties/query", {
            "lon": lon, "lat": lat,
            "property": ["clay", "sand", "silt", "soc", "phh2o"],
            "depth": ["0-5cm", "5-15cm", "15-30cm"], "value": "mean",
        }, timeout=timeout, tries=2)
        out = {}
        for layer in raw["properties"]["layers"]:
            name = layer["name"]
            d = layer["unit_measure"]["d_factor"]
            vals = [x["values"]["mean"] for x in layer["depths"] if x["values"]["mean"] is not None]
            if vals:
                out[name] = round(float(np.mean(vals)) / d, 2)
        if not {"clay", "sand"} <= out.keys():
            raise RuntimeError("SoilGrids returned no data here (water or urban pixel?)")
        out["source"] = "SoilGrids 2.0 (ISRIC), 0–30 cm mean"
        _write(path, out)
        return out
    except Exception:
        return dict(SOIL_FALLBACK)

# ---------------------------------------------------------------------------
# Earthdata products (filled in by scripts/fetch_earthdata.py when logged in)
# ---------------------------------------------------------------------------

def earthdata_series(name: str, lat: float, lon: float) -> pd.Series | None:
    """SMAP L4 root-zone moisture ('smap') or GPM IMERG rain ('imerg') if cached."""
    raw = _read(CACHE / f"{name}_{_key(lat, lon)}.json")
    if not raw:
        return None
    s = pd.Series(raw["values"], dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()

# ---------------------------------------------------------------------------
# Reference evapotranspiration (FAO-56)
# ---------------------------------------------------------------------------

def _ra(lat_deg: float, doy: np.ndarray) -> np.ndarray:
    """Extraterrestrial radiation, MJ m-2 day-1 (FAO-56 eq. 21)."""
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi / 365 * doy)
    dec = 0.409 * np.sin(2 * np.pi / 365 * doy - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    return (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))

def add_et0(df: pd.DataFrame, lat: float, elev: float) -> pd.DataFrame:
    """Penman-Monteith where radiation exists (1984+), Hargreaves before that."""
    df = df.copy()
    tmax, tmin = df["T2M_MAX"], df["T2M_MIN"]
    t = (tmax + tmin) / 2
    doy = df.index.day_of_year.values
    ra = _ra(lat, doy)

    p = df["PS"].fillna(101.3 * ((293 - 0.0065 * elev) / 293) ** 5.26)
    gamma = 0.000665 * p
    e0 = lambda x: 0.6108 * np.exp(17.27 * x / (x + 237.3))
    es = (e0(tmax) + e0(tmin)) / 2
    ea = df["RH2M"].clip(1, 100) / 100 * es
    delta = 4098 * e0(t) / (t + 237.3) ** 2
    u2 = df["WS2M"].fillna(2.0)
    rs = df["ALLSKY_SFC_SW_DWN"]
    rso = (0.75 + 2e-5 * elev) * ra
    rns = 0.77 * rs
    sigma = 4.903e-9
    rnl = sigma * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 \
        * (0.34 - 0.14 * np.sqrt(ea.clip(lower=0))) \
        * (1.35 * (rs / rso).clip(0, 1) - 0.35)
    rn = rns - rnl
    pm = (0.408 * delta * rn + gamma * 900 / (t + 273) * u2 * (es - ea)) \
        / (delta + gamma * (1 + 0.34 * u2))
    hg = 0.0023 * 0.408 * ra * (t + 17.8) * np.sqrt((tmax - tmin).clip(lower=0))
    df["ET0"] = pm.where(rs.notna(), hg).clip(lower=0)
    return df

def apply_climate_shift(df: pd.DataFrame, lat: float, elev: float,
                        dT: float = 1.5, rain_factor: float = 0.85) -> pd.DataFrame:
    """Stress test: warmer and drier. ET0 is recomputed, not just scaled."""
    out = df.copy()
    for c in ("T2M", "T2M_MAX", "T2M_MIN"):
        out[c] = out[c] + dT
    out["PRECTOTCORR"] = out["PRECTOTCORR"] * rain_factor
    # Holding relative humidity fixed while warming raises the vapour-pressure
    # deficit, which is the physically expected direction.
    return add_et0(out.drop(columns=["ET0"], errors="ignore"), lat, elev)

def load_site(lat: float, lon: float, offline: bool = False, wait_for_soil: bool = True) -> dict:
    """Weather (+ET0) and soil. With wait_for_soil=False the soil comes from the
    cache or the labelled regional default, so a new pin is ready in seconds;
    the app then fetches SoilGrids in the background."""
    df, elev = power_daily(lat, lon, offline=offline)
    df = add_et0(df, lat, elev)
    if wait_for_soil:
        soil = soilgrids(lat, lon, offline=offline)
    else:
        soil = soil_cached(lat, lon) or dict(SOIL_FALLBACK)
    return {"weather": df, "elev": elev, "soil": soil}
