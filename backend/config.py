"""Every judgment-call threshold in one place, each with an assumption tag.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

The Scientist lens lists this table verbatim, so a judge can see every number we
chose (rather than measured) and change it. Values are read through A[...] so a
typo fails loudly.
"""

ASSUMPTIONS = {
    # replay
    "replay_first_year": (1991, "first replay start year (plan: every year since 1991)"),
    "climate_adjust": (True, "warm each past year to today's climate by the site's measured Tmax trend before replay (wins the 3-season backtest)"),
    "canal_shift_days": (14, "canal mode may move a farm's summer sowing this many days earlier or later (inside the planting window)"),
    "spinup_days": (120, "bare-soil spin-up before each window so starting soil water comes from that year's weather"),
    "gap_days": (5, "minimum days between harvest and the next sowing"),
    # soil water
    "bare_root_m": (0.30, "depth of the evaporating layer on bare / fallow soil, m"),
    "zr_min_m": (0.30, "rooting depth at sowing, m (grows linearly to the crop maximum by end of development)"),
    "bare_evap_coef": (0.50, "bare-soil evaporation = coef x (relative wetness) x ET0"),
    "heavy_rain_mm": (25.0, "daily rain above this counts as heavy (runoff, erosion exposure)"),
    "runoff_cn_crop": ({"sand": 67, "sandy_loam": 78, "loam": 78, "clay_loam": 85, "clay": 89},
                       "NRCS curve number for cropped days by soil class (USDA TR-55 Table 2-2b, row crops, straight row, good; hydrologic groups A/B/B/C/D)"),
    "runoff_cn_bare": ({"sand": 77, "sandy_loam": 86, "loam": 86, "clay_loam": 91, "clay": 94},
                       "NRCS curve number for bare / fallow days (USDA TR-55 Table 2-2b, fallow, bare soil)"),
    "irrigation_efficiency": (0.60, "field application efficiency of surface irrigation (net / gross)"),
    "rice_percolation_mm_day": (3.0, "extra daily water a flooded rice field loses to percolation"),
    "rice_puddling_mm": (150.0, "water to puddle a rice field before transplanting"),
    # yield and money
    "heat_loss_per_day": (0.05, "yield lost per day above the crop's Tmax limit in its sensitive window"),
    "heat_loss_max": (0.35, "cap on heat yield loss"),
    "heat_stress_days": (3, "days above the Tmax limit that make a heat-stress season"),
    "amber_margin": (0.10, "barcode stripe is amber when profit is between 0 and this share of total cost"),
    "water_cost_egp_m3": (0.0, "farmers pay no volumetric fee for canal water in Egypt; set >0 to model pumping"),
    "cap_exclusion_share": (0.25, "exclude a rotation if the water cap leaves more than this share of its need unmet in a median year"),
    "tie_band": (0.05, "top two scores within this share of the score range = no clear winner"),
    # fusion
    "sigma_floor": (0.05, "minimum reading error used in fusion (relative wetness units)"),
    "sigma_model": (0.10, "model + analog-mismatch error added in quadrature to the sensor error (twin experiment: coverage stays near 80% from 0.03 to 0.15)"),
    "ess_min": (5.0, "if fewer past years effectively carry the answer, temper the likelihood until at least this many do"),
    "post_wetting_hours": (24, "drop readings taken this soon after rain or irrigation"),
    "confidence_bins": ((10, 40), "fewer than 10 valid readings = low, 10-40 = medium, more = high"),
    "coverage_band": ((0.70, 0.90), "an honest 80% range should cover about this share of hidden truths"),
    # vision
    "vision_min_conf": (0.60, "leaf-model labels below this confidence become 'unknown'"),
    "vision_alert": ((0.20, 20), "disease share and minimum image count that raise a review flag"),
    # danger windows
    # uncertainty beyond weather (Monte Carlo layer, replay.py / econ.mc_profit_year)
    "mc_draws": (40, "price and canal-supply draws per replayed year (seeded, reproducible)"),
    "price_cv": ({"wheat": 0.05, "rice": 0.20, "maize": 0.15, "cotton": 0.20, "tomato": 0.35, "potato": 0.30, "default": 0.15},
                 "season-to-season coefficient of variation of farm-gate price (wheat is bought at a state-announced price)"),
    "canal_short_prob": (0.20, "share of summers in which canal supply falls short at the field (farmer can change it in Plan Mode)"),
    "canal_short_supply": (0.75, "in a short summer, share of the crop's irrigation need that actually arrives"),
    "salinity_ece": (0.0, "soil salinity ECe, dS/m (0 = not saline; set from a lab test or the farmer's answer in Plan Mode)"),
    "danger_rule": ((2.0, 5), "|robust z| above 2.0 for 5+ consecutive days = danger window"),
}


class _A(dict):
    def __getitem__(self, k):
        return ASSUMPTIONS[k][0]


A = _A()


def tag(name: str) -> str:
    assert name in ASSUMPTIONS, name
    return f"assumption:{name}"


def table() -> list[dict]:
    return [dict(name=k, value=v[0], meaning=v[1], source=f"assumption:{k}") for k, v in ASSUMPTIONS.items()]
