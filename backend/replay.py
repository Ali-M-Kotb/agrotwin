"""Replay engine: candidate search, full replay, ranking.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

1. Quick pass  every crop alone through every window → median water, profit, loss share.
2. Beam search over 3 years × (winter, summer) slots using the quick numbers, the farmer's
               weights and the soil rules → ~40 promising, calendar-feasible rotations.
3. Full replay those + the farmer's existing rotation through the daily water balance.
4. Score       min-max normalise water, soil, profit, risk across that pool (direction-aware),
               weighted sum with the farmer's sliders.
5. Show        the existing rotation + the 2 best distinct alternatives, ranked; tie band;
               hard-constraint exclusions with reasons.
Optional fusion weights (one per window) turn every range into a weighted range.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

import econ
import waterbalance as wb
from config import A
from crops import CROPS, FALLOW, MM_TO_M3_PER_FEDDAN, family

BEAM = 120
POOL = 40


@dataclass
class Plan:
    existing: tuple[str, str] = ("wheat", "rice")          # (winter, summer) repeated 3 years
    candidates: list[str] = field(default_factory=lambda: list(CROPS))
    weights: dict = field(default_factory=lambda: dict(water=1.0, soil=1.0, profit=1.0, risk=1.0))
    irrigated: bool = True
    water_cap_m3: dict | None = None                       # {"winter": m3/fed, "summer": m3/fed}
    rain_mult: float = 1.0
    temp_offset: float = 0.0
    price_mult: float = 1.0
    price_overrides: dict = field(default_factory=dict)
    disease_families: dict = field(default_factory=dict)  # family -> label (from Scout sightings)
    soil_class: str = "clay_loam"
    salinity_ece: float = 0.0                            # dS/m (FAO-29)
    canal_short_prob: float | None = None                 # None = assumption:canal_short_prob


def effective_overrides(plan: Plan) -> dict:
    from crops import RAINFED_COSTS
    ov = {}
    if not plan.irrigated:
        ov = {c: {"cost": v} for c, v in RAINFED_COSTS.items()}
    for c, d in (plan.price_overrides or {}).items():
        ov.setdefault(c, {}).update(d)
    return ov


def existing_rotation(plan: Plan) -> tuple[str, ...]:
    w, s = plan.existing
    return (w or FALLOW, s or FALLOW) * wb.YEARS


def _pools(plan: Plan):
    ok = lambda c: c in CROPS and (plan.irrigated or CROPS[c]["rainfed_ok"])
    winter = [c for c in plan.candidates if ok(c) and CROPS[c]["season"] == "winter"] + [FALLOW]
    summer = [c for c in plan.candidates if ok(c) and CROPS[c]["season"] == "summer"] + [FALLOW]
    return winter, summer


# ---------------------------------------------------------------------------
# soil rules (transparent points, listed in the UI)
# ---------------------------------------------------------------------------

def soil_rules(rot: tuple[str, ...], plan: Plan, clay: float = 35) -> tuple[float, list[dict]]:
    score, why = 50.0, []
    crops = [c for c in rot if c != FALLOW]
    # history: the existing rotation's last two seasons precede this plan
    hist = [c for c in reversed(existing_rotation(plan)[-2:]) if c != FALLOW]
    chain = list(reversed(hist)) + list(rot)
    off = len(chain) - len(rot)
    for i in range(off, len(chain)):
        if chain[i] == FALLOW:
            continue
        fam = family(chain[i])
        prev = [k for k in range(i - 1, -1, -1) if chain[k] != FALLOW]
        if prev and family(chain[prev[0]]) == fam:
            score -= 12
            why.append(dict(kind="repeat", crop=chain[i], prev=chain[prev[0]], family=fam, pts=-12))
        elif len(prev) > 1 and family(chain[prev[1]]) == fam:
            score -= 5
            why.append(dict(kind="repeat2", crop=chain[i], prev=chain[prev[1]], family=fam, pts=-5))
    seen = set()
    for i, c in enumerate(rot):
        if c == FALLOW:
            continue
        if CROPS[c]["n_credit"][1] > 0:
            pts = 10 if c not in seen else 5
            score += pts
            if c not in seen:
                why.append(dict(kind="legume", crop=c, n=list(CROPS[c]["n_credit"]), pts=pts))
            seen.add(c)
        fam = family(c)
        if fam in plan.disease_families:
            pts = -30 if i < 2 else -20
            score += pts
            why.append(dict(kind="disease_host", crop=c, family=fam, disease=plan.disease_families[fam], pts=pts))
    for fam, dis in plan.disease_families.items():
        if not any(family(c) == fam for c in rot[:4]):
            score += 8
            why.append(dict(kind="disease_break", family=fam, disease=dis, pts=8))
    fams = {family(c) for c in crops}
    if len(fams) >= 3:
        score += 8
        why.append(dict(kind="diverse", n=len(fams), pts=8))
    if crops:
        score += (np.mean([CROPS[c]["residue"] for c in crops]) - 4) * 2
    if "potato" in crops and clay > 45:
        score -= 6
        why.append(dict(kind="heavy_clay", crop="potato", clay=clay, pts=-6))
    return float(np.clip(score, 0, 100)), why


# ---------------------------------------------------------------------------
# metrics for a simulated pool
# ---------------------------------------------------------------------------

def _metrics(sim, eco, r: int, plan: Plan, clay: float, weights: np.ndarray | None) -> dict:
    years = sim["years"]
    rot = sim["rotations"][r]
    water_yr = sim["irr_gross"][r].sum(1) * MM_TO_M3_PER_FEDDAN / wb.YEARS        # m3/fed/yr per window
    profit_yr = eco["profit"][r].sum(1) / wb.YEARS
    p_short = plan.canal_short_prob if plan.canal_short_prob is not None else A["canal_short_prob"]
    mc = econ.mc_profit_year(sim, eco, r, plan.irrigated, p_short)            # (windows, draws)
    cost_yr = eco["cost"][r].sum(1) / wb.YEARS
    season1 = eco["profit"][r, :, :2].sum(1)                                      # this coming year
    deficit = sim["deficit_days"][r].sum(1)
    bare = sim["bare_days"][r]
    erosion = sim["erosion"][r]
    heat_any = (sim["heat_days"][r] >= A["heat_stress_days"]).any(1)
    # Scout readings describe THIS season only, so fusion weights narrow this season's range;
    # the 3-year ranges stay on history alone (twin experiment: re-weighting them was overconfident).
    q = lambda x: [float(v) for v in econ.wquantile(x, [0.1, 0.5, 0.9], None)]
    qw = lambda x: [float(v) for v in econ.wquantile(x, [0.1, 0.5, 0.9], weights)]
    bc = econ.barcode(profit_yr, cost_yr, years)
    w = np.full(len(years), 1 / len(years))
    red = np.array([b["cls"] == "red" for b in bc])
    loss_mc = float((mc < 0).mean())
    worst = int(np.argmin(profit_yr))
    soil_pts, soil_why = soil_rules(rot, plan, clay)
    soil_why = [dict(w, source="computed:soil rules (points listed in METHODS.md)") for w in soil_why]
    n_lo = sum(CROPS[c]["n_credit"][0] for c in rot if c != FALLOW)
    n_hi = sum(CROPS[c]["n_credit"][1] for c in rot if c != FALLOW)
    slots = []
    for j, crop in enumerate(rot):
        s = dict(slot=j, year=j // 2 + 1, season=wb.SEASON_OF_SLOT[j], crop=crop,
                 source="computed: median over replay windows; sow date assumption:planting_windows")
        if crop != FALLOW:
            s.update(sow=list(CROPS[crop]["sow"]), days=int(sum(CROPS[crop]["stages"])),
                     water_m3=float(np.median(sim["irr_gross"][r, :, j]) * MM_TO_M3_PER_FEDDAN),
                     yield_frac=float(np.median(eco["yield_frac"][r, :, j])),
                     heat_years=int((sim["heat_days"][r, :, j] >= A["heat_stress_days"]).sum()))
        slots.append(s)
    return dict(
        seq=list(rot), slots=slots, years=[int(y) for y in years],
        water_m3=dict(p10=q(water_yr)[0], median=q(water_yr)[1], p90=q(water_yr)[2], unit="m3/feddan/yr", source="computed"),
        profit=dict(p10=q(mc.ravel())[0], median=q(mc.ravel())[1], p90=q(mc.ravel())[2], unit="EGP/feddan/yr",
                    source="computed: replayed weather × price variability × summer canal shortfalls (assumption:price_cv, canal_short_prob)"),
        profit_weather_only=dict(p10=q(profit_yr)[0], median=q(profit_yr)[1], p90=q(profit_yr)[2], unit="EGP/feddan/yr", source="computed"),
        loss_share_with_shocks=dict(value=loss_mc, source="computed"),
        season1_profit=dict(p10=qw(season1)[0], median=qw(season1)[1], p90=qw(season1)[2], unit="EGP/feddan",
                            source="computed" + (":weighted by Scout readings" if weights is not None else "")),
        season1_profit_unweighted=dict(p10=q(season1)[0], median=q(season1)[1], p90=q(season1)[2], unit="EGP/feddan",
                                       source="computed"),
        deficit_days=dict(median=float(np.median(deficit)), source="computed"),
        bare_days=dict(median=float(np.median(bare)), source="computed"),
        erosion_index=dict(median=float(np.median(erosion)), unit="mm heavy rain on bare soil / 3 yr", source="computed"),
        n_credit_kg_fed=dict(low=n_lo, high=n_hi, source="assumption:legume_n_credit"),
        heat_stress_share=dict(value=float((w * heat_any).sum()), source="computed"),
        loss_year_share=dict(value=float((w * red).sum()), source="computed"),
        worst_year=dict(year=int(years[worst]), profit=float(profit_yr[worst]), source="computed"),
        barcode=bc,
        soil_points=dict(value=soil_pts, source="computed"), soil_why=soil_why,
        _profit_yr=profit_yr, _water_yr=water_yr, _season1=season1,
    )


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------

def _quick(wx, plan: Plan, prices, cap_net):
    singles = []
    for c in plan.candidates:
        if c not in CROPS:
            continue
        rot = [FALLOW] * wb.SLOTS
        rot[0 if CROPS[c]["season"] == "winter" else 1] = c
        singles.append(tuple(rot))
    sim = wb.simulate(singles, wx, plan.soil_class, plan.irrigated, cap_net)
    eco = econ.slot_economics(sim, prices, plan.price_mult, effective_overrides(plan), plan.salinity_ece)
    out = {}
    for r, rot in enumerate(singles):
        j = 0 if rot[0] != FALLOW else 1
        p = eco["profit"][r, :, j]
        out[rot[j]] = dict(water=float(np.median(sim["irr_gross"][r, :, j])), profit=float(np.median(p)),
                           p10=float(np.percentile(p, 10)))
    return out


def _beam(plan: Plan, quick: dict, clay: float) -> list[tuple[str, ...]]:
    winter, summer = _pools(plan)
    w = plan.weights
    vals = {c: v for c, v in quick.items()}
    def norm(key, c, invert=False):
        xs = [v[key] for v in vals.values()]
        lo, hi = min(xs), max(xs)
        if c == FALLOW:
            x = 0.0 if key != "water" else 0.0
        else:
            x = vals[c][key]
        v = 0.5 if hi == lo else (x - lo) / (hi - lo)
        return 1 - v if invert else v
    def crop_value(c):
        if c == FALLOW:
            return 0.15 * w.get("water", 1) - 0.25 * w.get("profit", 1)
        return (w.get("water", 1) * norm("water", c, True) + w.get("profit", 1) * norm("profit", c)
                + w.get("risk", 1) * norm("p10", c))
    pairs = [(a, b) for a, b in itertools.product(winter, summer)]
    beam = [((), 0.0)]
    for _year in range(wb.YEARS):
        nxt = []
        for seq, _ in beam:
            for a, b in pairs:
                s = seq + (a, b)
                padded = s + (FALLOW,) * (wb.SLOTS - len(s))
                if wb.calendar(padded) is None:
                    continue
                v = sum(crop_value(c) for c in s) + w.get("soil", 1) * soil_rules(padded, plan, clay)[0] / 25
                nxt.append((s, v))
        nxt.sort(key=lambda x: -x[1])
        beam = nxt[:BEAM]
    out, seen = [], set()
    for s, _ in beam:
        k = frozenset(c for c in s if c != FALLOW)
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= POOL:
            break
    return out


def run(weather_wx: dict, plan: Plan, prices: dict, clay: float = 35,
        fusion_weights: np.ndarray | None = None) -> dict:
    cap_net = None
    if plan.irrigated and plan.water_cap_m3:
        cap_net = {k: v / MM_TO_M3_PER_FEDDAN * A["irrigation_efficiency"] for k, v in plan.water_cap_m3.items()}
    existing = existing_rotation(plan)
    if wb.calendar(existing) is None:
        raise ValueError("The current rotation does not fit the planting calendar "
                         f"({existing[0]} then {existing[1]}): the first crop is harvested after the second is sown.")
    quick = _quick(weather_wx, plan, prices, cap_net)
    pool = _beam(plan, quick, clay)
    rots = [existing] + [r for r in pool if r != existing]
    sim = wb.simulate(rots, weather_wx, plan.soil_class, plan.irrigated, cap_net)
    eco = econ.slot_economics(sim, prices, plan.price_mult, effective_overrides(plan), plan.salinity_ece)
    unmet = np.zeros(len(rots))
    if cap_net:
        free = wb.simulate(rots, weather_wx, plan.soil_class, plan.irrigated, None)
        need = free["irr_net"].sum((1, 2))
        unmet = 1 - np.median(sim["irr_net"].sum(2), axis=1) / np.maximum(np.median(free["irr_net"].sum(2), axis=1), 1)
    ms = [_metrics(sim, eco, r, plan, clay, fusion_weights) for r in range(len(rots))]

    # normalise across the pool, direction-aware
    def nrm(vals, invert=False):
        vals = np.asarray(vals, dtype=float)
        lo, hi = vals.min(), vals.max()
        v = np.full_like(vals, 0.5) if hi == lo else (vals - lo) / (hi - lo)
        return 1 - v if invert else v
    water = nrm([m["water_m3"]["median"] for m in ms], invert=True)
    soilv = nrm([m["soil_points"]["value"] - m["erosion_index"]["median"] / 5 for m in ms])
    profit = nrm([m["profit"]["median"] for m in ms])
    risk = nrm([0.5 * m["profit"]["p10"] for m in ms]) * 0.5 + nrm([m["loss_year_share"]["value"] for m in ms], True) * 0.5
    wts = {k: max(0.0, float(plan.weights.get(k, 0))) for k in ("water", "soil", "profit", "risk")}
    wsum = sum(wts.values()) or 1.0
    for i, m in enumerate(ms):
        m["scores"] = dict(water=round(float(100 * water[i]), 1), soil=round(float(100 * soilv[i]), 1),
                           profit=round(float(100 * profit[i]), 1), risk=round(float(100 * risk[i]), 1))
        m["total"] = round(float(sum(wts[k] * m["scores"][k] for k in wts) / wsum), 1)
        m["unmet_share"] = float(unmet[i])
        reasons = []
        if cap_net and unmet[i] > A["cap_exclusion_share"]:
            reasons.append(dict(kind="water_cap", unmet=float(unmet[i])))
        m["excluded"] = dict(is_excluded=bool(reasons) and i != 0, reasons=reasons)

    # existing + the two best distinct alternatives
    alts, seen = [], {frozenset(c for c in existing if c != FALLOW)}
    for i in sorted(range(1, len(ms)), key=lambda i: -ms[i]["total"]):
        if ms[i]["excluded"]["is_excluded"]:
            continue
        k = frozenset(c for c in ms[i]["seq"] if c != FALLOW)
        if k in seen:
            continue
        seen.add(k)
        alts.append(i)
        if len(alts) == 2:
            break
    three = [0] + alts
    ids = ["existing", "alt_1", "alt_2"]
    shown = []
    for rid, i in zip(ids, three):
        m = dict(ms[i])
        m["rotation_id"] = rid
        strengths = {k: m["scores"][k] for k in ("water", "soil", "profit", "risk")}
        m["strength"] = max(strengths, key=strengths.get)
        shown.append(m)
    order = sorted(shown, key=lambda m: -m["total"])
    span = max(m["total"] for m in ms) - min(m["total"] for m in ms) or 1
    tie = len(order) > 1 and (order[0]["total"] - order[1]["total"]) < A["tie_band"] * span
    for m in shown:
        m["rank"] = order.index(m) + 1
    return dict(rotations=shown, order=[m["rotation_id"] for m in order], no_clear_winner=bool(tie),
                pool_size=len(ms), years=[int(y) for y in sim["years"]],
                _all=ms, _sim=sim, _eco=eco, _index=three)
