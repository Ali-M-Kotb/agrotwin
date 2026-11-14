# Project page fields (paste-ready)

_AI-assisted draft (Claude) from Yaseen Abdelal's proposal, edited to match what shipped on 14 Nov 2026.
Check each field's character limit in the form._

**Project name**
AgroTwin: from the sky to the land

**High-level summary**
AgroTwin lets a farmer try a crop rotation against decades of their field's own weather before planting. For one
field it replays every year since 1991 of NASA POWER weather through a daily FAO-56 water balance for the farmer's
current rotation and two alternatives. It shows water, soil and profit as ranges, with a Harvest Barcode of good
and bad years. The Verdex Scout, a small field robot with soil, rain and air sensors and a leaf-disease camera,
adds readings that re-weight the past years. On our rain-fed test site, our own twin experiment shows this
season's profit range narrowing by 44–51% while staying honest. A farmer draws their field on a live map of NASA
layers (NDVI, SMAP soil moisture, IMERG rain) and gets totals for their own feddans. Each result has Farmer, Investor and Scientist
lenses in Arabic or English, a source tag on every number, and a Field Card to print or share on WhatsApp. It
supports farmers and agronomists and lists what satellites cannot see.

**NASA data**
NASA POWER daily meteorology (1981 onward; replay windows 1991–2024): temperature, rain, humidity, wind, solar
radiation and root-zone soil wetness, for reference ET, the water balance, heat stress and danger windows.
MODIS MOD13Q1 NDVI and MOD16A2GF evapotranspiration (via the ORNL DAAC), for crop-history detection and the
hindcast. NASA GIBS map layers (MODIS NDVI and land-surface temperature, SMAP L4 root-zone soil moisture, GPM IMERG
rain) on the interactive field map, with a time-lapse. SMAP L4 and GPM IMERG are wired for the robot bias check and rain cross-check, pending an Earthdata login.
[Delete that last sentence if SMAP/IMERG were fetched; then say what they showed.]

**Space agency partner and other data, resources and tools**
Verdex Scout readings and the plant-health image classifier (prior work by Ali Kotb and Mostafa Dawood, disclosed).
SoilGrids 2.0 (ISRIC). FAO-56 and FAO-33 methods and crop coefficients. Crop prices and costs: 19 quoted figures
(Arab Finance, USDA FAS GAIN EG2026-0002/0004/0007, Masrawy, Al Mal, Dostor, Ahram Gate) and 21 editable
assumptions, all in data/prices.csv. Open-source: Python, FastAPI, NumPy, pandas, PyTorch/timm, Leaflet, Plotly,
qrcode.

**Use of artificial intelligence**
AI coding agents (Claude, from Anthropic) helped write and review the code and documentation under human
supervision; the log is in docs/AI_USE.md and every AI-written file is marked. The Verdex leaf classifier
(DeiT-III, 95.5% on 1,878 grouped held-out images, 8 classes) was trained by its authors before the hackathon.
Optional Council explanations can be written by Claude from the structured result; a Number Auditor blocks any
number the engine did not compute (10/10 seeded bad sentences blocked in tests), and fixed templates are the
fallback. [List any other AI tools used. AI-generated images or video carry a visible AI watermark.]

**Detailed description: what is real, and how we know**
- Water balance: FAO-56 daily root-zone model, mass balance closes to under 1e-11 mm. Golden case hand-checked: wheat ETc = 800.125 mm at ET0 = 5 mm/day.
- Replay: 32 windows × ~40 candidate rotations in about 0.3 s; the three shown (current + 2) ranked by the farmer's sliders.
- Fusion: soil readings re-weight past years with a likelihood corrected for the soil's 25-day memory. A twin
  experiment (hide each year, replay it as readings) sets and checks the error model. On the rain-fed coast,
  135–180 days of readings cut this season's range by 44–51% at about the same coverage as plain history. In Morocco
  it helps only late in the season (29% at 180 days), and we say so. Readings never re-weight future seasons (that was overconfident in our test).
- Hindcast: on the coast, modelled drought days vs MODIS greenness ρ = −0.47 (n = 9).
- Provenance: 1,201 numbers in two full results, 0 without a source tag.
- Honest limits: history is not a forecast; 21 price/cost inputs are assumptions; the soil-robot data in the demo
  is SIMULATED (badge on screen) until the real robot posts; land rent is excluded; planting dates need local review.
