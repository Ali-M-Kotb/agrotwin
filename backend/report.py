"""Evidence, benefits, gaps, local-review flags and blind spots, in English and Arabic.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

Fixed templates filled only from fields of the result object; a sentence whose field is
missing is omitted. Every number in a sentence is also listed in `nums` with the result
path it came from, so the Number Auditor (council.py) can check any rewritten version.
"""
from __future__ import annotations

import json
from pathlib import Path

from crops import CROPS, FALLOW, FAMILY_AR, family, name

CONTENT = Path(__file__).resolve().parent.parent / "content"
_BLIND = json.loads((CONTENT / "blindspots.json").read_text()) if (CONTENT / "blindspots.json").exists() else []

DISEASE_AR = {"Potato late blight": "اللفحة المتأخرة في البطاطس", "Potato early blight": "اللفحة المبكرة في البطاطس",
              "Apple scab": "جرب التفاح", "Apple black rot": "العفن الأسود في التفاح",
              "Strawberry leaf scorch": "لفحة أوراق الفراولة"}
STRENGTH = {"water": ("saving water", "توفير المياه"), "soil": ("soil health", "صحة التربة"),
            "profit": ("profit", "الربح"), "risk": ("low risk", "تقليل المخاطر")}


def f(x) -> str:
    return f"{round(x):,}"


def label(seq, lang="en") -> str:
    # collapse a repeating 2-season pattern: "Wheat → Rice (×3)"
    pairs = [tuple(seq[i:i + 2]) for i in range(0, len(seq), 2)]
    if len(set(pairs)) == 1:
        a, b = pairs[0]
        parts = [name(c, lang) for c in (a, b) if c != FALLOW] or [name(FALLOW, lang)]
        core = (" ← " if lang == "ar" else " → ").join(parts)
        return f"{core} (×3)"
    sep = " ← " if lang == "ar" else " → "
    return sep.join(name(c, lang) for c in seq if c != FALLOW) or name(FALLOW, lang)


def _s(en, ar, nums=(), tone="info"):
    return dict(en=en, ar=ar, nums=list(nums), tone=tone)


