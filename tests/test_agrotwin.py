"""AgroTwin tests. AI-generated (Claude, Anthropic) under human review.

    make test   (or: python -m pytest -q)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import council  # noqa: E402
import data_sources as ds  # noqa: E402
import econ  # noqa: E402
import fusion as fu  # noqa: E402
import replay as rp  # noqa: E402
import scout  # noqa: E402
import waterbalance as wb  # noqa: E402
from crops import CROPS  # noqa: E402


def flat_weather(et0=5.0, rain=0.0, tmax=25.0, years=range(1990, 2001)):
    idx = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-31")
    df = pd.DataFrame(index=idx)
    df["ET0"], df["PRECTOTCORR"], df["T2M_MAX"] = et0, rain, tmax
    return df


# --- water balance -----------------------------------------------------------

def test_golden_case_irrigated_wheat_etc():
    """Hand arithmetic: wheat stages (25, 50, 65, 30), Kc (0.70, 1.15, 0.30), ET0 = 5 mm/day.
    Σ Kc = 25×0.70 + [50×0.70 + 0.45×(0+…+49)/50] + 65×1.15 + 30×(1.15+0.30)/2
         = 17.5 + 46.025 + 74.75 + 21.75 = 160.025  →  ETc = 800.125 mm.
    Irrigated, no cap → no stress → ETa = ETc."""
    w = flat_weather()
    wx = wb.weather_matrices(w, wb.windows(w)[:2])
    sim = wb.simulate([("wheat",) + ("fallow",) * 5], wx, "clay_loam", irrigated=True)
    assert sim["etc"][0, :, 0] == pytest.approx(800.125, abs=1e-6)
    assert sim["eta"][0, :, 0] == pytest.approx(800.125, abs=1e-6)
    assert sim["deficit_days"][0, :, 0].sum() == 0


def test_mass_balance_closes_within_1mm():
    w = flat_weather(rain=1.5)
    w.loc[w.index.day == 10, "PRECTOTCORR"] = 40.0       # heavy days → runoff + percolation
    wx = wb.weather_matrices(w, wb.windows(w))
    for irrigated in (True, False):
        sim = wb.simulate([("wheat", "rice") * 3, ("faba", "fallow") * 3], wx, "loam", irrigated)
        res = sim["_in"] - sim["_ro"] - sim["_et"] - sim["_dp"] + (sim["_Dr1"] - sim["_Dr0"]) + sim["_clamp"]
        assert np.abs(res).max() < 1.0


def test_fallow_has_zero_transpiration_and_counts_bare_days():
    w = flat_weather()
    wx = wb.weather_matrices(w, wb.windows(w))
    sim = wb.simulate([("fallow",) * 6], wx, "loam", irrigated=False)
    assert sim["transp_days"].sum() == 0 and sim["bare_days"].min() >= 365 * 3


def test_rainfed_never_irrigates_and_stresses():
    w = flat_weather()
    wx = wb.weather_matrices(w, wb.windows(w))
    sim = wb.simulate([("barley", "fallow") * 3], wx, "loam", irrigated=False)
    assert sim["irr_net"].sum() == 0 and sim["deficit_days"][0, :, 0].min() > 0


def test_identical_input_identical_output():
    w = flat_weather(rain=0.8)
    wx = wb.weather_matrices(w, wb.windows(w))
    a = wb.simulate([("faba", "maize") * 3], wx, "clay", True)
    b = wb.simulate([("faba", "maize") * 3], wx, "clay", True)
    assert np.array_equal(a["eta"], b["eta"]) and np.array_equal(a["irr_gross"], b["irr_gross"])


def test_calendar_rules():
    assert wb.calendar(("wheat", "maize") * 3) is not None
    assert wb.calendar(("wheat", "cotton") * 3) is None          # cotton sown before wheat harvest
    assert wb.calendar(("potato", "cotton", "wheat", "maize", "faba", "maize")) is not None   # cotton sown 25 Mar, after potato
    assert wb.calendar(("rice", "wheat") * 3) is None             # rice in a winter slot


# --- economics & ranking -----------------------------------------------------

@pytest.fixture(scope="module")
def delta():
    site = ds.load_site(31.25, 30.95, offline=True, wait_for_soil=False)
    wx = wb.weather_matrices(site["weather"], wb.windows(site["weather"]))
    return site, wx


def test_three_rotations_under_two_seconds(delta):
    import time
    site, wx = delta
    t = time.time()
    res = rp.run(wx, rp.Plan(existing=("wheat", "rice")), econ.load_prices(), 35)
    assert time.time() - t < 2.0
    assert [r["rotation_id"] for r in res["rotations"]] == ["existing", "alt_1", "alt_2"]
    assert len(res["years"]) >= 30 and res["years"][0] == 1991
    for r in res["rotations"]:
        assert len(r["barcode"]) == len(res["years"])
        assert r["profit"]["p10"] <= r["profit"]["median"] <= r["profit"]["p90"]


def test_profit_falls_with_price(delta):
    site, wx = delta
    a = rp.run(wx, rp.Plan(existing=("wheat", "rice")), econ.load_prices(), 35)
    b = rp.run(wx, rp.Plan(existing=("wheat", "rice"), price_mult=0.7), econ.load_prices(), 35)
    assert b["rotations"][0]["profit"]["median"] < a["rotations"][0]["profit"]["median"]


def test_legume_earns_nitrogen_credit(delta):
    site, wx = delta
    sim = wb.simulate([("faba", "maize") * 3, ("wheat", "maize") * 3], wx, "clay_loam", True)
    eco = econ.slot_economics(sim, econ.load_prices())
    assert eco["ncredit"][0, :, 1].min() > 0 and eco["ncredit"][1].sum() == 0


def test_weights_change_ranking(delta):
    site, wx = delta
    w = rp.run(wx, rp.Plan(existing=("wheat", "rice"), weights=dict(water=5, soil=0, profit=0, risk=0)), econ.load_prices(), 35)
    p = rp.run(wx, rp.Plan(existing=("wheat", "rice"), weights=dict(water=0, soil=0, profit=5, risk=0)), econ.load_prices(), 35)
    best = lambda res: next(r for r in res["rotations"] if r["rotation_id"] == res["order"][0])
    assert best(w)["water_m3"]["median"] <= best(p)["water_m3"]["median"]


def test_disease_sighting_demotes_host_family():
    plan = rp.Plan(existing=("wheat", "maize"))
    sick = rp.Plan(existing=("wheat", "maize"), disease_families={"Solanaceae": "Potato late blight"})
    rot = ("potato", "maize", "wheat", "soybean", "faba", "maize")
    assert rp.soil_rules(rot, sick)[0] < rp.soil_rules(rot, plan)[0]


def test_water_cap_excludes_thirsty_rotation(delta):
    site, wx = delta
    res = rp.run(wx, rp.Plan(existing=("wheat", "maize"), water_cap_m3={"winter": 1500, "summer": 2500}),
                 econ.load_prices(), 35)
    for m in res["_all"][1:]:
        if "rice" in m["seq"]:
            assert m["excluded"]["is_excluded"]


# --- fusion ------------------------------------------------------------------

def test_no_readings_uniform_weights():
    wet = np.random.default_rng(0).random((20, 365))
    fw = fu.weights_from({}, wet, 0.1, 5)
    assert np.allclose(fw["w"], 1 / 20)


def test_consistent_readings_concentrate_weights():
    rng = np.random.default_rng(1)
    wet = np.clip(rng.random((25, 1)) + 0.05 * rng.standard_normal((25, 200)), 0, 1)
    obs = {d: float(wet[3, d]) for d in range(150)}
    fw = fu.weights_from(obs, wet, 0.05, 5)
    assert fw["w"].argmax() == 3 and fw["ess"] >= fu.A["ess_min"] - 1e-9


def test_doubling_sigma_never_narrows():
    rng = np.random.default_rng(2)
    wet = rng.random((25, 200))
    obs = {d: float(wet[5, d]) for d in range(60)}
    a, b = fu.weights_from(obs, wet, 0.1, 5), fu.weights_from(obs, wet, 0.2, 5)
    assert b["ess"] >= a["ess"] - 1e-9


def test_fusion_refuses_without_calibration():
    with pytest.raises(fu.FusionRefused):
        fu.fuse([{"run_id": "x", "mode": "LIVE", "points": [{"t": "2026-11-01T00:00:00+00:00", "soil_raw": 40}]}],
                None, ("barley", "fallow") * 3, None, "loam", False)


# --- scout -------------------------------------------------------------------

def test_scout_run_contract():
    good = dict(run_id="run_t1", site_id="test", mode="REPLAY", robot="verdex", sent_at="2026-11-14T10:00:00Z",
                points=[dict(t="2026-11-14T09:00:00Z", soil_raw=41.0, air_temp_c=22.0, air_rh_pct=60, rain_flag=False)])
    assert scout.validate(good) == []
    assert scout.validate({**good, "mode": "MAYBE"})
    assert scout.validate({**good, "points": [dict(t="x", air_rh_pct=140)]})
    assert scout.validate({**good, "mode": "SIMULATED"})          # must name truth_year


def test_calibration_needs_three_samples():
    with pytest.raises(ValueError):
        scout.calibrate("test", [dict(raw=10, vwc=0.1), dict(raw=60, vwc=0.3)], "loam")


# --- Number Auditor: 10 bad sentences blocked, 10 good pass -------------------

RESULT = dict(years=list(range(1991, 2023)), rotations=[
    dict(rotation_id="existing", label=dict(en="Wheat → Rice (×3)", ar="القمح ← الأرز (×3)"),
         profit=dict(p10=54167.2, median=57419.4, p90=60009.0), water_m3=dict(median=9465.0),
         worst_year=dict(year=1999, profit=49028.5), loss_year_share=dict(value=0.0625)),
    dict(rotation_id="alt_1", label=dict(en="Faba bean → Maize (×3)", ar="الفول البلدي ← الذرة الشامية (×3)"),
         profit=dict(p10=76478.0, median=77485.0, p90=77485.0), water_m3=dict(median=7069.0),
         worst_year=dict(year=2012, profit=-1200.4), loss_year_share=dict(value=0.03125))])
P = "rotations[1]"
GOOD = [
    dict(text="Profit stayed between 76,478 and 77,485 EGP.", numbers=[dict(path=f"{P}.profit.p10", shown_as="76,478"), dict(path=f"{P}.profit.p90", shown_as="77,485")]),
    dict(text="The worst window began in 2012.", numbers=[dict(path=f"{P}.worst_year.year", shown_as="2012")]),
    dict(text="It lost money in 3% of past years.", numbers=[dict(path=f"{P}.loss_year_share.value", shown_as="3%")]),
    dict(text="الربح بين ٧٦٬٤٧٨ و٧٧٬٤٨٥ جنيه.", numbers=[dict(path=f"{P}.profit.p10", shown_as="٧٦٬٤٧٨"), dict(path=f"{P}.profit.p90", shown_as="٧٧٬٤٨٥")]),
    dict(text="Faba bean → Maize (×3) uses 7,069 m³.", numbers=[dict(path=f"{P}.water_m3.median", shown_as="7,069")]),
    dict(text="It saves about 2,396 m³ a year.", numbers=[dict(path="rotations[0].water_m3.median - rotations[1].water_m3.median", shown_as="2,396")]),
    dict(text="We replayed 32 seasons.", numbers=[dict(path="years.length", shown_as="32")]),
    dict(text="The worst year would have earned -1,200 EGP.", numbers=[dict(path=f"{P}.worst_year.profit", shown_as="-1,200")]),
    dict(text="Satellites cannot see salinity.", numbers=[]),
    dict(text="In the historical record, the current rotation made 57,419 EGP in a median year.", numbers=[dict(path="rotations[0].profit.median", shown_as="57,419")]),
]
BAD = [
    dict(text="Profit will be 80,000 EGP.", numbers=[]),                                                   # undeclared + certainty
    dict(text="Profit stayed above 76,000 EGP.", numbers=[dict(path=f"{P}.profit.p10", shown_as="76,000")]),  # wrong value
    dict(text="This plan guarantees a profit.", numbers=[]),                                              # certainty
    dict(text="It uses 7,069 m³ and saves 3,000 m³.", numbers=[dict(path=f"{P}.water_m3.median", shown_as="7,069")]),  # one undeclared
    dict(text="The worst window began in 2013.", numbers=[dict(path=f"{P}.worst_year.year", shown_as="2013")]),
    dict(text="Profit is 76,478 EGP.", numbers=[dict(path=f"{P}.profit.p11", shown_as="76,478")]),          # bad path
    dict(text="الربح مضمون هذا العام.", numbers=[]),                                                      # Arabic certainty
    dict(text="الربح ٩٠٬٠٠٠ جنيه.", numbers=[]),                                                          # Arabic-Indic undeclared
    dict(text="It lost money in 30% of years.", numbers=[dict(path=f"{P}.loss_year_share.value", shown_as="30%")]),
    dict(text="It will certainly save water.", numbers=[]),
]


def test_auditor_passes_all_good():
    for c in GOOD:
        ok, why = council.audit_claim(c, RESULT)
        assert ok, (c["text"], why)


def test_auditor_blocks_all_bad():
    for c in BAD:
        ok, _ = council.audit_claim(c, RESULT)
        assert not ok, c["text"]


# --- v1 contract (shared with Yaseen Abdelal's AgroTwin repo) ---------------

def test_v1_contract_valid_for_irrigated_and_rainfed():
    from fastapi.testclient import TestClient
    import app as api
    c = TestClient(api.app)
    for lat, lon, ex in ((31.25, 30.95, ["wheat", "rice"]), (31.28, 27.35, ["barley", "fallow"])):
        r = c.post("/api/v1/result", json=dict(lat=lat, lon=lon, existing=ex))
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["schema_version"] == "1.0.0" and len(doc["rotations"]) == 3
        for rot in doc["rotations"]:
            m = rot["metrics"]["profit_per_ha"]
            assert m["p10"] <= m["median"] <= m["p90"]


def test_runoff_curve_number_behaviour():
    import waterbalance as wb
    w = flat_weather(rain=0.0)
    w.loc[w.index.day == 5, "PRECTOTCORR"] = 60.0
    wx = wb.weather_matrices(w, wb.windows(w)[:3])
    sand = wb.simulate([("fallow",) * 6], wx, "sand", False)
    clay = wb.simulate([("fallow",) * 6], wx, "clay", False)
    assert clay["_ro"].sum() > sand["_ro"].sum() > 0          # clay sheds more of a 60 mm storm
