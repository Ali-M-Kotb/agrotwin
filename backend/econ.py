"""Yield, profit and the Harvest Barcode.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

Yield (FAO-33):   1 − Ya/Ym = Ky (1 − ETa/ETc), then a heat loss per day above the crop's
                  Tmax limit in its sensitive window (assumption:heat_loss_per_day, capped).
Profit per slot:  Ya · P · price_mult − cost − water_cost · gross m³ + N credit · P_N
                  (the N credit is earned by the crop that follows a legume).
Barcode stripe:   one per replay window: red if profit < 0, amber if 0 … amber_margin × cost,
                  green otherwise.
Prices and costs come from data/prices.csv when a row is there (quoted rows carry their URL),
else from the crops.py placeholders tagged assumption:prices_default.
"""
from __future__ import annotations

import csv
import zlib
from pathlib import Path

import numpy as np

from config import A
from crops import CROPS, FALLOW, MM_TO_M3_PER_FEDDAN, N_PRICE_EGP_KG
from waterbalance import SLOTS

PRICES_CSV = Path(__file__).resolve().parent.parent / "data" / "prices.csv"


def load_prices() -> dict:
    """crop -> {price, yield_t, cost, src:{price, yield_t, cost}}; plus 'nitrogen'."""
    out = {c: dict(price=v["price"], yield_t=v["yield_t"], cost=v["cost"],
                   src=dict(price="assumption:prices_default", yield_t="assumption:prices_default",
                            cost="assumption:prices_default"))
           for c, v in CROPS.items()}
    out["nitrogen"] = dict(price=N_PRICE_EGP_KG, src=dict(price="assumption:prices_default"))
    if not PRICES_CSV.exists():
        return out
    costs: dict = {}
    with open(PRICES_CSV, newline="") as f:
        for row in csv.DictReader(f):
            crop, item = (row.get("crop") or "").strip(), (row.get("item") or "").strip()
            try:
                val = float(row.get("value") or "")
            except ValueError:
                continue
            tag = (row.get("tag") or "").strip()
            src = f"quoted:{row['source_url'].strip()}" if tag == "quoted" and row.get("source_url") \
                else f"assumption:prices_csv_{crop}_{item}"
            if crop == "nitrogen" and item == "n_price":
                out["nitrogen"] = dict(price=val, src=dict(price=src))
            elif crop in out:
                if item == "farmgate_price":
                    out[crop]["price"], out[crop]["src"]["price"] = val, src
                elif item == "yield":
                    out[crop]["yield_t"], out[crop]["src"]["yield_t"] = val, src
                elif item.endswith("_cost"):
                    costs.setdefault(crop, []).append((val, src))
    for crop, items in costs.items():
        out[crop]["cost"] = sum(v for v, _ in items)
        srcs = {s for _, s in items}
        out[crop]["src"]["cost"] = srcs.pop() if len(srcs) == 1 else "computed:sum of prices.csv cost rows"
    return out


def slot_economics(sim: dict, prices: dict, price_mult: float = 1.0, overrides: dict | None = None, ece: float = 0.0) -> dict:
    """Per (rotation, window, slot): yield fraction, revenue, cost, profit (EGP / feddan)."""
    R, W = sim["etc"].shape[:2]
    yf = np.zeros((R, W, SLOTS))
    rev = np.zeros((R, W, SLOTS))
    cost = np.zeros((R, W, SLOTS))
    ncredit = np.zeros((R, W, SLOTS))
    n_price = prices["nitrogen"]["price"]
    wc = A["water_cost_egp_m3"]
    for r, rot in enumerate(sim["rotations"]):
        prev_legume = None
        for j, crop in enumerate(rot):
            if crop == FALLOW:
                continue
            c = CROPS[crop]
            pr = {**prices[crop], **(overrides or {}).get(crop, {})}
            etc = np.maximum(sim["etc"][r, :, j], 1e-6)
            ratio = np.clip(sim["eta"][r, :, j] / etc, 0, 1)
            heat = np.minimum(A["heat_loss_max"], A["heat_loss_per_day"] * sim["heat_days"][r, :, j])
            f = np.clip(1 - c["ky"] * (1 - ratio), 0, 1) * (1 - heat) * salinity_factor(crop, ece)
            yf[r, :, j] = f
            rev[r, :, j] = pr["yield_t"] * f * pr["price"] * price_mult
            cost[r, :, j] = pr["cost"] + wc * sim["irr_gross"][r, :, j] * MM_TO_M3_PER_FEDDAN
            if prev_legume:
                lo, hi = CROPS[prev_legume]["n_credit"]
                ncredit[r, :, j] = (lo + hi) / 2 * n_price
            prev_legume = crop if CROPS[crop]["n_credit"][1] > 0 else None
    profit = rev - cost + ncredit
    return dict(yield_frac=yf, revenue=rev, cost=cost, ncredit=ncredit, profit=profit)