def rotation_text(r: dict, i: int, existing: dict, ctx: dict) -> dict:
    """r: one shown rotation; existing: the farmer's current one; ctx: site / fusion facts."""
    p = f"rotations[{i}]"
    n, y0, y1 = len(r["years"]), r["years"][0], r["years"][-1]
    pr = r["profit"]
    why, ev, ben, gaps, rev = [], [], [], [], []

    if r["rotation_id"] == "existing":
        why.append(_s("This is what you grow now, replayed so you can compare like with like.",
                      "هذه هي دورتك الحالية، أعدنا تشغيلها لتقارن بها البدائل بإنصاف."))
    else:
        en_s, ar_s = STRENGTH[r["strength"]]
        why.append(_s(f"Suggested because it is strongest on {en_s} among the {ctx['pool_size']} rotations we replayed.",
                      f"مقترحة لأنها الأقوى في {ar_s} بين {ctx['pool_size']} دورة أعدنا تشغيلها.",
                      [(ctx["pool_size"], "pool_size")]))

    ev.append(_s(f"Replayed through {n} past seasons ({y0}–{y1 + 2}) of NASA POWER weather with a daily FAO-56 water balance.",
                 f"أعدنا تشغيلها على {n} موسماً سابقاً ({y0}–{y1 + 2}) من بيانات طقس ناسا بموازنة مائية يومية (FAO-56).",
                 [(n, f"{p}.years.length"), (y0, f"{p}.years[0]")]))
    ev.append(_s(f"In 8 of 10 past years profit stayed between {f(pr['p10'])} and {f(pr['p90'])} EGP per feddan per year.",
                 f"في 8 من كل 10 سنوات سابقة كان الربح بين {f(pr['p10'])} و{f(pr['p90'])} جنيه للفدان سنوياً.",
                 [(pr["p10"], f"{p}.profit.p10"), (pr["p90"], f"{p}.profit.p90")]))
    wy = r["worst_year"]
    ev.append(_s(f"Worst past window started in {wy['year']}: {f(wy['profit'])} EGP per feddan per year.",
                 f"أسوأ فترة سابقة بدأت في {wy['year']}: {f(wy['profit'])} جنيه للفدان سنوياً.",
                 [(wy["year"], f"{p}.worst_year.year"), (wy["profit"], f"{p}.worst_year.profit")],
                 tone="warn" if wy["profit"] < 0 else "info"))
    losses = round(r["loss_year_share"]["value"] * n)
    ev.append(_s(f"Lost money in {losses} of {n} past years.", f"خسرت في {losses} من {n} سنة سابقة.",
                 [(losses, f"{p}.loss_year_share"), (n, f"{p}.years.length")],
                 tone="warn" if losses else "good"))

    if r["rotation_id"] != "existing":
        d = existing["water_m3"]["median"] - r["water_m3"]["median"]
        if d > 200:
            ben.append(_s(f"Uses about {f(d)} m³ less irrigation water per feddan per year than your current rotation.",
                          f"تستهلك حوالي {f(d)} م³ مياه ري أقل للفدان سنوياً من دورتك الحالية.",
                          [(d, f"{p}.water_m3.median - rotations[0].water_m3.median")], tone="good"))
        elif d < -200:
            gaps.append(_s(f"Needs about {f(-d)} m³ more water per feddan per year than your current rotation.",
                           f"تحتاج حوالي {f(-d)} م³ مياه أكثر للفدان سنوياً من دورتك الحالية.",
                           [(-d, f"{p}.water_m3.median - rotations[0].water_m3.median")], tone="warn"))
        dp = r["profit"]["median"] - existing["profit"]["median"]
        if dp > 500:
            ben.append(_s(f"Median profit about {f(dp)} EGP per feddan per year higher than your current rotation.",
                          f"متوسط الربح أعلى بحوالي {f(dp)} جنيه للفدان سنوياً من دورتك الحالية.",
                          [(dp, f"{p}.profit.median - rotations[0].profit.median")], tone="good"))
        dl = existing["loss_year_share"]["value"] - r["loss_year_share"]["value"]
        if dl > 0.05:
            k = round(dl * n)
            ben.append(_s(f"{k} fewer losing years out of {n} than your current rotation.",
                          f"سنوات خسارة أقل بـ {k} من {n} مقارنة بدورتك الحالية.", [(k, f"{p}.loss_year_share"), (n, "years")],
                          tone="good"))
    for w in r["soil_why"]:
        k = w["kind"]
        if k == "legume":
            lo, hi = w["n"]
            ben.append(_s(f"{name(w['crop'])} is a legume: it leaves roughly {lo}–{hi} kg of nitrogen per feddan for the next crop.",
                          f"{name(w['crop'], 'ar')} محصول بقولي: يترك تقريباً {lo}–{hi} كجم نيتروجين للفدان للمحصول التالي.",
                          [(lo, "assumption:legume_n_credit"), (hi, "assumption:legume_n_credit")], tone="good"))
        elif k == "disease_break":
            ben.append(_s(f"Verdex saw {w['disease']} here: this plan keeps {w['family']} crops off the field for two years.",
                          f"رصد ڤيردكس {DISEASE_AR.get(w['disease'], w['disease'])} هنا: الخطة تُبعد محاصيل العائلة {FAMILY_AR.get(w['family'], w['family'])} عن الحقل لمدة سنتين.",
                          tone="good"))
        elif k == "disease_host":
            rev.append(_s(f"{name(w['crop'])} hosts {w['disease']}, which Verdex saw on this field.",
                          f"{name(w['crop'], 'ar')} عائل لمرض {DISEASE_AR.get(w['disease'], w['disease'])} الذي رصده ڤيردكس في هذا الحقل.",
                          tone="warn"))
        elif k == "repeat":
            rev.append(_s(f"{name(w['crop'])} follows {name(w['prev'])} from the same family ({w['family']}): pests carry over.",
                          f"{name(w['crop'], 'ar')} يأتي بعد {name(w['prev'], 'ar')} من نفس العائلة ({FAMILY_AR.get(w['family'], w['family'])}): الآفات تنتقل.",
                          tone="warn"))
        elif k == "diverse":
            ben.append(_s(f"Uses {w['n']} plant families, which breaks pest and disease cycles.",
                          f"تستخدم {w['n']} عائلات نباتية، مما يكسر دورة الآفات والأمراض.", [(w["n"], "soil_why")], tone="good"))
        elif k == "heavy_clay":
            rev.append(_s("Potato on heavy clay tends to give misshapen tubers.",
                          "البطاطس في الطين الثقيل تعطي غالباً درنات مشوهة.", tone="warn"))

    crops = [c for c in r["seq"] if c != FALLOW]
    assumed = sorted({c for c in crops if any(str(ctx["prices"][c]["src"][k]).startswith("assumption")
                                              for k in ("price", "yield_t", "cost"))})
    if assumed:
        gaps.append(_s("Price, yield or cost for " + ", ".join(name(c) for c in assumed) + " is an editable assumption, not a quoted figure.",
                       "السعر أو الإنتاجية أو التكلفة لـ " + "، ".join(name(c, "ar") for c in assumed) + " افتراض قابل للتعديل وليس رقماً منشوراً."))
    if not ctx["fusion_used"]:
        gaps.append(_s("No field readings yet: every past year counts equally.",
                       "لا توجد قراءات من الحقل بعد: كل السنوات السابقة لها نفس الوزن."))
    if not ctx["smap"]:
        gaps.append(_s("SMAP soil moisture is not connected yet (needs an Earthdata login); POWER root-zone wetness stands in.",
                       "بيانات رطوبة التربة SMAP غير متصلة بعد (تحتاج حساب Earthdata)؛ نستخدم بديلاً من NASA POWER."))
    if ctx["soil_fallback"]:
        gaps.append(_s("Soil texture is a regional default, not measured here.", "قوام التربة قيمة إقليمية افتراضية وليس قياساً من هنا."))
    for s in r["slots"]:
        if s["crop"] != FALLOW and s.get("heat_years", 0) >= max(3, round(0.15 * n)):
            rev.append(_s(f"{name(s['crop'])} hit heat stress in its sensitive stage in {s['heat_years']} of {n} years.",
                          f"{name(s['crop'], 'ar')} تعرّض لإجهاد حراري في مرحلته الحساسة في {s['heat_years']} من {n} سنة.",
                          [(s["heat_years"], f"{p}.slots.heat_years")], tone="warn"))
    if r["excluded"]["is_excluded"]:
        rev.append(_s("Excluded: your water allowance would leave too much of its need unmet.",
                      "مستبعدة: حصة المياه لا تكفي احتياجها.", tone="warn"))
    rev.append(_s("Sowing dates follow a typical calendar; a local agronomist should confirm them.",
                  "مواعيد الزراعة تقويم نموذجي؛ يجب أن يؤكدها مهندس زراعي محلي."))
    return dict(why=why, evidence=ev, benefits=ben, gaps=gaps, review=rev)


def blind_spots(shown: list[dict], ctx: dict) -> list[dict]:
    fams = {family(c) for r in shown for c in r["seq"] if c != FALLOW}
    crops = {c for r in shown for c in r["seq"] if c != FALLOW}
    facts = {"always"}
    facts.add("irrigated" if ctx["irrigated"] else "rainfed")
    facts |= {f"family:{x}" for x in fams if x}
    facts |= {f"crop:{c}" for c in crops}
    if (ctx.get("clay") or 0) > 40:
        facts.add("clay_over_40")
    facts.add("scout_data" if ctx["fusion_used"] else "no_scout_data")
    if ctx.get("disease_seen"):
        facts.add("scout_disease_seen")
    if ctx.get("lat", 0) > 31.0 and ctx.get("lon", 0) > 29.5:
        facts.add("north_delta")
    if ctx.get("cap_binding"):
        facts.add("water_cap_binding")
    out = []
    for b in _BLIND:
        if facts & set(b.get("triggers", [])):
            out.append(dict(id=b["id"], en=b["en"], ar=b["ar"], triggers=[t for t in b["triggers"] if t in facts],
                            needs_native_review=b.get("needs_native_review", True)))
    return out
