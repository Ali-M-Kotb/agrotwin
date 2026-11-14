# Changelog

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
