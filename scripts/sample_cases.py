"""Generate docs/SAMPLE_CASES.md: realistic farmer scenarios run through the real engine.

For the team (pitch rehearsal, judge Q&A), not shown in the app. Re-run after any engine change:

    python scripts/sample_cases.py
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app as api  # noqa: E402
import scout  # noqa: E402

c = TestClient(api.app)
f = lambda x: f"{round(x):,}"

CASES = [
    dict(title="Rice farmer in Kafr El-Sheikh who wants to save water",
         who="Owns 3 feddans near Kafr El-Sheikh, grows wheat in winter and rice in summer, worried about canal shortages.",
         body=dict(lat=31.25, lon=30.95, existing=["wheat", "rice"], weights=dict(water=5, soil=2, profit=2, risk=2))),
    dict(title="Same farmer, canal allowance capped",
         who="The irrigation district limits him to 2,500 m³/feddan in winter and 5,000 in summer.",
         body=dict(lat=31.25, lon=30.95, existing=["wheat", "rice"], water_cap_m3=dict(winter=2500, summer=5000))),
    dict(title="Same farmer in a hotter, drier future (+2 °C, −20 % rain)",
         who="Stress test: does the advice hold up if the climate keeps warming?",
         body=dict(lat=31.25, lon=30.95, existing=["wheat", "rice"], temp_offset=2.0, rain_mult=0.8)),
    dict(title="Beheira wheat–maize farmer who cares most about profit",
         who="Commercial grower, 10 feddans, wheat then maize, pays attention to prices.",
         body=dict(lat=30.98, lon=30.40, existing=["wheat", "maize"], weights=dict(water=1, soil=1, profit=5, risk=2))),
    dict(title="Gharbia wheat–maize farmer after a 30 % price drop",
         who="Wheat then maize; all crop prices fall 30 % (a price shock is a user input, never a forecast).",
         body=dict(lat=30.85, lon=30.85, existing=["wheat", "maize"], price_mult=0.7)),
    dict(title="Rain-fed barley on the Matrouh coast (no robot data)",
         who="Bedouin family farm, barley every winter, summer fallow; depends only on rain.",
         body=dict(lat=31.28, lon=27.35, existing=["barley", "fallow"])),
    dict(title="Saïs plain, Morocco: the same tool outside Egypt",
         who="Rain-fed wheat with summer fallow, about 450 mm of rain a year.",
         body=dict(lat=33.90, lon=-5.45, existing=["wheat", "fallow"])),
]

def run_case(cs: dict) -> list[str]:
    r = c.post("/api/simulate", json=cs["body"]).json()
    top = next(x for x in r["rotations"] if x["rotation_id"] == r["order"][0])
    ex = r["rotations"][0]
    L = [f"## {cs['title']}", "", f"_{cs['who']}_", "",
         f"**Answer:** {top['label']['en']}" + (" (keep the current rotation)" if top["rotation_id"] == "existing" else ""), "",
         "| | current rotation | suggested |", "|---|---|---|",
         f"| rotation | {ex['label']['en']} | {top['label']['en']} |",
         f"| profit, 8 of 10 years (EGP/feddan/yr) | {f(ex['profit']['p10'])} – {f(ex['profit']['p90'])} | {f(top['profit']['p10'])} – {f(top['profit']['p90'])} |",
         f"| irrigation (m³/feddan/yr, median) | {f(ex['water_m3']['median'])} | {f(top['water_m3']['median'])} |",
         f"| losing years of {len(top['years'])} | {round(ex['loss_year_share']['value'] * len(ex['years']))} | {round(top['loss_year_share']['value'] * len(top['years']))} |",
         f"| worst past window | {ex['worst_year']['year']}: {f(ex['worst_year']['profit'])} | {top['worst_year']['year']}: {f(top['worst_year']['profit'])} |",
         f"| score /100 | {ex['total']} | {top['total']} |", ""]
    why = [x["en"] for x in top["text"]["benefits"][:3]] + [x["en"] for x in top["text"]["review"] if x["tone"] == "warn"][:2]
    if why:
        L += ["What the app tells the farmer:", ""] + [f"- {w}" for w in why] + [""]
    if r.get("no_clear_winner"):
        L += ["- The app says there is **no clear winner** here: the top two are within 5 %.", ""]
    L += [f"Talking point: {talking_point(cs, ex, top, r)}", ""]
    return L

def talking_point(cs, ex, top, r):
    dw = ex["water_m3"]["median"] - top["water_m3"]["median"]
    if top["rotation_id"] == "existing":
        return "AgroTwin does not push change for its own sake: when the current rotation is best, it says so."
    if dw > 300:
        return f"For a 3-feddan farm that is about {f(dw * 3)} m³ of Nile water a year saved, with the profit range shown, not promised."
    return "The ranking moves when the farmer's priorities or the prices move — the sliders are the farmer's, the numbers are NASA's."

def scout_case() -> list[str]:
    """Matrouh barley with a hidden past drought season replayed as robot readings."""
    sid = "coast_01"
    scout.delete_runs(sid)
    sim = c.post("/api/scout/simulate", json=dict(lat=31.28, lon=27.35, truth_year=2008, days=150)).json()
    r = c.post("/api/simulate", json=dict(lat=31.28, lon=27.35, existing=["barley", "fallow"])).json()
    ex = r["rotations"][0]
    fz = r["fusion"]
    w, s, tr = ex["unweighted"]["season1_profit"], ex["season1_profit"], ex.get("truth", {})
    scout.delete_runs(sid)
    inside = s["p10"] <= tr.get("season1_profit", -1e9) <= s["p90"]
    return ["## The robot narrows the range: Matrouh barley, hidden 2008 season (SIMULATED)", "",
            "_The 2008/09 season is hidden from the model and replayed as 150 days of Scout soil readings with sensor noise. "
            "Badge on screen: SIMULATED._", "",
            "| | this season's profit range (EGP/feddan) |", "|---|---|",
            f"| history only | {f(w['p10'])} – {f(w['p90'])} (width {f(w['p90'] - w['p10'])}) |",
            f"| with Scout readings | {f(s['p10'])} – {f(s['p90'])} (width {f(s['p90'] - s['p10'])}) |",
            f"| hidden truth | {f(tr.get('season1_profit', 0))} — {'inside the narrowed range' if inside else 'outside the narrowed range'} |", "",
            f"Range {round(100 * (1 - (s['p90'] - s['p10']) / (w['p90'] - w['p10'])))} % narrower; effective past years carrying the answer: "
            f"{fz.get('ess', 0):.1f}; soil memory {fz.get('tau_days')} days; confidence {fz.get('confidence_label')}.", "",
            "Talking point: 'We hid a real past season from the model and let the robot measure it. The range closed in "
            "on the truth. Our backtest says this holds about 3 times in 4, which is what an honest 80 % range should do.'", ""]

def sighting_case() -> list[str]:
    body = dict(lat=31.25, lon=30.95, existing=["potato", "maize"])
    c.post("/api/robot/reset")
    before = c.post("/api/simulate", json=body).json()
    c.post("/api/robot/detect", json=dict(label="Potato___Late_blight", confidence=0.91, source="replay"))
    after = c.post("/api/simulate", json=body).json()
    c.post("/api/robot/reset")
    lab = lambda r: next(x for x in r["rotations"] if x["rotation_id"] == r["order"][0])["label"]["en"]
    return ["## Potato farmer: the leaf camera sees late blight", "",
            "_Kafr El-Sheikh, potato in winter, maize in summer. The Verdex camera records a late-blight sighting "
            "(the team's model: 89 % accuracy on held-out late-blight photos)._", "",
            f"- Before the sighting the app suggests: **{lab(before)}**",
            f"- After the sighting: **{lab(after)}**", "",
            "Talking point: the robot's camera feeds the rotation itself: a disease seen today pushes the potato family "
            "(potato, tomato) off the field for two years, and the card says why.", ""]

def main():
    bt = (ROOT / "qa" / "BACKTEST.md")
    L = ["# Sample cases (for the team, not the app)", "",
         f"_Generated {date.today()} by scripts/sample_cases.py from the real engine (NASA POWER 1991→2026, "
         "climate-adjusted replay). Prices: 19 quoted, 21 assumptions (data/prices.csv). Re-run after any change._", ""]
    for cs in CASES:
        L += run_case(cs)
    L += scout_case() + sighting_case()
    if bt.exists():
        L += ["## Backtest in one line", "", "Over the last three seasons at three sites, the replay forecast beat 'same as "
              "last year' by about half (CRPS) and contained the actual outcome in 67–78 % of cases. Details: qa/BACKTEST.md.", ""]
    (ROOT / "docs" / "SAMPLE_CASES.md").write_text("\n".join(L))
    print("\n".join(L))

if __name__ == "__main__":
    main()
