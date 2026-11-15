"""NASA POWER daily weather for every MERRA-2 grid cell under the GIBS training tiles (≈1.5 MB each).
   python scripts/fetch_power_grid.py"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import data_sources as ds  # noqa: E402
RAW = ROOT / "data" / "training" / "raw"; RAW.mkdir(parents=True, exist_ok=True); ds.CACHE = RAW
LATS = [30.5, 31.0, 31.5]                       # MERRA-2 0.5° centres covering 30.375–31.5 °N
LONS = [29.375, 30.0, 30.625, 31.25, 31.875, 32.5]  # 0.625° centres covering 29.25–32.625 °E
def one(p):
    try:
        ds.power_daily(*p, offline=False); return f"ok {p}"
    except Exception as e:  # noqa: BLE001
        return f"FAILED {p} {e}"
if __name__ == "__main__":
    with ThreadPoolExecutor(4) as ex:
        for line in ex.map(one, [(a, b) for a in LATS for b in LONS]):
            print(line, flush=True)
