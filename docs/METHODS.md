# Methods (one page)

_AI-generated (Claude, Anthropic) under human review. Numbers quoted here come from qa/REPORT.md of 14 Nov 2026._

**Data in.** NASA POWER daily point data, 1981 → 3 days ago (T2M, T2M_MAX, T2M_MIN, RH2M, PRECTOTCORR,
ALLSKY_SFC_SW_DWN, WS2M, PS, GWETROOT). MODIS MOD13Q1 NDVI and MOD16A2GF ET via the ORNL DAAC web service.
SoilGrids 2.0 texture → five FAO-56 soil classes. Prices from data/prices.csv (19 quoted, 21 assumption rows). Map layers: NASA GIBS WMTS (MODIS NDVI, SMAP L4
root-zone soil moisture, GPM IMERG, MODIS LST and true colour), display only.

**Reference ET.** FAO-56 Penman-Monteith from POWER; Hargreaves before 1984 (no radiation).

**Water balance (daily, FAO-56 ch. 8).** TAW = 1000(θFC − θWP)Zr, RAW = p·TAW with p = p_table + 0.04(5 − ETc);
Ks = 1 if Dr ≤ RAW, else (TAW − Dr)/((1 − p)TAW); ETa = Ks·Kc·ET0; Dr,i = Dr,i−1 − (P − RO) − I + ETa + DP.
Runoff is the NRCS curve-number method (S = 25400/CN − 254, Ia = 0.2S) with CN by soil class and by cover
(cropped vs bare; USDA TR-55 Table 2-2b), adopted from Yaseen Abdelal's AgroTwin engine. Crop coefficients follow
FAO-56 Table 12 as verified in that repository (wheat initial 0.70 for non-frozen soil; berseem 0.40/0.90/0.85).
Severe-deficit days (Ks = 0, root zone at wilting point) are reported separately from stress days (Ks < 1).
Roots grow linearly to the crop maximum by the end of development. Bare and fallow soil evaporates from a 0.3 m layer
with no transpiration. Irrigated fields refill to field capacity at sowing and whenever Dr > RAW, until the
seasonal cap. Flooded rice adds forced percolation (3 mm/day) and puddling (150 mm). Mass balance closes to
<1e-11 mm (tested).

**Climate-adjusted replay.** Before replay, each past year is warmed to this season's climate by the site's own
measured Tmax trend (all three temperatures shifted, ET0 recomputed). Adopted because it wins the backtest
(qa/BACKTEST.md): over the last three seasons it cut irrigation CRPS from 322 to 228 m³/feddan and raised profit
coverage from 70 % to 78 %; the plain replay already beats "same as last year" by ~50 %.

**Replay.** A rotation is 6 slots (winter/summer × 3 years). Window *y* runs the real weather of y, y+1, y+2
after a 120-day bare-soil spin-up: 32 windows, 1991–2024. All rotations × all windows run in one vectorised
loop (~0.06 s).

**Yield and money (FAO-33).** 1 − Ya/Ym = Ky(1 − ETa/ETc), times a heat loss of 5% per day above the crop's
Tmax limit in its sensitive window (cap 35%). Profit = Ya·P − cost − water cost + N credit·P_N (a legume's credit
goes to the next crop). Barcode stripe per window: red < 0, amber < 10% of cost, green otherwise.

**Search and ranking.** A beam search over the 6 slots (calendar-feasible only) picks about 40 candidates. Each
is fully replayed, and four metrics are min-max normalised across the pool: water (median m³/feddan/yr, lower
better), soil (transparent points: family repeats −12/−5, legumes +10, ≥3 families +8, residue, disease host
−30/−20, break +8, minus erosion), profit (median), risk (p10 profit and loss-year share). Score = slider-weighted
mean. Shown: the current rotation + the two best distinct crop sets. A tie band of 5% flags no clear winner. A
water cap excludes rotations that leave >25% of need unmet.

**Fusion (Sky + Scout).** Each window k predicts root-zone relative wetness h_k,t for the current crop on day
t. Readings are calibrated (raw → θ → relative wetness), filtered (duplicates, within 24 h of rain or
irrigation, ±0.25 spikes) and averaged per day. Weights: w_k ∝ exp(−½ Σ_t ((y_t − h_k,t)/σ)² / τ), where τ is
the soil's decorrelation time measured from the replay (25 days on the coast) and σ = hypot(σ_sensor,
σ_model). σ_model is chosen per site as the smallest value whose leave-one-out twin-experiment coverage stays
within 5 points of the unweighted range on average and within 12 points at every reading horizon (0.05 coast;
0.20 Morocco). If ESS < 5
the likelihood is tempered. **Readings only re-weight this season**: our twin experiment showed re-weighting
the 3-year outcome was overconfident (coverage 0.57 vs 0.75), so 3-year ranges stay on history.

