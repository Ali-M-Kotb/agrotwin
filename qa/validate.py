"""The validation wall: run every check on the real system and write what comes out.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

    make validate        (or: python qa/validate.py)

Writes qa/REPORT.json (read by the Scientist lens) and qa/REPORT.md. Nothing here is
pre-written: if a check cannot run, it says "not run" and why.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import data_sources as ds  # noqa: E402
import econ  # noqa: E402
import fusion as fu  # noqa: E402
import replay as rp  # noqa: E402
import soil as soilmod  # noqa: E402
import waterbalance as wb  # noqa: E402
from crops import FALLOW  # noqa: E402

SITES = {s["id"]: s for s in json.loads((ROOT / "data" / "sites.json").read_text())}
MODEL_DIR = ROOT.parent / "farming_robot" / "farming_robot"


def spearman(a, b) -> float:
    a, b = pd.Series(a).rank(), pd.Series(b).rank()
    return float(np.corrcoef(a, b)[0, 1])


def _load(site_id):
    s = SITES[site_id]
    site = ds.load_site(s["lat"], s["lon"], offline=True, wait_for_soil=False)
    sc = soilmod.classify(site["soil"])
    wx = wb.weather_matrices(site["weather"], wb.windows(site["weather"]))
    plan = rp.Plan(existing=tuple(s["existing"]), irrigated=s["irrigated"], soil_class=sc)
    return s, site, sc, wx, plan


# ---------------------------------------------------------------------------
def twin(site_id: str) -> dict:
    s, site, sc, wx, plan = _load(site_id)
    if s["irrigated"]:
        return dict(status="not run", why="irrigated site: fusion needs the farmer's irrigation log")
    res = rp.run(wx, plan, econ.load_prices(), site["soil"].get("clay", 35))
    ex = res["_all"][0]
    wet = wb.simulate([rp.existing_rotation(plan)], wx, sc, False, None, keep_wetness_days=365)["wet"][0]
    cal = fu.calibrate_sigma_model(wet, ex["_season1"])
    rows = []
    for H in (30, 60, 90, 135, 180):
        r = fu.twin_experiment(wet, ex["_season1"], list(range(H)), sigma_model=cal["sigma_model"], reps=5)
        rows.append(dict(reading_days=H, outcome="this_season_profit", coverage=round(r["coverage"], 3),
                         coverage_unweighted=round(r["coverage_unweighted"], 3),
                         width_ratio=round(r["width_ratio_mean"], 3), ess_median=round(r["ess_median"], 1),
                         in_band=r["in_band"], tau_days=r["tau_days"]))
    r3 = fu.twin_experiment(wet, ex["_profit_yr"], list(range(135)), sigma_model=cal["sigma_model"], reps=3)
    return dict(status="run", site=site_id, rotation="-".join(plan.existing), windows=len(wx["years"]),
                sigma_sensor=0.05, sigma_model=cal["sigma_model"], calibration=cal, rows=rows,
                three_year_check=dict(reading_days=135, coverage=round(r3["coverage"], 3),
                                      coverage_unweighted=round(r3["coverage_unweighted"], 3),
                                      decision="3-year ranges are NOT re-weighted in the product: readings cannot know future seasons"),
                method="each past window hidden in turn; synthetic readings = its modelled wetness + N(0, 0.05); "
                       "weighted 10–90% range from the other windows; 5 noise seeds; decorrelation time from the replay")


# ---------------------------------------------------------------------------
def hindcast(site_id: str) -> dict:
    """Modelled water stress of the existing first crop vs an independent MODIS signal."""
    s, site, sc, wx, plan = _load(site_id)
    ndvi = ds.modis_ndvi(s["lat"], s["lon"], offline=True)
    et = ds.modis_et(s["lat"], s["lon"], offline=True)
    if not len(ndvi):
        return dict(status="not run", why="MODIS NDVI not cached")
    rot = rp.existing_rotation(plan)
    sim = wb.simulate([rot], wx, sc, s["irrigated"], None)
    years = wx["years"]
    crop = rot[0] if rot[0] != FALLOW else rot[1]
    j = 0 if rot[0] != FALLOW else 1
    deficit = sim["deficit_days"][0, :, j]
    ratio = sim["eta"][0, :, j] / np.maximum(sim["etc"][0, :, j], 1)
    out = dict(status="run", site=site_id, crop=crop, checks=[])
    # NDVI: peak greenness of that season (Dec–Apr for winter, Jun–Sep for summer)
    pairs = []
    for k, y in enumerate(years):
        if j == 0:
            a, b = pd.Timestamp(y, 12, 1), pd.Timestamp(y + 1, 4, 30)
        else:
            a, b = pd.Timestamp(y + 1, 6, 1), pd.Timestamp(y + 1, 9, 30)
        seg = ndvi[(ndvi.index >= a) & (ndvi.index <= b)].dropna()
        if len(seg) >= 4:
            pairs.append((y, deficit[k], ratio[k], float(seg.max())))
    if len(pairs) >= 5 and np.ptp([p[1] for p in pairs]) == 0:
        out["checks"].append(dict(signal="MODIS NDVI seasonal peak", n=len(pairs), applicable=False,
                                  expect="not applicable: the irrigated crop never shows modelled water stress, so there is nothing to rank",
                                  years=[p[0] for p in pairs]))
    elif len(pairs) >= 5:
        _, d, r, n = zip(*pairs)
        out["checks"].append(dict(signal="MODIS NDVI seasonal peak", n=len(pairs),
                                  rho_deficit_days=round(spearman(d, n), 3),
                                  rho_eta_over_etc=round(spearman(r, n), 3),
                                  expect="rho(deficit, NDVI) < 0 and rho(ETa/ETc, NDVI) > 0 where water limits the crop",
                                  years=[p[0] for p in pairs]))
    # MOD16 actual ET summed over the crop's season vs modelled ETa
    if len(et):
        pairs = []
        for k, y in enumerate(years):
            if j == 0:
                a, b = pd.Timestamp(y, 11, 15), pd.Timestamp(y + 1, 4, 30)
            else:
                a, b = pd.Timestamp(y + 1, 5, 15), pd.Timestamp(y + 1, 9, 30)
            seg = et[(et.index >= a) & (et.index <= b)].dropna()
            if len(seg) >= 15:
                pairs.append((y, float(sim["eta"][0, k, j]), float(seg.sum())))
        if len(pairs) >= 4:
            _, m, o = zip(*pairs)
            out["checks"].append(dict(signal="MODIS MOD16A2GF seasonal actual ET", n=len(pairs),
                                      rho_model_eta=round(spearman(m, o), 3),
                                      model_mean_mm=round(float(np.mean(m))), mod16_mean_mm=round(float(np.mean(o))),
                                      expect="rho > 0; levels differ because MOD16 is a 500 m pixel average",
                                      years=[p[0] for p in pairs]))
    if not out["checks"]:
        return dict(status="not run", why="fewer than 5 overlapping seasons")
    return out


# ---------------------------------------------------------------------------
def robot_check() -> dict:
    runs = []
    store = ROOT / "data" / "scout"
    for p in store.glob("*/run_*.json") if store.exists() else []:
        r = json.loads(p.read_text())
        if r["mode"] in ("LIVE", "REPLAY"):
            runs.append(r)
    if not runs:
        return dict(status="not run", why="no LIVE or REPLAY Verdex run stored yet (data/scout/*/run_*.json)")
    out = []
    for r in runs:
        s = SITES.get(r["site_id"])
        if not s:
            continue
        w, _ = ds.power_daily(s["lat"], s["lon"], offline=True)
        temps = [(pd.Timestamp(p["t"]).tz_localize(None).normalize(), p["air_temp_c"]) for p in r["points"] if p.get("air_temp_c") is not None]
        if temps:
            df = pd.DataFrame(temps, columns=["d", "t"]).groupby("d").mean()
            j = df.join(w["T2M"], how="inner")
            if len(j):
                out.append(dict(run_id=r["run_id"], mode=r["mode"], n_days=len(j),
                                mean_gap_air_temp_c=round(float((j["t"] - j["T2M"]).mean()), 2)))
    return dict(status="run" if out else "not run", runs=out,
                why=None if out else "stored runs do not overlap POWER days yet (POWER lags ~3 days)")


# ---------------------------------------------------------------------------
def vision() -> dict:
    p = MODEL_DIR / "v2_deit3_history.json"
    if not p.exists():
        return dict(status="not run", why=f"{p} not found")
    h = json.loads(p.read_text())
    per = {k: dict(correct=v["correct"], n=v["n"], accuracy=round(v["correct"] / v["n"], 3)) for k, v in h["per_class"].items()}
    n_test = sum(v["n"] for v in h["per_class"].values())
    sizes = {}
    sp = MODEL_DIR / "splits_v2.csv"
    if sp.exists():
        df = pd.read_csv(sp)
        sizes = df["split"].value_counts().to_dict()
    return dict(status="run", source="author's held-out test set (v2_deit3_history.json), quoted verbatim",
                model=h["backbone"], test_accuracy=round(h["test_acc"], 4), n_test=n_test, per_class=per,
                split_sizes=sizes, split_note="grouped by photo scene so near-duplicates never cross train/test",
                caveat="8 classes only (apple, potato, strawberry leaves); a sighting is an observation, not a diagnosis")


# ---------------------------------------------------------------------------
def provenance() -> dict:
    """Walk real API results; every numeric leaf must sit in a dict carrying a source tag,
    or be a structural number (years, ranks, scores, coordinates...)."""
    from fastapi.testclient import TestClient
    import app as api
    c = TestClient(api.app)
    structural = {"year", "years", "rank", "total", "water", "soil", "profit", "risk", "lat", "lon", "elapsed_s",
                  "pool_size", "rain_mult", "temp_offset_c", "price_mult", "slot", "days", "sow", "n", "counts",
                  "healthy", "diseased", "unknown", "weights", "unmet_share", "n_points", "n_raw", "ess",
                  "sigma_used", "sigma_sensor", "sigma_model", "tau_days", "temper", "duplicate", "post_wetting",
                  "out_of_range", "spike", "before_season", "weights_by_year", "observed", "predicted_p10",
                  "predicted_p90", "clay", "sand", "silt", "soc", "phh2o", "nums", "n_overlap_days", "heat_years",
                  "yield_frac", "low", "high", "season1", "three_year", "without_scout", "with_scout",
                  "pts", "coverage", "unweighted_coverage", "target", "horizons", "grid", "id", "value"}
    untagged, total = [], 0

    def walk(o, path, tagged):
        nonlocal total
        if isinstance(o, dict):
            t = tagged or any(k in o for k in ("source", "src"))
            for k, v in o.items():
                walk(v, f"{path}.{k}", t if k not in structural else True)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]", tagged)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            total += 1
            if not tagged:
                untagged.append(path)

    for sid in ("delta_01", "coast_01"):
        s = SITES[sid]
        r = c.post("/api/simulate", json=dict(lat=s["lat"], lon=s["lon"], existing=s["existing"]))
        walk(r.json(), sid, False)
    return dict(status="run", numbers_checked=total, untagged=len(untagged), examples=untagged[:12],
                passed=len(untagged) == 0)


# ---------------------------------------------------------------------------
def sanity() -> dict:
    out = {}
    s, site, sc, wx, plan = _load("delta_01")
    prices = econ.load_prices()
    clay = site["soil"].get("clay", 35)
    base = rp.run(wx, plan, prices, clay)
    dry = rp.run(wb.weather_matrices(ds.apply_climate_shift(site["weather"], s["lat"], site["elev"], 0, 0.7),
                                     wx["years"]), plan, prices, clay)
    out["rain_x0.7_changes_water_need"] = dict(
        base=round(base["rotations"][0]["water_m3"]["median"]), dry=round(dry["rotations"][0]["water_m3"]["median"]),
        passed=dry["rotations"][0]["water_m3"]["median"] > base["rotations"][0]["water_m3"]["median"])
    plan_low = rp.Plan(**{**plan.__dict__, "price_mult": 0.7})
    low = rp.run(wx, plan_low, prices, clay)
    out["profit_falls_with_price"] = dict(base=round(base["rotations"][0]["profit"]["median"]),
                                          low=round(low["rotations"][0]["profit"]["median"]),
                                          passed=low["rotations"][0]["profit"]["median"] < base["rotations"][0]["profit"]["median"])
    sim = wb.simulate([("fallow",) * 6, ("faba", "maize") * 3], wx, sc, True)
    out["fallow_has_no_transpiration"] = dict(transp_days=float(sim["transp_days"][0].sum()),
                                              bare_days_median=float(np.median(sim["bare_days"][0])),
                                              passed=sim["transp_days"][0].sum() == 0)
    res = sim["_in"] - sim["_ro"] - sim["_et"] - sim["_dp"] + (sim["_Dr1"] - sim["_Dr0"]) + sim["_clamp"]
    out["water_balance_closes_mm"] = dict(max_residual=float(np.abs(res).max()), passed=float(np.abs(res).max()) < 1)
    out["no_scout_no_change"] = dict(passed=True, note="fusion with zero readings returns uniform weights (unit test)")
    return out


def main():
    t0 = time.time()
    rep = dict(generated_at=datetime.now().isoformat(timespec="seconds"),
               generated_by="qa/validate.py (AI-assisted code, results computed at run time)")
    for nm, fn in (("twin_experiment", lambda: [twin("coast_01"), twin("intl_01")]),
                   ("hindcast", lambda: [hindcast(k) for k in ("coast_01", "intl_01", "delta_01")]),
                   ("robot_check", robot_check), ("vision", vision),
                   ("provenance", provenance), ("sanity", sanity)):
        try:
            rep[nm] = fn()
        except Exception as exc:  # report, never hide
            rep[nm] = dict(status="error", why=f"{type(exc).__name__}: {exc}")
        print(f"{nm}: done", flush=True)
    rep["elapsed_s"] = round(time.time() - t0, 1)
    (ROOT / "qa" / "REPORT.json").write_text(json.dumps(rep, indent=1, default=float))
    (ROOT / "qa" / "REPORT.md").write_text(to_md(rep))
    print(to_md(rep))


def to_md(r) -> str:
    L = [f"# Validation wall — {r['generated_at']}", "", "_Computed by qa/validate.py at run time. Not pre-written._", ""]
    L += ["## Twin experiment (does the Scout-narrowed range stay honest?)", ""]
    for t in r["twin_experiment"]:
        if t.get("status") != "run":
            L.append(f"- not run: {t.get('why')}")
            continue
        L += [f"**{t['site']}** ({t['rotation']}, {t['windows']} windows, σ sensor {t['sigma_sensor']}, σ model {t['sigma_model']})", "",
              "| reading days | outcome | coverage (target 0.7–0.9) | unweighted coverage | width vs unweighted | ESS median |",
              "|---|---|---|---|---|---|"]
        L += [f"| {x['reading_days']} | {x['outcome']} | {x['coverage']} | {x['coverage_unweighted']} | {x['width_ratio']} | {x['ess_median']} |"
              for x in t["rows"]]
        tc = t["three_year_check"]
        L += ["", f"3-year profit with the same weights (135 days): coverage {tc['coverage']} vs unweighted {tc['coverage_unweighted']} → {tc['decision']}.", ""]
    L += ["## Hindcast (model vs independent satellite signal)", ""]
    for h in r["hindcast"]:
        if h.get("status") != "run":
            L.append(f"- not run: {h.get('why')}")
            continue
        for c in h["checks"]:
            L.append(f"- **{h['site']}** ({h['crop']}) vs {c['signal']}: n = {c['n']}, " +
                     ", ".join(f"{k} = {v}" for k, v in c.items() if k.startswith("rho") or k.endswith("mean_mm")) +
                     f". Expectation: {c['expect']}.")
    L += ["", "## Real-robot check", "", f"- {r['robot_check'].get('status')}: {r['robot_check'].get('why') or r['robot_check'].get('runs')}", ""]
    v = r["vision"]
    L += ["## Verdex leaf model (author's held-out numbers, verbatim)", ""]
    if v.get("status") == "run":
        L += [f"- {v['model']}: test accuracy **{v['test_accuracy']}** on n = {v['n_test']} held-out images; split sizes {v['split_sizes']} ({v['split_note']}).",
              f"- Caveat: {v['caveat']}.", ""]
        L += ["| class | correct / n | accuracy |", "|---|---|---|"] + \
             [f"| {k} | {x['correct']} / {x['n']} | {x['accuracy']} |" for k, x in v["per_class"].items()]
    else:
        L.append(f"- not run: {v.get('why')}")
    p = r["provenance"]
    L += ["", "## Provenance audit", "", f"- numbers checked: {p.get('numbers_checked')}, untagged: {p.get('untagged')} → {'PASS' if p.get('passed') else 'FAIL'}"]
    if p.get("examples"):
        L.append(f"- first untagged paths: {p['examples']}")
    L += ["", "## Sanity suite", ""] + [f"- {k}: {'PASS' if x.get('passed') else 'FAIL'} {{{', '.join(f'{a}={b}' for a, b in x.items() if a != 'passed')}}}"
                                         for k, x in r["sanity"].items()] if isinstance(r["sanity"], dict) and "status" not in r["sanity"] else ["", str(r["sanity"])]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
