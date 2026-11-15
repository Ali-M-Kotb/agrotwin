"""Crop table: agronomy from FAO papers, money from data/prices.csv.

Sources (each field below is tagged with one of these):
  FAO56_T11  stage lengths      FAO-56 Table 11, adapted to the Delta / Maghreb calendar
  FAO56_T12  Kc ini / mid / end FAO-56 Table 12 (wheat: non-frozen-soil row 0.70; berseem: averaged
             cutting effects 0.40/0.90/0.85, both per the FAO-56 check in Yaseen Abdelal's AgroTwin crops.yaml)
  FAO56_T22  max root depth and depletion fraction p (range midpoints)
  FAO33      seasonal yield response factor Ky, FAO Irrigation & Drainage Paper 33
  heat       Tmax limits in the sensitive window: commonly cited agronomic thresholds,
             tagged assumption:heat_limits until an agronomist reviews them
  calendar   sowing dates for Egypt / Morocco: assumption:planting_windows

Money defaults below are placeholders tagged assumption:prices_default; econ.py
overrides them from data/prices.csv rows that carry a quoted source.

1 feddan = 4,200 m² = 0.42 ha  →  1 mm over a feddan = 4.2 m³.
"""

FEDDAN_HA = 0.42
MM_TO_M3_PER_FEDDAN = 4.2

SRC = {
    "stages": "quoted:FAO-56 Table 11 (adapted: assumption:planting_windows)",
    "kc": "quoted:FAO-56 Table 12",
    "root_m": "quoted:FAO-56 Table 22 (midpoint)",
    "p": "quoted:FAO-56 Table 22",
    "ky": "quoted:FAO-33 seasonal Ky",
    "heat_tmax": "assumption:heat_limits",
    "sow": "assumption:planting_windows",
    "n_credit": "assumption:legume_n_credit",
    "money": "assumption:prices_default",
}

# stages: (initial, development, mid, late) days; critical: sensitive window (days after sowing)
# money: price EGP/t, yield t/feddan (potential, Ym), cost EGP/feddan
CROPS = {
    "wheat": dict(name="Wheat", name_ar="القمح", season="winter", family="Poaceae",
                  sow=(11, 15), stages=(25, 50, 65, 30), kc=(0.70, 1.15, 0.30), root_m=1.5, p=0.55,
                  ky=1.05, heat_tmax=32, critical=(95, 140), n_credit=(0, 0), residue=5, rainfed_ok=True,
                  price=14700, yield_t=2.7, cost=20000),
    "barley": dict(name="Barley", name_ar="الشعير", season="winter", family="Poaceae",
                   sow=(11, 15), stages=(20, 30, 60, 30), kc=(0.30, 1.15, 0.25), root_m=1.2, p=0.55,
                   ky=1.00, heat_tmax=33, critical=(75, 115), n_credit=(0, 0), residue=4, rainfed_ok=True,
                   price=10000, yield_t=1.2, cost=6000),
    "berseem": dict(name="Berseem clover", name_ar="البرسيم", season="winter", family="Fabaceae",
                    sow=(10, 20), stages=(20, 30, 115, 10), kc=(0.40, 0.90, 0.85), root_m=0.8, p=0.50,
                    ky=1.10, heat_tmax=38, critical=(120, 170), n_credit=(25, 60), residue=6, rainfed_ok=False,
                    price=1000, yield_t=30.0, cost=9000),
    "faba": dict(name="Faba bean", name_ar="الفول البلدي", season="winter", family="Fabaceae",
                 sow=(11, 1), stages=(20, 30, 60, 40), kc=(0.50, 1.15, 0.30), root_m=0.6, p=0.45,
                 ky=1.15, heat_tmax=30, critical=(60, 105), n_credit=(15, 40), residue=4, rainfed_ok=True,
                 price=30000, yield_t=1.4, cost=15000),
    "sugarbeet": dict(name="Sugar beet", name_ar="بنجر السكر", season="winter", family="Amaranthaceae",
                      sow=(10, 15), stages=(30, 45, 75, 50), kc=(0.35, 1.20, 0.70), root_m=0.9, p=0.55,
                      ky=1.00, heat_tmax=38, critical=(150, 200), n_credit=(0, 0), residue=2, rainfed_ok=False,
                      price=2000, yield_t=22.0, cost=25000),
    "potato": dict(name="Potato (winter)", name_ar="البطاطس (شتوي)", season="winter", family="Solanaceae",
                   sow=(11, 1), stages=(25, 30, 45, 30), kc=(0.50, 1.15, 0.75), root_m=0.5, p=0.35,
                   ky=1.10, heat_tmax=30, critical=(55, 100), n_credit=(0, 0), residue=1, rainfed_ok=False,
                   price=8000, yield_t=11.0, cost=70000),
    "maize": dict(name="Maize", name_ar="الذرة الشامية", season="summer", family="Poaceae",
                  sow=(5, 15), stages=(25, 40, 45, 30), kc=(0.30, 1.20, 0.35), root_m=1.2, p=0.55,
                  ky=1.25, heat_tmax=38, critical=(60, 85), n_credit=(0, 0), residue=6, rainfed_ok=False,
                  price=13000, yield_t=3.4, cost=20000),
    "sorghum": dict(name="Sorghum", name_ar="الذرة الرفيعة", season="summer", family="Poaceae",
                    sow=(5, 20), stages=(20, 35, 40, 30), kc=(0.30, 1.05, 0.55), root_m=1.5, p=0.55,
                    ky=0.90, heat_tmax=40, critical=(55, 85), n_credit=(0, 0), residue=6, rainfed_ok=False,
                    price=11000, yield_t=2.2, cost=14000),
    "rice": dict(name="Rice", name_ar="الأرز", season="summer", family="Poaceae",
                 sow=(5, 15), stages=(30, 30, 60, 30), kc=(1.05, 1.20, 0.75), root_m=0.5, p=0.20,
                 ky=1.20, heat_tmax=35, critical=(75, 105), n_credit=(0, 0), residue=4, rainfed_ok=False,
                 price=15000, yield_t=4.0, cost=22000, flooded=True),
    "cotton": dict(name="Cotton", name_ar="القطن", season="summer", family="Malvaceae",
                   sow=(3, 25), stages=(30, 50, 60, 50), kc=(0.35, 1.18, 0.60), root_m=1.3, p=0.65,
                   ky=0.85, heat_tmax=38, critical=(80, 130), n_credit=(0, 0), residue=3, rainfed_ok=False,
                   price=76000, yield_t=1.1, cost=35000),
    "tomato": dict(name="Tomato (summer)", name_ar="الطماطم (صيفي)", season="summer", family="Solanaceae",
                   sow=(5, 1), stages=(30, 40, 40, 25), kc=(0.60, 1.15, 0.80), root_m=0.9, p=0.40,
                   ky=1.05, heat_tmax=35, critical=(60, 100), n_credit=(0, 0), residue=2, rainfed_ok=False,
                   price=5000, yield_t=18.0, cost=70000),
    "soybean": dict(name="Soybean", name_ar="فول الصويا", season="summer", family="Fabaceae",
                    sow=(5, 20), stages=(20, 35, 60, 25), kc=(0.40, 1.15, 0.50), root_m=0.9, p=0.50,
                    ky=0.85, heat_tmax=37, critical=(55, 95), n_credit=(15, 40), residue=4, rainfed_ok=False,
                    price=22000, yield_t=1.3, cost=15000),
}

