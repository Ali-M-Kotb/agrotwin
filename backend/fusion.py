"""Sky + Scout fusion: re-weight past years by how well they match the field's own readings.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

Each past window k, replayed through the water balance, predicts the root-zone relative
wetness h_k,t for the current crop on day t of this season. The Scout measures y_t.

    w_k ∝ exp(−½ Σ_t ((y_t − h_k,t) / σ)²)        ESS = 1 / Σ w_k²

σ = hypot(max(calibration error, sigma_floor), sigma_model): sensor error plus the error of
standing in for this season with a past one. Daily soil wetness is strongly autocorrelated,
so the sum is divided by τ, the decorrelation time (days) measured from the replay itself;
otherwise 90 daily readings would count as 90 independent facts (the twin experiment showed
coverage collapsing to ~15 % without this). If ESS < ess_min the likelihood is tempered
(raised to a power < 1) until it recovers, and the result is flagged.

Readings are first calibrated (raw → θ → relative wetness), filtered (spikes, duplicates,
within post_wetting_hours of rain or irrigation), then averaged per day so 5-second
telemetry does not count as thousands of independent observations.

Refuses to run without a calibration id, and on an irrigated field without the farmer's
irrigation dates (otherwise the model cannot know when the soil was refilled).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np

import waterbalance as wb
from config import A
from soil import relative_wetness


class FusionRefused(Exception):
    pass


def season_start(today: date | None = None) -> date:
    today = today or date.today()
    return date(today.year if today.month >= 10 else today.year - 1, 10, 1)


def _parse_t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def daily_observations(points: list[dict], calibration: dict, soil_class: str,
                       start: date, irrigation_dates: list[str] | None = None) -> dict:
    """Calibrate, filter and average readings per day → {day_offset: relative wetness}."""
    wet_flags = [_parse_t(p["t"]) for p in points if p.get("rain_flag")]
    wet_flags += [datetime.combine(date.fromisoformat(d), datetime.min.time(), timezone.utc)
                  for d in (irrigation_dates or [])]
    hold = timedelta(hours=A["post_wetting_hours"])
    seen, kept, dropped = set(), [], dict(duplicate=0, post_wetting=0, out_of_range=0, spike=0, before_season=0)
    for p in sorted(points, key=lambda p: p["t"]):
        t = _parse_t(p["t"])
        key = (p["t"], p.get("soil_raw"))
        if key in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(key)
        if any(timedelta(0) <= t - w < hold for w in wet_flags):
            dropped["post_wetting"] += 1
            continue
        raw = p.get("soil_raw")
        if raw is None:
            continue
        vwc = calibration["a"] * float(raw) + calibration["b"]
        if not (0.0 <= vwc <= 0.6):
            dropped["out_of_range"] += 1
            continue
        d = (t.date() - start).days
        if d < 0:
            dropped["before_season"] += 1
            continue
        kept.append((d, relative_wetness(vwc, soil_class)))
    # spike filter: drop readings far from their day's median
    by_day: dict = {}
    for d, s in kept:
        by_day.setdefault(d, []).append(s)
    obs = {}
    for d, xs in by_day.items():
        med = float(np.median(xs))
        good = [x for x in xs if abs(x - med) <= 0.25]
        dropped["spike"] += len(xs) - len(good)
        if good:
            obs[d] = float(np.mean(good))
    return dict(obs=obs, n_raw=len(points), n_valid=sum(len(v) for v in by_day.values()) - dropped["spike"],
                dropped=dropped)


def decorrelation_days(wet: np.ndarray, max_lag: int = 120) -> int:
    """Lag (days) where the mean autocorrelation of wetness anomalies drops below 1/e."""
    an = wet - wet.mean(0)
    for lag in range(1, min(max_lag, wet.shape[1] - 2)):
        cs = [np.corrcoef(a[:-lag], a[lag:])[0, 1] for a in an if a[:-lag].std() > 0 and a[lag:].std() > 0]
        if cs and np.mean(cs) < np.exp(-1):
            return lag
    return max_lag


def weights_from(obs: dict, wet: np.ndarray, sigma: float, tau: int = 1,
                 exclude: int | None = None) -> dict:
    """wet: (W, days) predicted relative wetness per window. Returns weights, ESS, tempering."""
    W = wet.shape[0]
    days = sorted(d for d in obs if d < wet.shape[1])
    base = np.ones(W)
    if exclude is not None:
        base[exclude] = 0
    if not days:
        w = base / base.sum()
        return dict(w=w, ess=float(1 / (w ** 2).sum()), sigma=sigma, temper=1.0, guard=False, n=0)
    y = np.array([obs[d] for d in days])
    sse = ((y[None, :] - wet[:, days]) ** 2).sum(1) / max(tau, 1)
    temper, guard = 1.0, False
    for _ in range(60):
        logw = -0.5 * sse / sigma ** 2 * temper
        if exclude is not None:
            logw[exclude] = -np.inf
        logw -= logw.max()
        w = np.exp(logw)
        w /= w.sum()
        ess = 1 / (w ** 2).sum()
        if ess >= A["ess_min"]:
            break
        temper *= 0.85
        guard = True
    return dict(w=w, ess=float(ess), sigma=float(sigma), temper=float(temper), guard=guard, n=len(days))


def confidence(n_points: int, guard: bool) -> str:
    lo, hi = A["confidence_bins"]
    if n_points < lo or guard:
        return "low"
    return "medium" if n_points <= hi else "high"


def predicted_wetness(rotation: tuple[str, ...], wx: dict, soil_class: str, irrigated: bool,
                      irrigation_dates: list[str] | None, start: date) -> np.ndarray:
    """(W, 365) relative wetness of the field's current rotation, year 1 of each window."""
    irr_days = None
    if irrigated:
        if not irrigation_dates:
            raise FusionRefused("irrigated_needs_log")
        irr_days = np.zeros(365, dtype=bool)
        for d in irrigation_dates:
            k = (date.fromisoformat(d) - start).days
            if 0 <= k < 365:
                irr_days[k] = True
    sim = wb.simulate([rotation], wx, soil_class, irrigated, None, irrigation_days=irr_days,
                      keep_wetness_days=365)
    return sim["wet"][0]


