"""The Council: three advisors explain a result; the Number Auditor decides what reaches the screen.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

Advisors (agronomist, economist, skeptic) receive ONLY the structured result. Each claim must
declare every number it shows as {path, shown_as}, where path points into the result object.
The auditor:
  1. normalises Arabic-Indic digits and thousand separators, extracts every number in the text;
  2. requires each to match a declared entry, and each declared path to resolve to a value that
     rounds to what is shown (integer, one decimal, or ×100 for shares shown as %);
  3. blocks certainty words ("will", "guarantee", "certain", "سوف", "مضمون", "أكيد"...);
  4. replaces any blocked claim with a fixed template and counts it.
With ANTHROPIC_API_KEY (or an `ant auth login` profile) the advisors are written by Claude;
with no credentials or on any error they fall back to the templates. The demo never blocks.
"""
from __future__ import annotations

import json
import re

ADVISORS = ("agronomist", "economist", "skeptic")
MODEL = "claude-opus-5-5"

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
CERTAINTY = re.compile(r"\b(will|guarantee[sd]?|certain(ly)?|definitely|sure to)\b|سوف|سيحقق|مضمون|أكيد|بالتأكيد|حتماً",
                       re.IGNORECASE)
NUM = re.compile(r"-?\d+(?:\.\d+)?")


def normalise(text: str) -> str:
    t = text.translate(ARABIC_DIGITS)
    t = re.sub(r"(?<=\d)[,٬](?=\d{3})", "", t)
    return t.replace("٫", ".")


def resolve(result: dict, path: str):
    """'rotations[1].profit.median', 'years.length', or 'A - B' differences."""
    if " - " in path:
        a, b = path.split(" - ", 1)
        va, vb = resolve(result, a), resolve(result, b)
        return None if va is None or vb is None else va - vb
    cur = result
    for tok in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if tok.startswith("["):
            i = int(tok[1:-1])
            if not isinstance(cur, list) or i >= len(cur):
                return None
            cur = cur[i]
        elif tok == "length" and isinstance(cur, list):
            cur = len(cur)
        elif isinstance(cur, dict) and tok in cur:
            cur = cur[tok]
        else:
            return None
    return cur if isinstance(cur, (int, float)) and not isinstance(cur, bool) else None


def _matches(shown: float, value: float) -> bool:
    cands = [round(value), round(value, 1), round(value * 100), round(value * 100, 1)]
    return any(abs(shown - c) < 1e-6 for c in cands) or abs(abs(shown) - abs(round(value))) < 1e-6


def audit_claim(claim: dict, result: dict) -> tuple[bool, str]:
    raw = claim.get("text", "")
    # Rotation names (e.g. "Wheat → Rice (×3)") are labels, not claims: strip them first.
    for r in result.get("rotations", []):
        for lab in (r.get("label") or {}).values():
            raw = raw.replace(lab, " ")
    text = normalise(raw)
    if CERTAINTY.search(claim.get("text", "")):
        return False, "certainty word"
    declared = []
    for n in claim.get("numbers", []):
        v = resolve(result, n.get("path", ""))
        if v is None:
            return False, f"path does not resolve: {n.get('path')}"
        shown = NUM.findall(normalise(str(n.get("shown_as", ""))))
        if not shown or not _matches(float(shown[0]), v):
            return False, f"{n.get('shown_as')} does not match {n.get('path')} = {v:.4g}"
        declared.append(float(shown[0]))
    for x in NUM.findall(text):
        xv = float(x)
        if not any(abs(xv - d) < 1e-6 or abs(abs(xv) - abs(d)) < 1e-6 for d in declared):
            return False, f"undeclared number {x}"
    return True, "ok"


# ---------------------------------------------------------------------------
# fixed templates (also the fallback for any blocked claim)
# ---------------------------------------------------------------------------

def _fmt(x):
    return f"{round(x):,}"