# Rain-fed fields on the north-west coast and the Maghreb are low-input (no fertiliser
# programme, little labour); Delta cost studies would make every rain-fed crop a loss.
# EGP / feddan, tagged assumption:rainfed_low_input_costs until a local cost study is found.
RAINFED_COSTS = {"barley": 4000, "wheat": 6000, "faba": 6000}

FALLOW = "fallow"
FALLOW_INFO = dict(name="Fallow", name_ar="بور (بدون زراعة)", family=None)

FAMILY_AR = {
    "Poaceae": "النجيلية", "Fabaceae": "البقولية", "Amaranthaceae": "القطيفية",
    "Solanaceae": "الباذنجانية", "Malvaceae": "الخبازية", "Rosaceae": "الوردية",
}

N_PRICE_EGP_KG = 25.0   # assumption:prices_default until prices.csv has a quoted n_price

# The robot's leaf model (8 classes) mapped onto plant families.
DISEASE_CLASSES = {
    "Apple___Apple_scab": ("Rosaceae", "Apple scab", True),
    "Apple___Black_rot": ("Rosaceae", "Apple black rot", True),
    "Apple___healthy": ("Rosaceae", "Healthy apple leaf", False),
    "Potato___Early_blight": ("Solanaceae", "Potato early blight", True),
    "Potato___Late_blight": ("Solanaceae", "Potato late blight", True),
    "Potato___healthy": ("Solanaceae", "Healthy potato leaf", False),
    "Strawberry___Leaf_scorch": ("Rosaceae", "Strawberry leaf scorch", True),
    "Strawberry___healthy": ("Rosaceae", "Healthy strawberry leaf", False),
}

def name(c: str, lang: str = "en") -> str:
    if c == FALLOW:
        return FALLOW_INFO["name_ar" if lang == "ar" else "name"]
    return CROPS[c]["name_ar" if lang == "ar" else "name"]

def family(c: str):
    return None if c == FALLOW else CROPS[c]["family"]

def total_days(c: str) -> int:
    return sum(CROPS[c]["stages"])
