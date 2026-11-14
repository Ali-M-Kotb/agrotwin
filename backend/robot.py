"""Verdex robot link: live telemetry, a virtual robot, and ground-truth calibration.

Live:     the ESP32 publishes JSON on MQTT `farm/telemetry` every 5 s.
          scripts/mqtt_bridge.py forwards it to POST /api/robot/telemetry.
          Anything that can POST JSON (Bluetooth bridge, phone, curl) works too.
Virtual:  with no robot attached, a simulated robot produces readings that are
          anchored to the NASA data for the pin, so the numbers are plausible
          for that field and date. The UI labels every simulated value.

Calibration is the point of the robot in this app: a satellite pixel is 9 km
(SMAP) or ~50 km (POWER); the robot measures the one field the farmer owns.
"""
from __future__ import annotations

import math
import random
import time
from collections import deque
from datetime import date

import numpy as np
import pandas as pd

def plant_available_fraction(wetness: float) -> float:
    """POWER/SMAP root-zone wetness (0 dry … 1 saturated) → share of available water."""
    if wetness is None or np.isnan(wetness):
        wetness = 0.5
    return float(np.clip((wetness - 0.35) / (0.85 - 0.35), 0, 1))

ALIASES = {
    "temp": ("temperatureC", "temperature", "temp", "t", "T"),
    "hum": ("humidityPct", "humidity", "hum", "h", "RH"),
    "soil": ("soilMoisturePct", "soil_moisture", "soilMoisture", "soil", "moisture"),
    "rain": ("rainPct", "rain", "raindrop"),
    "anomaly": ("anomalyScore", "anomaly_score", "anomaly"),
}


def normalize(payload: dict) -> dict:
    out = {}
    for key, names in ALIASES.items():
        for n in names:
            if n in payload and payload[n] is not None:
                try:
                    out[key] = float(payload[n])
                except (TypeError, ValueError):
                    pass
                break
    if "lat" in payload and "lon" in payload:
        out["lat"], out["lon"] = float(payload["lat"]), float(payload["lon"])
    return out


def satellite_wetness(weather: pd.DataFrame) -> tuple[float, str, str]:
    """Latest POWER root-zone wetness, guarded against data-stream breaks.

    POWER switches to a near-real-time product for recent weeks, which can jump
    off its own 40-year range (seen at Kafr El-Sheikh on 2026-10-01: 0.58 → 0.32).
    When that happens we use the 10-year normal for today's date and say so.
    """
    g = weather["GWETROOT"].dropna()
    hist = g[g.index < g.index[-1] - pd.Timedelta(days=60)]
    lo, hi = hist.quantile(0.01) - 0.05, hist.quantile(0.99) + 0.05
    recent = float(g.tail(7).median())
    if lo <= recent <= hi:
        return recent, str(g.index[-1].date()), "latest"
    today = pd.Timestamp(date.today())
    h10 = hist[hist.index.year >= hist.index[-1].year - 10]
    normal = float(h10[abs(h10.index.day_of_year - today.day_of_year) <= 7].median())
    return normal, f"10-yr normal for {today:%d %b}", "normal (recent values off-range)"


