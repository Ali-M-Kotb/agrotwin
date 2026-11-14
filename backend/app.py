"""AgroTwin API: from the sky to the land.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

    ./run.sh               → http://127.0.0.1:8000
    VERDEX_OFFLINE=1       cache only (stage mode)
    AGROTWIN_TOKEN=...     bearer token the Scout must send to /api/scout/run (default: verdex-demo)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import council
import data_sources as ds
import fieldcard
import disease
import econ
import fusion as fu
import history
import replay as rp
import report
import scout
import soil as soilmod
import waterbalance as wb
from crops import CROPS, DISEASE_CLASSES, FALLOW, FAMILY_AR, FEDDAN_HA, family
from robot import Robot

ROOT = Path(__file__).resolve().parent.parent
OFFLINE = os.environ.get("VERDEX_OFFLINE") == "1"
TOKEN = os.environ.get("AGROTWIN_TOKEN", "verdex-demo")
SITES = {s["id"]: s for s in json.loads((ROOT / "data" / "sites.json").read_text())}

app = FastAPI(title="AgroTwin")
robot = Robot()
_sites: dict = {}
_site_locks: dict = {}
_locks_guard = threading.Lock()
_jobs: dict = {}
_wx_cache: dict = {}
_result_cache: dict = {}


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.floating, float)):
        return None if np.isnan(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


# ---------------------------------------------------------------------------
# sites (non-blocking; slow sources load in the background)
# ---------------------------------------------------------------------------

def _key_lock(key) -> threading.Lock:
    with _locks_guard:
        return _site_locks.setdefault(key, threading.Lock())


def site(lat: float, lon: float) -> dict:
    key = (round(lat, 3), round(lon, 3))
    if key in _sites:
        return _sites[key]
    with _key_lock(key):
        if key not in _sites:
            try:
                s = ds.load_site(*key, offline=OFFLINE, wait_for_soil=False)
            except FileNotFoundError:
                raise HTTPException(404, "This point is not cached and the app is in offline mode.")
            except Exception as exc:
                raise HTTPException(502, f"NASA POWER request failed: {exc}")
            s["lat"], s["lon"] = key
            _sites[key] = s
            if not OFFLINE:
                _start_background(key)
        return _sites[key]


def _start_background(key):
    lat, lon = key
    job = _jobs.setdefault(key, {})
    if "soil" not in job:
        if ds.soil_cached(lat, lon):
            job["soil"] = "done"
        else:
            job["soil"] = "loading"

            def soil_job():
                got = ds.soilgrids(lat, lon)
                if got.get("fallback"):
                    job["soil"] = "failed"
                else:
                    _sites[key]["soil"] = got
                    _result_cache.clear()
                    job["soil"] = "done"
            threading.Thread(target=soil_job, daemon=True).start()
    for nm, fn, product in (("ndvi", ds.modis_ndvi, "MOD13Q1"), ("et", ds.modis_et, "MOD16A2GF")):
        if nm in job:
            continue
        if ds.modis_cached(product, lat, lon) > 50:
            job[nm] = {"state": "done"}
            continue
        prog = {"state": "loading", "done": 0, "total": 0}
        job[nm] = prog

        def run(fn=fn, prog=prog):
            try:
                fn(lat, lon, progress=prog)
                prog["state"] = "done"
            except Exception as exc:
                prog["state"], prog["error"] = "failed", str(exc)[:200]
        threading.Thread(target=run, daemon=True).start()


def site_meta(lat, lon) -> dict:
    for s in SITES.values():
        if abs(s["lat"] - lat) < 1e-3 and abs(s["lon"] - lon) < 1e-3:
            return s
    return dict(id=f"pin_{lat:.3f}_{lon:.3f}".replace("-", "m"), name=f"{lat:.3f}, {lon:.3f}",
                name_ar=f"{lat:.3f}، {lon:.3f}", lat=lat, lon=lon, irrigated=True, existing=["wheat", "maize"])


@app.get("/api/sites")
def sites():
    return list(SITES.values())


@app.get("/api/site/status")
def site_status(lat: float, lon: float):
    key = (round(lat, 3), round(lon, 3))
    job = _jobs.get(key, {})
    return dict(soil=job.get("soil", "done" if ds.soil_cached(*key) else "missing"),
                ndvi=job.get("ndvi", {"state": "done" if ds.modis_cached("MOD13Q1", *key) else "missing"}),
                et=job.get("et", {"state": "done" if ds.modis_cached("MOD16A2GF", *key) else "missing"}))


@app.get("/api/crops")
def crops():
    prices = econ.load_prices()
    return _clean(dict(crops=CROPS, fallow=FALLOW, families_ar=FAMILY_AR, disease_classes=DISEASE_CLASSES,
                       prices=prices, assumptions=config.table(), soil_classes=soilmod.NAMES,
                       crop_sources=__import__("crops").SRC))


@app.get("/api/site")
def site_info(lat: float, lon: float):
    s = site(lat, lon)
    w = s["weather"]
    meta = site_meta(s["lat"], s["lon"])
    out = dict(lat=s["lat"], lon=s["lon"], elev=s["elev"], soil=s["soil"], meta=meta,
               soil_class=soilmod.classify(s["soil"]), climate=history.climate_summary(w))
    sources = [dict(name="NASA POWER daily weather (T, RH, rain, solar, wind)", status="ok", tag="nasa:POWER",
                    detail=f"{out['climate']['first']} → {out['climate']['last']}"),
               dict(name="Root-zone soil wetness (POWER GWETROOT, MERRA-2)", status="ok", tag="nasa:POWER GWETROOT",
                    detail="danger windows; stand-in until SMAP is connected")]
    try:
        ndvi = ds.modis_ndvi(s["lat"], s["lon"], offline=True)
    except Exception:
        ndvi = pd.Series(dtype=float)
    if len(ndvi):
        out["ndvi"] = dict(dates=[str(d.date()) for d in ndvi.index], values=ndvi.round(3).tolist(),
                           seasons=history.ndvi_seasons(ndvi), source="nasa:MODIS MOD13Q1")
        sources.append(dict(name="MODIS MOD13Q1 NDVI (250 m, 16-day)", status="ok", tag="nasa:MODIS MOD13Q1",
                            detail=f"{len(ndvi)} composites via ORNL DAAC"))
    else:
        sources.append(dict(name="MODIS MOD13Q1 NDVI (250 m, 16-day)", status="missing", tag="nasa:MODIS MOD13Q1",
                            detail="not cached (offline mode)" if OFFLINE else "downloading in the background…"))
    try:
        et = ds.modis_et(s["lat"], s["lon"], offline=True)
    except Exception:
        et = pd.Series(dtype=float)
    if len(et):
        out["mod16"] = dict(dates=[str(d.date()) for d in et.index], values=et.round(1).tolist(), source="nasa:MODIS MOD16A2GF")
        sources.append(dict(name="MODIS MOD16A2GF actual ET (500 m, 8-day)", status="ok", tag="nasa:MODIS MOD16A2GF",
                            detail=f"{len(et)} composites via ORNL DAAC"))
    else:
        sources.append(dict(name="MODIS MOD16A2GF actual ET (500 m, 8-day)", status="missing", tag="nasa:MODIS MOD16A2GF",
                            detail="not cached (offline mode)" if OFFLINE else "downloading in the background…"))
    for nm, label in (("smap", "SMAP L4 root-zone soil moisture (9 km)"), ("imerg", "GPM IMERG Final daily rain (0.1°)")):
        ser = ds.earthdata_series(nm, s["lat"], s["lon"])
        if ser is not None:
            out[nm] = dict(dates=[str(d.date()) for d in ser.index], values=ser.round(3).tolist())
            sources.append(dict(name=label, status="ok", tag=f"nasa:{nm.upper()}", detail=f"{len(ser)} days"))
        else:
            sources.append(dict(name=label, status="login", tag=f"nasa:{nm.upper()}",
                                detail="needs an Earthdata login: scripts/fetch_earthdata.py"))
    soil_state = _jobs.get((s["lat"], s["lon"]), {}).get("soil")
    sources.append(dict(name="Soil texture (SoilGrids 2.0, ISRIC)", status="fallback" if s["soil"].get("fallback") else "ok",
                        tag="quoted:https://soilgrids.org",
                        detail=s["soil"]["source"] + (" — loading in the background…" if soil_state == "loading" else "")))
    out["sources"] = sources
    out["danger"] = history.danger_windows(w, ndvi if len(ndvi) else None)
    return _clean(out)


# ---------------------------------------------------------------------------
# simulate: the main result
# ---------------------------------------------------------------------------

class SimRequest(BaseModel):
    lat: float
    lon: float
    existing: list[str] = Field(default_factory=lambda: ["wheat", "rice"])
    candidates: list[str] = Field(default_factory=lambda: list(CROPS))
    weights: dict = Field(default_factory=lambda: dict(water=1, soil=1, profit=1, risk=1))
    rain_mult: float = 1.0
    temp_offset: float = 0.0
    price_mult: float = 1.0
    irrigated: bool | None = None
    water_cap_m3: dict | None = None
    price_overrides: dict = {}
    soil_class: str | None = None
    use_scout: bool = True
    scout_run_ids: list[str] | None = None
    irrigation_dates: list[str] | None = None


def _wx(s, rain_mult, temp_offset):
    k = (s["lat"], s["lon"], round(rain_mult, 3), round(temp_offset, 2), id(s["weather"]))
    if k not in _wx_cache:
        w = s["weather"]
        if rain_mult != 1.0 or temp_offset != 0.0:
            w = ds.apply_climate_shift(w, s["lat"], s["elev"], temp_offset, rain_mult)
        _wx_cache[k] = wb.weather_matrices(w, wb.windows(s["weather"]))
    return _wx_cache[k]


def sigma_model_for(site_id, s, plan, wx, soil_class, irrigated) -> dict:
    """Per-site model-error σ, calibrated by the twin experiment and cached on disk."""
    rot = rp.existing_rotation(plan)
    p = ds.CACHE / f"fusion_sigma_{site_id}_{'-'.join(rot[:2])}.json"
    if p.exists():
        return json.loads(p.read_text())
    res = rp.run(wx, rp.Plan(existing=plan.existing, irrigated=False, soil_class=soil_class), econ.load_prices(),
                 s["soil"].get("clay", 35) or 35)
    wet = wb.simulate([rot], wx, soil_class, False, None, keep_wetness_days=365)["wet"][0]
    cal = fu.calibrate_sigma_model(wet, res["_all"][0]["_season1"])
    p.write_text(json.dumps(cal))
    return cal


def _sightings(runs) -> dict:
    lo = config.A["vision_min_conf"]
    c = dict(healthy=0, diseased=0, unknown=0)
    fams = {}
    items = [(d["label"], d["confidence"]) for d in robot.detections if d.get("known", True)]
    for r in runs:
        for p in r["points"]:
            ph = p.get("plant_health") or {}
            if ph.get("class"):
                items.append((ph["class"], ph.get("confidence", 0)))
    for label, conf in items:
        fam, pretty, is_dis = DISEASE_CLASSES.get(label, (None, label, False))
        if conf < lo:
            c["unknown"] += 1
        elif is_dis:
            c["diseased"] += 1
            if fam:
                fams[fam] = pretty
        else:
            c["healthy"] += 1
    n = sum(c.values())
    share, min_n = config.A["vision_alert"]
    return dict(counts=c, n=n, families=fams, model=disease._info.get("file", "v2_deit3.pt (DeiT-III small)"),
                alert=bool(n >= min_n and c["diseased"] / max(n, 1) >= share),
                note="Sightings are observations, not diagnoses.")


def _fingerprint(req: SimRequest, s) -> str:
    d = req.model_dump()
    d["_soil"] = s["soil"].get("source")
    d["_det"] = len(robot.detections)
    return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


@app.post("/api/simulate")
def simulate(req: SimRequest):
    t0 = time.time()
    s = site(req.lat, req.lon)
    meta = site_meta(s["lat"], s["lon"])
    irrigated = meta.get("irrigated", True) if req.irrigated is None else req.irrigated
    soil_class = req.soil_class or soilmod.classify(s["soil"])
    site_id = meta["id"]

    runs = []
    if req.use_scout:
        ids = req.scout_run_ids if req.scout_run_ids is not None else [r["run_id"] for r in scout.list_runs(site_id)]
        runs = scout.load_runs(site_id, ids)
    key = _fingerprint(req, s) + "|" + ",".join(r["run_id"] for r in runs)
    if key in _result_cache:
        return _result_cache[key]

    sight = _sightings(runs)
    plan = rp.Plan(existing=tuple(req.existing[:2]) if len(req.existing) >= 2 else (req.existing[0], FALLOW),
                   candidates=req.candidates, weights=req.weights, irrigated=irrigated,
                   water_cap_m3=req.water_cap_m3 if irrigated else None,
                   rain_mult=req.rain_mult, temp_offset=req.temp_offset, price_mult=req.price_mult,
                   price_overrides=req.price_overrides, disease_families=sight["families"], soil_class=soil_class)
    wx = _wx(s, req.rain_mult, req.temp_offset)
    prices = econ.load_prices()
    clay = s["soil"].get("clay", 35) or 35

    fusion_block = dict(used=False, reason="no_runs" if not runs else None)
    weights = None
    truth_year = None
    if runs:
        cal = scout.latest_calibration(site_id)
        sim_runs = [r for r in runs if r["mode"] == "SIMULATED"]
        if sim_runs:
            cal = json.loads((scout._site_dir(site_id) / f"cal_sim_{site_id}.json").read_text())
            truth_year = sim_runs[-1].get("truth_year")
            runs = sim_runs[-1:]          # one hidden year at a time
        try:
            sig = sigma_model_for(site_id, s, plan, wx, soil_class, irrigated) if not irrigated else None
            fb = fu.fuse(runs, cal, rp.existing_rotation(plan), wx, soil_class, irrigated, req.irrigation_dates,
                         sigma_model=sig["sigma_model"] if sig else None)
            if sig:
                fb["sigma_calibration"] = sig
            weights = np.asarray(fb.pop("weights"), dtype=float)
            if truth_year in wx["years"]:
                # The hidden year must not vote for itself: that is the twin experiment.
                weights[wx["years"].index(truth_year)] = 0
                weights = weights / weights.sum()
                fb["ess"] = float(1 / (weights ** 2).sum())
            fb["weights_by_year"] = {int(y): round(float(w), 4) for y, w in zip(wx["years"], weights)}
            fusion_block = fb
        except fu.FusionRefused as exc:
            fusion_block = dict(used=False, refused=str(exc))
    try:
        res = rp.run(wx, plan, prices, clay, fusion_weights=weights)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    shown = res["rotations"]
    ctx = dict(pool_size=res["pool_size"], prices=prices, fusion_used=weights is not None,
               smap=ds.earthdata_series("smap", s["lat"], s["lon"]) is not None,
               soil_fallback=bool(s["soil"].get("fallback")), irrigated=irrigated, clay=clay,
               lat=s["lat"], lon=s["lon"], disease_seen=bool(sight["families"]),
               cap_binding=any(m.get("unmet_share", 0) > 0.05 for m in shown))
    existing_m = shown[0]
    rot_out = []
    for i, m in enumerate(shown):
        m = dict(m)
        m["label"] = dict(en=report.label(m["seq"], "en"), ar=report.label(m["seq"], "ar"))
        m["text"] = report.rotation_text(m, i, existing_m, ctx)
        m["per_ha"] = dict(water_m3=round(m["water_m3"]["median"] / FEDDAN_HA),
                           profit=round(m["profit"]["median"] / FEDDAN_HA), source="computed:per feddan ÷ 0.42")
        if weights is not None:
            j = res["_index"][i]
            m["unweighted"] = dict(season1_profit=m["season1_profit_unweighted"])
            if truth_year in wx["years"]:
                k = wx["years"].index(truth_year)
                m["truth"] = dict(year=truth_year, profit=float(res["_all"][j]["_profit_yr"][k]),
                                  season1_profit=float(res["_all"][j]["_season1"][k]), source="computed:hidden year")
        rot_out.append(m)
    if weights is not None:
        top = rot_out[0]
        fusion_block["range_width"] = dict(
            without_scout=top["unweighted"]["season1_profit"]["p90"] - top["unweighted"]["season1_profit"]["p10"],
            with_scout=top["season1_profit"]["p90"] - top["season1_profit"]["p10"],
            metric="this season's profit, current rotation", unit="EGP/feddan", source="computed",
            note="Scout readings narrow this season only; 3-year ranges stay on history alone.")
        fusion_block["bias_check"] = dict(n_overlap_days=0, mean_gap=None, applied=False,
                                          note="SMAP not connected" if not ctx["smap"] else "see validation")
    modes = sorted({r["mode"] for r in runs}) if weights is not None else []
    out = dict(
        site=dict(id=site_id, name=meta.get("name"), name_ar=meta.get("name_ar"), lat=s["lat"], lon=s["lon"],
                  irrigated=irrigated, soil_class=soil_class, soil=s["soil"]),
        mode=modes[0] if len(modes) == 1 else ("MIXED" if modes else "NONE"),
        scenario=dict(rain_mult=req.rain_mult, temp_offset_c=req.temp_offset, price_mult=req.price_mult,
                      source="user input"),
        weights=req.weights, years=res["years"], pool_size=res["pool_size"],
        rotations=rot_out, order=res["order"], no_clear_winner=res["no_clear_winner"],
        fusion=fusion_block, scout_summary=sight,
        blind_spots=report.blind_spots(rot_out, ctx),
        elapsed_s=round(time.time() - t0, 2),
    )
    out = _clean(out)
    _result_cache[key] = out
    if len(_result_cache) > 200:
        _result_cache.pop(next(iter(_result_cache)))
    return out


# ---------------------------------------------------------------------------
# Council + Field Card
# ---------------------------------------------------------------------------

class ExplainRequest(SimRequest):
    lang: str = "en"
    use_llm: bool = True


@app.post("/api/council")
def council_ep(req: ExplainRequest):
    res = simulate(SimRequest(**req.model_dump(exclude={"lang", "use_llm"})))
    return council.explain(res, req.lang, req.use_llm)


_cards: dict = {}


@app.post("/api/fieldcard")
def fieldcard_ep(req: ExplainRequest, request: Request):
    res = simulate(SimRequest(**req.model_dump(exclude={"lang", "use_llm"})))
    url = f"{str(request.base_url).rstrip('/')}/?site={res['site']['id']}&lens=farmer&lang={req.lang}"
    cid = hashlib.sha1((url + json.dumps(res["order"]) + str(time.time())).encode()).hexdigest()[:10]
    _cards[cid] = fieldcard.card_html(res, req.lang, url)
    text = fieldcard.whatsapp(res, req.lang, url)
    return dict(id=cid, print_url=f"/fieldcard/{cid}", whatsapp=text, chars=len(text), url=url)


@app.get("/fieldcard/{cid}")
def fieldcard_view(cid: str):
    if cid not in _cards:
        raise HTTPException(404, "card expired; generate it again")
    return HTMLResponse(_cards[cid])


# ---------------------------------------------------------------------------
# Scout
# ---------------------------------------------------------------------------

def _auth(authorization: str | None):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad or missing bearer token")


@app.post("/api/scout/run")
def scout_run(run: dict, authorization: str | None = Header(default=None)):
    _auth(authorization)
    try:
        r = scout.store_run(run)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    _result_cache.clear()
    return r


class Calib(BaseModel):
    site_id: str
    samples: list[dict]
    soil_class: str | None = None


@app.post("/api/scout/calibrate")
def scout_calibrate(c: Calib):
    meta = SITES.get(c.site_id)
    sc = c.soil_class or (soilmod.classify(site(meta["lat"], meta["lon"])["soil"]) if meta else "loam")
    try:
        cal = scout.calibrate(c.site_id, c.samples, sc)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    _result_cache.clear()
    return cal


class SimRun(BaseModel):
    lat: float
    lon: float
    truth_year: int | None = None
    days: int = 135
    existing: list[str] | None = None


@app.post("/api/scout/simulate")
def scout_simulate(req: SimRun):
    s = site(req.lat, req.lon)
    meta = site_meta(s["lat"], s["lon"])
    sc = soilmod.classify(s["soil"])
    irrigated = meta.get("irrigated", True)
    if irrigated:
        raise HTTPException(422, "Simulated Scout runs are for rain-fed sites: on an irrigated field the "
                                 "model needs the farmer's irrigation dates to predict soil moisture.")
    ex = tuple((req.existing or meta.get("existing") or ["barley", FALLOW])[:2])
    wx = _wx(s, 1.0, 0.0)
    wet = wb.simulate([ex * wb.YEARS], wx, sc, False, None, keep_wetness_days=365)["wet"][0]
    years = wx["years"]
    ty = req.truth_year if req.truth_year in years else years[int(np.argmin(wet[:, :120].mean(1)))]
    scout.delete_runs(meta["id"])
    run, cal = scout.simulate_run(meta["id"], wet, years, ty, req.days, sc)
    _result_cache.clear()
    return dict(run_id=run["run_id"], truth_year=ty, days=req.days, n_points=len(run["points"]),
                mode="SIMULATED", calibration_id=cal["id"])


@app.get("/api/scout/runs")
def scout_runs(site_id: str):
    return dict(runs=scout.list_runs(site_id), calibration=scout.latest_calibration(site_id))


@app.delete("/api/scout/runs")
def scout_clear(site_id: str):
    scout.delete_runs(site_id)
    _result_cache.clear()
    return dict(ok=True)


@app.get("/api/scout/export")
def scout_export(site_id: str):
    return JSONResponse(scout.export(site_id), headers={
        "Content-Disposition": f'attachment; filename="agrotwin_{site_id}_my_farm_data.json"'})


# ---------------------------------------------------------------------------
# Robot telemetry + leaf camera (live Verdex)
# ---------------------------------------------------------------------------

@app.get("/api/robot/state")
def robot_state():
    st = robot.state()
    st["model"] = {k: v for k, v in disease._info.items() if k != "class_names"}
    return _clean(st)


@app.post("/api/robot/telemetry")
def telemetry(payload: dict):
    try:
        return robot.ingest(payload, source=payload.get("source", "live"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class Detection(BaseModel):
    label: str
    confidence: float = 0.9
    source: str = "replay"


@app.post("/api/robot/detect")
def detect(d: Detection):
    if d.label not in DISEASE_CLASSES:
        raise HTTPException(400, f"unknown class {d.label}")
    _result_cache.clear()
    return robot.detect(d.label, d.confidence, d.source)


@app.get("/api/model")
def model_info():
    return disease.load()


@app.post("/api/robot/diagnose")
async def diagnose(file: UploadFile = File(...)):
    data = await file.read()
    try:
        res = disease.classify(data)
    except RuntimeError as exc:
        raise HTTPException(503, f"disease model unavailable: {exc}")
    thumb = "data:image/jpeg;base64," + base64.b64encode(data).decode() if len(data) < 400_000 else None
    if res["known"]:
        d = robot.detect(res["label"], res["confidence"], "camera", image=thumb)
        d["known"] = True
        _result_cache.clear()
    res["recorded"] = res["known"]
    return res


@app.post("/api/robot/sim/start")
def robot_sim(req: SimRun):
    s = site(req.lat, req.lon)
    robot.start_sim(s["weather"], s["lat"], s["lon"])
    return dict(mode=robot.mode)


@app.post("/api/robot/reset")
def robot_reset():
    robot.reset()
    _result_cache.clear()
    return dict(mode=robot.mode)


# ---------------------------------------------------------------------------
# Validation wall + static demo
# ---------------------------------------------------------------------------

@app.get("/api/validation")
def validation():
    p = ROOT / "qa" / "REPORT.json"
    if not p.exists():
        return dict(status="not run", how="make validate")
    return _clean(json.loads(p.read_text()))


@app.get("/demo/{site_id}")
def demo(site_id: str):
    p = ROOT / "data" / "demo" / f"{site_id}.json"
    if not p.exists():
        raise HTTPException(404, "no precomputed demo for this site (run scripts/build_demo.py)")
    return json.loads(p.read_text())


@app.get("/api/health")
def health():
    return dict(ok=True, offline=OFFLINE, sites=len(SITES), model=disease._info.get("loaded"))


FRONT = ROOT / "frontend"


@app.get("/")
def index():
    return FileResponse(FRONT / "index.html")


app.mount("/static", StaticFiles(directory=FRONT), name="static")
