"""Download the Field Pulse training pixels: MODIS NDVI (2015 →) and NASA POWER daily weather
for ~45 cropland points across Egypt. Raw files go to data/training/raw/ (not committed);
pulse_train.py turns them into the compact table that is committed.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.
    python scripts/fetch_training.py
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import data_sources as ds  # noqa: E402

RAW = ROOT / "data" / "training" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
ds.CACHE = RAW

# Cropland points (approximate, rural). Region names are for the report only.
POINTS = [
    ("Kafr El-Sheikh", 31.18, 30.92), ("Kafr El-Sheikh", 31.32, 31.05), ("Kafr El-Sheikh", 31.08, 30.80),
    ("Dakahlia", 31.10, 31.45), ("Dakahlia", 30.98, 31.55), ("Dakahlia", 31.20, 31.30),
    ("Gharbia", 30.86, 30.95), ("Gharbia", 30.72, 31.10), ("Menoufia", 30.50, 30.98),
    ("Qalyubia", 30.38, 31.22), ("Sharqia", 30.70, 31.62), ("Sharqia", 30.52, 31.42),
    ("Sharqia", 30.85, 31.80), ("Beheira", 30.95, 30.45), ("Beheira", 30.80, 30.25),
    ("Beheira", 31.05, 30.30), ("Damietta", 31.32, 31.70), ("Alexandria", 31.05, 29.95),
    ("Nubaria", 30.62, 30.12), ("Wadi El-Natrun", 30.42, 30.30), ("Salheya", 30.62, 32.00),
    ("Ismailia", 30.55, 32.15), ("Giza", 29.75, 31.22), ("Fayoum", 29.32, 30.85),
    ("Fayoum", 29.22, 30.70), ("Fayoum", 29.40, 30.98), ("Beni Suef", 29.10, 31.05),
    ("Beni Suef", 28.95, 30.95), ("Minya", 28.20, 30.70), ("Minya", 27.95, 30.82),
    ("Minya", 28.45, 30.72), ("Asyut", 27.25, 31.05), ("Asyut", 27.05, 31.25),
    ("Sohag", 26.60, 31.62), ("Sohag", 26.40, 31.85), ("Qena", 26.10, 32.65),
    ("Luxor", 25.55, 32.50), ("Aswan", 24.45, 32.92), ("Aswan", 24.75, 32.90),
    ("East Oweinat", 22.58, 28.72), ("Toshka", 22.65, 31.55), ("Matrouh coast", 31.30, 27.20),
    ("Matrouh coast", 31.20, 27.65), ("Siwa", 29.22, 25.50), ("Kharga", 25.30, 30.58),
]


def one(p):
    name, lat, lon = p
    for attempt in range(3):
        try:
            n = len(ds.modis_ndvi(lat, lon, start="2015-01-01", offline=False).dropna())
            ds.power_daily(lat, lon, offline=False)
            return f"{name} {lat},{lon}: {n} NDVI dates"
        except Exception as e:  # noqa: BLE001
            time.sleep(10)
            err = e
    return f"{name} {lat},{lon}: FAILED {err}"


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        for line in pool.map(one, POINTS):
            print(line, flush=True)
