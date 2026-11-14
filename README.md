# AgroTwin: from the sky to the land

NASA Space Apps 2026 · *Field Shift: Adapting Farms with NASA Data*
Team: Ali Kotb, Mostafa Dawood, Yaseen Abdelal. The Verdex Scout robot is prior work by Ali Kotb and Mostafa Dawood (disclosed).
This repository merges two builds: this engine and product, and Yaseen Abdelal's AgroTwin scaffold
([github.com/Yaseen-Saad/AgroTwin](https://github.com/Yaseen-Saad/AgroTwin)): its v1 data contracts, curve-number runoff
and FAO-56-verified crop coefficients are now part of this engine. See [CHANGELOG.md](CHANGELOG.md).

For one field, AgroTwin replays **every year of NASA weather since 1991** through a daily
FAO-56 water balance for the farmer's current rotation and two alternatives. It shows water,
soil and profit as **ranges** and a **Harvest Barcode** (one stripe per past year). The **Verdex
Scout** robot's soil readings re-weight those past years, so this season's range visibly
narrows. Every number has a source tag, every result has Farmer, Investor and Scientist
lenses in Arabic or English, and a Field Card prints or goes out on WhatsApp.

> AI disclosure: the code and documents were written with Claude (Anthropic) under human review;
> see [docs/AI_USE.md](docs/AI_USE.md). The leaf classifier was trained by its author (Verdex).

## The product in one minute

- **Simple mode** (default, for farmers): tap your field on the map, pick what you grow, tap what
  matters (water, soil, profit, safety) and get one suggestion in plain Arabic or English, read aloud.
- **Advanced mode** (agronomists, judges):
  - **Live NASA layers on the map** via GIBS, with a date picker and a ▶ time-lapse:
    MODIS NDVI (16-day since 2000, 8-day rolling), **SMAP L4 root-zone soil moisture**,
    **GPM IMERG rain**, MODIS land-surface temperature, and MODIS true colour by date.
  - **Draw your real field boundary**: area in feddans and hectares, and totals for the whole farm.
  - **Click-anywhere inspector**: 10-year rain, reference ET, aridity, heat trend, soil and elevation.
  - **My farms**: saved fields with boundaries and a history of saved plans.
  - Every panel: lenses, Scout fusion, validation wall, Council, diagnosis.
- **Next 16 days**: the same water balance continued on the 16-day forecast → "irrigate around Sunday, about 220 m³/feddan".
- **Field Pulse, our own model**: trained on 11 years of MODIS + NASA POWER; forecasts field greenness 16/32 days ahead
  and flags images the weather doesn't explain, which tells the robot where to look (`qa/PULSE.md`).
- **Voice assistant**: tap the mic and ask in Egyptian Arabic («أروي امتى؟»). It calls AgroTwin's own engines and
  answers out loud. Speech recognition runs on the laptop; it works offline.
- **Time machine**: your field's last ten seasons read from MODIS (green or bare), replayed on real weather for your
  crops and for the suggestion: "since 2015 the suggestion would have saved N m³ and earned N EGP more per feddan".
- **Canal mode**: neighbours on one canal coordinate rotations and stagger summer sowing; the canal's worst week
  drops by about half while nobody gives up more than 10 points of their own score.
- **Egyptian Arabic voice**: advice read in Egyptian colloquial Arabic by the ar-EG neural voices (free, cached).
- **Three lenses that actually differ**: farmer, investor (stress test, profit spread), scientist (backtest, equations).
- **How it works** page at `/methods`: the method in plain language, with live validation numbers.
- **Installable** on a phone (web-app manifest and service worker); works with a weak signal.

## Proof for the judges

- `make validate` → qa/REPORT.md: twin experiment, hindcast vs MODIS, provenance audit, sanity suite.
- `python qa/backtest.py` → qa/BACKTEST.md: the last three seasons (2023/24–2025/26) at three sites, forecast
  from earlier years only. The replay beats "same as last year" by about 50 % (CRPS) for profit, irrigation and
  yield, and climate-adjusting past years improves it further (irrigation error −29 %, profit coverage 70 → 78 %).
- `python qa/pulse_train.py` → qa/PULSE.md: Field Pulse tested on held-out seasons and held-out fields against three baselines.
- `python scripts/sample_cases.py` → docs/SAMPLE_CASES.md: nine worked farmer scenarios for rehearsal.

## Run

```bash
cd agrotwin
./run.sh            # first run builds ~/.venvs/verdex; then http://127.0.0.1:8000
./run.sh offline    # stage mode: cache only, never touches the network
make test           # tests (golden case, mass balance, runoff, auditor, fusion, v1 contract)
make validate       # the validation wall → qa/REPORT.md (computed, never pre-written)
```

`run.sh` listens on the local network so a phone on the same Wi-Fi can open the Field
Card's QR link. Open the app through the laptop's LAN address (not `localhost`) before
printing a card on stage.

## Demo sites (all cached)

| site | water | why it's there |
|---|---|---|
| Kafr El-Sheikh, Nile Delta | irrigated | water-saving story (current: wheat → rice) |
| Matrouh coast | rain-fed | **Scout fusion demo**: profit swings with the rain; the robot narrows this season's range |
| Saïs plain, Morocco | rain-fed | works anywhere NASA POWER has data |
| Dakahlia, Beheira, Gharbia | irrigated | more Delta fields |

Clicking anywhere else fetches it live: the plan appears in about 4 s, and soil and MODIS
history arrive in the background (about 45 s).

## What is real, what is simulated

| | status |
|---|---|
| Weather 1981 → 3 days ago | **real**: NASA POWER daily |
| NDVI, actual ET | **real**: MODIS MOD13Q1, MOD16A2GF (ORNL DAAC) |
| Soil texture | **real**: SoilGrids 2.0 (labelled regional default while it loads) |
| SMAP, GPM IMERG | **wired, not yet fetched**: needs an Earthdata login (`scripts/fetch_earthdata.py`) |
| Prices, yields, costs | 19 quoted rows with URLs, 21 assumption rows: `data/prices.csv` |
| Leaf disease model | **real**: team's DeiT-III model, 95.5% on 1,878 held-out images |
| Scout soil readings | **SIMULATED** until the robot posts: a hidden past season replayed as readings (the badge says so) |

## The 3-minute demo

1. **Farmer lens, Arabic, Kafr El-Sheikh.** One suggestion, profit in 8 of 10 past
   years, water saved, one warning. Press 🔊 to have it read aloud.
2. **Harvest Barcode.** Three rows of stripes, one per year since 1991; hover a stripe for its profit.
3. **What-if.** Drag rain to −30% and warming to +2°. The ranking updates in under a second.
4. **Matrouh coast → Sky + Scout.** Hide 2007, send 135 days of readings. The badge says
   SIMULATED, and the range narrows while the hidden truth stays inside it.
5. **Blind spots + Council.** What satellites cannot see. Three advisors, every number audited.
6. **Investor lens.** Price sources: tap any number to see where it came from.
7. **Scientist lens.** Equations, the twin experiment, the hindcast, the provenance audit, every assumption.
8. **Field Card.** Printable A4 with QR code, plus WhatsApp text.

Say out loud which parts are SIMULATED. Judges forgive a replay; they don't forgive a surprise.

## Layout

```
backend/   app.py (API) · waterbalance.py (FAO-56, vectorised) · replay.py (search + ranking)
           econ.py (yield, profit, barcode) · fusion.py (Scout weights, twin experiment)
           scout.py (contract, calibration, simulator, farmer export) · council.py (advisors + Number Auditor)
           fieldcard.py (A4, WhatsApp, local QR) · report.py (evidence/gaps/review, AR+EN)
           history.py (trend, NDVI seasons, danger windows) · data_sources.py · crops.py · soil.py · config.py
backend/   pulse.py (Field Pulse model) · chat.py (voice assistant) · unique.py (time machine, canal) · outlook.py
frontend/  index.html · app.js · chat.js · methods.html · style.css · i18n/{en,ar}.json · vendor/ (Leaflet, Plotly, offline)
contracts/ scout_run.schema.json
content/   glossary.json · blindspots.json (AR+EN, flagged for native review)
data/      sites.json · prices.csv · cache/ (NASA downloads) · scout/ (farm data, exportable)
qa/        validate.py → REPORT.md · backtest.py → BACKTEST.md · pulse_train.py → PULSE.md
docs/      METHODS.md · DATA_SOURCES.md · AI_USE.md · PROJECT_PAGE.md
scripts/   precache.py · fetch_earthdata.py · robot_bridge.py
```

Connect the real robot: `python scripts/robot_bridge.py mqtt` (the ESP32 already publishes
`farm/telemetry`), or POST a Scout run to `/api/scout/run` with `Authorization: Bearer $AGROTWIN_TOKEN`.
Fusion refuses to run until the probe is calibrated (`POST /api/scout/calibrate`, 3+ oven-dried samples).