def fuse(runs: list[dict], calibration: dict | None, rotation, wx, soil_class, irrigated,
         irrigation_dates=None, today: date | None = None, sigma_model: float | None = None) -> dict:
    if not runs:
        return dict(used=False, reason="no_runs")
    if not calibration:
        raise FusionRefused("no_calibration")
    # SIMULATED / REPLAY runs carry the season they belong to; live runs use this season.
    start = date.fromisoformat(runs[0]["season_start"]) if runs[0].get("season_start") else season_start(today)
    points = [p for r in runs for p in r["points"]]
    od = daily_observations(points, calibration, soil_class, start, irrigation_dates)
    wet = predicted_wetness(rotation, wx, soil_class, irrigated, irrigation_dates, start)
    sensor = max(float(calibration.get("rmse_rel", 0.0)), A["sigma_floor"])
    sigma_model = A["sigma_model"] if sigma_model is None else sigma_model
    sigma = float(np.hypot(sensor, sigma_model))
    tau = decorrelation_days(wet)
    fw = weights_from(od["obs"], wet, sigma, tau)
    days = sorted(od["obs"])
    return dict(
        used=fw["n"] > 0, scout_run_ids=[r["run_id"] for r in runs],
        modes=sorted({r["mode"] for r in runs}),
        n_points=fw["n"], n_raw=od["n_raw"], dropped=od["dropped"],
        weights=fw["w"], ess=fw["ess"], sigma_used=fw["sigma"], sigma_sensor=sensor,
        sigma_model=sigma_model, tau_days=tau, temper=fw["temper"], guard=fw["guard"],
        confidence_label=confidence(fw["n"], fw["guard"]),
        calibration_id=calibration["id"],
        trace=dict(days=days, observed=[od["obs"][d] for d in days],
                   predicted_p10=np.percentile(wet[:, days], 10, axis=0).tolist() if days else [],
                   predicted_p90=np.percentile(wet[:, days], 90, axis=0).tolist() if days else [],
                   start=str(start)),
    )


# ---------------------------------------------------------------------------
# Twin experiment (plan section 5.4): is the narrowed range honest?
# ---------------------------------------------------------------------------

