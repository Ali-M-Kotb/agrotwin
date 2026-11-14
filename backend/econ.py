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


def slot_economics(sim: dict, prices: dict, price_mult: float = 1.0, overrides: dict | None = None) -> dict:
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
            f = np.clip(1 - c["ky"] * (1 - ratio), 0, 1) * (1 - heat)
            yf[r, :, j] = f
            rev[r, :, j] = pr["yield_t"] * f * pr["price"] * price_mult
            cost[r, :, j] = pr["cost"] + wc * sim["irr_gross"][r, :, j] * MM_TO_M3_PER_FEDDAN
            if prev_legume:
                lo, hi = CROPS[prev_legume]["n_credit"]
                ncredit[r, :, j] = (lo + hi) / 2 * n_price
            prev_legume = crop if CROPS[crop]["n_credit"][1] > 0 else None
    profit = rev - cost + ncredit
    return dict(yield_frac=yf, revenue=rev, cost=cost, ncredit=ncredit, profit=profit)


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
