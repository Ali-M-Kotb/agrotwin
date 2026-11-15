"""Seasonal peak-NDVI distribution of Nile Delta cropland (MODIS via NASA GIBS, 2018–2026) → backend/models/ndvi_peers.json.
Used by the planner's field productivity index.
    python scripts/ndvi_peers.py"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
peaks = {"winter": [], "summer": []}
for f in sorted((ROOT / "data" / "training" / "gibs").glob("ndvi_r*_c*.npz")):
    z = np.load(f)
    cube = np.where(z["ndvi"] > 0, z["ndvi"] / 200 - 0.2, np.nan).astype(np.float32)
    d = pd.to_datetime(z["dates"])
    valid = np.isfinite(cube).mean(0) >= 0.9
    mx = np.nanmax(cube, 0)
    crop = valid & (mx >= 0.55)
    for y in range(2018, 2026):
        for name, a, b in (("winter", pd.Timestamp(y, 12, 1), pd.Timestamp(y + 1, 4, 30)), ("summer", pd.Timestamp(y + 1, 6, 1), pd.Timestamp(y + 1, 10, 15))):
            sel = (d >= a) & (d <= b)
            if sel.sum() < 4:
                continue
            pk = np.nanmax(cube[sel], 0)[crop]
            peaks[name].append(pk[pk >= 0.45])          # cropped seasons only
out = {}
for k, v in peaks.items():
    v = np.concatenate(v)
    out[k] = dict(n=int(len(v)), p10=float(np.percentile(v, 10)), p25=float(np.percentile(v, 25)), median=float(np.median(v)),
                  p75=float(np.percentile(v, 75)), p90=float(np.percentile(v, 90)))
out["source"] = "MODIS MOD13Q1 NDVI decoded from NASA GIBS, core Nile Delta cropland pixels, cropped seasons 2018/19–2025/26"
(ROOT / "backend" / "models" / "ndvi_peers.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
