"""Plan Mode: a conversation (text or voice) that builds, explains and revises a three-year farm plan.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

The farmer talks; the agent fills a farm profile (crops now, area, salinity, canal reliability, priorities, crops to
keep or avoid), calls the plan engine (planner.make_plan: NASA POWER replay × FAO-56 × Monte Carlo, Field Pulse,
MODIS field index) and answers in Egyptian Arabic or English. Every revision ("keep rice", "less water",
"I have 3 feddans") re-plans in about two seconds.

Engines:
  rules  — fast slot-filling for Egyptian colloquial Arabic and English; no network, the stage default.
  claude — Claude Opus 5.5 with tools (update_profile, make_plan, explain); every number in its reply must
           match a tool result or the rules engine answers (same Number Auditor as backend/chat.py).
Sessions (profile, plan summary, last turns) persist in data/plans/ so a farmer can come back.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date
from pathlib import Path

import chat as ch
from crops import CROPS

ROOT = Path(__file__).resolve().parent.parent
SESS = ROOT / "data" / "plans"
MODEL = "claude-opus-5-5"
SLOTS = ("crops", "area", "salinity", "canal", "priority")
# Crops AgroTwin cannot model yet (no FAO-56 parameters / prices in the engine). Named back to the farmer, never guessed.
UNKNOWN_CROPS = {"بصل": ("البصل", "onion"), "ثوم": ("التوم", "garlic"), "مانجو": ("المانجا", "mango"), "مانجا": ("المانجا", "mango"),
                 "موالح": ("الموالح", "citrus"), "برتقال": ("البرتقال", "oranges"), "يوسفي": ("اليوسفي", "mandarins"), "ليمون": ("الليمون", "lemons"),
                 "عنب": ("العنب", "grapes"), "بطيخ": ("البطيخ", "watermelon"), "خيار": ("الخيار", "cucumber"), "فلفل": ("الفلفل", "peppers"),
                 "قصب": ("القصب", "sugarcane"), "نخل": ("النخل", "date palms"), "زيتون": ("الزيتون", "olives"), "سمسم": ("السمسم", "sesame"),
                 "فول سوداني": ("الفول السوداني", "peanuts"), "كتان": ("الكتان", "flax"), "onion": ("البصل", "onion"), "garlic": ("التوم", "garlic"),
                 "mango": ("المانجا", "mango"), "citrus": ("الموالح", "citrus"), "orange": ("البرتقال", "oranges"), "grape": ("العنب", "grapes"),
                 "watermelon": ("البطيخ", "watermelon"), "sugarcane": ("القصب", "sugarcane"), "olive": ("الزيتون", "olives"), "date palm": ("النخل", "date palms")}
KNOWN_AR = "قمح، شعير، برسيم، فول بلدي، بنجر، بطاطس، درة شامية، درة رفيعة، رز، قطن، طماطم، فول صويا"
KNOWN_EN = "wheat, barley, berseem, faba bean, sugar beet, potato, maize, sorghum, rice, cotton, tomato, soybean"

# ---------------------------------------------------------------------------
# session store
# ---------------------------------------------------------------------------

def load(sid: str | None) -> dict:
    if sid:
        p = SESS / f"{re.sub(r'[^a-z0-9-]', '', sid)}.json"
        if p.exists():
            return json.loads(p.read_text())
    return dict(sid=str(uuid.uuid4())[:12], profile={}, asked=[], history=[], plan=None, created=str(date.today()))


def save(s: dict):
    SESS.mkdir(parents=True, exist_ok=True)
    (SESS / f"{s['sid']}.json").write_text(json.dumps(s, ensure_ascii=False, default=str))


# ---------------------------------------------------------------------------
# understanding (rules)
# ---------------------------------------------------------------------------

_NUM_WORDS = {"نص": 0.5, "ربع": 0.25, "واحد": 1, "فدان واحد": 1, "اتنين": 2, "فدانين": 2, "تلاتة": 3, "تلات": 3, "اربعة": 4, "اربع": 4,
              "خمسة": 5, "خمس": 5, "ستة": 6, "عشرة": 10, "half": 0.5, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10}


def _number(t: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    if m:
        return float(m.group(1))
    for w, v in sorted(_NUM_WORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"(^|\s)" + re.escape(w) + r"(\s|$)", t):
            return v
    return None


def _has(t: str, *words) -> bool:
    return any(ch.norm_ar(w) in t for w in words)


def understand(text: str, s: dict) -> dict:
    """Return profile updates and flags from one utterance."""
    t = " " + ch.norm_ar(text) + " "
    up, flags = {}, set()
    crops = ch.crops_in(text)
    unknown = sorted({v for k, v in UNKNOWN_CROPS.items() if ch.norm_ar(k) in t})
    if unknown:
        up["unknown_crops"] = [list(u) for u in unknown]
        flags.add("unknown_crops")
    if _has(t, "عارف انا بزرع", "فاكر", "قلتلك", "قولتلك", "انا قلت", "انا بزرع ايه", "what do i grow", "do you know what", "what did i tell", "remember"):
        flags.add("recall")
    if _has(t, "السلام عليكم", "سلام عليكم", "ازيك", "صباح الخير", "مساء الخير", "اهلا", " hello", " hi ", "good morning"):
        flags.add("greeting")
    neg = _has(t, " مش عايز", " مش هزرع", " بلاش", " من غير", " without ", " no ", " not ", " don't want", " avoid", " مش ")
    keep = _has(t, " عايز ازرع", " لازم", " عايز ", " keep ", " include ", " must ", " i want ")
    if crops and neg and not _has(t, "بزرع", "زارع", "i grow", "i plant"):
        up["exclude"] = sorted(set((s["profile"].get("exclude") or []) + crops))
        flags.add("exclude")
    elif crops and keep and not _has(t, "بزرع", "زارع", "i grow", "i plant", "my crops"):
        up["must_include"] = sorted(set((s["profile"].get("must_include") or []) + crops))
        flags.add("keep")
    elif crops:
        w = next((c for c in crops if CROPS[c]["season"] == "winter"), None)
        sm = next((c for c in crops if CROPS[c]["season"] == "summer"), None)
        if w:
            up["winter"] = w
        if sm:
            up["summer"] = sm
        if w or sm:
            flags.add("crops")
    if _has(t, "فدان", "feddan", "acre") or ("area" in s.get("asked", [])[-1:] and _number(t) is not None):
        n = _number(t)
        if n and 0 < n < 500:
            up["area_feddan"] = n
            flags.add("area")
    if _has(t, "ملوح", "مالح", "ملح", "salin", "salt", "ece", "ds/m"):
        n = _number(t)
        if _has(t, " مش ", " لا ", " no ", " not ", "مفيش"):
            up["salinity_ece"] = 0.0
        elif n is not None and n < 30:
            up["salinity_ece"] = n
        else:
            up["salinity_ece"] = 4.0          # "my land is salty" without a test → moderate (assumption, said back to the farmer)
            flags.add("salinity_guess")
        flags.add("salinity")
    elif ("salinity" in s.get("asked", [])[-1:] and _has(t, " لا ", " لأ ", " مش ", " no ", " not ", "مفيش", "نضيف", "كويس", " fine", " good")) or \
            _has(t, "soil is fine", "soil is good", "soil is ok", "no salt", "not salty", "الارض كويسه", "الارض نضيفه", "مفيش ملوحه"):
        up["salinity_ece"] = 0.0
        flags.add("salinity")
    asked_last = s.get("asked", [])[-1:]
    if _has(t, "مبتقطعش", "مابتقطعش", "مش بتقطع", "عمرها ما", "مفيش انقطاع", "never short", "never runs short", "never cut") or \
            ("canal" in asked_last and re.fullmatch(r"\s*(لا|لأ|لاء|no|nope|never|ابدا)\s*[.!؟?]?\s*", ch.norm_ar(text))):
        up["canal_short_prob"] = 0.05
        flags.add("canal")
    elif _has(t, "مية قليل", "المية بتقطع", "بتقطع", "مفيش مية", "المية مش بتوصل", "شح", "short", "shortage", "not enough water", "canal is dry",
            "دايما", "على طول", "always", "often", "ساعات", "احيانا", "sometimes", "نادر", "rarely", "never", "ابدا", "بتوصل"):
        if _has(t, "دايما", "على طول", "always", "often", "كتير", "مفيش مية", "المية مش بتوصل"):
            up["canal_short_prob"] = 0.5
        elif _has(t, "نادر", "rarely", "never", "ابدا", "بتوصل كويس", "مش بتقطع"):
            up["canal_short_prob"] = 0.05
        else:
            up["canal_short_prob"] = 0.25
        flags.add("canal")
    pri = dict(s["profile"].get("priorities") or {"water": 1, "soil": 1, "profit": 1, "risk": 1})
    if _has(t, "مكسب", "فلوس", "ربح", "اكسب", "profit", "money", "earn", "income"):
        pri["profit"] = 2; flags.add("priority")
    if _has(t, "وفر مية", "اوفر مية", "مية اقل", "توفير المية", "save water", "saving water", "less water", "water saving", "care about water"):
        pri["water"] = 2; flags.add("priority")
    if _has(t, "صحة الارض", "صحة التربة", "خصوبة", "soil health", "rebuild soil", "soil fertility"):
        pri["soil"] = 2; flags.add("priority")
    if _has(t, "مخاطرة", "امان", "مضمون", "خساره", "خسارة", "risk", "safe", "loss"):
        pri["risk"] = 2; flags.add("priority")
    if "priority" in flags:
        up["priorities"] = pri
    if _has(t, "ابدا من الاول", "من جديد", "reset", "start over"):
        flags.add("reset")
    if _has(t, "ليه", "اشرح", "why", "explain"):
        flags.add("why")
    if _has(t, "امتى ازرع", "ميعاد", "when do i sow", "when to plant", "schedule", "الجدول"):
        flags.add("schedule")
    if _has(t, "اعمل الخطة", "الخطة", "خطة", "plan", "يلا", "go ahead", "make"):
        flags.add("plan_now")
    return dict(update=up, flags=flags)


# ---------------------------------------------------------------------------
# replies (Egyptian Arabic / English)
# ---------------------------------------------------------------------------

def _q(slot: str, ar: bool) -> str:
    Q = dict(
        crops=("بتزرع إيه دلوقتي في الشتا وفي الصيف؟ مثلًا: قمح ورز.", "What do you grow now in winter and summer? For example: wheat and rice."),
        area=("مساحة الأرض كام فدان؟", "How many feddans is the field?"),
        salinity=("الأرض فيها ملوحة؟ لو عملت تحليل قولّي الرقم، ولو مش عارف قول مش عارف.", "Is the soil salty? If you have a lab test tell me the EC number; otherwise say you don't know."),
        canal=("مية الترعة في الصيف بتقطع؟ دايمًا، ساعات، ولا نادر؟", "Does canal water run short in summer: often, sometimes or rarely?"),
        priority=("إيه أهم حاجة عندك: المكسب، توفير المية، صحة الأرض، ولا الأمان من الخسارة؟", "What matters most: profit, saving water, soil health, or avoiding losses?"),
    )
    return Q[slot][0 if ar else 1]


def _crops_spoken(seq, ar):
    names = []
    for c in seq[:2]:
        names.append(ch.AR_NAME.get(c, c) if ar else c)
    tail = (" كل سنة" if ar else ", every year") if list(seq) == list(seq[:2]) * 3 else (" وبعدين بنغيّر" if ar else ", then varied")
    return (" وبعده ".join(names) if ar else ", then ".join(names)) + tail


def summary(plan: dict, ar: bool) -> str:
    c, cur, d = plan["chosen"], plan["current"], plan["delta"]
    sow = plan["schedule"][0]
    k = lambda x: f"{round(x / 1000):,}"
    if ar:
        parts = [f"خطتك: {_crops_spoken(c['seq'], True)}.",
                 f"أول زرعة {ch.AR_NAME.get(sow['crop'], sow['crop'])} {ch._day(sow['sow'], 'ar')}."]
        if c["shift_days"]:
            parts.append(f"والزرعة الصيفي {'بدري' if c['shift_days'] < 0 else 'متأخرة'} {abs(c['shift_days'])} يوم عشان الحر والمية.")
        if c["strategy"] == "deficit":
            parts.append("وفي الصيف بنروي 85% من الاحتياج بس، والخسارة في المحصول صغيرة.")
        parts.append(f"المكسب في معظم السنين بين {k(c['profit']['p10'])} و{k(c['profit']['p90'])} ألف جنيه للفدان في السنة،")
        if d["water_m3_per_feddan"] < -200:
            saved = -d["water_m3_per_feddan"]
            parts.append(f"وبتوفّر حوالي {saved:,} متر مكعب مية للفدان في السنة.")
        dp = d["profit_egp_per_feddan"]
        if dp > 500:
            parts.append(f"يعني حوالي {k(dp)} ألف جنيه زيادة عن زراعتك الحالية للفدان.")
        elif dp < -500:
            parts.append(f"مكسبها أقل من زراعتك الحالية بحوالي {k(-dp)} ألف للفدان، في مقابل توفير المية وأمان أكتر. لو المكسب أهم قولّي.")
        area = plan["profile"].get("area_feddan", 1)
        if area != 1 and abs(plan["farm_totals"]["profit_change_egp"]) > 500:
            chg = plan["farm_totals"]["profit_change_egp"]
            parts.append(f"وعلى {area:g} فدان: حوالي {k(abs(chg))} ألف جنيه {'زيادة' if chg > 0 else 'أقل'} في السنة.")
        if plan.get("pulse") and plan["pulse"].get("send_scout"):
            parts.append("وخد بالك: آخر صورة قمر صناعي بتقول إن أرضك أقل من المتوقّع، اكشف عليها قبل الزراعة.")
        parts.append("تحب أغيّر حاجة؟")
        return " ".join(parts)
    parts = [f"Your plan: {_crops_spoken(c['seq'], False)}.", f"First sowing: {sow['crop']} around {ch._day(sow['sow'], 'en')}."]
    if c["shift_days"]:
        parts.append(f"Summer sowing moves {abs(c['shift_days'])} days {'earlier' if c['shift_days'] < 0 else 'later'}.")
    if c["strategy"] == "deficit":
        parts.append("In summer it irrigates 85% of the crop's need, at a small yield cost.")
    parts.append(f"Profit in most years: {k(c['profit']['p10'])}–{k(c['profit']['p90'])} thousand EGP per feddan per year.")
    if d["water_m3_per_feddan"] < -200:
        parts.append(f"It saves about {-d['water_m3_per_feddan']:,} m³ of water per feddan per year.")
    if d["profit_egp_per_feddan"] > 500:
        parts.append(f"About {k(d['profit_egp_per_feddan'])} thousand EGP more per feddan than your current rotation.")
    elif d["profit_egp_per_feddan"] < -500:
        parts.append(f"It earns about {k(-d['profit_egp_per_feddan'])} thousand EGP less per feddan than today, in exchange for water and lower risk; say if profit matters more.")
    if plan.get("pulse") and plan["pulse"].get("send_scout"):
        parts.append("Note: the latest satellite image shows your field below what the weather explains; check it before sowing.")
    parts.append("Want to change anything?")
    return " ".join(parts)


def explain(plan: dict, ar: bool) -> str:
    c, r = plan["chosen"], plan.get("runner_up")
    fi = plan.get("field_index", {})
    k = lambda x: f"{round(x / 1000):,}"
    if ar:
        out = [f"جرّبنا {plan['searched']} اختيار على طقس أرضك من 1991، بأسعار وانقطاع مية متغيّرين."]
        if r:
            out.append(f"اللي بعدها كانت {_crops_spoken(r['seq'], True)} بمكسب متوسط {k(r['profit']['median'])} ألف، وخطتك {k(c['profit']['median'])} ألف.")
        if fi.get("available"):
            out.append(f"وصور القمر الصناعي بتقول إن خضرة أرضك {'أعلى' if fi['factor'] >= 1 else 'أقل'} من متوسط الدلتا، فحسبنا المحصول على كده.")
        return " ".join(out)
    out = [f"We tried {plan['searched']} options on your field's weather since 1991, with varying prices and canal supply."]
    if r:
        out.append(f"The runner-up was {_crops_spoken(r['seq'], False)} at a median {k(r['profit']['median'])} thousand EGP; yours is {k(c['profit']['median'])} thousand.")
    if fi.get("available"):
        out.append(f"Satellite greenness puts your field {'above' if fi['factor'] >= 1 else 'below'} the Delta average, so yields were scaled accordingly.")
    return " ".join(out)


def schedule_text(plan: dict, ar: bool) -> str:
    rows = plan["schedule"][:4]
    if ar:
        return " ".join(f"{ch.AR_NAME.get(x['crop'], x['crop'])}: زراعة {ch._day(x['sow'], 'ar')}، حصاد {ch._day(x['harvest'], 'ar')}." for x in rows)
    return " ".join(f"{x['crop']}: sow {ch._day(x['sow'], 'en')}, harvest {ch._day(x['harvest'], 'en')}." for x in rows)


# ---------------------------------------------------------------------------
# turn
# ---------------------------------------------------------------------------

def _missing(profile: dict, asked: list) -> str | None:
    have = dict(crops="winter" in profile or "summer" in profile, area="area_feddan" in profile, salinity="salinity_ece" in profile,
                canal="canal_short_prob" in profile, priority="priorities" in profile)
    for slot in SLOTS:
        if not have[slot] and slot not in asked:
            return slot
    return None


def _profile_text(p: dict, ar: bool) -> str:
    parts = []
    cr = [x for x in (p.get("winter"), p.get("summer")) if x]
    unk = [u[0 if ar else 1] for u in p.get("unknown_crops") or []]
    if ar:
        if cr:
            parts.append("بتزرع " + " و".join(ch.AR_NAME.get(c, c) for c in cr))
        if unk:
            parts.append("وقلتلي على " + " و".join(unk) + " (دول لسه مش في حساباتي)")
        if "area_feddan" in p:
            parts.append(f"على {p['area_feddan']:g} فدان")
        if "salinity_ece" in p:
            parts.append("الأرض مش مالحة" if not p["salinity_ece"] else f"فيها ملوحة حوالي {p['salinity_ece']:g} دسي سيمنز")
        if "canal_short_prob" in p:
            parts.append({0.05: "ومية الترعة نادرًا ما بتقطع", 0.25: "والمية بتقطع ساعات في الصيف", 0.5: "والمية بتقطع كتير في الصيف"}.get(p["canal_short_prob"], "ومية الترعة محسوبة"))
        top = [k for k, v in (p.get("priorities") or {}).items() if v > 1]
        if top:
            parts.append("وأهم حاجة عندك " + " و".join({"profit": "المكسب", "water": "توفير المية", "soil": "صحة الأرض", "risk": "الأمان"}[k] for k in top))
        return ("انت قلتلي: " + "، ".join(parts) + ".") if parts else "لسه ماقلتليش حاجة عن أرضك."
    if cr:
        parts.append("you grow " + " and ".join(cr))
    if unk:
        parts.append("you mentioned " + " and ".join(unk) + " (not in my crop models yet)")
    if "area_feddan" in p:
        parts.append(f"{p['area_feddan']:g} feddans")
    if "salinity_ece" in p:
        parts.append("soil not saline" if not p["salinity_ece"] else f"salinity about {p['salinity_ece']:g} dS/m")
    if "canal_short_prob" in p:
        parts.append({0.05: "canal water rarely short", 0.25: "canal sometimes short in summer", 0.5: "canal often short in summer"}.get(p["canal_short_prob"], "canal reliability set"))
    return ("You told me: " + ", ".join(parts) + ".") if parts else "You haven't told me about your field yet."


def rules_turn(s: dict, text: str, ar: bool, make_plan) -> tuple[str, list]:
    u = understand(text, s)
    tools = []
    if "reset" in u["flags"]:
        s.update(profile={}, asked=[], plan=None)
        return (_q("crops", ar), tools)
    known_crops_now = any(k in u["update"] for k in ("winter", "summer"))
    s["profile"].update(u["update"])
    pre = ""
    if "greeting" in u["flags"]:
        tn = ch.norm_ar(text)
        pre = ("وعليكم السلام يا حاج، أهلًا بيك. " if "سلام" in tn else "الحمد لله تمام، أهلًا بيك يا حاج. " if "ازيك" in tn else "أهلًا بيك يا حاج. ") if ar else "Hello, welcome. "
    if "unknown_crops" in u["flags"] and not known_crops_now:
        names = [x[0 if ar else 1] for x in u["update"]["unknown_crops"]]
        if "crops" in s["asked"]:
            s["asked"].remove("crops")
        if ar:
            return (pre + f"{' و'.join(names)} لسه مش في الموديلات بتاعتي، فمقدرش أحسبهم صح ومش هخمّن. "
                    f"أنا بحسب دلوقتي: {KNOWN_AR}. لو عندك أرض تانية أو موسم تاني بتزرع فيه حاجة من دول قولّي، "
                    "أو قولّي «احسب على قمح ورز» كمثال."), tools
        return (pre + f"{' and '.join(names)} are not in my crop models yet, so I won't guess. I can plan with: {KNOWN_EN}. "
                "Tell me which of these you grow, or say “use wheat and rice” as an example."), tools
    if "recall" in u["flags"] and not u["update"]:
        return pre + _profile_text(s["profile"], ar) + (" تحب أغيّر حاجة؟" if ar else " Want to change anything?"), tools
    nxt = _missing(s["profile"], s["asked"])
    if s.get("plan") and "why" in u["flags"] and not u["update"]:
        return explain(s["plan"], ar), tools
    if s.get("plan") and "schedule" in u["flags"] and not u["update"]:
        return schedule_text(s["plan"], ar), tools
    has_crops = "winter" in s["profile"] or "summer" in s["profile"]
    if not has_crops:
        if "crops" not in s["asked"]:
            s["asked"].append("crops")
        return pre + _q("crops", ar), tools
    if nxt and "plan_now" not in u["flags"] and not s.get("plan"):
        s["asked"].append(nxt)
        if "salinity_guess" in u["flags"]:
            pre += ("هحسب الملوحة متوسطة (4 دسي سيمنز) لحد ما تعمل تحليل. " if ar else "I'll assume moderate salinity (4 dS/m) until you have a lab test. ")
        return pre + _q(nxt, ar), tools
    if s.get("plan") and not u["update"] and not ({"plan_now"} & u["flags"]):
        if pre:
            return pre + ("خطتك جاهزة على اليمين. تحب أغيّر حاجة؟" if ar else "Your plan is ready on the right. Want to change anything?"), tools
        return ("مفهمتش قصدك قوي. تقدر تقولّي مثلًا: «ليه الخطة دي؟»، «امتى أزرع؟»، «عايز أوفّر مية»، «مش عايز رز»، «عندي 5 فدان»، أو «انت فاكر أنا بزرع إيه؟». "
                "ولو حطّينا مفتاح Claude هفهم أي كلام." if ar else
                "I didn't quite get that. Try: “why this plan?”, “when do I sow?”, “save more water”, “no rice”, “I have 5 feddans”, or “what do I grow?”. "
                "With a Claude key I can understand free conversation."), tools
    plan = make_plan({k: v for k, v in s["profile"].items() if k != "unknown_crops"})
    tools.append(dict(tool="make_plan", args={k: v for k, v in s["profile"].items()}, source=plan.get("source")))
    s["plan"] = plan
    return pre + summary(plan, ar), tools


SYSTEM = """You are AgroTwin Plan Mode, a farm-planning assistant for smallholders in Egypt. Your reply is read aloud.
- Speak the farmer's language: Egyptian colloquial Arabic (address the farmer as "يا حاج") or plain English.
- Interview briefly (one question at a time) to fill the profile: current winter/summer crops, area in feddans, soil salinity,
  how often canal water runs short in summer, and priorities. Use update_profile whenever the farmer gives information.
