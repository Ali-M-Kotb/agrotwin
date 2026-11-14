"""Verdex Scout: run intake, calibration, simulator, farmer-owned storage.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

Modes travel with the data end to end:
  LIVE       the robot is posting now (scripts/robot_bridge.py → /api/scout/run or telemetry)
  REPLAY     a saved real run played back
  SIMULATED  generated from a hidden past year of the replay (the twin experiment, live on stage)

Everything a farm posts is stored under data/scout/<site_id>/ and can be exported in one
file: the farm's data stays with the farmer.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import numpy as np

from soil import SOIL_CLASSES

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "scout"
SCHEMA = json.loads((ROOT / "contracts" / "scout_run.schema.json").read_text())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _site_dir(site_id: str) -> Path:
    d = STORE / site_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# intake
# ---------------------------------------------------------------------------

def validate(run: dict) -> list[str]:
    errs = [f"{'/'.join(map(str, e.path)) or 'run'}: {e.message}"
            for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(run)]
    if run.get("mode") == "SIMULATED" and run.get("truth_year") is None:
        errs.append("SIMULATED runs must name their truth_year")
    return errs


def store_run(run: dict) -> dict:
    errs = validate(run)
    if errs:
        raise ValueError("; ".join(errs[:5]))
    path = _site_dir(run["site_id"]) / f"run_{run['run_id']}.json"
    path.write_text(json.dumps(run))
    return dict(run_id=run["run_id"], mode=run["mode"], n_points=len(run["points"]))


def list_runs(site_id: str) -> list[dict]:
    d = _site_dir(site_id)
    out = []
    for p in sorted(d.glob("run_*.json")):
        r = json.loads(p.read_text())
        out.append(dict(run_id=r["run_id"], mode=r["mode"], n_points=len(r["points"]),
                        sent_at=r["sent_at"], truth_year=r.get("truth_year"),
                        season_start=r.get("season_start")))
    return out


def load_runs(site_id: str, run_ids: list[str]) -> list[dict]:
    d = _site_dir(site_id)
    return [json.loads((d / f"run_{rid}.json").read_text()) for rid in run_ids
            if (d / f"run_{rid}.json").exists()]


def delete_runs(site_id: str):
    for p in _site_dir(site_id).glob("run_*.json"):
        p.unlink()


def export(site_id: str) -> dict:
    d = _site_dir(site_id)
    return dict(site_id=site_id, exported_at=_now(),
                note="Your farm's data. AgroTwin keeps it on this machine; nothing is pooled without consent.",
                runs=[json.loads(p.read_text()) for p in sorted(d.glob("run_*.json"))],
                calibrations=[json.loads(p.read_text()) for p in sorted(d.glob("cal_*.json"))])


# ---------------------------------------------------------------------------
# calibration: raw probe counts → volumetric water content
# ---------------------------------------------------------------------------

def calibrate(site_id: str, samples: list[dict], soil_class: str, mode: str = "LIVE") -> dict:
    """samples: [{raw, vwc}] with vwc from weighed-and-oven-dried soil (m3/m3). Linear fit."""
    if len(samples) < 3:
        raise ValueError("at least 3 calibration samples are needed (weigh, oven-dry, reweigh)")
    x = np.array([float(s["raw"]) for s in samples])
    y = np.array([float(s["vwc"]) for s in samples])
    if np.ptp(x) == 0:
        raise ValueError("samples need different raw readings (wet and dry soil)")
    a, b = np.polyfit(x, y, 1)
    rmse = float(np.sqrt(np.mean((a * x + b - y) ** 2)))
    fc, wp = SOIL_CLASSES[soil_class]
    cid = "cal_" + hashlib.sha1(json.dumps([samples, soil_class]).encode()).hexdigest()[:10]
    cal = dict(id=cid, site_id=site_id, a=float(a), b=float(b), rmse=rmse, rmse_rel=rmse / (fc - wp),
               n=len(samples), soil_class=soil_class, mode=mode, created=_now(),
               source=f"computed:linear fit of {len(samples)} samples", samples=samples)
    (_site_dir(site_id) / f"{cid}.json").write_text(json.dumps(cal))
    return cal


def latest_calibration(site_id: str) -> dict | None:
    cals = sorted(_site_dir(site_id).glob("cal_*.json"), key=lambda p: p.stat().st_mtime)
    return json.loads(cals[-1].read_text()) if cals else None


# ---------------------------------------------------------------------------
# simulator: the twin experiment, live
# ---------------------------------------------------------------------------

def simulate_run(site_id: str, wet: np.ndarray, years: list[int], truth_year: int, days: int,
                 soil_class: str, noise_rel: float = 0.05, readings_per_day: int = 4,
                 seed: int = 7) -> tuple[dict, dict]:
    """Readings generated from a hidden past year's modelled wetness + sensor noise.

    Returns (run, calibration). The calibration is SIMULATED too: a typical capacitive-probe
    line (raw 0–100 index) with the noise used here, so the fusion refuses nothing it would
    refuse in the field.
    """
    k = years.index(truth_year)
    rng = np.random.default_rng(seed)
    fc, wp = SOIL_CLASSES[soil_class]
    a, b = (fc - wp + 0.06) / 100.0, wp - 0.03          # raw 0..100 → vwc
    cal = dict(id=f"cal_sim_{site_id}", site_id=site_id, a=a, b=b, rmse=noise_rel * (fc - wp),
               rmse_rel=noise_rel, n=0, soil_class=soil_class, mode="SIMULATED", created=_now(),
               source="assumption:simulated_calibration")
    (_site_dir(site_id) / f"{cal['id']}.json").write_text(json.dumps(cal))
    start = date(truth_year, 10, 1)
    pts = []
    for d in range(min(days, wet.shape[1])):
        for h in range(readings_per_day):
            s = float(np.clip(wet[k, d] + rng.normal(0, noise_rel), 0, 1))
            vwc = wp + s * (fc - wp)
            raw = (vwc - b) / a
            t = datetime(start.year, start.month, start.day, 6 + 4 * h, tzinfo=timezone.utc) + timedelta(days=d)
            pts.append(dict(t=t.isoformat(timespec="seconds"), lat=None, lon=None, plot_label="plot A",
                            soil_raw=round(raw, 2), soil_vwc_pct=None, soil_calibration_id=cal["id"],
                            air_temp_c=None, air_rh_pct=None, rain_flag=False, plant_health=None))
    run = dict(run_id=f"sim_{truth_year}_{days}d_{int(time.time())}", site_id=site_id, mode="SIMULATED",
               robot="verdex-simulator", sent_at=_now(), fw="simulator-1",
               season_start=str(start), truth_year=truth_year, points=pts)
    store_run(run)
    return run, cal


def telemetry_to_point(r: dict) -> dict:
    """A reading from the live robot (backend/robot.py format) → Scout run point."""
    t = datetime.fromtimestamp(r["t"], timezone.utc).isoformat(timespec="seconds")
    return dict(t=t, lat=r.get("lat"), lon=r.get("lon"), plot_label="robot",
                soil_raw=r.get("soil"), soil_vwc_pct=None, soil_calibration_id=None,
                air_temp_c=r.get("temp"), air_rh_pct=r.get("hum"),
                rain_flag=(r.get("rain") or 0) > 30, plant_health=None)
