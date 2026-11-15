# Changelog

## 0.6.0 — 15 Nov 2026: AI-driven planning on NASA-trained models
- **Plan Mode** (`backend/plan_agent.py`, `backend/planner.py`, `frontend/plan.js`, `/api/plan`, `/api/plan/chat`): talk or type;
  the agent interviews the farmer (crops, area, salinity, canal reliability, priorities), remembers the farm, and builds a
  three-year plan by searching rotations × summer sowing (−14/0/+14 d) × water strategy (full / 85 %) through the FAO-56
  engine with price and canal-shortfall Monte Carlo. "Keep rice", "less water", "I have 3 feddans" re-plan in ≈2 s.
  Claude tool-use engine behind the Number Auditor when a key is set; offline Egyptian-Arabic/English rule engine otherwise.
- **Field Pulse v2**: trained on ≈1,200 Nile Delta cropland pixels (MODIS NDVI decoded from NASA GIBS with NASA's colour map,
  error 0.002 vs ORNL MOD13Q1) + 12 ORNL fields, 482,744 samples. Unseen seasons: +44 % vs persistence, +21 % vs best
  baseline, 80 % coverage; 7.7 km spatial blocks: +49 % / +28 %; independent ORNL fields: +47 %, 82 % coverage; physics
  inputs worth 27 %. Vectorised feature builder (15× faster).
- **Field productivity index**: each field's MODIS peak greenness vs 6.8 M Delta pixel-seasons scales its expected yields.
- **Honest ranges**: profit now includes price variability (per-crop CV), summer canal shortfalls, and FAO-29 salt
  tolerance (Maas–Hoffman); irrigated ranges are no longer flat. New inputs `salinity_ece`, `canal_short_prob`.
- **Independent evidence**: `qa/et_validation.py` (water engine vs MODIS MOD16 ET) and `qa/analog_skill.py` (pre-season
  analog weighting tested; no skill, so equal weights kept).
- Field alerts (`/api/alerts`, spoken) and consent-based outcome log (`/api/outcomes`) to collect labels for the next models.
- `scripts/gibs_fetch.py`, `scripts/fetch_power_grid.py`, `scripts/ndvi_peers.py`.
- **Prithvi-EO-2.0-300M-TL** (NASA–IBM foundation model, Apache-2.0) downloaded to data/models/prithvi (1.33 GB, git-ignored);
  `backend/prithvi.py` loads the encoder and turns multi-date HLS chips into field embeddings; crop-type head waits for
  HLS imagery and labelled fields; `scripts/prithvi_check.py`; `/api/prithvi/status`.
- Considered and not built: a machine-learned emulator of the water balance; the exact engine already searches a plan in ≈2 s.

## 0.5.0 — 14 Nov 2026: our own model, voice assistant, agent board
- **Field Pulse** (`backend/pulse.py`, `qa/pulse_train.py`, `/api/pulse`): a hybrid physics + machine-learning model
  trained on MODIS NDVI and NASA POWER. Gradient-boosted quantile trees; inputs include an FAO-56 bucket driven by an NDVI
  crop coefficient. It forecasts greenness 16 and 32 days ahead and flags images the weather does not explain (where to send
  the Scout). Tested on held-out seasons and held-out fields: 45% better than persistence, 81% of outcomes in the 80% range
  after split-conformal calibration. The physics inputs cut error by 10%.
- **Voice assistant** (`backend/chat.py`, `frontend/chat.js`, `/api/chat`, `/api/stt`): speak in Egyptian Arabic or English.
  Local Whisper (or the browser) turns speech into text; the assistant calls the replay, 16-day planner, Field Pulse, time
  machine, prices and robot state, and answers with an Egyptian neural voice. Works offline with a rules engine; with an API
  key, Claude chooses the tools and a number auditor rejects any figure no tool produced.