- When the profile is enough (or the farmer asks), call make_plan and present the plan in 3–4 short sentences: the rotation,
  first sowing date, profit range per feddan, water saved. Offer to change something.
- When the farmer asks to change something (keep or avoid a crop, less water, more profit, area), update_profile then make_plan again.
- Use only numbers from tool results, rounded the way people speak. Never promise outcomes. The decision is the farmer's.
- AgroTwin models only these crops: wheat, barley, berseem, faba bean, sugar beet, potato, maize, sorghum, rice, cotton, tomato, soybean.
  If the farmer grows something else (onion, mango, citrus...), say so plainly and ask what else they grow; never substitute silently.
- Answer questions about what the farmer already told you from the profile. Be warm and brief, like a good extension officer."""

TOOLS = [
    dict(name="update_profile", description="Update the farm profile. Crop keys: " + ", ".join(CROPS) + ". canal_short_prob: share of summers with canal shortage (0.05 rarely, 0.25 sometimes, 0.5 often). salinity_ece in dS/m (4 if salty but untested). priorities: weights 1–2 for water, soil, profit, risk.",
         input_schema=dict(type="object", properties=dict(
             winter=dict(type="string"), summer=dict(type="string"), area_feddan=dict(type="number"), salinity_ece=dict(type="number"),
             canal_short_prob=dict(type="number"), exclude=dict(type="array", items=dict(type="string")),
             must_include=dict(type="array", items=dict(type="string")),
             priorities=dict(type="object", properties=dict(water=dict(type="number"), soil=dict(type="number"), profit=dict(type="number"), risk=dict(type="number")))))),
    dict(name="make_plan", description="Build the 3-year plan from the current profile (replay of 32 NASA POWER years, FAO-56, price and canal-supply uncertainty, Field Pulse, satellite field index). Returns chosen rotation, schedule, ranges, comparison with today.",
         input_schema=dict(type="object", properties={})),
]


def _slim(plan):
    return dict(chosen=plan["chosen"], current=plan["current"], delta=plan["delta"], farm_totals=plan["farm_totals"],
                runner_up=plan.get("runner_up"), schedule=[{k: x[k] for k in ("crop", "season", "sow", "harvest", "water_m3_per_feddan", "yield_t_per_feddan")} for x in plan["schedule"]],
                risks=[r["text"] for r in plan["risks"]], field_index=plan["field_index"].get("factor"), searched=plan["searched"])


def claude_turn(s: dict, text: str, ar: bool, make_plan):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None, [], []
    try:
        import anthropic
    except ImportError:
        return None, [], []
    client = anthropic.Anthropic()
    msgs = [dict(role=m["role"], content=m["text"]) for m in s["history"][-8:]]
    msgs.append(dict(role="user", content=f"[profile so far: {json.dumps(s['profile'], ensure_ascii=False)}; today {date.today()}]\n{text}"))
    results, tools = [], []
    try:
        for _ in range(6):
            resp = client.messages.create(model=MODEL, max_tokens=1200, system=SYSTEM, tools=TOOLS, messages=msgs)
            if resp.stop_reason == "refusal":
                return None, results, tools
            uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not uses:
                return (" ".join(b.text for b in resp.content if b.type == "text").strip() or None), results, tools
            msgs.append(dict(role="assistant", content=resp.content))
            outs = []
            for u in uses:
                if u.name == "update_profile":
                    s["profile"].update({k: v for k, v in (u.input or {}).items() if v is not None})
                    r = dict(ok=True, profile=s["profile"])
                elif u.name == "make_plan":
                    plan = make_plan(s["profile"]); s["plan"] = plan
                    r = _slim(plan)
                else:
                    r = dict(error="unknown tool")
                results.append(r); tools.append(dict(tool=u.name, args=u.input, source="AgroTwin plan engine"))
                outs.append(dict(type="tool_result", tool_use_id=u.id, content=json.dumps(r, ensure_ascii=False, default=str)))
            msgs.append(dict(role="user", content=outs))
    except Exception:  # noqa: BLE001
        return None, results, tools
    return None, results, tools


def turn(sid: str | None, text: str, lang: str, make_plan) -> dict:
    s = load(sid)
    has_ar = any("؀" <= c <= "ۿ" for c in text)
    ar = has_ar or (lang == "ar" and not re.search(r"[A-Za-z]{3,}", text))
    reply, results, tools = claude_turn(s, text, ar, make_plan)
    engine = "claude"
    if reply:
        bad = ch.audit(reply, results + [s["profile"]], text)
        if bad:
            reply = None
    if not reply:
        engine = "rules"
        reply, t2 = rules_turn(s, text, ar, make_plan)
        tools += t2
    s["history"] += [dict(role="user", text=text), dict(role="assistant", text=reply)]
    s["history"] = s["history"][-20:]
    save(s)
    return dict(sid=s["sid"], reply=reply, lang="ar" if ar else "en", engine=engine, tools=tools,
                profile=s["profile"], plan=s.get("plan"), next_question=_missing(s["profile"], s["asked"]))
