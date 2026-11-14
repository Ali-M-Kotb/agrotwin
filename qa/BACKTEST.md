# Backtest — last three seasons (2026-11-14T15:28:48)

_Computed by qa/backtest.py. Forecasts use only years before each test season; 'actual' is the season replayed on its real NASA POWER weather (not a measured harvest)._

## Summary across sites, rotations and seasons

| metric | cases | in 80% range (raw) | in 80% range (climate-adjusted) | CRPS raw | CRPS adjusted | error: same as last year | error: long-term average | skill vs last year (adjusted) |
|---|---|---|---|---|---|---|---|---|
| profit, EGP/feddan | 27 | 70% | 78% | 4113.71 | 3996.45 | 7779.24 | 6768.19 | +49% |
| irrigation, m³/feddan | 9 | 67% | 67% | 321.997 | 228.12 | 515.048 | 498.068 | +56% |
| yield, share of potential | 27 | 70% | 74% | 0.0834 | 0.0803 | 0.1618 | 0.1336 | +50% |

Skill = 1 − CRPS / (error of 'same as last year'). Positive means the replay beats repeating last season.

## Kafr El-Sheikh, Nile Delta (irrigated, Tmax trend +0.296 °C/decade)

**wheat → rice → wheat → rice → wheat → rice**

| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |
|---|---|---|---|---|---|
| 2023/24 | profit, EGP/feddan | 60,009.14 | 48,290.83 – 60,009.14 | yes | 60,009.14 |
| 2023/24 | irrigation, m³/feddan | 10,010.87 | 9,162.83 – 10,456.75 | yes | 9,148.21 |
| 2023/24 | yield, share of potential | 1.00 | 0.95 – 1.00 | yes | 1.00 |
| 2024/25 | profit, EGP/feddan | 51,729.10 | 48,290.83 – 60,009.14 | yes | 57,079.56 |
| 2024/25 | irrigation, m³/feddan | 10,126.61 | 9,191.24 – 10,459.85 | yes | 9,793.17 |
| 2024/25 | yield, share of potential | 0.95 | 0.95 – 1.00 | **no** | 1.00 |
| 2025/26 | profit, EGP/feddan | 60,009.14 | 48,290.83 – 60,009.14 | yes | 60,009.14 |
| 2025/26 | irrigation, m³/feddan | 10,481.38 | 9,208.16 – 10,462.94 | **no** | 10,010.87 |
| 2025/26 | yield, share of potential | 1.00 | 0.96 – 1.00 | yes | 1.00 |

**faba → maize → faba → maize → faba → maize**

| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |
|---|---|---|---|---|---|
| 2023/24 | profit, EGP/feddan | 77,485.30 | 77,485.30 – 77,485.30 | yes | 77,485.30 |
| 2023/24 | irrigation, m³/feddan | 7,464.25 | 6,719.56 – 7,706.54 | yes | 6,668.99 |
| 2023/24 | yield, share of potential | 1.00 | 1.00 – 1.00 | yes | 1.00 |
| 2024/25 | profit, EGP/feddan | 77,485.30 | 77,485.30 – 77,485.30 | yes | 77,485.30 |
| 2024/25 | irrigation, m³/feddan | 7,497.01 | 6,736.33 – 7,719.56 | yes | 7,186.67 |
| 2024/25 | yield, share of potential | 1.00 | 1.00 – 1.00 | yes | 1.00 |
| 2025/26 | profit, EGP/feddan | 77,485.30 | 77,485.30 – 77,485.30 | yes | 77,485.30 |
| 2025/26 | irrigation, m³/feddan | 7,843.06 | 6,776.12 – 7,726.05 | **no** | 7,464.25 |
| 2025/26 | yield, share of potential | 1.00 | 1.00 – 1.00 | yes | 1.00 |

**faba → maize → potato → maize → faba → maize**

| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |
|---|---|---|---|---|---|
| 2023/24 | profit, EGP/feddan | 77,485.30 | 77,485.30 – 77,485.30 | yes | 77,485.30 |
| 2023/24 | irrigation, m³/feddan | 7,464.25 | 6,719.56 – 7,706.54 | yes | 6,668.99 |
| 2023/24 | yield, share of potential | 1.00 | 1.00 – 1.00 | yes | 1.00 |
| 2024/25 | profit, EGP/feddan | 77,485.30 | 77,485.30 – 77,485.30 | yes | 77,485.30 |
| 2024/25 | irrigation, m³/feddan | 7,497.01 | 6,736.33 – 7,719.56 | yes | 7,186.67 |
| 2024/25 | yield, share of potential | 1.00 | 1.00 – 1.00 | yes | 1.00 |
| 2025/26 | profit, EGP/feddan | 77,485.30 | 77,485.30 – 77,485.30 | yes | 77,485.30 |
| 2025/26 | irrigation, m³/feddan | 7,843.06 | 6,776.12 – 7,726.05 | **no** | 7,464.25 |
| 2025/26 | yield, share of potential | 1.00 | 1.00 – 1.00 | yes | 1.00 |

Independent satellite signal for the same winters (MODIS):

| season | NDVI peak | MOD16 ET (mm) | model yield share, first crop |
|---|---|---|---|
| 2023/24 | 0.851 | 216.3 | 1.0 |
| 2024/25 | 0.846 | 211.6 | 0.95 |
| 2025/26 | 0.809 | None | 1.0 |

## Matrouh coast, rain-fed (rain-fed, Tmax trend +0.276 °C/decade)

**barley → fallow → barley → fallow → barley → fallow**

| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |
|---|---|---|---|---|---|
| 2023/24 | profit, EGP/feddan | 4,401.56 | 4,375.69 – 9,982.43 | yes | 10,591.58 |
| 2023/24 | yield, share of potential | 0.57 | 0.57 – 0.96 | yes | 1.00 |
| 2024/25 | profit, EGP/feddan | 4,989.30 | 4,379.82 – 9,853.88 | yes | 8,052.15 |
| 2024/25 | yield, share of potential | 0.61 | 0.57 – 0.95 | yes | 0.82 |
| 2025/26 | profit, EGP/feddan | 2,964.20 | 4,362.83 – 9,724.37 | **no** | 4,401.56 |
| 2025/26 | yield, share of potential | 0.48 | 0.57 – 0.94 | **no** | 0.57 |

**faba → fallow → faba → fallow → wheat → fallow**

| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |
|---|---|---|---|---|---|
| 2023/24 | profit, EGP/feddan | 6,317.12 | 6,701.75 – 32,128.04 | **no** | 43,203.47 |
| 2023/24 | yield, share of potential | 0.22 | 0.23 – 0.69 | **no** | 0.88 |
| 2024/25 | profit, EGP/feddan | 9,061.28 | 6,679.40 – 32,029.30 | yes | 21,254.35 |
| 2024/25 | yield, share of potential | 0.27 | 0.23 – 0.68 | yes | 0.49 |
| 2025/26 | profit, EGP/feddan | 683.43 | 6,350.69 – 31,930.30 | **no** | 6,317.12 |
| 2025/26 | yield, share of potential | 0.12 | 0.22 – 0.68 | **no** | 0.22 |

**faba → fallow → faba → fallow → faba → fallow**

| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |
|---|---|---|---|---|---|
| 2023/24 | profit, EGP/feddan | 6,317.12 | 6,701.75 – 32,128.04 | **no** | 43,203.47 |
| 2023/24 | yield, share of potential | 0.22 | 0.23 – 0.69 | **no** | 0.88 |
| 2024/25 | profit, EGP/feddan | 9,061.28 | 6,679.40 – 32,029.30 | yes | 21,254.35 |
| 2024/25 | yield, share of potential | 0.27 | 0.23 – 0.68 | yes | 0.49 |
| 2025/26 | profit, EGP/feddan | 683.43 | 6,350.69 – 31,930.30 | **no** | 6,317.12 |
| 2025/26 | yield, share of potential | 0.12 | 0.22 – 0.68 | **no** | 0.22 |

Independent satellite signal for the same winters (MODIS):

| season | NDVI peak | MOD16 ET (mm) | model yield share, first crop |
|---|---|---|---|
| 2023/24 | 0.142 | None | 0.574 |
| 2024/25 | 0.15 | None | 0.614 |
| 2025/26 | 0.106 | None | 0.476 |

## Saïs plain, Morocco (rain-fed, Tmax trend +0.333 °C/decade)

**wheat → fallow → wheat → fallow → wheat → fallow**

| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |
|---|---|---|---|---|---|
| 2023/24 | profit, EGP/feddan | 28,398.90 | 29,664.78 – 42,392.24 | **no** | 36,007.49 |
| 2023/24 | yield, share of potential | 0.71 | 0.74 – 1.00 | **no** | 0.87 |
| 2024/25 | profit, EGP/feddan | 42,120.46 | 28,714.97 – 42,386.54 | yes | 25,034.80 |
| 2024/25 | yield, share of potential | 0.99 | 0.72 – 1.00 | yes | 0.64 |
| 2025/26 | profit, EGP/feddan | 41,363.72 | 28,376.44 – 42,379.50 | yes | 28,398.90 |
| 2025/26 | yield, share of potential | 0.98 | 0.71 – 1.00 | yes | 0.71 |

**faba → fallow → faba → fallow → wheat → fallow**

| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |
|---|---|---|---|---|---|
| 2023/24 | profit, EGP/feddan | 25,677.68 | 23,643.50 – 49,624.30 | yes | 24,865.88 |
| 2023/24 | yield, share of potential | 0.57 | 0.53 – 1.00 | yes | 0.56 |
| 2024/25 | profit, EGP/feddan | 29,881.77 | 23,734.14 – 49,600.18 | yes | 31,481.18 |
| 2024/25 | yield, share of potential | 0.65 | 0.53 – 1.00 | yes | 0.67 |
| 2025/26 | profit, EGP/feddan | 46,723.19 | 23,823.44 – 49,575.28 | yes | 25,677.68 |
| 2025/26 | yield, share of potential | 0.95 | 0.54 – 1.00 | yes | 0.57 |

**faba → fallow → faba → fallow → faba → fallow**

| season | metric | actual | forecast 10–90% (adjusted) | inside? | same as last year |
|---|---|---|---|---|---|
| 2023/24 | profit, EGP/feddan | 25,677.68 | 23,643.50 – 49,624.30 | yes | 24,865.88 |
| 2023/24 | yield, share of potential | 0.57 | 0.53 – 1.00 | yes | 0.56 |
| 2024/25 | profit, EGP/feddan | 29,881.77 | 23,734.14 – 49,600.18 | yes | 31,481.18 |
| 2024/25 | yield, share of potential | 0.65 | 0.53 – 1.00 | yes | 0.67 |
| 2025/26 | profit, EGP/feddan | 46,723.19 | 23,823.44 – 49,575.28 | yes | 25,677.68 |
| 2025/26 | yield, share of potential | 0.95 | 0.54 – 1.00 | yes | 0.57 |

Independent satellite signal for the same winters (MODIS):

| season | NDVI peak | MOD16 ET (mm) | model yield share, first crop |
|---|---|---|---|
| 2023/24 | 0.746 | 206.9 | 0.71 |
| 2024/25 | 0.762 | 199.2 | 0.994 |
| 2025/26 | 0.728 | None | 0.978 |

