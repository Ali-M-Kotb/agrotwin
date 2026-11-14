# AgroTwin: from the sky to the land
NASA Space Apps 2026 · challenge "Field Shift: Adapting Farms with NASA Data"
Team: Ali Kotb, Mostafa Dawood, Yaseen Abdelal · Verdex Scout = prior work (Ali Kotb & Mostafa Dawood), disclosed.

> AI-assisted: this spec, the code and the data files were written with Claude (Anthropic) under human review. See docs/AI_USE.md.

## One sentence
For one field, AgroTwin replays every year of NASA weather since 1991 through a daily
FAO-56 water balance for the farmer's current rotation and two alternatives, shows
water, soil and profit as **ranges** and a **Harvest Barcode**, and lets the
**Verdex Scout** robot re-weight those past years with real field readings so the
range visibly narrows. It supports farmers and agronomists. It never replaces them.

## What was merged
| From the Verdex planner (built 13 Nov, working) | From the AgroTwin plan (Yaseen, 14 Nov) |
|---|---|
| Real NASA POWER 1981→now, MODIS NDVI + MOD16 ET (ORNL, no login), SoilGrids | Daily FAO-56 root-zone water balance (TAW, RAW, Ks), irrigated vs rain-fed |
| FastAPI + offline-capable vanilla JS UI, Leaflet + Plotly bundled | 3 rotations (existing + 2 alternatives) over every replay window since 1991 → p10/p50/p90 |
| Team's trained leaf model (v2_deit3, 8 classes) running in-app | Harvest Barcode, worst year, loss-year share |
| Robot telemetry bridge (MQTT/serial/replay), virtual robot | Scout run contract, calibration id gate, fusion weights + ESS guard |
| Disease detection → crop-family penalty, live re-rank | Twin experiment (coverage), hindcast (Spearman), provenance audit |
| Arabic/English with RTL, printable plan | Farmer / Investor / Scientist lenses, source chip on every number, LIVE/REPLAY/SIMULATED badge |
| Climate stress test | Rain / warming / price scenario sliders, danger windows (robust z) |
| — | Council (agronomist, economist, skeptic) + Number Auditor; Field Card + local QR + WhatsApp text |

Architecture choice: **keep FastAPI + vanilla JS** (no Next.js). It already runs fully
offline on stage and needs no build step; the 36-hour budget goes to the engine,
fusion and validation, which is what the Validity judges probe.

## Demo sites (data/sites.json)
| id | where | water | role |
|---|---|---|---|
| delta_01 | Kafr El-Sheikh, Nile Delta (31.25, 30.95) | irrigated | main Egypt story: water saving |
| coast_01 | North-west coast near Matrouh (31.28, 27.35) | rain-fed | **Scout fusion demo** (no irrigation log needed) |
| intl_01 | Saïs plain, Morocco (33.90, −5.45) | rain-fed | "works anywhere POWER has data" |
+ three more cached Delta fields (Dakahlia, Beheira, Gharbia).

## Rules
1. Every number in an API result carries a source tag: `nasa:<product>`, `computed`,
   `scout:<run_id>`, `quoted:<url>` or `assumption:<name>`. The provenance audit fails on any untagged number.
2. Data mode LIVE | REPLAY | SIMULATED | NONE travels with Scout data end to end and is always on screen.
3. Every threshold that is a judgment call lives in `backend/config.py` with an `assumption:` name and shows in the Scientist lens.
4. Validation results are computed by `make validate` into qa/REPORT.md. Never pre-written.
5. No NASA logos, flags or insignia.

## P0 (must ship) / P1 / P2 — status is tracked in HANDOFF.md
P0: pin → 3 rotations replayed since 1991 as ranges · barcode · evidence / benefits / gaps / local-review flags ·
priority mixer + scenario sliders · Scout fusion with narrowing range · lenses + AR/EN · source chips + mode badge.
P1: plant sightings on the timeline · Council + Number Auditor · Field Card with QR + WhatsApp text · danger-window timeline.
P2 (slides only): live WhatsApp bot, sub-field zones, co-op mode, carbon.

## Jobs only humans can do (before Sunday)
1. Confirm the hub's real deadline and how to declare Verdex as prior work.
2. Ali: a real serial/MQTT log from the robot (even 30 minutes in a pot), a few photos, and the probe calibration (3+ soil samples, weighed, oven-dried, reweighed).
3. Earthdata login (urs.earthdata.nasa.gov) → `scripts/fetch_earthdata.py` for SMAP + IMERG.
4. 15 minutes with a farmer or agronomist on the crop table and Farmer-lens wording.
5. A native Arabic reader signs off content/*.json (every string is flagged needs_native_review).
6. Record the 30-second video with English subtitles; submit by Sunday 8 PM.
