# AgroTwin: from the sky to the land

NASA Space Apps 2026 · *Field Shift: Adapting Farms with NASA Data*
Team: Ali Kotb, Mostafa Dawood, Yaseen Abdelal. The Verdex Scout robot is prior work by Ali Kotb and Mostafa Dawood (disclosed).

For one field, AgroTwin replays **every year of NASA weather since 1991** through a daily
FAO-56 water balance for the farmer's current rotation and two alternatives. It shows water,
soil and profit as **ranges** and a **Harvest Barcode** (one stripe per past year). The **Verdex
Scout** robot's soil readings re-weight those past years, so this season's range visibly
narrows. Every number has a source tag, every result has Farmer, Investor and Scientist
lenses in Arabic or English, and a Field Card prints or goes out on WhatsApp.

> AI disclosure: the code and documents were written with Claude (Anthropic) under human review;
> see [docs/AI_USE.md](docs/AI_USE.md). The leaf classifier was trained by its author (Verdex).

## Run

```bash
cd agrotwin
./run.sh            # first run builds ~/.venvs/verdex; then http://127.0.0.1:8000
./run.sh offline    # stage mode: cache only, never touches the network
make test           # 20 tests (golden case, mass balance, auditor, fusion, contracts)
make validate       # the validation wall → qa/REPORT.md (computed, never pre-written)
```

`run.sh` listens on the local network so a phone on the same Wi-Fi can open the Field
Card's QR link. Open the app through the laptop's LAN address (not `localhost`) before
printing a card on stage.

## Demo sites (all cached)

| site | water | why it's there |
|---|---|---|
| Kafr El-Sheikh, Nile Delta | irrigated | water-saving story (current: wheat → rice) |
| Matrouh coast | rain-fed | **Scout fusion demo**: the barcode shows real drought years in red |
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
frontend/  index.html · app.js · style.css · i18n/{en,ar}.json · vendor/ (Leaflet, Plotly, offline)
contracts/ scout_run.schema.json
content/   glossary.json · blindspots.json (AR+EN, flagged for native review)
data/      sites.json · prices.csv · cache/ (NASA downloads) · scout/ (farm data, exportable)
qa/        validate.py → REPORT.md / REPORT.json
docs/      METHODS.md · DATA_SOURCES.md · AI_USE.md · PROJECT_PAGE.md
scripts/   precache.py · fetch_earthdata.py · robot_bridge.py
```

Connect the real robot: `python scripts/robot_bridge.py mqtt` (the ESP32 already publishes
`farm/telemetry`), or POST a Scout run to `/api/scout/run` with `Authorization: Bearer $AGROTWIN_TOKEN`.
Fusion refuses to run until the probe is calibrated (`POST /api/scout/calibrate`, 3+ oven-dried samples).
