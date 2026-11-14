# Decision log (append-only)

## DEC-001 · Merge rather than restart (14 Nov)
Kept this engine (vectorised replay, fusion, validation wall) and adopted from Yaseen's repo the curve-number runoff,
FAO Table 12 Kc values and the v1 contracts. Reason: our engine was further along; theirs had better-verified coefficients.

## DEC-002 · Robot readings only re-weight this season (14 Nov)
The twin experiment showed re-weighting the 3-year outcome was overconfident (coverage 0.57 vs 0.75).

## DEC-003 · Climate-adjust the replay (14 Nov)
Past years are warmed by the site's own Tmax trend because it wins the backtest (irrigation error −29%).

## DEC-004 · Train our own model: Field Pulse (14 Nov)
"Connecting APIs is not a project." We chose a model with real labels (MODIS NDVI) and an honest test (held-out seasons and
held-out fields) over a crop-type or yield model with no ground truth. Hybrid inputs (FAO-56 bucket driven by NDVI) earn
their place: removing them makes the model 10% worse. Ranges are conformal-calibrated.

## DEC-005 · Voice assistant: rules first, Claude optional (14 Nov)
On stage there may be no internet or API key, so a keyword router for Egyptian Arabic answers by default; Claude chooses
tools when a key exists, and any number it says that no tool produced sends the answer back to the rules engine.
Speech recognition runs locally (faster-whisper small) so farmers' voices never leave the laptop.

## DEC-006 · Egyptian voice = Microsoft Edge neural voices via edge-tts (14 Nov)
Free and no key, and the only free ar-EG neural voices we found. Non-NASA, disclosed; MP3s cached; the browser voice is the fallback.
