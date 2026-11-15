"""Bulk MODIS NDVI for Field Pulse v2, from NASA GIBS (no login, works while the ORNL service is down).

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

GIBS serves MODIS Terra MOD13Q1 16-day NDVI as colour-mapped PNG tiles (EPSG:4326, 250 m, level 8 =
1.125° tiles of 512 × 512 px ≈ 240 m). The official GIBS colour map (data/training/MODIS_L3_NDVI_colormap.xml)
maps every colour back to an NDVI bin 0.005 wide, so the tiles decode to quantitative NDVI.
Accuracy is checked against the ORNL MOD13Q1 values cached for Kafr El-Sheikh (qa/pulse_train.py).

Default: three core-Delta tiles (row 52, cols 186–188 ≈ 30.4–31.5°N, 29.3–32.6°E), 2018–2026, about 90 MB.
Stored as uint8 per pixel per date: 0 = no data, else NDVI = code / 200 − 0.2.
    python scripts/gibs_fetch.py
"""
import io
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "training" / "gibs"
OUT.mkdir(parents=True, exist_ok=True)
CMAP = ROOT / "data" / "training" / "MODIS_L3_NDVI_colormap.xml"
URL = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/MODIS_Terra_L3_NDVI_16Day/default/{d}/250m/8/{r}/{c}.png"
TILES = [(52, 186), (52, 187), (52, 188)]
SPAN = 1.125  # degrees per level-8 tile


def tile_bounds(r, c):
    lon0 = -180 + c * SPAN
    lat0 = 90 - r * SPAN
    return lat0, lon0  # top-left corner; pixel size SPAN/512


def lut():
    """rgb -> uint8 code (0 = no data)."""
    m = {}
    for rgb, tr, lo, hi in re.findall(r'<ColorMapEntry rgb="([\d,]+)" transparent="(true|false)"[^>]*value="\[([-\d.]+),([-\d.]+)\)"', CMAP.read_text()):
        if tr == "true":
            continue
        v = (float(lo) + float(hi)) / 2
        m[tuple(int(x) for x in rgb.split(","))] = int(np.clip(round((v + 0.2) * 200), 1, 255))
    return m


def composite_dates(start=2018, end_date=None):
    end_date = end_date or date.today()
    out = []
    for y in range(start, end_date.year + 1):
        d = date(y, 1, 1)
        while d.year == y and d <= end_date - timedelta(days=20):
            out.append(d)
            d += timedelta(days=16)
    return out


def fetch(args):
    d, r, c, L = args
    for k in range(4):
        try:
            resp = requests.get(URL.format(d=d.isoformat(), r=r, c=c), timeout=60)
            if resp.status_code == 200 and resp.content[:4] == b"\x89PNG":
                im = Image.open(io.BytesIO(resp.content)).convert("RGB")
                a = np.asarray(im).reshape(-1, 3)
                keys = (a[:, 0].astype(np.int32) << 16) | (a[:, 1].astype(np.int32) << 8) | a[:, 2]
                out = np.zeros(len(keys), np.uint8)
                for rgb, code in L.items():
                    out[keys == ((rgb[0] << 16) | (rgb[1] << 8) | rgb[2])] = code
                return d, r, c, out.reshape(512, 512), len(resp.content)
            if resp.status_code in (400, 404):
                return d, r, c, None, 0
        except Exception:  # noqa: BLE001
            time.sleep(3 * (k + 1))
    return d, r, c, None, 0


def main():
    L = lut()
    dates = composite_dates()
    jobs = [(d, r, c, L) for (r, c) in TILES for d in dates]
    cubes = {t: np.zeros((len(dates), 512, 512), np.uint8) for t in TILES}
    got, mb = 0, 0.0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for d, r, c, arr, n in pool.map(fetch, jobs):
            mb += n / 1e6
            if arr is not None:
                cubes[(r, c)][dates.index(d)] = arr
                got += 1
            if got % 60 == 0:
                print(f"{got}/{len(jobs)} tiles, {mb:.1f} MB", flush=True)
    for (r, c), cube in cubes.items():
        lat0, lon0 = tile_bounds(r, c)
        np.savez_compressed(OUT / f"ndvi_r{r}_c{c}.npz", ndvi=cube, dates=np.array([d.isoformat() for d in dates]),
                            lat0=lat0, lon0=lon0, px=SPAN / 512)
    print(f"done: {got}/{len(jobs)} tiles, {mb:.1f} MB downloaded")


if __name__ == "__main__":
    main()