def twin_experiment(wet: np.ndarray, outcome: np.ndarray, reading_days: list[int],
                    sigma_sensor: float = 0.05, sigma_model: float | None = None,
                    reps: int = 3) -> dict:
    """Each window in turn is the hidden truth; synthetic readings = its wetness + sensor noise.

    outcome: (W,) the quantity whose range we report (e.g. this season's profit).
    Reports coverage of the weighted 10–90 % range (target ~80 %), its width relative to the
    unweighted range, the unweighted coverage as a baseline, and the ESS spread.
    """
    from econ import wquantile
    sigma_model = A["sigma_model"] if sigma_model is None else sigma_model
    sigma = float(np.hypot(sigma_sensor, sigma_model))
    tau = decorrelation_days(wet)
    W = wet.shape[0]
    covered, base_cov, ratios, esss = [], [], [], []
    for seed in range(reps):
        rng = np.random.default_rng(seed)
        for k in range(W):
            obs = {d: float(np.clip(wet[k, d] + rng.normal(0, sigma_sensor), 0, 1)) for d in reading_days}
            fw = weights_from(obs, wet, sigma, tau, exclude=k)
            others = np.delete(np.arange(W), k)
            lo, hi = wquantile(outcome[others], [0.1, 0.9], fw["w"][others])
            ulo, uhi = np.quantile(outcome[others], [0.1, 0.9])
            covered.append(lo <= outcome[k] <= hi)
            base_cov.append(ulo <= outcome[k] <= uhi)
            ratios.append((hi - lo) / max(uhi - ulo, 1e-9))
            esss.append(fw["ess"])
    cov = float(np.mean(covered))
    return dict(n_windows=W, n_reading_days=len(reading_days), reps=reps,
                sigma_sensor=sigma_sensor, sigma_model=sigma_model, tau_days=tau,
                coverage=cov, coverage_unweighted=float(np.mean(base_cov)),
                width_ratio_mean=float(np.mean(ratios)),
                ess_p10=float(np.percentile(esss, 10)), ess_median=float(np.median(esss)),
                ess_p90=float(np.percentile(esss, 90)),
                target_band=list(A["coverage_band"]),
                in_band=bool(A["coverage_band"][0] <= cov <= A["coverage_band"][1]))


def calibrate_sigma_model(wet: np.ndarray, outcome: np.ndarray, horizons=(30, 90, 135, 180),
                          grid=(0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.45), slack: float = 0.05) -> dict:
    """Pick the smallest model-error σ whose leave-one-out twin-experiment coverage (each hidden
    year never votes for itself) stays within `slack` of the unweighted range's own coverage,
    with a floor of 0.70. One scalar chosen from a 7-value grid; disclosed as in-sample."""
    from econ import wquantile
    W = wet.shape[0]
    allk = np.arange(W)
    tau = decorrelation_days(wet)

    def cov(sig, subset):
        hits, base = [], []
        for H in horizons:
            days = list(range(min(H, wet.shape[1])))
            for seed in range(2):
                rng = np.random.default_rng(seed)
                for k in subset:
                    obs = {d: float(np.clip(wet[k, d] + rng.normal(0, 0.05), 0, 1)) for d in days}
                    fw = weights_from(obs, wet, float(np.hypot(0.05, sig)), tau, exclude=k)
                    o = np.delete(np.arange(W), k)
                    lo, hi = wquantile(outcome[o], [0.1, 0.9], fw["w"][o])
                    ulo, uhi = np.quantile(outcome[o], [0.1, 0.9])
                    hits.append(lo <= outcome[k] <= hi)
                    base.append(ulo <= outcome[k] <= uhi)
        return float(np.mean(hits)), float(np.mean(base))
    chosen, fit, target = grid[-1], None, None
    base = None
    for sig in grid:
        c, b = cov(sig, allk)
        base, target = b, max(0.70, b - slack)
        if c >= target:
            chosen, fit = sig, c
            break
    return dict(sigma_model=chosen, coverage=fit, unweighted_coverage=base, target=target,
                horizons=list(horizons), grid=list(grid),
                source="computed:leave-one-out twin-experiment calibration (in-sample choice of one scalar)")
