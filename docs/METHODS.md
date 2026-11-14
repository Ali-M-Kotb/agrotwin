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

**Known limits.** History is not a forecast. Prices are partly assumptions. Planting dates are typical, not
local. The probe reads one spot. SMAP and IMERG are wired but not yet fetched (login). Costs exclude land rent.
The leaf model knows 8 classes.
