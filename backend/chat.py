"""Voice assistant: the farmer asks (by voice), the assistant calls AgroTwin's own engines and answers
(by voice) in Egyptian Arabic or English.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

Two engines, same tools:
  - "claude": Claude Opus 5.5 chooses and calls the tools (needs ANTHROPIC_API_KEY). Every number in its
    reply is checked against the tool results; if one cannot be traced, the rules engine answers instead.
  - "rules":  a keyword router for Egyptian colloquial Arabic and English. No network, no key — the stage default.
Tools never invent data: each one wraps an existing endpoint (replay, 16-day planner, Field Pulse, prices,
time machine, robot state) and returns its source tag.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date

MODEL = "claude-opus-5-5"

# ---------------------------------------------------------------------------
# language helpers
# ---------------------------------------------------------------------------

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def norm_ar(s: str) -> str:
    s = re.sub(r"[ً-ْـ]", "", s.translate(_AR_DIGITS))
    return (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي").lower())


CROP_WORDS = {
    "wheat": ["قمح", "wheat"], "barley": ["شعير", "barley"], "berseem": ["برسيم", "berseem", "clover"],
    "faba": ["فول", "faba", "bean"], "sugarbeet": ["بنجر", "beet"], "potato": ["بطاطس", "بطاطا", "potato"],
    "maize": ["ذره", "دره", "maize", "corn"], "sorghum": ["رفيعه", "sorghum"], "rice": ["رز", "ارز", "rice"],
    "cotton": ["قطن", "cotton"], "tomato": ["طماطم", "قوطه", "tomato"], "soybean": ["صويا", "soy"],
}
WINTER = {"wheat", "barley", "berseem", "faba", "sugarbeet", "potato"}
AR_NAME = {"wheat": "القمح", "barley": "الشعير", "berseem": "البرسيم", "faba": "الفول البلدي", "sugarbeet": "البنجر",
           "potato": "البطاطس", "maize": "الدرة الشامية", "sorghum": "الدرة الرفيعة", "rice": "الرز", "cotton": "القطن",
           "tomato": "الطماطم", "soybean": "فول الصويا", "fallow": "أرض بور"}


def crops_in(text: str) -> list[str]:
    t = norm_ar(text)
    found = []
    for crop, words in CROP_WORDS.items():
        for w in words:
            pat = r"\b" + re.escape(w) + r"s?\b" if w.isascii() else re.escape(w)
            for m in re.finditer(pat, t):
                found.append((m.start(), crop))
    found.sort()
    out = []
    for _, c in found:
        if c == "maize" and "sorghum" in out:
            continue
        if c == "faba" and "soybean" in [x for _, x in found]:
            continue
        if c not in out:
            out.append(c)
    if "sorghum" in out and "maize" in out:
        out.remove("maize")
    return out


INTENTS = [
    ("irrigation", ["اروي", "نروي", "يروي", "هروي", "الري", "ريه", "ري ", "اسقي", "نسقي", "سقي", "irrigat", "water the", "when to water"]),
    ("weather", ["مطر", "الجو", "حر ", "حراره", "سقعه", "برد", "weather", "rain", "forecast", "hot", "temperature"]),
    ("pulse", ["حال الارض", "الارض عامله", "عامله ايه", "عامل ايه", "حالها", "شكلها", "حال ارضي", "الزرع عامل", "القمر الصناعي", "صحه", "خضرا", "خضره", "ضعيف", "صفرا", "مريض", "health", "green", "ndvi", "how is my field", "doing"]),
    ("history", ["زمان", "اللي فات", "السنين", "عشر سنين", "past", "history", "last years", "since"]),
    ("robot", ["روبوت", "الحساس", "سكاوت", "robot", "scout", "sensor", "probe"]),
    ("price", ["سعر", "بكام", "اسعار", "price", "cost"]),
    ("recommend", ["ازرع", "نزرع", "هزرع", "يزرع", "زراعه", "محصول", "احسن", "انصح", "نصيحه", "مكسب", "ربح", "هكسب", "فلوس", "توفير", "اوفر",
                   "recommend", "what should", "plant", "grow", "rotation", "profit", "earn", "best", "save water"]),
    ("hello", ["سلام", "ازيك", "صباح", "مساء", "اهلا", "hello", "hi ", "hey", "good morning"]),
    ("help", ["تعمل ايه", "بتعرف", "مساعده", "help", "what can you"]),
]


def intents_in(text: str) -> list[str]:
    t = " " + norm_ar(text) + " "
    pos = {name: min((t.find(w) for w in words if w in t), default=-1) for name, words in INTENTS}
    hits = sorted((n for n, p in pos.items() if p >= 0), key=lambda n: pos[n])   # in the order the farmer asked
    if "price" in hits and "recommend" in hits and not any(w in t for w in ("ازرع", "نزرع", "plant", "grow", "recommend")):
        hits.remove("recommend")
    return hits


def spoken_label(label: str, lang: str) -> str:
    """'Faba bean → Maize (×3)' → 'faba bean, then maize, every year'."""
    rep = "(×3)" in label
    label = label.replace("(×3)", "").strip()
    parts = [x.strip() for x in re.split(r"[→←]", label) if x.strip()]
    if lang == "ar":
        return " وبعده ".join(parts) + (" كل سنة" if rep else "")
    return ", then ".join(p.lower() for p in parts) + (", every year" if rep else "")


def k(n: float) -> str:
    """Spoken-style rounding: 77485 → '77 ألف' / '77 thousand'."""
    return f"{round(n / 1000):,}" if abs(n) >= 10000 else f"{round(n):,}"


# ---------------------------------------------------------------------------
# tools (each wraps an existing AgroTwin function; `api` is a dict of callables from app.py)
# ---------------------------------------------------------------------------

TOOLS = [
    dict(name="recommend_rotation", description="Replay crop rotations for the farmer's field on NASA POWER weather since 1991 and return the top suggestions with profit range (EGP per feddan per year), irrigation water (m³ per feddan per year) and the share of good years. Use for: what to plant, profit, saving water.",
         input_schema=dict(type="object", properties=dict(
             winter=dict(type="string", description="farmer's current winter crop key (wheat, barley, berseem, faba, sugarbeet, potato)"),
             summer=dict(type="string", description="farmer's current summer crop key (maize, sorghum, rice, cotton, tomato, soybean)")))),
    dict(name="irrigation_plan", description="Next 16 days: when to irrigate and how much (m³ per feddan), from the FAO-56 water balance on NASA POWER plus the Open-Meteo forecast.",
         input_schema=dict(type="object", properties={})),
    dict(name="weather_forecast", description="16-day weather totals for the field: rain (mm), reference evapotranspiration (mm), hottest day (°C). Source Open-Meteo (non-NASA).",
         input_schema=dict(type="object", properties={})),
    dict(name="field_pulse", description="AgroTwin's trained model: how green the field is in the latest MODIS image, whether that is what the weather explains, and the 16/32-day greenness forecast. Use for: how is my field doing, is something wrong.",
         input_schema=dict(type="object", properties={})),
    dict(name="crop_price", description="Quoted price, yield and cost per feddan for one crop, with the source.",
         input_schema=dict(type="object", properties=dict(crop=dict(type="string")), required=["crop"])),
    dict(name="field_history", description="Time machine: the field's past seasons seen by MODIS since 2015, replayed; cumulative water saved and extra profit if the suggestion had been used.",
         input_schema=dict(type="object", properties={})),
    dict(name="robot_status", description="Verdex Scout robot: connection mode (LIVE, SIMULATED, offline) and latest soil readings or leaf-disease detections.",
         input_schema=dict(type="object", properties={})),
]


class Toolbox:
    def __init__(self, api: dict, ctx: dict):
        self.api, self.ctx, self.calls = api, ctx, []

    def run(self, name: str, args: dict) -> dict:
        fn = getattr(self, "t_" + name, None)
        if fn is None:
            return dict(error=f"unknown tool {name}")
        try:
            out = fn(**(args or {}))
        except Exception as exc:  # noqa: BLE001
            out = dict(error=str(exc)[:200])
        self.calls.append(dict(tool=name, args=args, source=out.get("source", "")))
        return out

    # -- tools ------------------------------------------------------------
    def t_recommend_rotation(self, winter: str | None = None, summer: str | None = None):
        w = winter or self.ctx.get("winter") or "wheat"
        s = summer or self.ctx.get("summer") or "rice"
        r = self.api["simulate"](self.ctx["lat"], self.ctx["lon"], [w, s])
        rows = []
        for rid in [x for x in r["order"]]:
            x = next(z for z in r["rotations"] if z["rotation_id"] == rid)
            rows.append(dict(id=rid, crops=x["seq"][:2], label_en=x["label"]["en"], label_ar=x["label"]["ar"],
                             profit_median=round(x["profit"]["median"]), profit_p10=round(x["profit"]["p10"]),
                             profit_p90=round(x["profit"]["p90"]), water_m3=round(x["water_m3"]["median"]),
                             loss_year_share=x["loss_year_share"]["value"], worst_year=x["worst_year"]["year"],
                             is_current=rid == "existing"))
        cur = next(z for z in rows if z["is_current"])
        top = next(z for z in rows if not z["is_current"]) if rows[0]["is_current"] else rows[0]
        return dict(current=cur, suggestion=top, all=rows, years=f"{r['years'][0]}–{r['years'][-1]}",
                    unit="per feddan per year", source="computed: FAO-56 replay on nasa:POWER since 1991")

    def t_irrigation_plan(self):
        p = self.api["ahead"](self.ctx["lat"], self.ctx["lon"], self.ctx.get("winter") or "wheat", self.ctx.get("summer") or "rice")["plan"]
        if not p.get("available"):
            return dict(available=False, reason=p.get("reason"))
        return dict(available=True, crop_now=p.get("crop_now"), next_crop=p.get("next_crop"),
                    irrigate_on=p.get("irrigate_on", [])[:3], rain_days=p.get("rain_refills", [])[:3],
                    forecast_rain_mm=p.get("forecast_rain_mm"), today=str(date.today()), source=p.get("source"))

    def t_weather_forecast(self):
        fc = self.api["forecast"](self.ctx["lat"], self.ctx["lon"])
        if fc is None or not len(fc):
            return dict(available=False, reason="forecast unavailable offline")
        return dict(available=True, days=len(fc), rain_mm=round(float(fc["PRECTOTCORR"].sum()), 1),
                    rainy_days=int((fc["PRECTOTCORR"] > 1).sum()), et0_mm=round(float(fc["ET0"].sum()), 1),
                    hottest_c=round(float(fc["T2M_MAX"].max()), 1), hottest_day=str(fc["T2M_MAX"].idxmax().date()),
                    source="Open-Meteo 16-day forecast (non-NASA)")

    def t_field_pulse(self):
        p = self.api["pulse"](self.ctx["lat"], self.ctx["lon"])
        if not p.get("available"):
            return dict(available=False, reason=p.get("reason"))
        return dict(available=True, latest_image=p["latest_image"], ndvi=p["latest_ndvi"], normal=p["normal_now"],
                    status=(p["latest_check"] or {}).get("status"), forecast_16d=p["forecast"][0] if p["forecast"] else None,
                    send_scout=p["send_scout"], source=p["source"])

    def t_crop_price(self, crop: str):
        c = crop.lower().strip()
        if c not in self.api["prices"]:
            hit = crops_in(crop)
            c = hit[0] if hit else c
        p = self.api["prices"].get(c)
        if not p:
            return dict(error=f"no price for {crop}")
        return dict(crop=c, price_egp_per_t=round(p["price"]), yield_t_per_feddan=p["yield_t"], cost_egp_per_feddan=round(p["cost"]),
                    source=p["src"].get("price", ""))

    def t_field_history(self):
        T = self.api["timemachine"](self.ctx["lat"], self.ctx["lon"], self.ctx.get("winter") or "wheat", self.ctx.get("summer") or "rice")
        if not T.get("available"):
            return dict(available=False, reason=T.get("reason"))
        last = T["years"][-1]
        return dict(available=True, since=T["first"], seasons_green=T["seasons_green"], seasons_seen=T["seasons_seen"],
                    water_saved_m3=last["cum_water_saved_m3"], extra_profit_egp=last["cum_extra_profit"],
                    suggested_en=T["suggested_label"]["en"], suggested_ar=T["suggested_label"]["ar"], unit="per feddan, cumulative",
                    source=T["source"])

    def t_robot_status(self):
        st = self.api["robot"]()
        mode = {"offline": "offline", "live": "LIVE", "simulated": "SIMULATED"}.get(st.get("mode"), st.get("mode"))
        last = st["readings"][-1] if st.get("readings") else None
        return dict(mode=mode, latest_reading=last, detections=st.get("detections", [])[-3:],
                    note="SIMULATED readings are a replayed past season, not a real robot" if mode == "SIMULATED" else "",
                    source="Verdex Scout bridge")


# ---------------------------------------------------------------------------
# rules engine
# ---------------------------------------------------------------------------

def _day(d: str, lang: str) -> str:
    import pandas as pd
    ts = pd.Timestamp(d)
    if lang == "ar":
        days = ["الاتنين", "التلات", "الأربع", "الخميس", "الجمعة", "السبت", "الحد"]
        months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
        return f"يوم {days[ts.dayofweek]} {ts.day} {months[ts.month - 1]}"
    return ts.strftime("%A %d %B")


def _say(intent: str, box: Toolbox, lang: str, text: str) -> str:
    ar = lang == "ar"
    if intent == "hello":
        return ("أهلًا يا حاج! أنا مساعد أجروتوين. اسألني تزرع إيه، أو تروي امتى، أو أرضك عاملة إيه." if ar else
                "Hello! I'm the AgroTwin assistant. Ask me what to plant, when to irrigate, or how your field is doing.")
    if intent == "help":
        return ("أقدر أقولك تزرع إيه وتكسب قد إيه، تروي امتى، الجو هيعمل إيه، أرضك عاملة إيه من القمر الصناعي، وأسعار المحاصيل." if ar else
                "I can tell you what to plant and what it earned in past years, when to irrigate, the weather ahead, how your field looks from space, and crop prices.")
    if intent == "recommend":
        r = box.run("recommend_rotation", {})
        if "error" in r:
            return "معلش، مقدرتش أحسبها دلوقتي." if ar else "Sorry, I couldn't compute that right now."
        s, c = r["suggestion"], r["current"]
        good = round(10 * (1 - s["loss_year_share"]))
        lab_ar, lab_en = spoken_label(s["label_ar"], "ar"), spoken_label(s["label_en"], "en")
        dw = c["water_m3"] - s["water_m3"]
        if ar:
            often = "وكانت بتكسب في كل السنين اللي جرّبناها" if good >= 10 else f"وكانت بتكسب في {good} سنين من كل عشرة"
            msg = (f"بعد ما جرّبنا على طقس أرضك من {r['years'][:4]}، أحسن حاجة {lab_ar}. "
                   f"مكسبها كان حوالي {k(s['profit_median'])} ألف جنيه للفدان في السنة، {often}. ")
            if dw > 200:
                msg += f"وبتوفّر حوالي {k(dw)} متر مكعب مية للفدان كل سنة."
            elif dw < -200:
                msg += f"بس بتاخد مية أكتر بحوالي {k(-dw)} متر مكعب للفدان."
            return msg + " القرار في الآخر قرارك."
        often = "profitable in every year we replayed" if good >= 10 else f"profitable in {good} of 10 years"
        msg = (f"Replaying your field's weather since {r['years'][:4]}, the best option is {lab_en}: "
               f"about {k(s['profit_median'])} thousand EGP per feddan per year, {often}. ")
        if dw > 200:
            msg += f"It saves about {k(dw)} m³ of water per feddan each year."
        elif dw < -200:
            msg += f"It uses about {k(-dw)} m³ more water per feddan."
        return msg + " The decision is yours."
    if intent == "irrigation":
        p = box.run("irrigation_plan", {})
        if not p.get("available"):
            return "مفيش توقّعات جو متاحة دلوقتي، جرّب وانت متصل بالنت." if ar else "No forecast available right now; try again online."
        ev = p["irrigate_on"]
        if not ev:
            return (f"الأرض فيها مية كفاية، مش محتاج تروي في الـ١٦ يوم الجايين." if ar else
                    "The soil has enough water; no irrigation needed in the next 16 days.")
        e = ev[0]
        return (f"أول رية {_day(e['date'], 'ar')}، حوالي {k(e['gross_m3_per_feddan'])} متر مكعب للفدان." if ar else
                f"Next irrigation around {_day(e['date'], 'en')}, about {k(e['gross_m3_per_feddan'])} m³ per feddan.")
    if intent == "weather":
        f = box.run("weather_forecast", {})
        if not f.get("available"):
            return "مفيش توقّعات جو متاحة دلوقتي." if ar else "No forecast available right now."
        if ar:
            rain = "مفيش مطر تقريبًا" if f["rain_mm"] < 2 else f"هينزل حوالي {f['rain_mm']:.0f} مللي مطر"
            return f"في الـ١٦ يوم الجايين {rain}، وأحرّ يوم هيوصل {f['hottest_c']:.0f} درجة {_day(f['hottest_day'], 'ar')}."
        rain = "almost no rain" if f["rain_mm"] < 2 else f"about {f['rain_mm']:.0f} mm of rain"
        return f"Next 16 days: {rain}; the hottest day reaches {f['hottest_c']:.0f}°C on {_day(f['hottest_day'], 'en')}."
    if intent == "pulse":
        p = box.run("field_pulse", {})
        if not p.get("available"):
            return "لسه مفيش صور قمر صناعي كفاية للأرض دي." if ar else "Not enough satellite history for this field yet."
        st = p["status"]
        if ar:
            base = {"below": "أقل من اللي الجو يفسّره، ممكن يكون في مشكلة في الأرض نفسها. ابعت الروبوت أو لفّ عليها",
                    "above": "أخضر من المتوقّع، كويس",
                    "expected": "ماشية طبيعي زي ما الجو والموسم بيقولوا"}.get(st, "")
            f = p.get("forecast_16d")
            tail = f" وفي الـ١٦ يوم الجايين متوقّع الخضرة تبقى حوالي {f['mid']:.2f}." if f else ""
            return f"آخر صورة من القمر الصناعي بتقول إن أرضك {base}.{tail}"
        base = {"below": "below what the weather explains — something on the field may be wrong; send the Scout or walk it",
                "above": "greener than expected", "expected": "about what the weather and the season explain"}.get(st, "")
        f = p.get("forecast_16d")
        return f"The latest satellite image says your field is {base}." + (f" In 16 days greenness should be about {f['mid']:.2f}." if f else "")
    if intent == "history":
        T = box.run("field_history", {})
        if not T.get("available"):
            return "مفيش تاريخ قمر صناعي للأرض دي لسه." if ar else "No satellite history for this field yet."
        if ar:
            return (f"من موسم {T['since']}، لو كنت زرعت {spoken_label(T['suggested_ar'], 'ar')} كنت وفّرت حوالي {k(T['water_saved_m3'])} "
                    f"{'ألف ' if abs(T['water_saved_m3']) >= 10000 else ''}متر مكعب مية، وكسبت {k(T['extra_profit_egp'])} ألف جنيه زيادة للفدان.")
        return (f"Since {T['since']}, {spoken_label(T['suggested_en'], 'en')} would have saved about {T['water_saved_m3']:,} m³ of water "
                f"and earned {k(T['extra_profit_egp'])} thousand EGP more per feddan.")
    if intent == "robot":
        r = box.run("robot_status", {})
        if r["mode"] == "offline":
            return "الروبوت مش متوصّل دلوقتي." if ar else "The Scout robot isn't connected right now."
        tag = " (دي قراءات تجريبية، مش روبوت حقيقي)" if ar and r["mode"] == "SIMULATED" else (" (simulated readings, not a real robot)" if r["mode"] == "SIMULATED" else "")
        return ("الروبوت شغّال" if ar else "The Scout is connected") + tag + "."
    if intent == "price":
        cs = crops_in(text) or [box.ctx.get("winter") or "wheat"]
        p = box.run("crop_price", {"crop": cs[0]})
        if "error" in p:
            return "معنديش سعر للمحصول ده." if ar else "I don't have a price for that crop."
        return (f"سعر {AR_NAME.get(p['crop'], p['crop'])} حوالي {p['price_egp_per_t']:,} جنيه للطن، والفدان بيطلّع حوالي {p['yield_t_per_feddan']:.1f} طن." if ar else
                f"{p['crop'].title()} sells at about {p['price_egp_per_t']:,} EGP per tonne; a feddan yields about {p['yield_t_per_feddan']:.1f} t.")
    return ""


def rules_answer(text: str, lang: str, box: Toolbox) -> str:
    its = intents_in(text)
    if not its:
        its = ["recommend"] if crops_in(text) else ["help"]
    if len(its) > 1 and "hello" in its:
        its.remove("hello")
    parts = [_say(i, box, lang, text) for i in its[:2]]
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Claude engine
# ---------------------------------------------------------------------------

SYSTEM = """You are the AgroTwin voice assistant for small farmers in Egypt. Your answer is read aloud.
Rules:
- Reply in the farmer's language: Egyptian colloquial Arabic (عامية مصرية, simple words, address the farmer as "يا حاج") when they speak Arabic, plain English otherwise.
- Two or three short sentences. No lists, no markdown, no emoji.
- Call tools for every fact. Use only numbers that appear in tool results; round them the way a person would speak (77,485 → "حوالي 77 ألف").
- Never promise an outcome ("guaranteed", "will definitely"). Past years are evidence, not a forecast.
- If the robot mode is SIMULATED, say the readings are simulated.
- End advice about changing crops with: the decision is the farmer's ("القرار في الآخر قرارك")."""


