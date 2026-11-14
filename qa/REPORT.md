# Validation wall — 2026-11-14T14:05:08

_Computed by qa/validate.py at run time. Not pre-written._

## Twin experiment (does the Scout-narrowed range stay honest?)

**coast_01** (barley-fallow, 32 windows, σ sensor 0.05, σ model 0.05)

| reading days | outcome | coverage (target 0.7–0.9) | unweighted coverage | width vs unweighted | ESS median |
|---|---|---|---|---|---|
| 30 | this_season_profit | 0.694 | 0.75 | 0.946 | 20.8 |
| 60 | this_season_profit | 0.644 | 0.75 | 0.888 | 6.5 |
| 90 | this_season_profit | 0.637 | 0.75 | 0.773 | 5.4 |
| 135 | this_season_profit | 0.725 | 0.75 | 0.565 | 5.4 |
| 180 | this_season_profit | 0.762 | 0.75 | 0.489 | 5.5 |

3-year profit with the same weights (135 days): coverage 0.583 vs unweighted 0.75 → 3-year ranges are NOT re-weighted in the product: readings cannot know future seasons.

**intl_01** (wheat-fallow, 32 windows, σ sensor 0.05, σ model 0.2)

| reading days | outcome | coverage (target 0.7–0.9) | unweighted coverage | width vs unweighted | ESS median |
|---|---|---|---|---|---|
| 30 | this_season_profit | 0.844 | 0.75 | 1.018 | 14.4 |
| 60 | this_season_profit | 0.744 | 0.75 | 0.98 | 7.8 |
| 90 | this_season_profit | 0.688 | 0.75 | 0.996 | 6.4 |
| 135 | this_season_profit | 0.706 | 0.75 | 0.967 | 6.1 |
| 180 | this_season_profit | 0.656 | 0.75 | 0.712 | 5.7 |

3-year profit with the same weights (135 days): coverage 0.625 vs unweighted 0.781 → 3-year ranges are NOT re-weighted in the product: readings cannot know future seasons.

## Hindcast (model vs independent satellite signal)

- **coast_01** (barley) vs MODIS NDVI seasonal peak: n = 9, rho_deficit_days = -0.467, rho_eta_over_etc = 0.5. Expectation: rho(deficit, NDVI) < 0 and rho(ETa/ETc, NDVI) > 0 where water limits the crop.
- **intl_01** (wheat) vs MODIS NDVI seasonal peak: n = 9, rho_deficit_days = -0.35, rho_eta_over_etc = 0.233. Expectation: rho(deficit, NDVI) < 0 and rho(ETa/ETc, NDVI) > 0 where water limits the crop.
- **intl_01** (wheat) vs MODIS MOD16A2GF seasonal actual ET: n = 4, rho_model_eta = -0.8, model_mean_mm = 357, mod16_mean_mm = 161. Expectation: rho > 0; levels differ because MOD16 is a 500 m pixel average.
- **delta_01** (wheat) vs MODIS NDVI seasonal peak: n = 9, . Expectation: not applicable: the irrigated crop never shows modelled water stress, so there is nothing to rank.
- **delta_01** (wheat) vs MODIS MOD16A2GF seasonal actual ET: n = 4, rho_model_eta = 0.2, model_mean_mm = 503, mod16_mean_mm = 192. Expectation: rho > 0; levels differ because MOD16 is a 500 m pixel average.

## Real-robot check

- not run: no LIVE or REPLAY Verdex run stored yet (data/scout/*/run_*.json)

## Verdex leaf model (author's held-out numbers, verbatim)

- deit3_small_patch16_224.fb_in22k_ft_in1k: test accuracy **0.9547** on n = 1878 held-out images; split sizes {'train': 13651, 'test': 1878, 'val': 562} (grouped by photo scene so near-duplicates never cross train/test).
- Caveat: 8 classes only (apple, potato, strawberry leaves); a sighting is an observation, not a diagnosis.

| class | correct / n | accuracy |
|---|---|---|
| Apple___Apple_scab | 373 / 383 | 0.974 |
| Apple___Black_rot | 146 / 149 | 0.98 |
| Apple___healthy | 525 / 534 | 0.983 |
| Potato___Early_blight | 111 / 125 | 0.888 |
| Potato___Late_blight | 171 / 192 | 0.891 |
| Potato___healthy | 184 / 192 | 0.958 |
| Strawberry___Leaf_scorch | 168 / 183 | 0.918 |
| Strawberry___healthy | 115 / 120 | 0.958 |

## Provenance audit

- numbers checked: 1201, untagged: 0 → PASS

## Sanity suite

- rain_x0.7_changes_water_need: PASS {base=9750, dry=9838}
- profit_falls_with_price: PASS {base=57419, low=26093}
- fallow_has_no_transpiration: PASS {transp_days=0.0, bare_days_median=1170.0}
- water_balance_closes_mm: PASS {max_residual=1.2105871860512707e-11}
- no_scout_no_change: PASS {note=fusion with zero readings returns uniform weights (unit test)}
