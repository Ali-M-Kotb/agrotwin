"""Plan engine: from a farm profile to a full three-year plan.

Steps (all on real NASA data, every number tagged):
 1. Field productivity index from the field's own MODIS NDVI peaks vs 6.8 M Nile Delta cropland pixel-seasons
    (backend/models/ndvi_peers.json, from NASA GIBS). Scales potential yields for this field.
 2. Field Pulse (trained model): this season's status; a field below what the weather explains is flagged.
 3. Replay every candidate rotation on 32 climate-adjusted NASA POWER years (replay.run), with the farmer's
    constraints: crops to avoid / keep, water budget, soil salinity (FAO-29), canal-shortfall frequency.
 4. Search: top rotations × summer sowing (−14 / 0 / +14 days) × water strategy (full / 85 % deficit) through the
    exact FAO-56 engine plus the price and canal-shortfall Monte Carlo. Every option is kept for the trade-off chart.
 5. The plan: crops, sowing and harvest dates, water per season, yield and profit ranges, totals for the farm,
    comparison with today's rotation, risks and actions.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

import econ
import replay as rp
import waterbalance as wb
from config import A
from crops import CROPS, FALLOW, MM_TO_M3_PER_FEDDAN

PEERS = json.loads((Path(__file__).resolve().parent / "models" / "ndvi_peers.json").read_text()) \
    if (Path(__file__).resolve().parent / "models" / "ndvi_peers.json").exists() else None
_SHIFT_LOCK = threading.Lock()
SHIFTS = (-14, 0, 14)
DEFICIT = 0.85

DEFAULTS = dict(area_feddan=1.0, winter="wheat", summer="rice", salinity_ece=0.0, canal_short_prob=None,
                water_budget_m3=None, priorities=dict(water=1.0, soil=1.0, profit=1.0, risk=1.0),
                exclude=[], must_include=[], irrigated=None)

def field_index(ndvi) -> dict:
    """Ratio of the field's median cropped-season NDVI peak to the Delta peer median, clipped to 0.8–1.1."""
    if ndvi is None or PEERS is None or len(ndvi.dropna()) < 60:
        return dict(factor=1.0, available=False, reason="no satellite history or peer table", source="assumption:no_index")
    import pandas as pd
    s = ndvi.dropna()
    out = {}
    for name, a, b in (("winter", (12, 1), (4, 30)), ("summer", (6, 1), (10, 15))):
        pk = []
        for y in range(s.index[0].year, s.index[-1].year + 1):
            lo = pd.Timestamp(y, *a); hi = pd.Timestamp(y + (1 if name == "winter" else 0), *b)
            seg = s[(s.index >= lo) & (s.index <= hi)]
            if len(seg) >= 4 and seg.max() >= 0.45:
                pk.append(float(seg.max()))
        if pk:
            out[name] = dict(field_peak=round(float(np.median(pk)), 3), peer_median=round(PEERS[name]["median"], 3), seasons=len(pk))
    if not out:
        return dict(factor=1.0, available=False, reason="no cropped seasons detected", source="assumption:no_index")
    ratio = float(np.mean([v["field_peak"] / v["peer_median"] for v in out.values()]))
    return dict(factor=round(float(np.clip(ratio, 0.8, 1.1)), 3), raw_ratio=round(ratio, 3), available=True, seasons=out,
                source="computed: field's MODIS NDVI peaks vs 6.8 M Delta cropland pixel-seasons (NASA GIBS); yield scaled in proportion, clipped 0.8–1.1 (assumption:ndvi_yield_scaling)")

def _season_start() -> date:
    t = date.today()
    return date(t.year if t.month >= 10 else t.year - 1, 10, 1)

def _evaluate(rots, wx, plan, prices, overrides, shift, strategy, need_summer):
    cap = None
    if strategy == "deficit" and plan.irrigated:
        cap = {"winter": 1e9, "summer": need_summer * DEFICIT}
    if plan.water_cap_m3 and plan.irrigated:
        base = {k: v / MM_TO_M3_PER_FEDDAN * A["irrigation_efficiency"] for k, v in plan.water_cap_m3.items()}
        cap = {k: min(base.get(k, 1e9), (cap or {}).get(k, 1e9)) for k in ("winter", "summer")}
    with _SHIFT_LOCK:
        wb.SOW_SHIFT["summer"] = shift
        try:
            ok = [r for r in rots if wb.calendar(r) is not None]
            if not ok:
                return [], None
            sim = wb.simulate(ok, wx, plan.soil_class, plan.irrigated, cap)
            cals = {r: wb.calendar(r) for r in ok}
        finally:
            wb.SOW_SHIFT["summer"] = 0
    eco = econ.slot_economics(sim, prices, plan.price_mult, overrides, plan.salinity_ece)
    p_short = plan.canal_short_prob if plan.canal_short_prob is not None else A["canal_short_prob"]
    out = []
    for i, r in enumerate(ok):
        mc = econ.mc_profit_year(sim, eco, i, plan.irrigated, p_short)
        water = sim["irr_gross"][i].sum(1) * MM_TO_M3_PER_FEDDAN / wb.YEARS
        out.append(dict(seq=list(r), shift=shift, strategy=strategy, cal=cals[r],
                        profit=dict(p10=float(np.percentile(mc, 10)), median=float(np.median(mc)), p90=float(np.percentile(mc, 90))),
                        water=dict(p10=float(np.percentile(water, 10)), median=float(np.median(water)), p90=float(np.percentile(water, 90))),
                        loss_share=float((mc < 0).mean()), _i=i))
    return out, (sim, eco)

