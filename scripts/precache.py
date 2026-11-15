"""Download and cache every no-login NASA dataset for the demo sites.

    python scripts/precache.py            # all sites in data/sites.json
    python scripts/precache.py 31.1 30.9  # one extra point

Safe to re-run: finished downloads are kept, MODIS resumes where it stopped.
POWER and soil go first (seconds); MODIS is slow (10 dates per request), so
every site × product runs in parallel.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import data_sources as ds  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

def fast(lat, lon, label):
    df, elev = ds.power_daily(lat, lon)
    soil = ds.soilgrids(lat, lon)
    print(f"{label}: POWER {df.index[0].date()} → {df.index[-1].date()} ({len(df)} days, "
          f"elev {elev:.0f} m) | soil clay {soil.get('clay')}% [{soil['source']}]", flush=True)

def modis(kind, lat, lon, label):
    fn = ds.modis_ndvi if kind == "ndvi" else ds.modis_et
    s = fn(lat, lon)
    return f"{label}: {kind} {len(s)} composites"

if __name__ == "__main__":
    if len(sys.argv) == 3:
        pts = [dict(lat=float(sys.argv[1]), lon=float(sys.argv[2]), name="custom")]
    else:
        pts = json.loads((ROOT / "data" / "sites.json").read_text())
    for p in pts:
        try:
            fast(p["lat"], p["lon"], p["name"])
        except Exception as exc:
            print(f"{p['name']}: POWER/soil FAILED {exc}", flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(modis, k, p["lat"], p["lon"], p["name"]): (k, p["name"])
                for p in pts for k in ("ndvi", "et")}
        for f in as_completed(futs):
            try:
                print(f.result(), flush=True)
            except Exception as exc:
                print(f"{futs[f]} FAILED {exc}", flush=True)
    print("done", flush=True)