# FAO-29 (Ayers & Westcot, 1985, Table 4; after Maas & Hoffman, 1977): yield falls by b % per dS/m of soil
# salinity ECe above the threshold a (dS/m).  Yr = 100 − b (ECe − a).
SALT_TOLERANCE = {
    "wheat": (6.0, 7.1), "barley": (8.0, 5.0), "berseem": (1.5, 5.7), "faba": (1.6, 9.6), "sugarbeet": (7.0, 5.9),
    "potato": (1.7, 12.0), "maize": (1.7, 12.0), "sorghum": (6.8, 16.0), "rice": (3.0, 12.0), "cotton": (7.7, 5.2),
    "tomato": (2.5, 9.9), "soybean": (5.0, 20.0),
}
SALT_SOURCE = "FAO-29 (Ayers & Westcot 1985) Table 4, Maas–Hoffman salt tolerance"


def salinity_factor(crop: str, ece: float) -> float:
    if not ece or crop not in SALT_TOLERANCE:
        return 1.0
    a, b = SALT_TOLERANCE[crop]
    return float(min(1.0, max(0.0, 1 - b / 100 * max(0.0, ece - a))))


def _price_draws(crop: str, k: int, seed: int = 7) -> np.ndarray:
    cv = A["price_cv"].get(crop, A["price_cv"]["default"])
    rng = np.random.default_rng(zlib.crc32(f"price|{crop}|{seed}".encode()))
    s = np.sqrt(np.log(1 + cv ** 2))
    return rng.lognormal(-s * s / 2, s, k)          # mean 1


def mc_profit_year(sim: dict, eco: dict, r: int, irrigated: bool, p_short: float | None = None,
                   supply: float | None = None, draws: int | None = None, seed: int = 11) -> np.ndarray:
    """Profit per (window, draw), EGP / feddan / yr: replayed weather × price variability × summer canal shortfalls.
    A short summer delivers only `supply` of the irrigation need; the unmet water comes off ETa and yield follows FAO-33."""
    from waterbalance import SEASON_OF_SLOT, YEARS
    k = int(draws or A["mc_draws"])
    p_short = A["canal_short_prob"] if p_short is None else p_short
    supply = A["canal_short_supply"] if supply is None else supply
    W = sim["etc"].shape[1]
    rng = np.random.default_rng(seed)
    short = rng.random((W, k, YEARS)) < p_short                    # same draws for every rotation (fair comparison)
    total = np.zeros((W, k))
    for j, crop in enumerate(sim["rotations"][r]):
        if crop == FALLOW:
            continue
        c = CROPS[crop]
        rev = eco["revenue"][r, :, j][:, None] * _price_draws(crop, k)[None, :]
        if irrigated and SEASON_OF_SLOT[j] == "summer" and p_short > 0:
            etc = np.maximum(sim["etc"][r, :, j], 1e-6)
            eta = sim["eta"][r, :, j]
            d_et = (1 - supply) * sim["irr_net"][r, :, j]
            f0 = np.clip(1 - c["ky"] * (1 - np.clip(eta / etc, 0, 1)), 1e-6, 1)
            f1 = np.clip(1 - c["ky"] * (1 - np.clip((eta - d_et) / etc, 0, 1)), 0, 1)
            cut = (f1 / f0)[:, None]
            rev = np.where(short[:, :, j // 2], rev * cut, rev)
        total += rev - eco["cost"][r, :, j][:, None] + eco["ncredit"][r, :, j][:, None]
    return total / YEARS


def barcode(window_profit: np.ndarray, window_cost: np.ndarray, years: list[int]) -> list[dict]:
    """window_profit / cost: (W,) EGP per feddan per year averaged over the window."""
    out = []
    for y, p, c in zip(years, window_profit, window_cost):
        cls = "red" if p < 0 else ("amber" if p < A["amber_margin"] * c else "green")
        out.append(dict(year=int(y), profit=float(round(p)), cls=cls, source="computed"))
    return out


def wquantile(x: np.ndarray, q, w: np.ndarray | None = None):
    """Weighted quantiles (w None = equal weights)."""
    x = np.asarray(x, dtype=float)
    if w is None:
        return np.quantile(x, q)
    o = np.argsort(x)
    xs, ws = x[o], np.asarray(w, dtype=float)[o]
    cw = np.cumsum(ws) - 0.5 * ws
    cw /= ws.sum()
    return np.interp(q, cw, xs)
