"""Field Card: one printable page, one WhatsApp text (< 600 characters), one local QR code.

Built only from the result object; the QR is generated on this machine (no outside service).
"""
from __future__ import annotations

import html
import io

import qrcode
import qrcode.image.svg

from crops import FALLOW, name

def _f(x):
    return f"{round(x):,}"

def qr_svg(url: str) -> str:
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()

def _top(result):
    tid = result["order"][0]
    return next(r for r in result["rotations"] if r["rotation_id"] == tid)

def whatsapp(result: dict, lang: str, url: str) -> str:
    r, ex = _top(result), result["rotations"][0]
    site = result["site"]["name_ar" if lang == "ar" else "name"]
    pr = r["profit"]
    dw = ex["water_m3"]["median"] - r["water_m3"]["median"]
    losses = round(r["loss_year_share"]["value"] * len(r["years"]))
    if lang == "ar":
        lines = [f"🌱 أجروتوين — {site}", f"الاقتراح: {r['label']['ar']}",
                 f"الربح في 8 من 10 سنوات: {_f(pr['p10'])}–{_f(pr['p90'])} جنيه/فدان/سنة",
                 f"سنوات خسارة: {losses} من {len(r['years'])}"]
        if r["rotation_id"] != "existing" and dw > 200:
            lines.append(f"توفير مياه: ~{_f(dw)} م³/فدان/سنة")
        lines += ["⚠️ راجع ملوحة التربة والآفات مع مهندس زراعي.", f"البيانات: {result['mode'] if result['mode'] != 'NONE' else 'ناسا فقط'}", url]
    else:
        lines = [f"🌱 AgroTwin — {site}", f"Suggested: {r['label']['en']}",
                 f"Profit in 8 of 10 past years: {_f(pr['p10'])}–{_f(pr['p90'])} EGP/feddan/yr",
                 f"Losing years: {losses} of {len(r['years'])}"]
        if r["rotation_id"] != "existing" and dw > 200:
            lines.append(f"Water saved: ~{_f(dw)} m³/feddan/yr")
        lines += ["⚠️ Check salinity and pests with a local agronomist.",
                  f"Data: {result['mode'] if result['mode'] != 'NONE' else 'NASA only'}", url]
    text = "\n".join(lines)
    return text if len(text) < 600 else text[:590] + "…"

def card_html(result: dict, lang: str, url: str) -> str:
    ar = lang == "ar"
    L = (lambda en, a: a if ar else en)
    r = _top(result)
    t = r["text"]
    esc = html.escape
    rows = "".join(
        f"<tr><td>{s['year']}</td><td>{L('Winter','شتوي') if s['season']=='winter' else L('Summer','صيفي')}</td>"
        f"<td>{esc(name(s['crop'], lang))}</td><td>{_f(s.get('water_m3', 0)) if s['crop'] != FALLOW else '–'}</td></tr>"
        for s in r["slots"])
    bars = "".join(f"<i class='{b['cls']}' title='{b['year']}: {_f(b['profit'])}'></i>" for b in r["barcode"])
    lst = lambda items: "".join(f"<li>{esc(x[lang])}</li>" for x in items)
    blind = "".join(f"<li><b>{esc(b[lang]['title'])}</b> — {esc(b[lang]['check'])}</li>" for b in result["blind_spots"][:5])
    return f"""<!doctype html><html lang="{lang}" dir="{'rtl' if ar else 'ltr'}"><head><meta charset="utf-8">
<title>AgroTwin Field Card</title><style>
body{{font:13px/1.45 -apple-system,'Segoe UI','Geeza Pro',sans-serif;margin:14mm;color:#18241c}}
h1{{font-size:20px;margin:0}} h2{{font-size:15px;margin:14px 0 6px}} table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #bbb;padding:4px 6px;text-align:start}} .bc{{display:flex;gap:1px;height:22px;margin:4px 0}}
.bc i{{flex:1}} .green{{background:#2f7d4f}} .amber{{background:#e0a526}} .red{{background:#c0392b}}
.top{{display:flex;justify-content:space-between;gap:16px}} .badge{{border:1px solid #333;border-radius:6px;padding:2px 8px;font-weight:700}}
.qr svg{{width:110px;height:110px}} .muted{{color:#666;font-size:11px}}
@media print{{@page{{size:A4;margin:10mm}} body{{margin:0}}}}</style></head><body>
<div class="top"><div><h1>{L('AgroTwin Field Card','بطاقة الحقل — أجروتوين')}</h1>
<div>{esc(result['site']['name_ar' if ar else 'name'])} · {result['site']['lat']}, {result['site']['lon']}</div>
<div style="margin-top:6px"><span class="badge">{result['mode']}</span></div>
<h2>{L('Our suggestion','اقتراحنا')}: {esc(r['label'][lang])}</h2>
<div>{L('Profit in 8 of 10 past years','الربح في 8 من 10 سنوات')}: <b>{_f(r['profit']['p10'])} – {_f(r['profit']['p90'])}</b> {L('EGP / feddan / year','جنيه/فدان/سنة')}</div>
<div>{L('Water','المياه')}: <b>{_f(r['water_m3']['median'])}</b> {L('m³ / feddan / year','م³/فدان/سنة')}</div></div>
<div class="qr">{qr_svg(url)}<div class="muted">{L('Scan to open','امسح للفتح')}</div></div></div>
<h2>{L('Harvest Barcode: one stripe per past year','باركود الحصاد: شريط لكل سنة سابقة')}</h2><div class="bc">{bars}</div>
<div class="muted">{L('green = profit, amber = thin margin, red = loss','أخضر = ربح، أصفر = هامش ضعيف، أحمر = خسارة')} · {r['years'][0]}–{r['years'][-1]}</div>
<h2>{L('Plan','الخطة')}</h2><table><tr><th>{L('Year','السنة')}</th><th>{L('Season','الموسم')}</th><th>{L('Crop','المحصول')}</th><th>{L('Irrigation m³/feddan','الري م³/فدان')}</th></tr>{rows}</table>
<h2>{L('Why','لماذا')}</h2><ul>{lst(t['why'] + t['benefits'][:3])}</ul>
<h2>{L('Three actions','ثلاث خطوات')}</h2><ol>
<li>{L('Show this card to your agronomist and check the list below.','اعرض هذه البطاقة على المهندس الزراعي وراجع القائمة بالأسفل.')}</li>
<li>{L('Confirm seed and buyer for the first crop before sowing.','تأكد من التقاوي والمشتري للمحصول الأول قبل الزراعة.')}</li>
<li>{L('Let the Verdex Scout read your soil this season to narrow the range.','اترك روبوت ڤيردكس يقرأ تربتك هذا الموسم لتضييق المدى.')}</li></ol>
<h2>{L('What satellites cannot see: check locally','ما لا تراه الأقمار الصناعية: يُفحص محلياً')}</h2><ul>{blind}</ul>
<p class="muted">{L('History is not a forecast. AgroTwin supports your judgment and your agronomist; it never replaces them. Data: NASA POWER, MODIS, SoilGrids, Verdex Scout.',
'التاريخ ليس توقعاً. أجروتوين يدعم قرارك ومهندسك الزراعي ولا يحل محلهما. البيانات: NASA POWER وMODIS وSoilGrids وروبوت ڤيردكس.')}</p>
</body></html>"""
