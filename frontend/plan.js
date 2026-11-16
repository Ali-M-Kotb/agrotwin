/* AgroTwin Plan Mode
 * A conversation (voice or text) that builds and revises a three-year farm plan through /api/plan/chat,
 * with the plan drawn live beside it: rotation, schedule, ranges, trade-off chart, risks and field intelligence. */
const PlanUI = (() => {
  // Nothing is kept between visits: every page load starts a new conversation with no field chosen.
  const P = { sid: null, open: false, plan: null, next: "location", located: false, awaitMap: false };
  const q = (s) => document.querySelector(s);
  const AR = () => S.lang === "ar";
  const CROP = (c) => cname(c);

  const PIN = `<svg class="pm-pin" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>`;
  const CHIPS = {
    location: [["كفر الشيخ", "Kafr El-Sheikh"], ["الدقهلية", "Dakahlia"], ["البحيرة", "Beheira"], ["المنيا", "Minya"]],
    crops: [["قمح ورز", "Wheat and rice"], ["قمح وذرة", "Wheat and maize"], ["برسيم وذرة", "Berseem and maize"], ["بنجر وقطن", "Sugar beet and cotton"]],
    area: [["فدان", "1 feddan"], ["3 فدان", "3 feddans"], ["5 فدان", "5 feddans"], ["10 فدان", "10 feddans"], ["مش عارف", "I don't know"]],
    salinity: [["الأرض مش مالحة", "Soil is fine"], ["فيها ملوحة شوية", "A bit salty"], ["مش عارف", "I don't know"]],
    canal: [["المية نادر ما تقطع", "Rarely short"], ["بتقطع ساعات", "Sometimes short"], ["بتقطع دايمًا", "Often short"], ["مش عارف", "I don't know"]],
    priority: [["المكسب", "Profit"], ["توفير المية", "Save water"], ["صحة الأرض", "Soil health"], ["الأمان من الخسارة", "Avoid losses"], ["كله زي بعضه", "All equally"]],
    confirm: [["أيوه، اعمل الخطة", "Yes, make the plan"], ["عايز أغيّر حاجة", "Change something"]],
    done: [["خطة تانية", "Another plan"], ["عايز أغيّر حاجة", "Change something"], ["ليه الخطة دي؟", "Why this plan?"], ["امتى أزرع؟", "When do I sow?"], ["عايز أوفّر مية أكتر", "Save more water"], ["أكسب أكتر", "More profit"], ["عايز أزرع رز", "Keep rice"]],
  };

  function build() {
    if (q("#planmode")) return;
    document.body.insertAdjacentHTML("beforeend", `
      <section id="planmode" class="planmode hidden" aria-label="Plan Mode">
        <div class="pm-chat">
          <header><div><div class="kick"></div><b class="pm-title"></b><div class="meta pm-sub"></div></div><button class="pm-x" aria-label="close">×</button></header>
          <div class="pm-log"></div>
          <div class="pm-chips"></div>
          <form class="pm-bar"><button type="button" class="mic" aria-label="talk"><svg><use href="#i-mic"/></svg></button><input type="text" autocomplete="off"><button type="submit" class="send">→</button></form>
        </div>
        <div class="pm-board"><div class="pm-empty"></div><div class="pm-plan hidden"></div></div>
      </section>`);
    q("#planmode .pm-x").onclick = toggle;
    q("#planmode form").onsubmit = (e) => {
      e.preventDefault(); const v = q("#planmode input").value.trim(); if (!v) return;
      q("#planmode input").value = "";
      if (!P.located && !P.plan && byName(v)) return;     // a governorate typed as the answer to "where is your field?"
      send(v);
    };
    q("#planmode .mic").onclick = () => Chat.listen(send, (v) => { q("#planmode input").value = v; });
    q("#planmode .pm-sub").insertAdjacentHTML("afterend", `<div class="pm-ai"></div>`);
    api("/api/ai/status").then((a) => { P.ai = a; aiBadge(); }).catch(() => {});
    labels();
    const header = document.querySelector("header.bar");
    if (header) new ResizeObserver(() => {
      q("#planmode").style.top = header.offsetHeight + "px";
    }).observe(header);
  }

  function labels() {
    if (!q("#planmode")) return;
    if (t("pm_title") === "pm_title") { setTimeout(labels, 250); return; }
    q("#planmode").dir = AR() ? "rtl" : "ltr";
    q("#planmode .kick").textContent = t("pm_kick");
    q("#planmode .pm-title").textContent = t("pm_title");
    q("#planmode .pm-sub").textContent = t("pm_sub");
    q("#planmode input").placeholder = t("pm_ph");
    q("#planmode .pm-empty").innerHTML = t("pm_empty");
    const log = q("#planmode .pm-log");
    if (!log.children.length) msg("bot", t("pm_hello"));
    else if (log.children.length === 1 && log.firstElementChild.classList.contains("bot")) log.firstElementChild.textContent = t("pm_hello");
    chips(); aiBadge();
    if (P.plan) render(P.plan);
    const header = document.querySelector("header.bar");
    if (header) q("#planmode").style.top = header.offsetHeight + "px";
  }

  function aiBadge() {
    const el = q("#planmode .pm-ai"); if (!el || !P.ai) return;
    const on = P.ai.active;
    el.className = "pm-ai " + (on ? "on" : "off");
    el.title = "";
    el.textContent = on ? (AR() ? "المحادثة متاحة" : "Conversation available")
      : (AR() ? "وضع بدون نت: أسئلة وتعديلات أساسية" : "Offline: common questions and plan changes");
  }

  function chips() {
    if (!P.located && !P.plan) return locationChips();
    const set = CHIPS[P.plan ? "done" : (P.next || "crops")] || [];
    q("#planmode .pm-chips").innerHTML = set.map((c) => `<button type="button">${esc(c[AR() ? 0 : 1])}</button>`).join("");
    document.querySelectorAll("#planmode .pm-chips button").forEach((b) => {
      b.onclick = () => send(!P.plan && (P.next || "crops") === "crops"
        ? (AR() ? "أنا بزرع " : "I grow ") + b.textContent : b.textContent);
    });
  }

  function locationChips() {
    const box = q("#planmode .pm-chips");
    box.innerHTML = `<button type="button" class="pm-gps">${PIN}<span>${AR() ? "موقعي الحالي" : "Use my location"}</span></button>`
      + CHIPS.location.map((c) => `<button type="button" class="pm-gov">${esc(c[AR() ? 0 : 1])}</button>`).join("")
      + `<button type="button" class="pm-mappick">${AR() ? "هختار على الخريطة" : "Pick on the map"}</button>`;
    box.querySelector(".pm-gps").onclick = useMyLocation;
    box.querySelectorAll(".pm-gov").forEach((b) => (b.onclick = () => byName(b.textContent)));
    box.querySelector(".pm-mappick").onclick = () => {
      P.awaitMap = true; toggle();
      if (typeof toast === "function") toast(AR() ? "دوس على أرضك في الخريطة" : "Tap your field on the map");
    };
  }

  // the field location: GPS, a governorate name, or a tap on the map
  function nearestPlace(lat, lon) {
    let best = null, bd = 1e9;
    (MapUI.places || []).forEach((p) => { const d = Math.hypot(p[2] - lat, (p[3] - lon) * Math.cos(lat * Math.PI / 180)); if (d < bd) { bd = d; best = p; } });
    return best && bd < 0.6 ? best[AR() ? 1 : 0] : null;      // within ~60 km
  }
  async function setField(lat, lon, label, place) {
    lat = +lat.toFixed(3); lon = +lon.toFixed(3);
    await Promise.resolve(selectSite({ lat, lon })).catch(() => {});
    P.located = true;
    send(label, { located: true, place });
  }
  function useMyLocation() {
    if (!navigator.geolocation) { msg("bot", AR() ? "الجهاز ده مش بيدّي الموقع. اكتب اسم المحافظة أو اختار على الخريطة." : "This device can't share its location. Type your governorate or pick it on the map."); return; }
    msg("bot pending", AR() ? "بحدد موقعك…" : "Finding your location…");
    navigator.geolocation.getCurrentPosition((pos) => {
      q("#planmode .pending")?.remove();
      const { latitude: la, longitude: lo } = pos.coords, near = nearestPlace(la, lo);
      const where = `${near ? (AR() ? "قرب " : "near ") + near + " " : ""}(${la.toFixed(3)}, ${lo.toFixed(3)})`;
      setField(la, lo, (AR() ? "📍 موقعي الحالي" : "📍 My current location"), where);
    }, () => {
      q("#planmode .pending")?.remove();
      msg("bot", AR() ? "مقدرتش أحدد موقعك. اسمح للمتصفح بالموقع، أو اكتب اسم المحافظة، أو اختار على الخريطة." : "I couldn't get your location. Allow location in the browser, type your governorate, or pick it on the map.");
    }, { enableHighAccuracy: true, timeout: 10000 });
  }
  function byName(text) {
    const p = MapUI.findPlace ? MapUI.findPlace(text) : null;
    if (!p) return false;
    setField(p[2], p[3], text, p[AR() ? 1 : 0]);
    return true;
  }
  function pickedOnMap(pt) {
    if (!P.awaitMap) return;
    P.awaitMap = false;
    if (!P.open) toggle();
    const near = nearestPlace(pt.lat, pt.lon);
    P.located = true;
    send(AR() ? "📍 اخترت أرضي على الخريطة" : "📍 I picked my field on the map",
      { located: true, place: `${near ? (AR() ? "قرب " : "near ") + near + " " : ""}(${pt.lat.toFixed(3)}, ${pt.lon.toFixed(3)})` });
  }

  function msg(role, text, extra = "") {
    const log = q("#planmode .pm-log");
    log.insertAdjacentHTML("beforeend", `<div class="msg ${role}" dir="auto">${esc(text)}${extra}</div>`);
    log.scrollTop = log.scrollHeight;
  }

  async function send(text, opt = {}) {
    build(); if (!P.open) toggle();
    msg("me", text);
    msg("bot pending", AR() ? "براجع بيانات أرضك…" : "Checking your field…");
    let r;
    try {
      r = await api("/api/plan/chat", { method: "POST", body: JSON.stringify({ text, lang: S.lang, lat: S.site.lat, lon: S.site.lon, sid: P.sid, located: !!opt.located, place: opt.place || null }) });
    } catch (e) { q("#planmode .pending").remove(); msg("bot", e.message); return; }
    q("#planmode .pending").remove();
    P.sid = r.sid; P.next = r.next_question;
    if (r.next_question === "location") P.located = false;
    const used = (r.tools || []).length ? `<div class="used">${AR() ? "استخدمت: محرّك الخطة (٣٢ سنة طقس ناسا · نبض الأرض · صور الأقمار)" : "used: plan engine (32 years of NASA weather · Field Pulse · satellite field index)"}</div>` : "";
    msg("bot", r.reply, used);
    if (r.plan) { P.plan = r.plan; render(r.plan); }
    else if (P.plan) {                                   // the plan was cleared (e.g. a new field): show the empty board again
      P.plan = null; q("#planmode .pm-plan").classList.add("hidden"); q("#planmode .pm-empty").classList.remove("hidden");
    }
    api("/api/ai/status").then((a) => { P.ai = a; aiBadge(); }).catch(() => {});
    chips();
    Chat.say(r.reply, r.lang === "ar");
  }

  const k = (x) => (Math.abs(x) >= 10000 ? `${fmt(Math.round(x / 1000))}k` : fmt(Math.round(x)));
  function render(p) {
    q("#planmode .pm-empty").classList.add("hidden");
    const el = q("#planmode .pm-plan"); el.classList.remove("hidden");
    const L = AR(), c = p.chosen, cur = p.current, d = p.delta, ft = p.farm_totals;
    const seq = (s) => s.map(CROP).join(" → ");
    const loc = L ? "ar-EG" : "en-GB";
    const dt = (x) => new Date(x + "T00:00:00").toLocaleDateString(loc, { day: "numeric", month: "short", year: "2-digit" });
    const fi = p.field_index || {}, pu = p.pulse || {};
    el.innerHTML = `
      <div class="kick">${t("pm_plan_kick")} · ${esc(L ? p.site.name_ar || p.site.name : p.site.name)}</div>
      <h2>${esc(seq(c.seq.slice(0, 2)))}</h2>
      <div class="meta">${esc(seq(c.seq))}${c.shift_days ? ` · ${t("pm_shift", { d: digits((c.shift_days > 0 ? "+" : "") + c.shift_days) })}` : ""}${c.strategy === "deficit" ? ` · ${t("pm_deficit")}` : ""}</div>
      <div class="pm-figs">
        <div><b>${digits(k(c.profit.p10))}–${digits(k(c.profit.p90))}</b><span>${t("pm_profit")}</span></div>
        <div><b class="${d.profit_egp_per_feddan >= 0 ? "up" : "down"}">${d.profit_egp_per_feddan >= 0 ? "+" : "−"}${digits(k(Math.abs(d.profit_egp_per_feddan)))}</b><span>${t("pm_vs_now")}</span></div>
        <div><b class="${d.water_m3_per_feddan <= 0 ? "up" : "down"}">${d.water_m3_per_feddan <= 0 ? "−" : "+"}${digits(fmt(Math.abs(d.water_m3_per_feddan)))}</b><span>${t("pm_water")}</span></div>
        <div><b>${digits(Math.round(100 * (1 - c.loss_share)))}%</b><span>${t("pm_safe")}</span></div>
      </div>
      ${ft.area_feddan !== 1 ? `<div class="meta">${t("pm_farm", { a: digits(ft.area_feddan), p: digits(k(ft.profit_change_egp)), w: digits(fmt(Math.abs(ft.water_change_m3))) })}</div>` : ""}
      <h3>${t("pm_schedule")}</h3>
      <table class="plain pm-sched"><tr><th>${t("pm_season")}</th><th>${t("pm_crop")}</th><th>${t("pm_sow")}</th><th>${t("pm_harvest")}</th><th>${t("pm_wat")}</th><th>${t("pm_yield")}</th></tr>
        ${p.schedule.map((x) => `<tr><td>${digits(x.year)} · ${t(x.season)}</td><td>${esc(CROP(x.crop))}${x.salt_factor < 0.95 ? ` <small class="down">(${t("pm_salt")} ${digits(Math.round(100 * x.salt_factor))}%)</small>` : ""}</td><td>${dt(x.sow)}</td><td>${dt(x.harvest)}</td><td class="n">${digits(fmt(x.water_m3_per_feddan.median))}</td><td class="n">${digits(x.yield_t_per_feddan.median)}</td></tr>`).join("")}
      </table>
      <h3>${t("pm_tradeoff")}</h3>
      <div id="pm-chart" class="chart small"></div>
      <div class="pm-two">
        <div><h3>${t("pm_intel")}</h3><ul class="pm-list">
          <li>${fi.available ? t("pm_fi", { f: digits(Math.round(100 * fi.factor)) }) : esc(fi.reason || "")}</li>
          <li>${pu && pu.available ? t(pu.send_scout ? "pm_pulse_bad" : "pm_pulse_ok", { d: esc(pu.latest_image || "") }) : t("pm_pulse_na")}</li>
          <li>${t("pm_searched", { n: digits(p.searched), s: digits(p.elapsed_s) })}</li></ul></div>
        <div><h3>${t("pm_risks")}</h3><ul class="pm-list">${p.risks.map((r) => `<li>${esc(L && r.text_ar ? r.text_ar : r.text)}</li>`).join("")}</ul>
          <h3>${t("pm_actions")}</h3><ul class="pm-list">${(L && p.actions_ar ? p.actions_ar : p.actions).map((a) => `<li>${esc(a)}</li>`).join("")}</ul></div>
      </div>
      <div class="meta">${t("pm_source")} · <span class="chip-num" data-src="${esc(p.source)}">${t("source")}</span></div>`;
    const opts = p.options;
    const mk = (f, name, color, size, sym) => ({ x: opts.filter(f).map((o) => o.water_median), y: opts.filter(f).map((o) => o.profit_median), mode: "markers", name, marker: { color, size, symbol: sym || "circle", line: { width: 1, color: "#fff" } },
      text: opts.filter(f).map((o) => `${seq(o.seq.slice(0, 2))}${o.shift_days ? ` (${o.shift_days > 0 ? "+" : ""}${o.shift_days}d)` : ""}${o.strategy === "deficit" ? " 85%" : ""}`), hovertemplate: "%{text}<br>%{x:,} m³ · %{y:,} EGP<extra></extra>" });
    plot("pm-chart", [
      mk((o) => !o.is_current && !o.is_chosen, L ? "اختيارات تانية" : "other options", "#b8c2bb", 8),
      mk((o) => o.is_current, L ? "زراعتك الحالية" : "today's rotation", CLAY, 13, "diamond"),
      mk((o) => o.is_chosen, L ? "الخطة" : "the plan", FIELD, 16, "star"),
    ], { xaxis: { title: { text: L ? "مية الري، م³/فدان/سنة" : "irrigation, m³/feddan/yr", font: { size: 11 } }, gridcolor: "#ece8de" },
      yaxis: { title: { text: L ? "المكسب الوسيط، جنيه/فدان" : "median profit, EGP/feddan", font: { size: 11 } }, gridcolor: "#ece8de" }, margin: { t: 8, b: 44, l: 64, r: 10 } });
  }

  function toggle() {
    build();
    P.open = !P.open;
    q("#planmode").classList.toggle("hidden", !P.open);
    document.body.classList.toggle("planning", P.open);
    const b = q("#btn-plan"); if (b) b.classList.toggle("on", P.open);
    const h = document.querySelector("header.bar");
    if (h) q("#planmode").style.top = h.offsetHeight + "px";
    if (P.open) { labels(); q("#planmode input").focus(); }
  }

  try { localStorage.removeItem("agrotwin.plan.sid"); } catch {}   // clear what older versions kept
  return { toggle, labels, send, pickedOnMap, state: P };
})();
