"""Fetch the two login-only NASA products for the demo sites.

  SMAP L4 root-zone soil moisture (SPL4SMGP, 9 km, 3-hourly)  via NASA AppEEARS
  GPM IMERG Final daily rainfall (GPM_3IMERGDF, 0.1°)          via earthaccess

1. Make a free account at https://urs.earthdata.nasa.gov
2. Export your login (or put it in ~/.netrc for urs.earthdata.nasa.gov):
       export EARTHDATA_USERNAME=...   EARTHDATA_PASSWORD=...
3. pip install earthaccess xarray h5netcdf
4. python scripts/fetch_earthdata.py smap            # all demo sites, 2016 → now
   python scripts/fetch_earthdata.py imerg --days 365

Results go to data/cache/{smap,imerg}_<lat>_<lon>.json and the app picks them
up on the next page load: the Sources tab turns green and robot calibration
switches from POWER/MERRA-2 to SMAP.
"""
import argparse
import io
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
APPEEARS = "https://appeears.earthdatacloud.nasa.gov/api"

def sites():
    return json.loads((ROOT / "data" / "sites.json").read_text())

def key(lat, lon):
    return f"{lat:.3f}_{lon:.3f}"

def creds():
    u, p = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if not (u and p):
        import netrc
        try:
            auth = netrc.netrc().authenticators("urs.earthdata.nasa.gov")
            u, p = auth[0], auth[2]
        except Exception:
            sys.exit("Set EARTHDATA_USERNAME / EARTHDATA_PASSWORD or ~/.netrc first.")
    return u, p

# ---------------------------------------------------------------------------
# SMAP L4 via AppEEARS point sampling (no 140 MB HDF5 downloads)
# ---------------------------------------------------------------------------

def smap(start: str):
    u, p = creds()
    tok = requests.post(f"{APPEEARS}/login", auth=(u, p), timeout=60).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}

    products = requests.get(f"{APPEEARS}/product", timeout=60).json()
    prod = sorted(x["ProductAndVersion"] for x in products if x["ProductAndVersion"].startswith("SPL4SMGP"))[-1]
    layers = requests.get(f"{APPEEARS}/product/{prod}", timeout=60).json()
    layer = next(k for k in layers if k.endswith("sm_rootzone"))
    print(f"using {prod} / {layer}")

    pts = sites()
    task = {
        "task_type": "point",
        "task_name": "verdex_smap",
        "params": {
            "dates": [{"startDate": pd.Timestamp(start).strftime("%m-%d-%Y"),
                       "endDate": date.today().strftime("%m-%d-%Y")}],
            "layers": [{"product": prod, "layer": layer}],
            "coordinates": [{"latitude": s["lat"], "longitude": s["lon"], "id": s["id"]} for s in pts],
        },
    }
    tid = requests.post(f"{APPEEARS}/task", json=task, headers=H, timeout=60).json()["task_id"]
    print(f"AppEEARS task {tid} submitted; this usually takes 5–30 minutes…")
    while True:
        st = requests.get(f"{APPEEARS}/task/{tid}", headers=H, timeout=60).json()["status"]
        print("  status:", st, flush=True)
        if st == "done":
            break
        if st in ("error", "expired"):
            sys.exit(f"task {st}")
        time.sleep(60)

    files = requests.get(f"{APPEEARS}/bundle/{tid}", headers=H, timeout=60).json()["files"]
    csv = next(f for f in files if f["file_name"].endswith(".csv") and "results" in f["file_name"])
    raw = requests.get(f"{APPEEARS}/bundle/{tid}/{csv['file_id']}", headers=H, timeout=300).text
    df = pd.read_csv(io.StringIO(raw))
    col = next(c for c in df.columns if c.endswith("sm_rootzone"))
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    for s in pts:
        sub = df[df["ID"] == s["id"]]
        daily = sub.groupby("Date")[col].mean()
        daily = daily[(daily > 0) & (daily < 1)]
        out = {"source": f"{prod} {layer} (AppEEARS)", "units": "m3/m3",
               "values": {str(d): round(float(v), 4) for d, v in daily.items()}}
        (CACHE / f"smap_{key(s['lat'], s['lon'])}.json").write_text(json.dumps(out))
        print(f"{s['name']}: {len(daily)} days of SMAP root-zone moisture")

# ---------------------------------------------------------------------------
# GPM IMERG daily via earthaccess (reads only the pixels it needs)
# ---------------------------------------------------------------------------

def imerg(days: int):
    import earthaccess
    import xarray as xr

    earthaccess.login(strategy="environment" if os.environ.get("EARTHDATA_USERNAME") else "netrc")
    end = date.today() - timedelta(days=120)  # Final run lags ~3.5 months
    start = end - timedelta(days=days)
    res = earthaccess.search_data(short_name="GPM_3IMERGDF", version="07",
                                  temporal=(str(start), str(end)))
    print(f"{len(res)} IMERG daily files {start} → {end}")
    files = earthaccess.open(res)
    pts = sites()
    vals = {s["id"]: {} for s in pts}
    for i, f in enumerate(files):
        ds = xr.open_dataset(f, engine="h5netcdf")
        day = str(pd.Timestamp(ds["time"].values[0]).date())
        for s in pts:
            v = float(ds["precipitation"].sel(lat=s["lat"], lon=s["lon"], method="nearest").values.squeeze())
            vals[s["id"]][day] = round(v, 2)
        if i % 30 == 0:
            print(f"  {i}/{len(files)} {day}", flush=True)
    for s in pts:
        out = {"source": "GPM_3IMERGDF v07 (earthaccess)", "units": "mm/day", "values": vals[s["id"]]}
        (CACHE / f"imerg_{key(s['lat'], s['lon'])}.json").write_text(json.dumps(out))
        print(f"{s['name']}: {len(vals[s['id']])} days of IMERG rain")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("product", choices=["smap", "imerg"])
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--days", type=int, default=365)
    a = ap.parse_args()
    smap(a.start) if a.product == "smap" else imerg(a.days)