class Robot:
    def __init__(self):
        self.readings: deque = deque(maxlen=720)
        self.detections: list[dict] = []
        self.mode = "offline"          # offline | live | simulated
        self.last_live = 0.0
        self.sim = None                # simulation parameters when running

    # -- live -----------------------------------------------------------------
    def ingest(self, payload: dict, source: str = "live") -> dict:
        r = normalize(payload)
        if not r:
            raise ValueError("no recognised sensor fields")
        r["t"] = time.time()
        r["source"] = source
        self.readings.append(r)
        if source == "live":
            self.mode, self.last_live = "live", r["t"]
        return r

    def detect(self, label: str, confidence: float, source: str = "live", image: str | None = None) -> dict:
        d = dict(label=label, confidence=float(confidence), t=time.time(), source=source, image=image)
        self.detections.append(d)
        return d

    def reset(self):
        self.__init__()

    # -- virtual robot ----------------------------------------------------------
    def start_sim(self, weather: pd.DataFrame, lat: float, lon: float):
        today = pd.Timestamp(date.today())
        recent = weather[weather.index.year >= weather.index[-1].year - 10]
        doy = today.day_of_year
        win = recent[(abs(recent.index.day_of_year - doy) <= 3)]
        sat, _, _ = satellite_wetness(weather)
        self.sim = dict(
            lat=lat, lon=lon, t0=time.time(),
            tmax=float(win["T2M_MAX"].mean()), tmin=float(win["T2M_MIN"].mean()),
            rh=float(win["RH2M"].mean()),
            # The virtual field is a little drier than its satellite pixel —
            # the kind of difference calibration exists to catch.
            soil0=100 * plant_available_fraction(sat) * 0.82,
            heading=random.uniform(0, 2 * math.pi), x=0.0, y=0.0,
        )
        self.mode = "simulated"
        for _ in range(12):            # a minute of history so charts aren't empty
            self._sim_step(backfill=True)

    def _sim_step(self, backfill: bool = False):
        s = self.sim
        now = time.time()
        elapsed = now - s["t0"]
        hour = time.localtime(now).tm_hour + time.localtime(now).tm_min / 60
        diurnal = (math.sin((hour - 9) / 24 * 2 * math.pi) + 1) / 2
        temp = s["tmin"] + (s["tmax"] - s["tmin"]) * diurnal + random.gauss(0, 0.3)
        rh = float(np.clip(s["rh"] + 12 * (0.5 - diurnal) + random.gauss(0, 1.5), 10, 100))
        soil = float(np.clip(s["soil0"] - elapsed / 120 + random.gauss(0, 0.8), 3, 100))
        # wander slowly around the pin (~30 m) so the map shows a moving robot
        s["heading"] += random.gauss(0, 0.4)
        s["x"] = float(np.clip(s["x"] + 3 * math.cos(s["heading"]), -30, 30))
        s["y"] = float(np.clip(s["y"] + 3 * math.sin(s["heading"]), -30, 30))
        lat = s["lat"] + s["y"] / 111_000
        lon = s["lon"] + s["x"] / (111_000 * math.cos(math.radians(s["lat"])))
        r = dict(temp=round(temp, 1), hum=round(rh, 1), soil=round(soil, 1), rain=0.0,
                 anomaly=round(abs(random.gauss(0, 0.15)), 3), lat=lat, lon=lon,
                 t=now if not backfill else now - 5 * (12 - len(self.readings)), source="simulated")
        self.readings.append(r)

    def tick(self):
        """Called on every state poll; advances the virtual robot every 5 s."""
        if self.mode == "live" and time.time() - self.last_live > 60:
            self.mode = "simulated" if self.sim else "offline"
        if self.mode == "simulated" and self.sim:
            if not self.readings or time.time() - self.readings[-1]["t"] >= 5:
                self._sim_step()

    # -- calibration against NASA -------------------------------------------------
    def calibration(self, weather: pd.DataFrame, smap: pd.Series | None) -> dict | None:
        rs = [r for r in self.readings if "soil" in r]
        if not rs:
            return None
        recent = rs[-12:]
        robot_soil = float(np.mean([r["soil"] for r in recent]))
        robot_temp = np.mean([r["temp"] for r in recent if "temp" in r]) if any("temp" in r for r in recent) else None

        sat_wet, sat_date, how = satellite_wetness(weather)
        sat_source = "NASA POWER root-zone wetness (MERRA-2)" + ("" if how == "latest" else ", " + how)
        if smap is not None and len(smap.dropna()):
            sm = smap.dropna()
            sat_source, sat_date = "SMAP L4 root-zone", str(sm.index[-1].date())
            # SPL4SMGP root-zone soil moisture is volumetric (m³/m³); ~0.50 is saturation for clay.
            sat_wet = float(np.clip(sm.iloc[-1] / 0.50, 0, 1))
        sat_avail = plant_available_fraction(sat_wet) * 100
        factor = float(np.clip(robot_soil / max(sat_avail, 5), 0.3, 2.0))

        today = pd.Timestamp(date.today())
        w10 = weather[weather.index.year >= weather.index[-1].year - 10]
        win = w10[abs(w10.index.day_of_year - today.day_of_year) <= 3]
        normal_t = float(win["T2M"].mean())
        return dict(
            robot_soil=round(robot_soil, 1), satellite_soil=round(sat_avail, 1),
            satellite_source=sat_source, satellite_date=sat_date,
            factor=round(factor, 2),
            robot_temp=None if robot_temp is None else round(float(robot_temp), 1),
            power_normal_temp=round(normal_t, 1),
            n=len(recent),
        )

    def state(self) -> dict:
        self.tick()
        return dict(mode=self.mode, readings=list(self.readings)[-60:], detections=self.detections[-10:])
