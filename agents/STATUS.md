# Status snapshot

> Updated: 2026-11-14 · Version **0.6.1** · Tests: `make test` → 39 passed

## One line

The product runs end to end on real NASA data, offline-capable, in Arabic and English. It has its own trained model
(Field Pulse) and a voice assistant that answers in Egyptian Arabic. Robot data is SIMULATED until the Verdex
Scout posts a real run. Deck and video are not started.

## What works (each verified in the browser this session)

| Area | State |
|---|---|
| Replay + ranking (32 years, 3 rotations, ranges) | done |
| Backtest, last 3 seasons, 3 sites (`qa/BACKTEST.md`) | done: about 50% better than "same as last year" |
| Field Pulse model (`qa/PULSE.md`) | done: 45% better than persistence at 16 days, 81% coverage; 12 fields only |
| Plan Mode (`/api/plan`, `/api/plan/chat`) | done: rules engine offline; Claude engine needs a key |
| Uncertainty: price, canal shortfall, FAO-29 salinity | done |
| Field Pulse v2 (1,200 GIBS pixels, independent test) | done |
| Voice assistant (`/api/chat`, `/api/stt`, `/api/speak`) | done: rules engine offline; Claude engine needs `ANTHROPIC_API_KEY` (not tested live) |
| Time machine, canal mode, stress test | done |
| Lenses (farmer, investor, scientist) differ | done |
| `/methods` page with live numbers | done |
| Map (GIBS layers, drawing, inspector, farms) | done |

## Blocked / waiting on humans

- ORNL MODIS service unreachable on 14 Nov → Field Pulse has 12 fields; run `scripts/fetch_training.py` when it's back, then `qa/pulse_train.py`.
- Real robot run + probe calibration (Ali, Mostafa).
- Native Egyptian Arabic review of `frontend/i18n/ar.json`, `content/*.json` and `backend/chat.py` replies.
- Earthdata login for SMAP / IMERG time series.
- Deck (7 slides) and 30-second video.
