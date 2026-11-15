"""Soil classes and water-holding limits.

theta_FC / theta_WP are midpoints of the ranges in FAO-56 (Allen et al. 1998),
Table 19 "Typical soil water characteristics for different soil types".
FAO-56 has no 'clay loam' row; we use its 'silty clay loam' row and say so.
"""

FAO56_T19 = "quoted:https://www.fao.org/4/x0490e/x0490e0c.htm#TopOfPage (FAO-56 Table 19, range midpoints)"

SOIL_CLASSES = {
    #             theta_FC, theta_WP   (m3/m3)
    "sand":       (0.12, 0.045),
    "sandy_loam": (0.23, 0.110),
    "loam":       (0.25, 0.120),
    "clay_loam":  (0.335, 0.205),   # FAO-56 'silty clay loam' row
    "clay":       (0.36, 0.220),
}

NAMES = {
    "sand": ("Sand", "رملية"), "sandy_loam": ("Sandy loam", "رملية طميية"),
    "loam": ("Loam", "طميية"), "clay_loam": ("Clay loam", "طينية طميية"),
    "clay": ("Clay", "طينية"),
}

def classify(soil: dict) -> str:
    """USDA-triangle shortcut from SoilGrids sand/clay %, collapsed to the 5 classes."""
    clay = soil.get("clay") or 35
    sand = soil.get("sand") or 30
    if clay >= 40:
        return "clay"
    if clay >= 27:
        return "clay_loam"
    if sand >= 85:
        return "sand"
    if sand >= 52 and clay < 20:
        return "sandy_loam"
    return "loam"

def taw_per_m(soil_class: str) -> float:
    fc, wp = SOIL_CLASSES[soil_class]
    return 1000 * (fc - wp)          # mm of plant-available water per m of root zone

def relative_wetness(vwc: float, soil_class: str) -> float:
    fc, wp = SOIL_CLASSES[soil_class]
    return min(1.0, max(0.0, (vwc - wp) / (fc - wp)))