def make_plan(site: dict, wx: dict, profile: dict, prices: dict, soil_class: str, irrigated: bool, clay: float,
              ndvi=None, pulse_status: dict | None = None) -> dict:
    t0 = time.time()
    p = {**DEFAULTS, **{k: v for k, v in profile.items() if v is not None}}
    pri = {**DEFAULTS["priorities"], **(p.get("priorities") or {})}
    fi = field_index(ndvi)
    overrides = {}
    for c in CROPS:
        if fi["factor"] != 1.0:
            overrides[c] = {"yield_t": prices[c]["yield_t"] * fi["factor"]}
    budget = p.get("water_budget_m3")
    plan = rp.Plan(existing=(p["winter"], p["summer"]), candidates=[c for c in CROPS if c not in (p.get("exclude") or [])],
                   weights=pri, irrigated=irrigated, soil_class=soil_class, salinity_ece=float(p.get("salinity_ece") or 0),
                   canal_short_prob=p.get("canal_short_prob"), price_overrides=overrides,
                   water_cap_m3=({"winter": 0.4 * budget, "summer": 0.6 * budget} if (budget and irrigated) else None))
    res = rp.run(wx, plan, prices, clay)
    ov = rp.effective_overrides(plan)
    must = set(p.get("must_include") or [])
    pool = sorted(res["_all"][1:], key=lambda m: -m["total"])
    if must:
        pool = [m for m in pool if must <= set(m["seq"])] or pool
    cands, seen = [], set()
    for m in pool:
        k = tuple(m["seq"])
        if k not in seen and not m.get("excluded", {}).get("is_excluded"):
            seen.add(k); cands.append(k)
        if len(cands) == 4:
            break
    existing = rp.existing_rotation(plan)
    rots = [existing] + [c for c in cands if c != existing]
    # summer irrigation need (median net mm) of the unconstrained run, for the deficit strategy
    sim0 = res["_sim"]
    need_summer = float(np.median(sim0["irr_net"][:, :, 1::2].sum(2)) / wb.YEARS) if irrigated else 0
    options = []
    for shift in SHIFTS:
        for strategy in (("full", "deficit") if irrigated else ("full",)):
            got, _ = _evaluate(rots, wx, plan, prices, ov, shift, strategy, max(need_summer, 1))
            options += got
    # score every option (direction-aware), weights from the farmer's priorities
    def nrm(v, inv=False):
        v = np.asarray(v, float); lo, hi = v.min(), v.max()
        z = np.full_like(v, 0.5) if hi == lo else (v - lo) / (hi - lo)
        return 1 - z if inv else z
    soil_pts = {tuple(m["seq"]): m["soil_points"]["value"] for m in res["_all"]}
    W = nrm([o["water"]["median"] for o in options], True)
    P = nrm([o["profit"]["median"] for o in options])
    R = nrm([o["profit"]["p10"] for o in options]) * 0.6 + nrm([o["loss_share"] for o in options], True) * 0.4
    S = nrm([soil_pts.get(tuple(o["seq"]), 0) for o in options])
    ws = sum(pri.values()) or 1
    for i, o in enumerate(options):
        o["score"] = round(float(100 * (pri["water"] * W[i] + pri["profit"] * P[i] + pri["risk"] * R[i] + pri["soil"] * S[i]) / ws), 1)
        o["is_current"] = tuple(o["seq"]) == existing and o["shift"] == 0 and o["strategy"] == "full"
    current = next(o for o in options if o["is_current"])
    eligible = [o for o in options if must <= set(o["seq"])] or options
    best = max(eligible, key=lambda o: o["score"])
    runner = max((o for o in options if tuple(o["seq"]) != tuple(best["seq"])), key=lambda o: o["score"], default=None)
    # detailed schedule for the chosen option (re-run once for slot-level numbers)
    got, (sim, eco) = _evaluate([tuple(best["seq"])], wx, plan, prices, ov, best["shift"], best["strategy"], max(need_summer, 1))
    start = _season_start()
    area = float(p.get("area_feddan") or 1)
    sched = []
    for j, crop, s, e in got[0]["cal"]:
        yf = eco["yield_frac"][0, :, j]
        yt = (ov.get(crop, {}).get("yield_t") or prices[crop]["yield_t"])
        wat = sim["irr_gross"][0, :, j] * MM_TO_M3_PER_FEDDAN
        prof = eco["profit"][0, :, j]
        sched.append(dict(
            year=j // 2 + 1, season=wb.SEASON_OF_SLOT[j], crop=crop,
            sow=str(start + timedelta(days=s)), harvest=str(start + timedelta(days=e)),
            water_m3_per_feddan=dict(p10=round(float(np.percentile(wat, 10))), median=round(float(np.median(wat))), p90=round(float(np.percentile(wat, 90)))),
            yield_t_per_feddan=dict(p10=round(float(np.percentile(yf * yt, 10)), 2), median=round(float(np.median(yf * yt)), 2), p90=round(float(np.percentile(yf * yt, 90)), 2)),
            profit_egp_per_feddan=dict(p10=round(float(np.percentile(prof, 10))), median=round(float(np.median(prof)))),
            salt_factor=round(econ.salinity_factor(crop, plan.salinity_ece), 2),
            source="computed: FAO-56 replay on 32 NASA POWER years; FAO-33 yield; quoted prices"))
    risks = []
    if plan.salinity_ece and plan.salinity_ece > 0:
        sens = [x["crop"] for x in sched if x["salt_factor"] < 0.9]
        AR = {"wheat": "القمح", "barley": "الشعير", "berseem": "البرسيم", "faba": "الفول", "sugarbeet": "البنجر", "potato": "البطاطس", "maize": "الدرة الشامية",
              "sorghum": "الدرة الرفيعة", "rice": "الرز", "cotton": "القطن", "tomato": "الطماطم", "soybean": "فول الصويا"}
        ss = sorted(set(sens))
        risks.append(dict(kind="salinity", text=f"Soil ECe {plan.salinity_ece:g} dS/m: yield cut for " + (", ".join(ss) or "none of the planned crops"),
                          text_ar=f"ملوحة التربة {plan.salinity_ece:g} دسي سيمنز/م: المحصول بيقلّ في " + ("، ".join(AR.get(c, c) for c in ss) or "ولا محصول في الخطة"),
                          source=econ.SALT_SOURCE))
    if irrigated:
        p_short = plan.canal_short_prob if plan.canal_short_prob is not None else A["canal_short_prob"]
        risks.append(dict(kind="canal", text=f"Summer canal shortfall in {round(100 * p_short)}% of years is included in the ranges",
                          text_ar=f"انقطاع مية الترعة في الصيف في {round(100 * p_short)}٪ من السنين محسوب في الأرقام", source="assumption:canal_short_prob"))
    if pulse_status and pulse_status.get("send_scout"):
        risks.append(dict(kind="field_pulse", text="Field Pulse: the latest satellite image is below what the weather explains; check the field before sowing",
                          text_ar="نبض الأرض: آخر صورة قمر صناعي أقل من اللي الجو يفسّره؛ اكشف على الأرض قبل الزراعة", source=pulse_status.get("source")))
    actions = ["Test soil salinity (EC) at the agricultural directorate lab before switching crops"] if not plan.salinity_ece else []
    actions += [f"Sow {sched[0]['crop']} around {sched[0]['sow']}", "Use the 16-day planner for the first irrigation date",
                "Record what you plant and harvest (it trains the next models)"]
    actions_ar = (["حلّل ملوحة التربة في معمل مديرية الزراعة قبل ما تغيّر المحاصيل"] if not plan.salinity_ece else []) + \
        [f"ازرع أول محصول حوالي {sched[0]['sow']}", "استخدم مخطط الـ١٦ يوم لميعاد أول رية", "سجّل اللي زرعته وحصدته (بيدرّب الموديلات الجاية)"]
    tot = lambda o, k: round(o[k]["median"] * area)
    return dict(
        profile=p, field_index=fi, pulse=pulse_status,
        chosen=dict(seq=best["seq"], shift_days=best["shift"], strategy=best["strategy"], score=best["score"],
                    profit=best["profit"], water=best["water"], loss_share=best["loss_share"]),
        current=dict(seq=current["seq"], profit=current["profit"], water=current["water"], loss_share=current["loss_share"], score=current["score"]),
        runner_up=dict(seq=runner["seq"], shift_days=runner["shift"], strategy=runner["strategy"], profit=runner["profit"], water=runner["water"], score=runner["score"]) if runner else None,
        delta=dict(profit_egp_per_feddan=round(best["profit"]["median"] - current["profit"]["median"]),
                   water_m3_per_feddan=round(best["water"]["median"] - current["water"]["median"])),
        farm_totals=dict(area_feddan=area, profit_egp_median=tot(best, "profit"), water_m3_median=tot(best, "water"),
                         profit_change_egp=round((best["profit"]["median"] - current["profit"]["median"]) * area),
                         water_change_m3=round((best["water"]["median"] - current["water"]["median"]) * area)),
        schedule=sched, risks=risks, actions=actions, actions_ar=actions_ar,
        options=[dict(seq=o["seq"], shift_days=o["shift"], strategy=o["strategy"], profit_median=round(o["profit"]["median"]),
                      profit_p10=round(o["profit"]["p10"]), water_median=round(o["water"]["median"]), score=o["score"],
                      is_current=o["is_current"], is_chosen=(o is best)) for o in options],
        searched=len(options), elapsed_s=round(time.time() - t0, 2),
        source="computed: replay of 32 climate-adjusted NASA POWER years × FAO-56 × price/canal Monte Carlo; field index from NASA MODIS (GIBS); Field Pulse model",
    )
