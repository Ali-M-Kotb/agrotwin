"""Backtest: would AgroTwin have called the last three seasons, using only the past?

    python qa/backtest.py           → qa/BACKTEST.md + qa/BACKTEST.json

For each demo site, each test season S (Oct S → the following autumn) of the last three that
NASA POWER fully covers, and each rotation shown at that site:
  forecast  = the spread of the season's outcome replayed on every PRIOR year only
              (windows whose first season ended before Oct 1 of S: start year ≤ S−2)
  actual    = the same season replayed on S's real NASA POWER weather
Scores (lower is better for errors):
  in_80pct_range   is the actual inside the forecast's 10–90 % range?
  CRPS             continuous ranked probability score of the forecast ensemble vs the actual
                   (rewards a sharp range that contains the truth; the standard score for ensembles)
  baselines        "same as last year" (the most recent prior season) and "long-term average"
Variants: raw history vs climate-adjusted history (each past year warmed to today's climate by
the site's own Tmax trend, ET0 recomputed). The product uses whichever wins here.

Honest scope: "actual" is the model driven by observed weather, not a measured harvest (no
field-level yield records exist for these points). An independent satellite check is reported
alongside: MODIS NDVI season peak and MOD16 ET for the same seasons.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import data_sources as ds  # noqa: E402
import econ  # noqa: E402
import replay as rp  # noqa: E402
import soil as soilmod  # noqa: E402
import waterbalance as wb  # noqa: E402
from crops import FALLOW, MM_TO_M3_PER_FEDDAN  # noqa: E402

SITES = {s["id"]: s for s in json.loads((ROOT / "data" / "sites.json").read_text())}
TEST_SITES = ["delta_01", "coast_01", "intl_01"]

def crps(ens: np.ndarray, x: float) -> float:
    ens = np.asarray(ens, float)
    return float(np.mean(np.abs(ens - x)) - 0.5 * np.mean(np.abs(ens[:, None] - ens[None, :])))

def padded(weather: pd.DataFrame) -> pd.DataFrame:
    """Append 2 years after the data end (copies of the last two years) so a window starting in
    a recent year has room for slots 2+. Only the first season is scored, which never reaches
    the padding (checked below)."""
    parts, last = [weather], weather
    for k in (1, 2):
        tail = weather.iloc[-730:].copy()
        tail.index = tail.index + pd.Timedelta(days=730 * k)
        parts.append(tail[tail.index > parts[-1].index[-1]])
    return pd.concat(parts)

def season1(rot, wx, soil_class, irrigated, prices, overrides):
    sim = wb.simulate([rot], wx, soil_class, irrigated)
    eco = econ.slot_economics(sim, prices, 1.0, overrides)
    return dict(profit=eco["profit"][0, :, :2].sum(1),
                water=sim["irr_gross"][0, :, :2].sum(1) * MM_TO_M3_PER_FEDDAN,
                yield_frac=np.where(eco["yield_frac"][0, :, 0] > 0, eco["yield_frac"][0, :, 0], eco["yield_frac"][0, :, 1]))

def run_site(sid: str, prices) -> dict:
    s = SITES[sid]
    site = ds.load_site(s["lat"], s["lon"], offline=True, wait_for_soil=False)
    w, elev = site["weather"], site["elev"]
    sc = soilmod.classify(site["soil"])
    data_end = w.index[-1]
    wp = padded(w)
    # last three seasons whose first season (Oct S → ~Nov S+1) is fully observed
    tests = [S for S in range(data_end.year - 4, data_end.year)
             if pd.Timestamp(S, 10, 1) + pd.Timedelta(days=400) <= data_end][-3:]
    starts = list(range(1991, tests[-1] + 1))
    plan = rp.Plan(existing=tuple(s["existing"]), irrigated=s["irrigated"], soil_class=sc)
    shown = rp.run(wb.weather_matrices(w, wb.windows(w)), plan, prices, site["soil"].get("clay", 35))["rotations"]
    rots = [tuple(r["seq"]) for r in shown]
    overrides = rp.effective_overrides(plan)

    # site warming trend (°C / year) from annual mean Tmax, used by the climate-adjusted variant
    ann = w["T2M_MAX"].groupby(w.index.year).mean().iloc[:-1]
    trend = float(np.polyfit(ann.index.values, ann.values, 1)[0])

    variants = {}
    raw = wb.weather_matrices(wp, starts)
    variants["raw"] = raw
    # climate-adjusted: warm each start year y to the climate of the test season
    adj_mats = {}
    for S in tests:
        frames = []
        for y in starts:
            dT = trend * (S - y)
            frames.append(ds.apply_climate_shift(wp, s["lat"], elev, dT, 1.0) if abs(dT) > 1e-6 else wp)
        adj_mats[S] = frames
    out = dict(site=sid, name=s["name"], irrigated=s["irrigated"], soil_class=sc, tmax_trend_per_decade=round(trend * 10, 3),
               test_seasons=[f"{S}/{str(S + 1)[2:]}" for S in tests], rotations=[], data_end=str(data_end.date()))
    for rot in rots:
        res_raw = season1(rot, raw, sc, s["irrigated"], prices, overrides)
        rows = []
        for S in tests:
            k_test = starts.index(S)
            prior = [i for i, y in enumerate(starts) if y <= S - 2]
            # climate-adjusted ensemble for this test season
            adj = {"profit": [], "water": [], "yield_frac": []}
            for i in prior:
                wx_i = wb.weather_matrices(adj_mats[S][i], [starts[i]])
                r1 = season1(rot, wx_i, sc, s["irrigated"], prices, overrides)
                for kk in adj:
                    adj[kk].append(r1[kk][0])
            row = dict(season=f"{S}/{str(S + 1)[2:]}")
            for metric in ("profit", "water", "yield_frac"):
                if metric == "water" and not s["irrigated"]:
                    continue
                actual = float(res_raw[metric][k_test])
                ens_raw = res_raw[metric][prior]
                ens_adj = np.array(adj[metric])
                last = float(res_raw[metric][prior[-1]])
                mean = float(np.mean(ens_raw))
                lo, hi = np.quantile(ens_raw, [0.1, 0.9])
                alo, ahi = np.quantile(ens_adj, [0.1, 0.9])
                row[metric] = dict(
                    actual=round(actual, 3),
                    raw=dict(p10=round(lo, 3), median=round(float(np.median(ens_raw)), 3), p90=round(hi, 3),
                             in_range=bool(lo <= actual <= hi), crps=round(crps(ens_raw, actual), 4)),
                    adjusted=dict(p10=round(alo, 3), median=round(float(np.median(ens_adj)), 3), p90=round(ahi, 3),
                                  in_range=bool(alo <= actual <= ahi), crps=round(crps(ens_adj, actual), 4)),
                    last_year=dict(value=round(last, 3), abs_err=round(abs(last - actual), 4)),
                    long_term_mean=dict(value=round(mean, 3), abs_err=round(abs(mean - actual), 4)),
                    n_prior=len(prior))
            rows.append(row)
        out["rotations"].append(dict(seq=list(rot), label=" → ".join(c for c in rot[:2] if c != FALLOW) or "fallow", seasons=rows))
    # independent satellite signal for the same seasons
    ndvi = ds.modis_ndvi(s["lat"], s["lon"], offline=True)
    et = ds.modis_et(s["lat"], s["lon"], offline=True)
    sat = []
    for S in tests:
        a, b = pd.Timestamp(S, 11, 15), pd.Timestamp(S + 1, 5, 15)
        seg = ndvi[(ndvi.index >= a) & (ndvi.index <= b)].dropna()
        eseg = et[(et.index >= a) & (et.index <= b)].dropna()
        sat.append(dict(season=f"{S}/{str(S + 1)[2:]}", winter_ndvi_peak=round(float(seg.max()), 3) if len(seg) else None,
                        winter_mod16_et_mm=round(float(eseg.sum()), 1) if len(eseg) > 15 else None,
                        model_first_crop_yield_frac=round(float(season1(rots[0], raw, sc, s["irrigated"], prices, overrides)["yield_frac"][starts.index(S)]), 3)))
    out["satellite_check"] = sat
    return out

def summarize(sites: list[dict]) -> dict:
    agg = {}
    for st in sites:
        for r in st["rotations"]:
            for row in r["seasons"]:
                for metric in ("profit", "water", "yield_frac"):
                    if metric not in row:
                        continue
                    m = row[metric]
                    a = agg.setdefault(metric, dict(n=0, raw_in=0, adj_in=0, crps_raw=[], crps_adj=[], last=[], mean=[], scale=[]))
                    a["n"] += 1
                    a["raw_in"] += m["raw"]["in_range"]
                    a["adj_in"] += m["adjusted"]["in_range"]
                    a["crps_raw"].append(m["raw"]["crps"])
                    a["crps_adj"].append(m["adjusted"]["crps"])
                    a["last"].append(m["last_year"]["abs_err"])
                    a["mean"].append(m["long_term_mean"]["abs_err"])
    out = {}
    for metric, a in agg.items():
        # for a single-value forecast CRPS equals the absolute error, so the scores are comparable
        out[metric] = dict(
            cases=a["n"],
            coverage_raw=round(a["raw_in"] / a["n"], 3), coverage_adjusted=round(a["adj_in"] / a["n"], 3),
            crps_raw=round(float(np.mean(a["crps_raw"])), 4), crps_adjusted=round(float(np.mean(a["crps_adj"])), 4),
            mae_same_as_last_year=round(float(np.mean(a["last"])), 4), mae_long_term_mean=round(float(np.mean(a["mean"])), 4),
            skill_vs_last_year_raw=round(1 - np.mean(a["crps_raw"]) / max(np.mean(a["last"]), 1e-9), 3),
            skill_vs_last_year_adjusted=round(1 - np.mean(a["crps_adj"]) / max(np.mean(a["last"]), 1e-9), 3),
        )
    return out

def to_md(rep: dict) -> str:
    L = [f"# Backtest — last three seasons ({rep['generated_at']})", "",
         "_Computed by qa/backtest.py. Forecasts use only years before each test season; 'actual' is the season "
         "replayed on its real NASA POWER weather (not a measured harvest)._", "",
         "## Summary across sites, rotations and seasons", "",
         "| metric | cases | in 80% range (raw) | in 80% range (climate-adjusted) | CRPS raw | CRPS adjusted | error: same as last year | error: long-term average | skill vs last year (adjusted) |",
         "|---|---|---|---|---|---|---|---|---|"]
    names = dict(profit="profit, EGP/feddan", water="irrigation, m³/feddan", yield_frac="yield, share of potential")
    for k, v in rep["summary"].items():
        L.append(f"| {names[k]} | {v['cases']} | {v['coverage_raw']:.0%} | {v['coverage_adjusted']:.0%} | {v['crps_raw']:g} | {v['crps_adjusted']:g} | "
                 f"{v['mae_same_as_last_year']:g} | {v['mae_long_term_mean']:g} | {v['skill_vs_last_year_adjusted']:+.0%} |")
    L += ["", "Skill = 1 − CRPS / (error of 'same as last year'). Positive means the replay beats repeating last season.", ""]
    for st in rep["sites"]:
        L += [f"## {st['name']} ({'irrigated' if st['irrigated'] else 'rain-fed'}, Tmax trend {st['tmax_trend_per_decade']:+} °C/decade)", ""]
        for r in st["rotations"]:
            L += [f"**{' → '.join(r['seq'])}**", "", "| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |", "|---|---|---|---|---|---|"]
            for row in r["seasons"]:
                for metric in ("profit", "water", "yield_frac"):
                    if metric in row:
                        m = row[metric]
                        L.append(f"| {row['season']} | {names[metric]} | {m['actual']:,.2f} | {m['adjusted']['p10']:,.2f} – {m['adjusted']['p90']:,.2f} | "
                                 f"{'yes' if m['adjusted']['in_range'] else '**no**'} | {m['last_year']['value']:,.2f} |")
            L.append("")
        L += ["Independent satellite signal for the same winters (MODIS):", "", "| season | NDVI peak | MOD16 ET (mm) | model yield share, first crop |", "|---|---|---|---|"]
        L += [f"| {x['season']} | {x['winter_ndvi_peak']} | {x['winter_mod16_et_mm']} | {x['model_first_crop_yield_frac']} |" for x in st["satellite_check"]]
        L.append("")
    return "\n".join(L) + "\n"

def main():
    prices = econ.load_prices()
    sites = [run_site(sid, prices) for sid in TEST_SITES]
    rep = dict(generated_at=datetime.now().isoformat(timespec="seconds"), sites=sites, summary=summarize(sites),
               generated_by="qa/backtest.py (AI-assisted code; results computed at run time)")
    (ROOT / "qa" / "BACKTEST.json").write_text(json.dumps(rep, indent=1))
    (ROOT / "qa" / "BACKTEST.md").write_text(to_md(rep))
    print(to_md(rep))

if __name__ == "__main__":
    main()