**Validation wall (qa/REPORT.md).**
- **Twin experiment, coast:** 135 days of readings → this season's range 44% narrower with coverage 0.73
  (unweighted 0.75); 180 days → 51% narrower, 0.76. The 60–90 day dip (0.64) is reported.
- **Twin experiment, Morocco:** no narrowing until 180 days (29% narrower, coverage 0.66 vs 0.75).
- **Hindcast, coast barley vs MODIS NDVI peak:** ρ = −0.47 (deficit days), +0.50 (ETa/ETc), n = 9.
- **Hindcast, Morocco wheat vs NDVI peak:** ρ = −0.35 / +0.23 (n = 9), right direction but weak; vs MOD16, n = 4, not informative.
- **Leaf model:** 95.5% on 1,878 grouped held-out images.
- **Provenance audit:** 1,201 numbers, 0 untagged.

**Looking ahead (non-NASA, disclosed).** The 16-day planner continues the same FAO-56 balance on the Open-Meteo
forecast (FAO ET0, rain). The 3-month ECMWF SEAS5 outlook is shown as context only, not bias-corrected and never
used in scores.

**Time machine.** For each agricultural year since MODIS began, the field counts as cropped in a season if the
NDVI peak is ≥ 0.45 and rises ≥ 0.12 above the season's low (winter Dec–Apr, summer Jun–Oct). Cropped seasons are
replayed with the farmer's stated crop, bare ones as fallow; the suggestion is replayed on the same weather. The
satellite sees green, not the crop name.

**Canal mode.** Each farm's options are its rotations within 10 points of its own best, times summer sowing moved
−14/0/+14 days (inside the planting window). Each option's average daily irrigation over the replay years is scaled by
farm area; a greedy search picks the combination with the lowest peak 7-day canal demand.

**Field Pulse (our model).** One sample per MODIS composite (16 days, 250 m) per field. Inputs: the last four NDVI
values and slopes; the field's seasonal NDVI normal for now and for the target date (leave-one-year-out in training);
NASA POWER rain, ET0, Tmax and its anomaly, heat days and GWETROOT over 16–60 days; and physics inputs from an FAO-56
single bucket (TAW 100 mm, p = 0.5) driven by Kc = 1.25·NDVI − 0.10: crop demand ETc and the stress factor Ks.
Target: NDVI change 16 and 32 days ahead. Model: scikit-learn HistGradientBoosting with quantile loss (10/50/90%), then
split-conformal widening (CQR) on the last 20% of training dates. Tests (qa/PULSE.md): train before Jul 2023 and test on
Oct 2023 onward; leave one field out. Baselines: persistence, seasonal normal, normal + damped anomaly. An image below
the 10th percentile is flagged as "not explained by the weather".

**Voice assistant.** Speech → text with faster-whisper "small" on the laptop (or the browser recogniser). A keyword
router for Egyptian colloquial Arabic and English (or Claude with tool use, when a key exists) calls seven tools that
wrap existing endpoints. Every number in a Claude reply must match a tool result (±3%, or the same value in thousands)
or the rules engine answers instead. Text → speech with ar-EG neural voices (edge-tts).

**Uncertainty beyond weather (v0.6).** Each replayed year is crossed with 40 seeded draws of farm-gate price (log-normal,
per-crop CV; wheat 5 % because it is bought at a state price) and of summer canal supply (a short summer in 20 % of years by
default, delivering 75 % of the irrigation need; the unmet water comes off ETa and yield follows FAO-33). Soil salinity uses
FAO-29 Maas–Hoffman salt tolerance (yield −b % per dS/m above threshold a).

**Plan Mode.** Profile → replay → search over the top rotations × summer sowing −14/0/+14 days × full or 85 % summer irrigation
(exact FAO-56 engine, ≈2 s) → score by the farmer's priorities → schedule with dates, water, yields and ranges. Field yields are
scaled by the field's MODIS peak NDVI relative to the Delta peer median (clipped 0.8–1.1, assumption:ndvi_yield_scaling).

**Known limits.** History is not a forecast. Prices are partly assumptions. Planting dates are typical, not
local. The probe reads one spot. SMAP and IMERG are wired but not yet fetched (login). Costs exclude land rent.
The leaf model knows 8 classes.
