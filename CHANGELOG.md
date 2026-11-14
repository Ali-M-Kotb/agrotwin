# Changelog

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
