"""Verify the downloaded Prithvi-EO-2.0-300M-TL encoder loads and produces field embeddings.
Uses the HLS example chip shipped with the model (Mexico, 2018) — no HLS download needed.
     python scripts/prithvi_check.py"""
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import prithvi  # noqa: E402

def main():
    import rasterio
    print(prithvi.status())
    with rasterio.open(prithvi.DIR / "example_t1.tif") as r:
        img = r.read().astype(np.float32)                   # (6, H, W)
        b = r.bounds
        lat, lon = (b.top + b.bottom) / 2, (b.left + b.right) / 2
        crs = r.crs
    if crs and not crs.is_geographic:
        from rasterio.warp import transform
        xs, ys = transform(crs, "EPSG:4326", [lon], [lat]); lon, lat = xs[0], ys[0]
    chip = img[:, :224, :224]
    t0 = time.time()
    enc, missing = prithvi.load(1)
    print(f"encoder loaded in {time.time() - t0:.1f}s; params {sum(p.numel() for p in enc.parameters()):,}; missing encoder keys: {len(missing)}")
    e1 = prithvi.embed(chip[None], [(2018, 26)], lat, lon)
    noise = np.random.default_rng(0).normal(1500, 800, chip.shape).astype(np.float32)
    e2 = prithvi.embed(noise[None], [(2018, 26)], lat, lon)
    cos = float(e1["embedding"] @ e2["embedding"] / np.linalg.norm(e1["embedding"]) / np.linalg.norm(e2["embedding"]))
    # within-image structure: patch embeddings of land vs. other patches should vary
    pv = np.linalg.norm(e1["patches"] - e1["patches"].mean(0), axis=1)
    print(f"example chip at {lat:.3f}, {lon:.3f}: embedding {e1['embedding'].shape}, {e1['tokens']} patch tokens, {e1['seconds']}s on CPU")
    print(f"cosine(real chip, noise) = {cos:.3f} (lower = the model separates real land from noise); patch-embedding spread {pv.mean():.2f}")

if __name__ == "__main__":
    main()