- `scripts/fetch_training.py`: 45 cropland points across Egypt for more training data
- `AGENTS.md`, `CLAUDE.md`, `CONTINUE.md`, `agents/` board (structure adapted from Yaseen Abdelal's repo); `tests/test_agents.py`
- `/methods`: new sections on Field Pulse and the voice assistant, with live numbers

## 0.4.0 — 14 Nov 2026: time machine, canal mode, Egyptian voice, methods page
- **Time machine** (`/api/timemachine`): MODIS NDVI says, season by season since 2015, whether this field was green or bare;
  each season is replayed on that year's real NASA POWER weather for the farmer's crops and for the suggestion; running
  totals of water saved and extra profit
- **Canal mode** (`/api/canal`): neighbours on one canal pick among rotations within 10 points of their own best and
  stagger summer sowing by ±14 days to cut the canal's peak weekly demand (demo canal: 17,374 → 7,822 m³, −55 %)
- **Egyptian Arabic voice** (`/api/speak`): Microsoft Edge neural voices ar-EG-Salma / ar-EG-Shakir via edge-tts, free,
  no key, MP3 cached; the advice is written in Egyptian colloquial Arabic; browser speech is the fallback
- **Lenses now differ**: farmer (next irrigation, scout, time machine, canal), investor (stress-tested profit, profit
  distribution, prices, canal), scientist (backtest, equations, validation)
- **Stress test** (`/api/sensitivity`): the same three rotations re-run under price ±20 %, dry, hot, and hot+dry+cheap
- **Methods page** (`/methods`): how it works in plain language, with live numbers from the validation and backtest
- Field-notebook visual style throughout; wording fixes

## 0.3.0 — 14 Nov 2026: backtest, look-ahead, map-first design
- qa/backtest.py: last three seasons, forecast from earlier years only, CRPS vs 'same as last year' and long-term mean
- Climate-adjusted replay (site Tmax trend), adopted because it wins the backtest
- 16-day irrigation planner (Open-Meteo forecast + FAO-56 balance) and SEAS5 seasonal outlook (context only)
- Map-first interface: sheet + full-screen map, tool rail, layer panel, timeline bar; field-notebook styling, no emoji
- Fixes: Council hidden in Simple mode; cotton sown 25 Mar (inside the verified window); Gharbia default rotation
- Danger windows: zero-MAD fallback (from Yaseen Abdelal's danger.py)
- docs/SAMPLE_CASES.md for pitch rehearsal

## 0.2.0 — 14 Nov 2026: merge with the AgroTwin scaffold + product map

Merged from Yaseen Abdelal's AgroTwin repo (github.com/Yaseen-Saad/AgroTwin):
- NRCS curve-number runoff (extended here to per-soil, per-cover curve numbers from USDA TR-55)
- FAO-56 Table 12 crop-coefficient corrections (wheat initial 0.70, berseem 0.40 / 0.90 / 0.85)
- severe-deficit days separate from stress days
- the frozen v1 contracts (`contracts/v1`); `POST /api/v1/result` emits the v1 result and is schema-tested

Kept from this engine: the vectorised replay, beam search and ranking, Scout fusion with twin-experiment
calibration, quoted price sources, the validation wall, the Council and Number Auditor, and the Field Card.
Not carried over: the fixture-only Next.js front end and its static SVG map (superseded by the live map below).

New product features:
- Simple / Advanced modes; a guided 3-step flow in Simple mode
- Interactive map: live NASA GIBS layers (NDVI, SMAP root-zone soil moisture, IMERG rain, land-surface
  temperature, true colour) with a date picker and time-lapse, official legends, place search (Arabic and
  English), locate-me, a click-anywhere inspector (`GET /api/point`)
- Draw the field boundary → area in feddans and totals for the whole farm
- My farms: saved fields, boundaries and plan history (`/api/farms`)
- Installable web app (manifest and network-first service worker)
- Fusion calibration now also bounds every reading horizon, not just the average

## 0.1.0 — 14 Nov 2026: AgroTwin engine
Daily FAO-56 replay since 1991, Harvest Barcode, Scout fusion, validation wall, three lenses, Council, Field Card.
