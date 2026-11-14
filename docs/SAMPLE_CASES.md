# Sample cases (for the team, not the app)

_Generated 2026-11-14 by scripts/sample_cases.py from the real engine (NASA POWER 1991→2026, climate-adjusted replay). Prices: 19 quoted, 21 assumptions (data/prices.csv). Re-run after any change._

## Rice farmer in Kafr El-Sheikh who wants to save water

_Owns 3 feddans near Kafr El-Sheikh, grows wheat in winter and rice in summer, worried about canal shortages._

**Answer:** Faba bean → Maize (×3)

| | current rotation | suggested |
|---|---|---|
| rotation | Wheat → Rice (×3) | Faba bean → Maize (×3) |
| profit, 8 of 10 years (EGP/feddan/yr) | 52,197 – 58,056 | 76,478 – 77,485 |
| irrigation (m³/feddan/yr, median) | 9,929 | 7,269 |
| losing years of 32 | 0 | 0 |
| worst past window | 1999: 49,437 | 2018: 75,471 |
| score /100 | 4.5 | 81.2 |

What the app tells the farmer:

- Uses about 2,660 m³ less irrigation water per feddan per year than your current rotation.
- Median profit about 22,274 EGP per feddan per year higher than your current rotation.
- Faba bean is a legume: it leaves roughly 15–40 kg of nitrogen per feddan for the next crop.

- The app says there is **no clear winner** here: the top two are within 5 %.

Talking point: For a 3-feddan farm that is about 7,979 m³ of Nile water a year saved, with the profit range shown, not promised.

## Same farmer, canal allowance capped

_The irrigation district limits him to 2,500 m³/feddan in winter and 5,000 in summer._

**Answer:** Faba bean → Maize → Potato (winter) → Maize → Faba bean → Maize

| | current rotation | suggested |
|---|---|---|
| rotation | Wheat → Rice (×3) | Faba bean → Maize → Potato (winter) → Maize → Faba bean → Maize |
| profit, 8 of 10 years (EGP/feddan/yr) | 13,060 – 16,163 | 70,458 – 71,465 |
| irrigation (m³/feddan/yr, median) | 5,500 | 7,062 |
| losing years of 32 | 0 | 0 |
| worst past window | 2007: 10,570 | 2018: 69,451 |
| score /100 | 31.2 | 64.1 |

What the app tells the farmer:

- Median profit about 56,566 EGP per feddan per year higher than your current rotation.
- Faba bean is a legume: it leaves roughly 15–40 kg of nitrogen per feddan for the next crop.
- Uses 3 plant families, which breaks pest and disease cycles.

- The app says there is **no clear winner** here: the top two are within 5 %.

Talking point: The ranking moves when the farmer's priorities or the prices move — the sliders are the farmer's, the numbers are NASA's.

## Same farmer in a hotter, drier future (+2 °C, −20 % rain)

_Stress test: does the advice hold up if the climate keeps warming?_

**Answer:** Faba bean → Maize (×3)

| | current rotation | suggested |
|---|---|---|
| rotation | Wheat → Rice (×3) | Faba bean → Maize (×3) |
| profit, 8 of 10 years (EGP/feddan/yr) | 37,098 – 46,338 | 71,443 – 76,478 |
| irrigation (m³/feddan/yr, median) | 10,642 | 7,930 |
| losing years of 32 | 0 | 0 |
| worst past window | 2007: 33,853 | 2020: 68,421 |
| score /100 | 6.2 | 80.5 |

What the app tells the farmer:

- Uses about 2,712 m³ less irrigation water per feddan per year than your current rotation.
- Median profit about 36,049 EGP per feddan per year higher than your current rotation.
- Faba bean is a legume: it leaves roughly 15–40 kg of nitrogen per feddan for the next crop.

- The app says there is **no clear winner** here: the top two are within 5 %.

Talking point: For a 3-feddan farm that is about 8,136 m³ of Nile water a year saved, with the profit range shown, not promised.

## Beheira wheat–maize farmer who cares most about profit

_Commercial grower, 10 feddans, wheat then maize, pays attention to prices._

**Answer:** Faba bean → Maize (×3)

| | current rotation | suggested |
|---|---|---|
| rotation | Wheat → Maize (×3) | Faba bean → Maize (×3) |
| profit, 8 of 10 years (EGP/feddan/yr) | 31,011 – 39,807 | 55,409 – 56,336 |
| irrigation (m³/feddan/yr, median) | 8,893 | 8,029 |
| losing years of 32 | 0 | 0 |
| worst past window | 2003: 28,590 | 2002: 55,409 |
| score /100 | 10.4 | 89.6 |

What the app tells the farmer:

- Uses about 865 m³ less irrigation water per feddan per year than your current rotation.
- Median profit about 21,694 EGP per feddan per year higher than your current rotation.
- Faba bean is a legume: it leaves roughly 15–40 kg of nitrogen per feddan for the next crop.
- Maize hit heat stress in its sensitive stage in 32 of 32 years.
- Maize hit heat stress in its sensitive stage in 32 of 32 years.