def templates(result: dict, lang: str = "en") -> dict:
    rots = result["rotations"]
    top_id = result["order"][0]
    i = next(k for k, r in enumerate(rots) if r["rotation_id"] == top_id)
    r, ex = rots[i], rots[0]
    p = f"rotations[{i}]"
    lab = r["label"][lang]
    ar = lang == "ar"
    out = {a: [] for a in ADVISORS}
    nlo, nhi = r["n_credit_kg_fed"]["low"], r["n_credit_kg_fed"]["high"]
    if nhi > 0:
        out["agronomist"].append(dict(
            text=(f"في السجل التاريخي، {lab} تضيف بقوليات تترك {nlo}–{nhi} كجم نيتروجين للفدان على مدى الدورة."
                  if ar else f"{lab} brings in legumes that leave {nlo}–{nhi} kg of nitrogen per feddan over the rotation."),
            numbers=[dict(path=f"{p}.n_credit_kg_fed.low", shown_as=str(nlo)),
                     dict(path=f"{p}.n_credit_kg_fed.high", shown_as=str(nhi))]))
    bd = r["bare_days"]["median"]
    out["agronomist"].append(dict(
        text=(f"التربة تبقى بدون غطاء حوالي {round(bd)} يوماً في الدورة؛ الغطاء يحمي من التعرية."
              if ar else f"The soil sits bare for about {round(bd)} days over the rotation; cover protects it from erosion."),
        numbers=[dict(path=f"{p}.bare_days.median", shown_as=str(round(bd)))]))
    pr = r["profit"]
    out["economist"].append(dict(
        text=(f"في السجل التاريخي كانت {lab} ستحقق بين {_fmt(pr['p10'])} و{_fmt(pr['p90'])} جنيه للفدان سنوياً في 8 من كل 10 سنوات."
              if ar else f"In the historical record, {lab} would have made between {_fmt(pr['p10'])} and {_fmt(pr['p90'])} EGP per feddan per year in 8 of 10 years."),
        numbers=[dict(path=f"{p}.profit.p10", shown_as=_fmt(pr["p10"])), dict(path=f"{p}.profit.p90", shown_as=_fmt(pr["p90"])),
                 dict(path="const.eight", shown_as="8"), dict(path="const.ten", shown_as="10")]))
    wy = r["worst_year"]
    out["economist"].append(dict(
        text=(f"أسوأ فترة بدأت في {wy['year']} بربح {_fmt(wy['profit'])} جنيه للفدان سنوياً."
              if ar else f"Its worst past window began in {wy['year']}, at {_fmt(wy['profit'])} EGP per feddan per year."),
        numbers=[dict(path=f"{p}.worst_year.year", shown_as=str(wy["year"])),
                 dict(path=f"{p}.worst_year.profit", shown_as=_fmt(wy["profit"]))]))
    ls = r["loss_year_share"]["value"]
    out["skeptic"].append(dict(
        text=(f"في {round(ls * 100)}٪ من السنوات السابقة خسرت هذه الدورة؛ والتاريخ ليس توقعاً، فقد يأتي عام أسوأ."
              if ar else f"This rotation lost money in {round(ls * 100)}% of past years, and history is not a forecast: a worse year can come."),
        numbers=[dict(path=f"{p}.loss_year_share.value", shown_as=f"{round(ls * 100)}%")]))
    out["skeptic"].append(dict(
        text=("لا ترى الأقمار الصناعية ملوحة التربة ولا النيماتودا؛ اطلب من مهندس زراعي فحص الحقل قبل التغيير."
              if ar else "Satellites cannot see soil salinity or nematodes; ask a local agronomist to check the field before switching."),
        numbers=[]))
    return out


def _consts(result: dict) -> dict:
    r = dict(result)
    r["const"] = {"eight": 8, "ten": 10}
    return r


# ---------------------------------------------------------------------------
# LLM advisors
# ---------------------------------------------------------------------------

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["advisors"],
    "properties": {"advisors": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["advisor", "claims"],
        "properties": {
            "advisor": {"type": "string", "enum": list(ADVISORS)},
            "claims": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["text", "numbers"],
                "properties": {"text": {"type": "string"},
                               "numbers": {"type": "array", "items": {
                                   "type": "object", "additionalProperties": False, "required": ["path", "shown_as"],
                                   "properties": {"path": {"type": "string"}, "shown_as": {"type": "string"}}}}}}}}}}},
}

SYSTEM = """You are the AgroTwin Council: an agronomist, an economist and a skeptic explaining a crop-rotation
result to a small farmer and to judges. Use ONLY numbers that appear in the JSON you are given.
For every number you write, add an entry to that claim's `numbers` list with the JSON path it came from
(e.g. "rotations[1].profit.p10", "rotations[0].worst_year.year", "years.length", or "A - B" for a difference)
and the text exactly as shown. Shares may be shown as percentages of the stored 0–1 value.
Write about the past ("would have", "in the historical record"); never say will, guarantee or certain.
Two short claims per advisor. The skeptic names a real limit of the data. Plain words, no jargon."""


def _slim(result: dict) -> dict:
    keep = ("rotation_id", "label", "seq", "water_m3", "profit", "season1_profit", "loss_year_share", "worst_year",
            "n_credit_kg_fed", "bare_days", "deficit_days", "heat_stress_share", "scores", "total", "rank", "strength")
    return dict(site=result["site"]["name"], irrigated=result["site"]["irrigated"], years=result["years"],
                order=result["order"], no_clear_winner=result["no_clear_winner"], mode=result["mode"],
                rotations=[{k: r[k] for k in keep if k in r} for r in result["rotations"]])


def llm_claims(result: dict, lang: str) -> dict | None:
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM,
            messages=[{"role": "user", "content":
                       f"Language: {'Arabic (Modern Standard, farmer-friendly)' if lang == 'ar' else 'English'}.\n"
                       f"Result JSON:\n{json.dumps(_slim(result), ensure_ascii=False)}"}],
        )
        if resp.stop_reason == "refusal":
            return None
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
        return {a["advisor"]: a["claims"] for a in data["advisors"]}
    except Exception:
        return None


def explain(result: dict, lang: str = "en", use_llm: bool = True) -> dict:
    tmpl = templates(result, lang)
    src = llm_claims(result, lang) if use_llm else None
    used_llm = src is not None
    src = src or tmpl
    checked = _consts(result)
    out, blocked, total = {}, 0, 0
    for a in ADVISORS:
        claims = []
        fallback = tmpl.get(a, [])
        for k, c in enumerate(src.get(a, [])):
            total += 1
            ok, why = audit_claim(c, checked)
            if ok:
                claims.append(dict(text=c["text"], numbers=c["numbers"], audited=True))
            else:
                blocked += 1
                fb = fallback[k] if k < len(fallback) else None
                if fb and audit_claim(fb, checked)[0]:
                    claims.append(dict(text=fb["text"], numbers=fb["numbers"], audited=True, replaced=why))
        out[a] = claims
    return dict(advisors=out, lang=lang, model=MODEL if used_llm else "templates",
                audit=dict(passed=blocked == 0, claims=total, blocked_claims=blocked, fallback_used=not used_llm),
                note="Every number shown passed the Number Auditor against the engine's result.")
