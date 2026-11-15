# Data sources

_AI-generated (Claude, Anthropic) under human review._

| Dataset | Product / version | Resolution | Access | Used for | Status |
|---|---|---|---|---|---|
| NASA POWER daily | AG community, point API; T2M, T2M_MAX, T2M_MIN, RH2M, PRECTOTCORR, ALLSKY_SFC_SW_DWN, WS2M, PS, GWETROOT, GWETTOP | 0.5° × 0.625° (meteorology) | power.larc.nasa.gov, no login | ET0, water balance, heat stress, replay windows, danger windows | cached for 6 sites, 1981 → 2026-11-10 |
| MODIS NDVI | MOD13Q1 v061, band 250m_16_days_NDVI | 250 m, 16-day | ORNL DAAC MODIS web service, no login | crop-history peaks, NDVI suggestion, hindcast | cached 2015 → 2026 |
| MODIS ET | MOD16A2GF, band ET_500m | 500 m, 8-day | ORNL DAAC, no login | hindcast against modelled ETa | cached 2020 → 2026 |
| SoilGrids 2.0 | clay, sand, silt, soc, phh2o, 0–30 cm mean | 250 m | rest.isric.org | soil class → θFC/θWP | cached |
| SMAP L4 | SPL4SMGP (latest version on AppEEARS), sm_rootzone | 9 km, 3-hourly | AppEEARS, Earthdata login | robot bias check, calibration | wired (scripts/fetch_earthdata.py), not fetched |
| GPM IMERG | GPM_3IMERGDF v07, precipitation | 0.1°, daily | earthaccess, Earthdata login | rain cross-check vs POWER and the robot's rain flag | wired, not fetched |
| FAO-56 | Tables 11, 12, 19, 22 | – | publication | stages, Kc, θ, root depth, p | cited in crops.py / soil.py |
| FAO-33 | seasonal Ky | – | publication | yield response | cited in crops.py |
| Prices & costs | see data/prices.csv (source_url per row) | – | Arab Finance, USDA GAIN EG2026-0002/0004/0007, Masrawy, Al Mal, Dostor, Ahram Gate, Amwal Al Ghad | profit | 19 quoted rows, 21 assumption rows |
| Verdex Scout | ESP32 + soil probe, DHT, rain-drop sensor, PTZ camera; leaf model v2_deit3 | field point | MQTT / serial bridge, POST /api/scout/run | fusion, sightings | model real; soil runs SIMULATED until the robot posts |
| NASA GIBS map layers | MODIS_Terra_L3_NDVI_16Day, MODIS_Terra_NDVI_8Day, SMAP_L4_Analyzed_Root_Zone_Soil_Moisture, IMERG_Precipitation_Rate, MODIS_Terra_Land_Surface_Temp_Day, MODIS_Terra_CorrectedReflectance_TrueColor | 250 m – 9 km | gibs.earthdata.nasa.gov WMTS, no login | interactive map with date and time-lapse; official legends bundled | display only, not used in calculations |
| Open-Meteo forecast (non-NASA) | ECMWF/GFS blend: daily FAO ET0, rain, Tmax/Tmin, 16 days | ~10 km | api.open-meteo.com, no key | 16-day irrigation planner | cached 6 h |
| Open-Meteo seasonal (non-NASA) | ECMWF SEAS5 ensemble, daily rain and Tmax, ~6 months | ~36 km | seasonal-api.open-meteo.com, no key | outlook shown as context | not used in scores |
| Text to speech (non-NASA) | Microsoft Edge neural voices ar-EG-SalmaNeural / ar-EG-ShakirNeural via the edge-tts package | – | online, no key | reading the advice aloud in Egyptian Arabic | MP3 cached in data/audio; browser speech as fallback |
| Speech recognition (non-NASA) | OpenAI Whisper "small" weights via faster-whisper (MIT licence), run locally | – | downloaded once from Hugging Face, then offline | voice assistant input | no audio leaves the laptop; the browser recogniser is tried first |
| MODIS NDVI via NASA GIBS | MODIS_Terra_L3_NDVI_16Day tiles (EPSG:4326, level 8, ≈240 m) decoded with NASA's GIBS colour map MODIS_L3_NDVI (0.005 bins) | 250 m, 16-day | gibs.earthdata.nasa.gov, no login | Field Pulse v2 training (≈1,200 Delta pixels, 2018–2026) and the Delta peer table | 93 MB, 3 tiles; error 0.002 vs ORNL MOD13Q1 where pixels align |
| Prithvi-EO-2.0-300M-TL | NASA–IBM geospatial foundation model, pre-trained on NASA HLS (Apache-2.0) | 30 m HLS chips, 224 px, 4 dates | Hugging Face ibm-nasa-geospatial, 1.33 GB | field embeddings for the crop-type detector | downloaded; HLS imagery and labels pending |
| Field Pulse training set | MOD13Q1 NDVI + POWER daily at 12 cached fields (45 more listed in scripts/fetch_training.py) | 250 m / 0.5° | as above | training and testing our model | 6,420 samples, 2015 → 2026 |
| Language model (non-NASA) | NVIDIA Build API, nvidia/nemotron-3-ultra-550b-a55b (or Claude / any OpenAI-compatible model via .env) | — | API key in agrotwin/.env (git-ignored) | open conversation in Plan Mode and the assistant, grounded in computed facts | numbers audited; offline engine as fallback |
| Map tiles | Esri World Imagery, OpenStreetMap | – | online only | background map | the rest of the app works offline |