Talking point: For a 3-feddan farm that is about 2,594 m³ of Nile water a year saved, with the profit range shown, not promised.

## Gharbia wheat–maize farmer after a 30 % price drop

_Wheat then maize; all crop prices fall 30 % (a price shock is a user input, never a forecast)._

**Answer:** Faba bean → Sorghum (×3)

| | current rotation | suggested |
|---|---|---|
| rotation | Wheat → Maize (×3) | Faba bean → Sorghum (×3) |
| profit, 8 of 10 years (EGP/feddan/yr) | 7,608 – 13,765 | 21,768 – 25,122 |
| irrigation (m³/feddan/yr, median) | 8,897 | 7,248 |
| losing years of 32 | 0 | 0 |
| worst past window | 2003: 5,913 | 1999: 21,017 |
| score /100 | 6.2 | 76.6 |

What the app tells the farmer:

- Uses about 1,649 m³ less irrigation water per feddan per year than your current rotation.
- Median profit about 13,548 EGP per feddan per year higher than your current rotation.
- Faba bean is a legume: it leaves roughly 15–40 kg of nitrogen per feddan for the next crop.
- Sorghum hit heat stress in its sensitive stage in 25 of 32 years.
- Sorghum hit heat stress in its sensitive stage in 26 of 32 years.

- The app says there is **no clear winner** here: the top two are within 5 %.

Talking point: For a 3-feddan farm that is about 4,948 m³ of Nile water a year saved, with the profit range shown, not promised.

## Rain-fed barley on the Matrouh coast (no robot data)

_Bedouin family farm, barley every winter, summer fallow; depends only on rain._

**Answer:** Faba bean → Faba bean → Wheat

| | current rotation | suggested |
|---|---|---|
| rotation | Barley (×3) | Faba bean → Faba bean → Wheat |
| profit, 8 of 10 years (EGP/feddan/yr) | 5,583 – 8,209 | 15,698 – 28,762 |
| irrigation (m³/feddan/yr, median) | 0 | 0 |
| losing years of 32 | 0 | 0 |
| worst past window | 2008: 3,551 | 2008: 9,065 |
| score /100 | 19.9 | 73.5 |

What the app tells the farmer:

- Median profit about 13,755 EGP per feddan per year higher than your current rotation.
- Faba bean is a legume: it leaves roughly 15–40 kg of nitrogen per feddan for the next crop.
- Faba bean follows Faba bean from the same family (Fabaceae): pests carry over.

Talking point: The ranking moves when the farmer's priorities or the prices move — the sliders are the farmer's, the numbers are NASA's.

## Saïs plain, Morocco: the same tool outside Egypt

_Rain-fed wheat with summer fallow, about 450 mm of rain a year._

**Answer:** Faba bean → Faba bean → Wheat

| | current rotation | suggested |
|---|---|---|
| rotation | Wheat (×3) | Faba bean → Faba bean → Wheat |
| profit, 8 of 10 years (EGP/feddan/yr) | 31,129 – 39,324 | 32,131 – 44,848 |
| irrigation (m³/feddan/yr, median) | 0 | 0 |
| losing years of 32 | 0 | 0 |
| worst past window | 1999: 27,563 | 2021: 28,376 |
| score /100 | 56.0 | 78.7 |

What the app tells the farmer:

- Median profit about 2,246 EGP per feddan per year higher than your current rotation.
- Faba bean is a legume: it leaves roughly 15–40 kg of nitrogen per feddan for the next crop.
- Faba bean follows Faba bean from the same family (Fabaceae): pests carry over.

- The app says there is **no clear winner** here: the top two are within 5 %.

Talking point: The ranking moves when the farmer's priorities or the prices move — the sliders are the farmer's, the numbers are NASA's.

## The robot narrows the range: Matrouh barley, hidden 2008 season (SIMULATED)

_The 2008/09 season is hidden from the model and replayed as 150 days of Scout soil readings with sensor noise. Badge on screen: SIMULATED._

| | this season's profit range (EGP/feddan) |
|---|---|
| history only | 4,362 – 9,844 (width 5,482) |
| with Scout readings | 2,774 – 7,536 (width 4,761) |
| hidden truth | 3,695 — inside the narrowed range |

Range 13 % narrower; effective past years carrying the answer: 10.1; soil memory 25 days; confidence low.

Talking point: 'We hid a real past season from the model and let the robot measure it. The range closed in on the truth. Our backtest says this holds about 3 times in 4, which is what an honest 80 % range should do.'

## Potato farmer: the leaf camera sees late blight

_Kafr El-Sheikh, potato in winter, maize in summer. The Verdex camera records a late-blight sighting (the team's model: 89 % accuracy on held-out late-blight photos)._

- Before the sighting the app suggests: **Faba bean → Maize (×3)**
- After the sighting: **Faba bean → Maize (×3)**

Talking point: the robot's camera feeds the rotation itself: a disease seen today pushes the potato family (potato, tomato) off the field for two years, and the card says why.

## Backtest in one line

Over the last three seasons at three sites, the replay forecast beat 'same as last year' by about half (CRPS) and contained the actual outcome in 67–78 % of cases. Details: qa/BACKTEST.md.