def _numbers(s: str) -> list[float]:
    s = s.translate(_AR_DIGITS)
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", s)]


def _allowed(obj, acc: set):
    if isinstance(obj, dict):
        for v in obj.values():
            _allowed(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _allowed(v, acc)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        acc.add(float(obj))
    elif isinstance(obj, str):
        acc.update(_numbers(obj))


def audit(reply: str, tool_results: list, user_text: str) -> list[float]:
    ok: set[float] = set()
    for r in tool_results:
        _allowed(r, ok)
    ok.update(_numbers(user_text))
    bad = []
    for n in _numbers(reply):
        if n <= 31 or 1990 <= n <= 2100:      # dates, days, small counts
            continue
        if any(abs(n - v) <= max(0.03 * abs(v), 1) or abs(n * 1000 - v) <= 0.03 * abs(v) or abs(n - v / 1000) <= 1
               for v in ok if v):
            continue
        bad.append(n)
    return bad


def claude_answer(text: str, lang: str, box: Toolbox, history: list) -> tuple[str | None, list]:
    """Language-model engine (Claude or any OpenAI-compatible provider, see backend/llm.py)."""
    import llm
    if not llm.provider():
        return None, []
    ctx = f"Field: lat {box.ctx['lat']:.3f}, lon {box.ctx['lon']:.3f}; current crops: winter {box.ctx.get('winter')}, summer {box.ctx.get('summer')}. Today {date.today()}."
    messages = [dict(role=m["role"], content=m["text"]) for m in history[-6:] if m.get("text")]
    messages.append(dict(role="user", content=f"[{ctx}]\n{text}"))
    results = []

    def execute(name, args):
        r = box.run(name, args)
        results.append(r)
        return r
    return llm.run_tools(SYSTEM, messages, TOOLS, execute, max_rounds=5, max_tokens=1024), results

TALK = """You are AgroTwin, a friendly assistant for Egyptian smallholder farmers. Your reply is read aloud.
- Farmer writes Arabic → answer ONLY in Egyptian colloquial Arabic, no English words, address him as "يا حاج". English → plain English.
- 1 to 3 short sentences, no lists, no markdown, no emoji.
- Answer ONLY from the FACTS (computed by AgroTwin from NASA data for this field). If the answer is not there, say you don't know and
  suggest the local agricultural extension officer. Use only numbers from the FACTS. Never promise outcomes."""


def _llm_talk(text: str, lang: str, box: "Toolbox", history: list, asked_crops: list | None = None):
    import llm
    if not llm.provider():
        return None, []
    facts = dict(field=box.ctx)
    for name in ("recommend_rotation", "irrigation_plan", "field_pulse"):
        r = box.run(name, {})
        if "error" not in r:
            facts[name] = r
    for crop in (asked_crops or [])[:2]:
        # pair the crop with a partner that fits the calendar (cotton is sown in late March, so it cannot follow wheat)
        partners = ([box.ctx.get("summer"), "maize", "rice", "sorghum", "soybean", "fallow"] if crop in WINTER
                    else [box.ctx.get("winter"), "potato", "sugarbeet", "berseem", "faba", "barley", "wheat", "fallow"])
        for other in [x for x in partners if x]:
            w, sm = (crop, other) if crop in WINTER else (other, crop)
            r = box.run("recommend_rotation", {"winter": w, "summer": sm})
            if "error" not in r:
                facts[f"if_you_grow_{crop}"] = dict(rotation=r["current"], best_alternative=r["suggestion"], unit=r["unit"],
                                                    note=f"{crop} computed in the rotation {w} → {sm}")
                break
    msgs = [dict(role=m["role"], content=m["text"]) for m in history[-6:] if m.get("text")]
    reply_lang = "Egyptian colloquial Arabic" if any("\u0600" <= c <= "\u06ff" for c in text) else "English"
    msgs.append(dict(role="user", content=f"FACTS: {json.dumps(facts, ensure_ascii=False, default=str)[:9000]}\n\nReply language: {reply_lang}\nFarmer: {text}"))
    reply = llm.talk(TALK, msgs)
    if not reply:
        return None, []
    bad = audit(reply, [facts], text)
    return (None, bad) if bad else (re.sub(r"[*#_`]", "", reply).strip(), [])


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def answer(text: str, lang: str, ctx: dict, history: list, api: dict) -> dict:
    # answer in the language the farmer spoke; the UI language only breaks ties
    has_ar = any("\u0600" <= ch <= "\u06ff" for ch in text)
    has_en = bool(re.search(r"[A-Za-z]{2,}", text))
    lang = "ar" if has_ar else ("en" if has_en else ("ar" if lang == "ar" else "en"))
    ctx = dict(ctx)
    update = {}
    cs = crops_in(text)
    if cs and any(w in norm_ar(text) for w in ("بزرع", "زارع", "عندي", "زرعت", "i grow", "i plant", "my crop", "growing")):
        w = next((c for c in cs if c in WINTER), None)
        s = next((c for c in cs if c not in WINTER), None)
        if w:
            update["winter"] = ctx["winter"] = w
        if s:
            update["summer"] = ctx["summer"] = s
    box = Toolbox(api, ctx)
    # Hybrid: questions the keyword router understands go to the exact engines (fast, audited by construction);
    # anything else is answered by the language model from this field's computed facts, then audited.
    engine, blocked, reply = "rules", [], None
    t_ = " " + norm_ar(text) + " "
    asked_crops = crops_in(text) if (("?" in text or "؟" in text or any(w in t_ for w in (
        "ينفع", "ايه رايك", "رايك", "كويس", "good idea", "should i", "is it", "what about", "how about", "worth"))) and
        not any(w in t_ for w in ("بزرع", "زارع", "i grow", "i plant"))) else []
    if (not intents_in(text) and not crops_in(text)) or asked_crops:
        reply, blocked = _llm_talk(text, lang, box, history, asked_crops)
        if reply:
            engine = "llm"
    if not reply:
        reply = rules_answer(text, lang, box)
    return dict(reply=reply, lang=lang, engine=engine, tools=box.calls, ctx_update=update,
                blocked_numbers=blocked,
                note="Every number comes from AgroTwin's own tools; the rules engine answers when no API key is set "
                     "or when a number in the AI reply could not be traced.")
