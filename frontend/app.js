/* AgroTwin front end — AI-generated (Claude, Anthropic) under human review.
 * Plain JS, no build step, works offline (Leaflet + Plotly bundled). Talks to backend/app.py. */
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const ROT_COLORS = { existing: "#7a7f7a", alt_1: "#23704a", alt_2: "#2b6cb0" };

const S = {
  lang: "en", lens: "farmer", arDigits: false, I: {}, crops: {}, prices: {}, assumptions: [], sources: {},
  sites: [], site: null, siteData: null, result: null, prevResult: null, council: null, validation: null,
  tab: "danger", map: null, pin: null, robotMarker: null, simSeq: 0, selSeq: 0, candidates: new Set(),
  robotOn: false, detail: {},
};

// ---------------------------------------------------------------------------
// i18n + number formatting
// ---------------------------------------------------------------------------
function t(k, vars = {}) {
  let s = (S.I[S.lang] && S.I[S.lang][k]) ?? S.I.en?.[k] ?? k;
  for (const [a, b] of Object.entries(vars)) s = s.replaceAll(`{${a}}`, b);
  return s;
}
const AR_DIG = "٠١٢٣٤٥٦٧٨٩";
function digits(s) { return S.lang === "ar" && S.arDigits ? String(s).replace(/[0-9]/g, (d) => AR_DIG[d]) : String(s); }
function fmt(x, d = 0) {
  if (x == null || isNaN(x)) return "–";
  return digits(Number(x).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }));
}
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
// Every number on screen is a chip that opens its source tag.
function num(v, src, d = 0, suffix = "") {
  return `<span class="chip-num" tabindex="0" data-src="${esc(src || "computed")}">${fmt(v, d)}${suffix}</span>`;
}
function cname(c) {
  if (c === "fallow") return t("fallow");
  const k = S.crops[c];
  return k ? (S.lang === "ar" ? k.name_ar : k.name) : c;
}
async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
function busy(on) { $("#loading").classList.toggle("hidden", !on); $("#loading-text").textContent = t("loading"); }

function applyI18n() {
  document.documentElement.lang = S.lang;
  document.documentElement.dir = S.lang === "ar" ? "rtl" : "ltr";
  $$("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  $$("[data-i18n-ph]").forEach((el) => (el.placeholder = t(el.dataset.i18nPh)));
  if (window.MapUI && MapUI.map) MapUI.relabel();
  $("#btn-digits").classList.toggle("hidden", S.lang !== "ar");
  $("#mode-badge").title = t("mode_hint");
}

// ---------------------------------------------------------------------------
// inputs
// ---------------------------------------------------------------------------
function buildInputs() {
  const keepW = $("#ex-w").value, keepS = $("#ex-s").value;
  for (const [id, season] of [["ex-w", "winter"], ["ex-s", "summer"]]) {
    const opts = Object.entries(S.crops).filter(([, c]) => c.season === season).map(([k]) => k).concat(["fallow"]);
    $("#" + id).innerHTML = opts.map((k) => `<option value="${k}">${esc(cname(k))}</option>`).join("");
  }
  if (keepW) $("#ex-w").value = keepW;
  if (keepS) $("#ex-s").value = keepS;
  const box = $("#cand");
  box.innerHTML = "";
  Object.keys(S.crops).forEach((k) => {
    const el = document.createElement("span");
    el.className = "chip" + (S.candidates.has(k) ? " on" : "");
    el.textContent = cname(k);
    el.onclick = () => { S.candidates.has(k) ? S.candidates.delete(k) : S.candidates.add(k); el.classList.toggle("on"); schedule(); };
    box.appendChild(el);
  });
  $("#leaf-class").innerHTML = Object.entries(S.diseaseClasses || {}).map(([k, v]) => `<option value="${k}">${esc(v[1])}</option>`).join("");
  $("#leaf-class").value = "Potato___Late_blight";
  renderSiteChips();
}

function renderSiteChips() {
  const box = $("#site-chips");
  box.innerHTML = "";
  S.sites.forEach((s) => {
    const el = document.createElement("span");
    const on = S.site && Math.abs(S.site.lat - s.lat) < 1e-3 && Math.abs(S.site.lon - s.lon) < 1e-3;
    el.className = "chip site" + (on ? " on" : "");
    el.textContent = S.lang === "ar" ? s.name_ar : s.name;
    el.title = s.role || "";
    el.onclick = () => selectSite(s);
    box.appendChild(el);
  });
}

function sliderOut(id) {
  const v = +$("#" + id).value;
  if (id === "x-rain" || id === "x-price") return (v > 0 ? "+" : "") + digits(v) + "%";
  if (id === "x-warm") return "+" + digits(v) + "°";
  return digits(v);
}

function body(extra = {}) {
  return {
    lat: S.site.lat, lon: S.site.lon,
    existing: [$("#ex-w").value, $("#ex-s").value],
    candidates: [...S.candidates],
    weights: Object.fromEntries(["water", "soil", "profit", "risk"].map((k) => [k, +$("#w-" + k).value])),
    rain_mult: 1 + +$("#x-rain").value / 100, temp_offset: +$("#x-warm").value, price_mult: 1 + +$("#x-price").value / 100,
    water_cap_m3: $("#cap-on").checked ? { winter: +$("#cap-w").value, summer: +$("#cap-s").value } : null,
    ...extra,
  };
}

// ---------------------------------------------------------------------------
// map + site
// ---------------------------------------------------------------------------
async function initMap() {
  await MapUI.init({ lang: () => S.lang, onPick: (p) => selectSite(p), onFarmOpen: openFarm });
  S.map = MapUI.map;
}

// ---------------------------------------------------------------------------
// modes: Simple (guided, farmer) / Advanced (map tools, every panel)
// ---------------------------------------------------------------------------
function setMode(m) {
  S.mode = m;
  document.body.dataset.mode = m;
  $$(".modes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === m));
  if (m === "simple") setLens("farmer");
  try { localStorage.setItem("agrotwin.mode", m); } catch {}
  setTimeout(() => { if (S.map) S.map.invalidateSize(); window.dispatchEvent(new Event("resize")); }, 60);
  if (S.result) renderHero();
}

const PRESETS = { water: "w-water", soil: "w-soil", profit: "w-profit", risk: "w-risk" };
function syncPris() {
  $$("#pris button").forEach((b) => b.classList.toggle("on", +$("#" + PRESETS[b.dataset.p]).value >= 3));
}
function wizardBind() {
  const mirror = (a, b) => { $(a).onchange = () => { $(b).value = $(a).value; schedule(); }; };
  $("#sw-w").innerHTML = $("#ex-w").innerHTML; $("#sw-s").innerHTML = $("#ex-s").innerHTML;
  $("#sw-w").value = $("#ex-w").value; $("#sw-s").value = $("#ex-s").value;
  mirror("#sw-w", "#ex-w"); mirror("#sw-s", "#ex-s");
  $$("#pris button").forEach((b) => (b.onclick = () => {
    const inp = $("#" + PRESETS[b.dataset.p]);
    inp.value = +inp.value >= 3 ? 1 : 4;
    inp.dispatchEvent(new Event("input"));
    syncPris();
  }));
  syncPris();
}
function toast(msg) {
  const el = $("#toast"); el.textContent = msg; el.classList.remove("hidden");
  clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.add("hidden"), 2600);
}

// ---------------------------------------------------------------------------
// My farms (saved on this machine via the API)
// ---------------------------------------------------------------------------
async function loadFarms() {
  try { S.farms = await api("/api/farms"); } catch { S.farms = []; }
  MapUI.showFarms(S.farms);
  renderFarms();
}
function renderFarms() {
  const ar = S.lang === "ar";
  $("#farms").innerHTML = (S.farms || []).map((f) => `<li data-id="${f.id}" class="${S.farm && S.farm.id === f.id ? "on" : ""}">
      <span><b>${esc(f.name)}</b><br><small>${f.area_ha ? fmt(f.area_ha / 0.42, 2) + (ar ? " فدان" : " feddan") + " · " : ""}${esc(cname(f.existing[0]))} / ${esc(cname(f.existing[1]))} · ${(f.plans || []).length} ${ar ? "خطة" : "plans"}</small></span>
      <button class="ghost small" data-del="${f.id}">✕</button></li>`).join("") || `<li class="meta">${t("farms_empty")}</li>`;
  $$("#farms li[data-id]").forEach((li) => (li.onclick = (e) => {
    if (e.target.dataset.del) return;
    openFarm(S.farms.find((f) => f.id === li.dataset.id));
  }));
  $$("#farms button[data-del]").forEach((b) => (b.onclick = async () => {
    await fetch(`/api/farms/${b.dataset.del}`, { method: "DELETE" });
    if (S.farm && S.farm.id === b.dataset.del) S.farm = null;
    loadFarms();
  }));
  const f = S.farm && (S.farms || []).find((x) => x.id === S.farm.id);
  $("#farm-plans").innerHTML = f && f.plans && f.plans.length ? `<h3>${t("farm_plans")}: ${esc(f.name)}</h3><ul class="plans">${f.plans.map((p) =>
    `<li><b>${esc(p.label)}</b> · ${esc(p.saved)}<br>${fmt(p.profit.p10)}–${fmt(p.profit.p90)} ${t("per_fed_yr")} · ${fmt(p.water_m3.median)} m³ · ${esc(p.mode)}</li>`).join("")}</ul>` : "";
  $("#farm-name").value = S.farm ? S.farm.name : "";
}
function openFarm(f) {
  S.farm = f;
  $("#ex-w").value = f.existing[0]; $("#ex-s").value = f.existing[1];
  selectSite({ lat: f.lat, lon: f.lon, polygon: f.polygon, area_ha: f.area_ha, farmName: f.name });
  renderFarms();
}
async function saveFarm() {
  if (!S.site) return;
  const name = $("#farm-name").value.trim() || (S.lang === "ar" ? "حقلي" : "My field");
  const fld = MapUI.getField();
  const meta = (S.siteData && S.siteData.meta) || {};
  const body = { id: S.farm && S.farm.name === name ? S.farm.id : null, name, lat: S.site.lat, lon: S.site.lon,
    polygon: fld ? fld.polygon : null, area_ha: fld ? fld.area_ha : null,
    existing: [$("#ex-w").value, $("#ex-s").value], irrigated: meta.irrigated !== false };
  S.farm = await api("/api/farms", { method: "POST", body: JSON.stringify(body) });
  await loadFarms();
  toast(t("farm_saved"));
}
async function savePlan() {
  if (!S.result) return;
  if (!S.farm) await saveFarm();
  const top = topRot();
  await api(`/api/farms/${S.farm.id}/plans`, { method: "POST", body: JSON.stringify({
    label: top.label[S.lang], rotation_id: top.rotation_id, seq: top.seq, profit: top.profit, water_m3: top.water_m3,
    loss_year_share: top.loss_year_share.value, scenario: S.result.scenario, weights: S.result.weights, mode: S.result.mode }) });
  await loadFarms();
  toast(t("plan_saved"));
}

async function selectSite(s) {
  const mine = ++S.selSeq;
  S.site = s;
  if (s.polygon) MapUI.setField(s.polygon);
  else if (s.id) MapUI.setField(null);
  if (S.farm && (Math.abs(S.farm.lat - s.lat) > 1e-3 || Math.abs(S.farm.lon - s.lon) > 1e-3)) { S.farm = null; renderFarms(); }
  if (S.pin) S.pin.setLatLng([s.lat, s.lon]); else S.pin = L.marker([s.lat, s.lon]).addTo(S.map);
  S.map.flyTo([s.lat, s.lon], Math.max(S.map.getZoom(), s.polygon ? 15 : 11), { duration: 0.8 });
  renderSiteChips();
  busy(true);
  try {
    const d = await api(`/api/site?lat=${s.lat}&lon=${s.lon}`);
    if (mine !== S.selSeq) return;
    S.siteData = d;
    const meta = d.meta || {};
    if (meta.existing && !s.farmName) { $("#ex-w").value = meta.existing[0]; $("#ex-s").value = meta.existing[1]; }
    $("#sw-w").value = $("#ex-w").value; $("#sw-s").value = $("#ex-s").value;
    const fld = MapUI.getField();
    $("#wiz-field").textContent = (s.farmName || (S.lang === "ar" ? (meta.name_ar || meta.name) : meta.name)) +
      (fld ? ` · ${(fld.area_ha / 0.42).toFixed(2)} ${S.lang === "ar" ? "فدان" : "feddan"}` : "");
    siteMeta();
    renderDiag();
    S.prevResult = null;
    await simulate();
    watchSite(s.lat, s.lon);
  } catch (e) { $("#site-meta").textContent = e.message; }
  finally { if (mine === S.selSeq) busy(false); }
}

function siteMeta() {
  const d = S.siteData, m = d.meta || {};
  const sc = S.soilNames?.[d.soil_class]?.[S.lang === "ar" ? 1 : 0] || d.soil_class;
  $("#site-meta").innerHTML = `${esc(S.lang === "ar" ? (m.name_ar || m.name) : m.name)} · ${m.irrigated ? t("irrigated") : t("rainfed")}<br>
    ${digits(d.lat.toFixed(3))}, ${digits(d.lon.toFixed(3))} · ${esc(sc)} (${num(d.soil.clay, d.soil.source, 0, "% clay")})${d.soil.fallback ? " *" : ""}`;
}

async function watchSite(lat, lon) {
  const tok = (S.watch = (S.watch || 0) + 1);
  let prev = null;
  while (tok === S.watch) {
    let st;
    try { st = await api(`/api/site/status?lat=${lat}&lon=${lon}`); } catch { return; }
    const loading = st.soil === "loading" || st.ndvi.state === "loading" || st.et.state === "loading";
    const pct = (p) => (p.total ? Math.round((100 * p.done) / p.total) + "%" : "…");
    $("#site-progress").classList.toggle("hidden", !loading);
    if (loading) $("#site-progress").textContent = `${t("bg_loading")}: soil ${st.soil === "loading" ? "…" : "✓"} · NDVI ${st.ndvi.state === "loading" ? pct(st.ndvi) : "✓"} · ET ${st.et.state === "loading" ? pct(st.et) : "✓"}`;
    if (prev && ((prev.soil === "loading" && st.soil !== "loading") || (prev.ndvi.state === "loading" && st.ndvi.state !== "loading"))) {
      S.siteData = await api(`/api/site?lat=${lat}&lon=${lon}`);
      siteMeta(); renderDiag(); simulate();
    }
    prev = st;
    if (!loading) return;
    await new Promise((r) => setTimeout(r, 2500));
  }
}

// ---------------------------------------------------------------------------
// simulate + render
// ---------------------------------------------------------------------------
let timer = null;
function schedule() { clearTimeout(timer); timer = setTimeout(simulate, 300); }

async function simulate(reason) {
  if (!S.site) return;
  const mine = ++S.simSeq;
  try {
    const res = await api("/api/simulate", { method: "POST", body: JSON.stringify(body()) });
    if (mine !== S.simSeq) return;
    S.prevResult = S.result;
    S.result = res;
    S.council = null;
    render(reason);
    loadAhead();
    loadTM(); loadPulse();
    loadInvest();
    if (S.canal) runCanal.stale = true;
  } catch (e) {
    $("#showdown-sub").textContent = e.message;
  }
}

async function loadAhead() {
  const key = `${S.site.lat},${S.site.lon},${$("#ex-w").value},${$("#ex-s").value}`;
  if (S.aheadKey === key && S.ahead) return renderAhead();
  S.aheadKey = key;
  $("#ahead").innerHTML = `<div class="meta">${t("ahead_loading")}</div>`;
  try { S.ahead = await api(`/api/ahead?lat=${S.site.lat}&lon=${S.site.lon}&winter=${$("#ex-w").value}&summer=${$("#ex-s").value}`); }
  catch (e) { S.ahead = null; $("#ahead").innerHTML = `<div class="meta">${esc(e.message)}</div>`; return; }
  renderAhead();
}
function renderAhead() {
  const A = S.ahead, p = A && A.plan;
  if (!p || !p.available) { $("#ahead").innerHTML = `<div class="meta">${t("ahead_none")}</div>`; return; }
  const loc = S.lang === "ar" ? "ar-EG" : "en-GB";
  const dname = (d) => new Date(d + "T00:00:00").toLocaleDateString(loc, { weekday: "short", day: "numeric", month: "short" });
  const irr = new Set(p.irrigate_on.map((e) => e.date));
  let call;
  if (p.irrigate_on.length) {
    const e = p.irrigate_on[0];
    call = t("ahead_irrigate", { day: dname(e.date), m3: fmt(e.gross_m3_per_feddan) });
  } else if (S.result && !S.result.site.irrigated) call = t("ahead_rainfed", { rain: fmt(p.forecast_rain_mm, 1) });
  else call = t("ahead_noirr");
  const next = p.next_crop && !p.crop_now ? `<div class="meta">${t("ahead_next", { crop: cname(p.next_crop.crop), day: dname(p.next_crop.sow) })}</div>` : "";
  const bars = p.wetness.map((w) => `<div class="${w.forecast ? "fc" : ""}${irr.has(w.date) ? " irr" : ""}" title="${w.date}: ${Math.round(w.value * 100)}%"><i style="height:${Math.round(w.value * 100)}%"></i></div>`).join("");
  const first = p.wetness[0], last = p.wetness[p.wetness.length - 1];
  let out = `<div class="ahead-call">${esc(call)}</div>${next}
    <div class="ahead-days">${bars}</div>
    <div class="ahead-axis"><span>${first ? dname(first.date) : ""}</span><span>${t("ahead_axis")}</span><span>${last ? dname(last.date) : ""}</span></div>
    <div class="meta">${t("ahead_totals", { rain: fmt(p.forecast_rain_mm, 1), et0: fmt(p.forecast_et0_mm, 0) })} · <span class="chip-num" data-src="${esc(p.source)}">${t("source")}</span></div>`;
  const se = A.seasonal;
  if (se && se.available && S.mode === "advanced") {
    const q = se.periods.find((x) => x.months === 3) || se.periods[0];
    const word = (d) => d.above > 0.5 ? t("out_above") : d.below > 0.5 ? t("out_below") : t("out_normal");
    out += `<div class="outlook"><b>${t("out_title")}</b> (${q.start} → ${q.end}, ${q.members} ${t("out_members")}): ${t("out_rain")} ${word(q.rain)}, ${t("out_temp")} ${word(q.tmax)}.
      <span class="chip-num" data-src="${esc(se.caveat)}">${t("out_caveat")}</span></div>`;
  }
  $("#ahead").innerHTML = out;
}


// ---------------------------------------------------------------------------
// shared chart look (no default Plotly styling)
// ---------------------------------------------------------------------------
const INK = "#1b1f1a", RULE = "#d9d4c7", FIELD = "#2e5e3a", NILE = "#2d5f8b", CLAY = "#b5562a", WHEAT = "#c9972b";
function plot(id, traces, layout = {}) {
  Plotly.react(id, traces, Object.assign({
    margin: { t: 8, b: 34, l: 52, r: 10 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: getComputedStyle(document.body).fontFamily, size: 11, color: "#4a5148" },
    xaxis: { gridcolor: "#ece8de", linecolor: RULE, zeroline: false }, yaxis: { gridcolor: "#ece8de", linecolor: RULE, zeroline: false },
    legend: { orientation: "h", y: -0.22, font: { size: 11 } }, showlegend: true,
  }, layout), { displayModeBar: false, responsive: true });
}

// ---------------------------------------------------------------------------
// Field Pulse: our trained model (backend/pulse.py, qa/PULSE.md)
// ---------------------------------------------------------------------------
async function loadPulse() {
  const key = `${S.site.lat},${S.site.lon}`;
  if (S.pulseKey === key && S.pulse) return renderPulse();
  S.pulseKey = key; S.pulse = null;
  $("#pulse").innerHTML = `<div class="meta">…</div>`;
  try { S.pulse = await api(`/api/pulse?lat=${S.site.lat}&lon=${S.site.lon}`); }
  catch (e) { $("#pulse").innerHTML = `<div class="meta">${esc(e.message)}</div>`; return; }
  renderPulse();
}
function dateStr(d) {
  return new Date(d + "T00:00:00").toLocaleDateString(S.lang === "ar" ? "ar-EG" : "en-GB", { day: "numeric", month: "long" });
}
function pulseWord(v) {
  if (v == null) return "–";
  const k = v >= 0.6 ? "pl_v_full" : v >= 0.4 ? "pl_v_green" : v >= 0.25 ? "pl_v_thin" : "pl_v_bare";
  return t(k);
}
function renderPulse() {
  const P = S.pulse, L = S.lang;
  if (!P) return;
  if (!P.available) { $("#pulse").innerHTML = `<div class="meta">${esc(P.reason)}</div>`; Plotly.purge("pulse-chart"); return; }
  const c = P.latest_check, f = P.forecast[0], f2 = P.forecast[1];
  const status = c ? t("pl_st_" + c.status) : "";
  const trend = f ? (f.mid > P.latest_ndvi + 0.03 ? t("pl_up") : f.mid < P.latest_ndvi - 0.03 ? t("pl_down") : t("pl_flat")) : "";
  const sk = P.skill || {};
  $("#pulse").innerHTML = `
    <div class="bigline">${t("pl_line", { date: dateStr(P.latest_image), word: pulseWord(P.latest_ndvi), v: digits(P.latest_ndvi.toFixed(2)), status })}</div>
    ${f ? `<div class="meta">${t("pl_next", { trend, lo: digits(f.low.toFixed(2)), hi: digits(f.high.toFixed(2)), normal: digits(f.normal.toFixed(2)) })}</div>` : ""}
    ${P.send_scout ? `<div class="flag">${t("pl_scout")}</div>` : ""}
    <div class="meta">${t("pl_skill", { pct: digits(Math.round(100 * (sk.skill_vs_persistence_16d || 0))), cov: digits(Math.round(100 * (sk.coverage_80_16d || 0))), n: fmt(P.trained_on ? P.trained_on.samples : 0) })}
      · <a href="/methods#pulse">${t("how_link")}</a> · <span class="chip-num" data-src="${esc(P.source + ". " + P.caveat)}">${t("source")}</span></div>`;
  const ch = P.checks;
  const fx = [ch.length ? ch[ch.length - 1].date : P.latest_image].concat(P.forecast.map((x) => x.date));
  const flo = [P.latest_ndvi].concat(P.forecast.map((x) => x.low)), fhi = [P.latest_ndvi].concat(P.forecast.map((x) => x.high));
  const below = ch.filter((x) => x.status === "below");
  plot("pulse-chart", [
    { x: ch.map((x) => x.date).concat(ch.map((x) => x.date).reverse()), y: ch.map((x) => x.high).concat(ch.map((x) => x.low).reverse()), fill: "toself", fillcolor: "rgba(46,94,58,0.12)", line: { width: 0 }, name: L === "ar" ? "المتوقّع من الطقس" : "expected from the weather", hoverinfo: "skip" },
    { x: ch.map((x) => x.date), y: ch.map((x) => x.observed), mode: "lines+markers", line: { color: FIELD, width: 2 }, marker: { size: 4 }, name: L === "ar" ? "اللي القمر الصناعي شافه" : "seen by MODIS" },
    { x: fx.concat([...fx].reverse()), y: fhi.concat([...flo].reverse()), fill: "toself", fillcolor: "rgba(201,151,43,0.22)", line: { width: 0 }, name: L === "ar" ? "توقّع ١٦ و٣٢ يوم" : "16- and 32-day forecast", hoverinfo: "skip" },
    { x: fx, y: [P.latest_ndvi].concat(P.forecast.map((x) => x.mid)), mode: "lines", line: { color: WHEAT, width: 2, dash: "dot" }, showlegend: false },
    { x: below.map((x) => x.date), y: below.map((x) => x.observed), mode: "markers", marker: { color: CLAY, size: 9, symbol: "x" }, name: L === "ar" ? "أقل من المتوقّع" : "below expected" },
  ], { yaxis: { title: { text: "NDVI", font: { size: 10 } }, gridcolor: "#ece8de", range: [0, 1] } });
}

// ---------------------------------------------------------------------------
// Time machine: the field's past seasons, read from MODIS and replayed
// ---------------------------------------------------------------------------
async function loadTM() {
  const key = `${S.site.lat},${S.site.lon},${$("#ex-w").value},${$("#ex-s").value}`;
  if (S.tmKey === key && S.tm) return renderTM();
  S.tmKey = key; S.tm = null;
  $("#tm").innerHTML = `<div class="meta">…</div>`;
  try { S.tm = await api(`/api/timemachine?lat=${S.site.lat}&lon=${S.site.lon}&winter=${$("#ex-w").value}&summer=${$("#ex-s").value}`); }
  catch (e) { $("#tm").innerHTML = `<div class="meta">${esc(e.message)}</div>`; return; }
  renderTM();
}
function renderTM() {
  const T = S.tm, L = S.lang;
  if (!T || !T.available) { $("#tm").innerHTML = `<div class="meta">${t("tm_none")}</div>`; Plotly.purge("tm-chart"); return; }
  const last = T.years[T.years.length - 1];
  const fld = MapUI.getField && MapUI.getField();
  const fed = fld ? fld.area_ha / 0.42 : null;
  const strip = T.years.flatMap((y) => y.seasons.map((s) => {
    const c = s.satellite.cropped, cls = c === true ? "g" : c === false ? "b" : "u";
    return `<div class="${cls}" title="${y.year} ${t(s.season)}: NDVI ${s.satellite.peak ?? "–"}">${s.season === "winter" ? "W" : "S"}</div>`;
  })).join("");
  const rows = T.years.map((y) => `<tr><td>${esc(y.year)}</td>
      <td class="n">${fmt(y.actual.profit)} · ${fmt(y.actual.water_m3)} m³</td>
      <td class="n">${fmt(y.suggested.profit)} · ${fmt(y.suggested.water_m3)} m³</td>
      <td class="n ${y.cum_extra_profit >= 0 ? "delta-up" : "delta-down"}">${y.cum_extra_profit >= 0 ? "+" : ""}${fmt(y.cum_extra_profit)}</td></tr>`).join("");
  $("#tm").innerHTML = `
    <div class="bigline">${t("tm_line", { first: esc(T.first), water: fmt(last.cum_water_saved_m3), profit: fmt(last.cum_extra_profit) })}</div>
    ${fed ? `<div class="meta">${t("tm_line_field", { fed: fmt(fed, 2), water: fmt(last.cum_water_saved_m3 * fed), profit: fmt(last.cum_extra_profit * fed) })}</div>` : ""}
    <div class="seasons">${strip}</div>
    <div class="meta">${t("tm_seen", { green: digits(T.seasons_green), seen: digits(T.seasons_seen) })} · <span class="chip-num" data-src="${esc(T.source + ". " + T.caveat)}">${t("source")}</span></div>
    <table class="plain"><tr><th>${t("tm_year")}</th><th>${t("tm_actual")}<br><small>${esc(T.existing_label[L])}</small></th><th>${t("tm_alt")}<br><small>${esc(T.suggested_label[L])}</small></th><th>${t("tm_cum")}</th></tr>${rows}</table>`;
  plot("tm-chart", [
    { x: T.years.map((y) => y.year), y: T.years.map((y) => y.cum_water_saved_m3), name: L === "ar" ? "مية اتوفرت (م³/فدان)" : "water saved (m³/feddan)", line: { color: NILE, width: 2 }, yaxis: "y" },
    { x: T.years.map((y) => y.year), y: T.years.map((y) => y.cum_extra_profit), name: L === "ar" ? "مكسب زيادة (جنيه/فدان)" : "extra profit (EGP/feddan)", line: { color: FIELD, width: 2, dash: "dot" }, yaxis: "y2" },
  ], { yaxis2: { overlaying: "y", side: "right", showgrid: false }, margin: { t: 8, b: 34, l: 52, r: 52 } });
}

// ---------------------------------------------------------------------------
// Canal mode: neighbours on one canal, planned together
// ---------------------------------------------------------------------------
async function runCanal() {
  const ids = (S.farms || []).map((f) => f.id);
  busy(true);
  try { S.canal = await api("/api/canal", { method: "POST", body: JSON.stringify({ farm_ids: ids.length >= 2 ? ids : null }) }); renderCanal(); }
  catch (e) { $("#canal").innerHTML = `<div class="meta">${esc(e.message)}</div>`; }
  finally { busy(false); }
}
function renderCanal() {
  const C = S.canal, L = S.lang;
  if (!C) return;
  const pk = C.peak_week_m3;
  const pct = Math.round(100 * (1 - pk.coordinated / pk.current));
  const extra = Math.round(100 * (1 - pk.coordinated / pk.each_alone));
  const gu = Math.max(...C.farms.map((f) => f.coordinated.gives_up));
  $("#canal-src").textContent = C.demo ? t("canal_demo") : t("canal_saved");
  const loc = L === "ar" ? "ar-EG" : "en-GB";
  const rows = C.farms.map((f) => `<tr><td><b>${esc(f.name)}</b><br><small>${esc(f.current.label[L])}</small></td><td class="n">${fmt(f.area_feddan, 1)}</td>
      <td>${esc(f.coordinated.label[L])}</td>
      <td class="n">${f.coordinated.summer_sowing ? new Date(f.coordinated.summer_sowing.date + "T00:00:00").toLocaleDateString(loc, { day: "numeric", month: "short" }) + (f.coordinated.summer_sowing.shift_days ? ` (${f.coordinated.summer_sowing.shift_days > 0 ? "+" : ""}${f.coordinated.summer_sowing.shift_days})` : "") : "–"}</td></tr>`).join("");
  let line = t("canal_line", { now: fmt(pk.current), coord: fmt(pk.coordinated), pct: digits(pct), extra: digits(extra), gu: digits(gu) });
  if (gu <= 0) line = line.replace(/,? (and no one gives up|ومحدش بيتنازل).*$/, S.lang === "ar" ? "، " + t("canal_nogu") : ", " + t("canal_nogu"));
  $("#canal").innerHTML = `<div class="bigline">${line}</div>
    <table class="plain"><tr><th>${t("canal_farm")}</th><th class="n">${t("canal_area")}</th><th>${t("canal_plan")}</th><th class="n">${t("canal_sow")}</th></tr>${rows}</table>
    <div class="meta"><span class="chip-num" data-src="${esc(C.method + ". " + C.source)}">${t("source")}</span></div>`;
  const start = new Date(C.week_start + "T00:00:00");
  const xs = C.weekly_m3.current.map((_, i) => new Date(start.getTime() + i * 7 * 864e5));
  plot("canal-chart", [
    { x: xs, y: C.weekly_m3.current, name: t("canal_now"), line: { color: "#9a9a8e", width: 1.5 } },
    { x: xs, y: C.weekly_m3.each_alone, name: t("canal_alone"), line: { color: NILE, width: 1.5, dash: "dot" } },
    { x: xs, y: C.weekly_m3.coordinated, name: t("canal_coord"), line: { color: FIELD, width: 2.5 } },
  ], { yaxis: { title: { text: "m³ / week", font: { size: 10 } }, gridcolor: "#ece8de" } });
}

// ---------------------------------------------------------------------------
// Investor lens: risk and return under shocks, and the spread of past outcomes
// ---------------------------------------------------------------------------
async function loadInvest() {
  if (S.mode !== "advanced" || S.lens !== "investor" || !S.result) return;
  const key = JSON.stringify(body());
  if (S.invKey === key && S.inv) return renderInvest();
  S.invKey = key;
  try { S.inv = await api("/api/sensitivity", { method: "POST", body: JSON.stringify(body()) }); renderInvest(); } catch {}
}
function renderInvest() {
  const V = S.inv, L = S.lang;
  if (!V) return;
  const cases = Object.keys(V.cases);
  const head = V.rotations.map((r) => `<th class="n">${esc(r.label[L])}</th>`).join("");
  const rows = cases.map((c) => `<tr><td>${t("inv_case_" + c)}</td>${V.cases[c].map((x) =>
    `<td class="n">${fmt(x.median)}<br><small>(${fmt(x.p10)})</small></td>`).join("")}</tr>`).join("");
  $("#invest").innerHTML = `<table class="plain"><tr><th></th>${head}</tr>${rows}</table>
    <div class="meta">EGP / feddan / yr · <span class="chip-num" data-src="${esc(V.source)}">${t("source")}</span></div>`;
  const R = S.result;
  plot("dist-chart", R.rotations.map((r, i) => ({
    type: "box", name: r.label[L].length > 28 ? r.label[L].slice(0, 26) + "…" : r.label[L], y: r.barcode.map((b) => b.profit),
    boxpoints: "all", jitter: 0.4, pointpos: 0, marker: { size: 4, color: [INK, FIELD, NILE][i] }, line: { color: [INK, FIELD, NILE][i], width: 1 },
    fillcolor: "rgba(0,0,0,0)" })), { showlegend: false, yaxis: { title: { text: "EGP / feddan / yr, each past year", font: { size: 10 } }, gridcolor: "#ece8de" } });
}

// ---------------------------------------------------------------------------
// Scientist lens: the backtest table
// ---------------------------------------------------------------------------
async function loadBacktest() {
  if (S.bt) return renderBacktest();
  try { S.bt = await api("/api/backtest"); renderBacktest(); } catch {}
}
function renderBacktest() {
  const B = S.bt;
  if (!B || !B.summary) { $("#bt").innerHTML = `<div class="meta">${t("val_not_run")}</div>`; return; }
  const name = { profit: S.lang === "ar" ? "الربح" : "Profit", water: S.lang === "ar" ? "مياه الري" : "Irrigation", yield_frac: S.lang === "ar" ? "الإنتاجية" : "Yield" };
  const rows = Object.entries(B.summary).map(([k, v]) => `<tr><td>${name[k]}</td><td class="n">${digits(v.cases)}</td>
      <td class="n">${Math.round(v.coverage_adjusted * 100)}%</td><td class="n">${fmt(v.crps_adjusted, k === "yield_frac" ? 3 : 0)}</td>
      <td class="n">${fmt(v.mae_same_as_last_year, k === "yield_frac" ? 3 : 0)}</td><td class="n delta-up">${v.skill_vs_last_year_adjusted > 0 ? "+" : ""}${Math.round(v.skill_vs_last_year_adjusted * 100)}%</td></tr>`).join("");
  $("#bt").innerHTML = `<table class="plain"><tr><th></th><th class="n">cases</th><th class="n">in 80% range</th><th class="n">CRPS</th><th class="n">'same as last year' error</th><th class="n">skill</th></tr>${rows}</table>
    <div class="meta">${esc(B.sites.map((x) => x.name).join(" · "))} · ${esc(B.sites[0].test_seasons.join(", "))} · <a href="https://github.com/Ali-M-Kotb/agrotwin/blob/main/qa/BACKTEST.md" target="_blank">qa/BACKTEST.md</a></div>`;
}

// ---------------------------------------------------------------------------
// Voice: Egyptian Arabic neural voice (server, cached) with the browser voice as fallback
// ---------------------------------------------------------------------------
function egyptianScript() {
  const R = S.result, top = topRot(), keep = top.rotation_id === "existing";
  const k = (x) => Math.round(x / 1000);
  const dw = Math.round((R.rotations[0].water_m3.median - top.water_m3.median) / 100) * 100;
  const plan = S.ahead && S.ahead.plan;
  let s = keep ? `يا حاج، بعد ما شُفنا طقس أرضك من سنة ألف وتسعمية واحد وتسعين، دورتك الحالية ${top.label.ar} لسه هي الأنسب.`
    : `يا حاج، بعد ما شُفنا طقس أرضك من سنة ألف وتسعمية واحد وتسعين، بننصحك تجرّب ${top.label.ar.replace(/\(×3\)/, "")}.`;
  s += ` في تمن سنين من كل عشرة، مكسبها كان بين ${k(top.profit.p10)} و ${k(top.profit.p90)} ألف جنيه للفدان في السنة.`;
  if (!keep && dw > 200) s += ` وبتوفّر حوالي ${dw} متر مكعب مية للفدان كل سنة.`;
  if (plan && plan.irrigate_on && plan.irrigate_on.length) {
    const d = new Date(plan.irrigate_on[0].date + "T00:00:00").toLocaleDateString("ar-EG", { weekday: "long", day: "numeric", month: "long" });
    s += ` وأول رية المفروض تكون حوالي يوم ${d}.`;
  }
  s += " وقبل ما تغيّر، اسأل المهندس الزراعي يحلّل ملوحة الأرض. القرار في الآخر قرارك.";
  return s;
}
async function speakAdvice() {
  const btn = $("#btn-speak");
  if (S.audio && !S.audio.paused) { S.audio.pause(); return; }
  const ar = S.lang === "ar";
  const text = ar ? egyptianScript() : S.speakEn;
  btn.disabled = true;
  try {
    const r = await fetch("/api/speak", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang: ar ? "ar" : "en", voice: ar ? (S.voice === "m" ? "ar-EG-ShakirNeural" : "ar-EG-SalmaNeural") : "en-GB-SoniaNeural" }) });
    if (!r.ok) throw new Error("voice");
    S.audio = new Audio(URL.createObjectURL(await r.blob()));
    await S.audio.play();
  } catch { speak(text); } finally { btn.disabled = false; }
}

function topRot() { const r = S.result; return r.rotations.find((x) => x.rotation_id === r.order[0]); }

function render(reason) {
  const R = S.result;
  const mb = $("#mode-badge");
  mb.className = "mode " + R.mode;
  mb.textContent = t("mode_" + R.mode);
  renderHero();
  $("#showdown-sub").textContent = t("showdown_sub", { n: digits(R.years.length), pool: digits(R.pool_size), ms: digits(R.elapsed_s) });
  $("#tie").classList.toggle("hidden", !R.no_clear_winner);
  $("#tie").textContent = t("no_clear_winner");
  $("#rotations").innerHTML = R.rotations.map(rotCard).join("");
  $$("#rotations .ttabs button").forEach((b) => (b.onclick = () => {
    S.detail[b.dataset.rid] = b.dataset.k;
    $("#rotations").innerHTML = R.rotations.map(rotCard).join("");
    render.wire();
  }));
  render.wire();
  renderInvestor();
  renderScout(reason);
  renderBlind();
  renderCouncil();
  renderScience();
}
render.wire = () => {
  $$("#rotations .ttabs button").forEach((b) => (b.onclick = () => {
    S.detail[b.dataset.rid] = b.dataset.k;
    $("#rotations").innerHTML = S.result.rotations.map(rotCard).join("");
    render.wire();
  }));
};

function renderHero() {
  const R = S.result, top = topRot(), ex = R.rotations[0], L = S.lang;
  const keep = top.rotation_id === "existing";
  const dw = ex.water_m3.median - top.water_m3.median;
  const why = (top.text.benefits[0] || top.text.why[0] || {})[L] || "";
  const bs = R.blind_spots[0];
  const warnItem = top.text.review.find((x) => x.tone === "warn");
  const warn = warnItem ? warnItem[L] : (bs ? `${bs[L].title}: ${bs[L].check}` : "");
  const clim = R.climate && R.climate.adjusted ? `<div class="meta">${t("climate_note", { tr: (R.climate.tmax_trend_per_decade > 0 ? "+" : "") + digits(R.climate.tmax_trend_per_decade) })}</div>` : "";
  $("#hero").innerHTML = `
    <div class="kicker">${esc(keep ? t("hero_keep") : t("hero_title"))}</div>
    <div class="big">${esc(top.label[L])}</div>
    <div class="figs">
      <div><div class="k">${t("hero_money")}</div><div class="val">${num(top.profit.p10, top.profit.source)}–${num(top.profit.p90, top.profit.source)}</div><div class="unit">${t("per_fed_yr")}</div></div>
      <div><div class="k">${t("hero_water")}</div><div class="val">${!keep && dw > 100 ? num(dw, "computed: current − suggested, median year") : "–"}</div><div class="unit">${t("m3_fed_yr")}</div></div>
      <div><div class="k">${t("loss_years")}</div><div class="val">${num(Math.round(top.loss_year_share.value * top.years.length), top.loss_year_share.source)} / ${digits(top.years.length)}</div><div class="unit">${digits(top.years[0])}–${digits(top.years[top.years.length - 1] + 2)}</div></div>
    </div>
    <div class="why">${esc(why)}</div>
    ${fieldTotals(top)}
    ${warn ? `<div class="warnline"><svg><use href="#i-warn"/></svg><span><b>${t("hero_warn")}.</b> ${esc(warn)}</span></div>` : ""}
    ${clim}
    <button id="btn-speak" class="txt speak"><svg><use href="#i-speak"/></svg>${t("hero_read")}</button>${L === "ar" ? `<span class="voice"><button data-v="f" class="${S.voice !== "m" ? "on" : ""}">${t("voice_f")}</button><button data-v="m" class="${S.voice === "m" ? "on" : ""}">${t("voice_m")}</button></span>` : ""}`;
  S.speakEn = `${keep ? t("hero_keep") : t("hero_title")}: ${top.label.en.replace("(×3)", "")}. ${t("hero_money")}: ${Math.round(top.profit.p10).toLocaleString("en")} to ${Math.round(top.profit.p90).toLocaleString("en")} pounds per feddan a year. ${why} ${warn}`;
  $("#btn-speak").onclick = speakAdvice;
  $$(".voice button").forEach((b) => (b.onclick = () => { S.voice = b.dataset.v; renderHero(); }));
}

function fieldTotals(top) {
  const f = MapUI.getField && MapUI.getField();
  if (!f) return `<div class="totals meta">${t(S.mode === "advanced" ? "draw_tip_adv" : "draw_tip")}</div>`;
  const fed = f.area_ha / 0.42;
  return `<div class="totals">${t("totals", { fed: fmt(fed, 2) })}: <b>${num(top.profit.p10 * fed, "computed: per-feddan range × drawn area")} – ${num(top.profit.p90 * fed, "computed: per-feddan range × drawn area")}</b> EGP/yr ·
    <b>${num(top.water_m3.median * fed, "computed: median m³/feddan × drawn area")}</b> m³/yr</div>`;
}

function speak(text) {
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.replaceAll("→", ",").replaceAll("←", "،").replace(/\(×3\)/g, ""));
  u.lang = S.lang === "ar" ? "ar-EG" : "en-US";
  u.rate = 0.95;
  speechSynthesis.speak(u);
}

function barcodeHTML(r) {
  const worst = r.worst_year.year, truth = r.truth?.year;
  return `<div class="barcode">${r.barcode.map((b) =>
    `<i class="${b.cls}${b.year === worst ? " worst" : ""}${b.year === truth ? " truth" : ""}" title="${b.year}: ${fmt(b.profit)} EGP/feddan/yr" data-src="computed: window ${b.year}–${b.year + 2}, profit ${Math.round(b.profit)} EGP/feddan/yr"></i>`).join("")}</div>
    <div class="bc-axis"><span>${digits(r.years[0])}</span><span>${t("worst")}: ${digits(worst)}</span><span>${digits(r.years[r.years.length - 1])}</span></div>`;
}

function rangeBar(lo, hi, med, min, max, cls = "") {
  const pos = (v) => (100 * (v - min)) / (max - min || 1);
  return `<div class="range"><div class="band ${cls}" style="left:${pos(lo)}%;width:${Math.max(1, pos(hi) - pos(lo))}%"></div>
    <div class="med" style="left:${pos(med)}%"></div></div>`;
}

function rotCard(r) {
  const R = S.result, L = S.lang, best = R.order[0] === r.rotation_id;
  const allP = R.rotations.flatMap((x) => [x.profit.p10, x.profit.p90]);
  const pmin = Math.min(0, ...allP), pmax = Math.max(...allP);
  const k = S.detail[r.rotation_id] || "why";
  const slots = r.slots.map((s) => `<div class="slot ${s.crop === "fallow" ? "fallow" : s.season}"><b>${esc(cname(s.crop))}</b>${digits(s.year)}·${t(s.season)}</div>`).join("");
  const tabs = ["why", "evidence", "benefits", "gaps", "review"].map((x) =>
    `<button class="${x === k ? "on" : ""}" data-rid="${r.rotation_id}" data-k="${x}">${t("tab_" + x)} ${digits(r.text[x].length)}</button>`).join("");
  const items = r.text[k].map((x) => `<li class="${x.tone}">${esc(x[L])}</li>`).join("") || "<li>–</li>";
  return `<article class="rot r-${r.rotation_id}${best ? " best" : ""}">
    <div class="hd"><div><div class="who">${r.rotation_id === "existing" ? t("current") : t("alt")} · ${t("rank", { r: digits(r.rank) })}
      ${r.rotation_id !== "existing" ? `<span class="badge">${t("strength_" + r.strength)}</span>` : ""}
      ${r.excluded.is_excluded ? `<span class="badge ex">${t("excluded")}</span>` : ""}</div>
      <div class="lab">${esc(r.label[L])}</div></div>
      <div class="tot">${num(r.total, "computed: weighted sum of the four scores with your sliders")}<small>/100</small></div></div>
    <div class="timeline">${slots}</div>
    <div><div class="meta">${t("barcode")} — ${t("barcode_hint")}</div>${barcodeHTML(r)}</div>
    <div class="kv">
      <span>${t("profit_range")}</span><b>${num(r.profit.p10, r.profit.source)} – ${num(r.profit.p90, r.profit.source)}</b>
    </div>
    ${rangeBar(r.profit.p10, r.profit.p90, r.profit.median, pmin, pmax)}
    <div class="kv">
      <span>${t("water_use")}</span><b>${num(r.water_m3.median, r.water_m3.source)} ${t("m3_fed_yr")}</b>
      <span>${t("loss_years")}</span><b>${num(Math.round(r.loss_year_share.value * r.years.length), r.loss_year_share.source)} / ${digits(r.years.length)}</b>
    </div>
    <div class="scorebar adv-only">${["water", "soil", "profit", "risk"].map((x) =>
      `<div><i style="width:${r.scores[x]}%"></i><span>${t("sc_" + x)}</span><b>${num(r.scores[x], "computed: min-max across " + R.pool_size + " replayed rotations")}</b></div>`).join("")}</div>
    <div class="simple-why">${esc(((r.text.benefits[0] || r.text.why[0]) || {})[L] || "")}</div>
    <div class="ttabs">${tabs}</div>
    <ul class="tlist">${items}</ul>
  </article>`;
}

function renderInvestor() {
  const R = S.result, L = S.lang;
  const rows = R.rotations.map((r) => `<div class="card" style="border-top:4px solid ${ROT_COLORS[r.rotation_id]}">
      <b>${esc(r.label[L])}</b>
      <div class="kv" style="margin-top:6px">
        <span>${t("inv_range")}</span><b>${num(r.profit.p10, r.profit.source)} / ${num(r.profit.median, r.profit.source)} / ${num(r.profit.p90, r.profit.source)}</b>
        <span>${t("inv_worst")}</span><b>${digits(r.worst_year.year)}: ${num(r.worst_year.profit, r.worst_year.source)}</b>
        <span>${t("inv_loss")}</span><b>${num(r.loss_year_share.value * 100, r.loss_year_share.source, 0, "%")}</b>
        <span>${t("water_use")}</span><b>${num(r.water_m3.p10, r.water_m3.source)} – ${num(r.water_m3.p90, r.water_m3.source)}</b>
        <span>N</span><b>${num(r.n_credit_kg_fed.low, r.n_credit_kg_fed.source)}–${num(r.n_credit_kg_fed.high, r.n_credit_kg_fed.source)} kg/fed</b>
      </div></div>`).join("");
  const used = [...new Set(R.rotations.flatMap((r) => r.seq).filter((c) => c !== "fallow"))];
  const pr = used.map((c) => { const p = S.prices[c]; return `<tr><td>${esc(cname(c))}</td><td>${num(p.price, p.src.price)}</td><td>${num(p.yield_t, p.src.yield_t, 2)}</td><td>${num(p.cost, p.src.cost)}</td></tr>`; }).join("");
  $("#investor").innerHTML = `<h2>${t("investor_title")} · ${t("per_fed_yr")}</h2><div class="inv-grid">${rows}</div>
    <h3>${t("inv_prices")}</h3><table class="t"><tr><th></th><th>EGP/t</th><th>t/feddan</th><th>EGP/feddan</th></tr>${pr}</table>
    <div class="meta">${S.lang === "ar" ? "اضغط أي رقم لرؤية مصدره. التكاليف لا تشمل إيجار الأرض." : "Tap any number to see its source. Costs exclude land rent."}</div>`;
}

// ---------------------------------------------------------------------------
// Scout
// ---------------------------------------------------------------------------
function renderScout(reason) {
  const R = S.result, f = R.fusion || {}, L = S.lang;
  const irrigated = R.site.irrigated;
  const years = R.years;
  const ty = S.truthYear && years.includes(S.truthYear) ? S.truthYear : (f.used && R.rotations[0].truth ? R.rotations[0].truth.year : 2007);
  $("#scout-controls").innerHTML = irrigated ? `<div class="banner">${t("scout_irrigated")}</div>` : `
    <div class="meta">${t("scout_sim")}</div>
    <div class="grid2"><label>${t("scout_year")}<select id="sc-year">${years.map((y) => `<option ${y === ty ? "selected" : ""}>${y}</option>`).join("")}</select></label>
    <div class="slider" style="grid-template-columns:1fr 1fr 40px"><label>${t("scout_days")}</label><input type="range" id="sc-days" min="30" max="210" step="15" value="${S.scDays || 135}"><output>${digits(S.scDays || 135)}</output></div></div>
    <div class="btn-row"><button id="btn-scout">${t("scout_run")}</button>
      <button id="btn-scout-clear" class="ghost">${t("scout_clear")}</button>
      <a class="btn ghost" href="/api/scout/export?site_id=${encodeURIComponent(R.site.id)}">${t("scout_export")}</a></div>`;
  if (!irrigated) {
    $("#sc-days").oninput = (e) => { S.scDays = +e.target.value; e.target.nextElementSibling.textContent = digits(S.scDays); };
    $("#btn-scout").onclick = sendScout;
    $("#btn-scout-clear").onclick = async () => { await fetch(`/api/scout/runs?site_id=${R.site.id}`, { method: "DELETE" }); simulate(); };
  }
  const stats = $("#fusion-stats"), viz = $("#range-viz");
  if (!f.used) {
    stats.innerHTML = "";
    viz.innerHTML = `<div class="meta">${f.refused ? t("fusion_refused_" + f.refused) : t("scout_none")}</div>`;
    Plotly.purge("fusion-chart");
    return;
  }
  stats.innerHTML = `
    <div class="stat"><span>${t("readings")}</span><b>${num(f.n_points, "scout:" + f.scout_run_ids.join(","))}</b></div>
    <div class="stat"><span>${t("ess")}</span><b>${num(f.ess, "computed: 1/Σw²", 1)}</b></div>
    <div class="stat"><span>${t("tau")}</span><b>${num(f.tau_days, "computed: decorrelation time of modelled soil wetness")}</b></div>
    <div class="stat"><span>${t("confidence")}</span><b>${t("conf_" + f.confidence_label)}</b></div>`;
  const ex = R.rotations[0], w = ex.unweighted.season1_profit, s = ex.season1_profit, tr = ex.truth;
  const lo = Math.min(w.p10, s.p10, tr ? tr.season1_profit : Infinity), hi = Math.max(w.p90, s.p90, tr ? tr.season1_profit : -Infinity);
  const pad = (hi - lo) * 0.08, mn = lo - pad, mx = hi + pad;
  const pos = (v) => (100 * (v - mn)) / (mx - mn);
  const width0 = w.p90 - w.p10, width1 = s.p90 - s.p10;
  const pct = Math.round(100 * (1 - width1 / width0));
  const truthMark = tr ? `<div class="tr" style="left:${pos(tr.season1_profit)}%" title="${t("truth")} ${tr.year}"></div>` : "";
  const startW = reason === "scout" ? `left:${pos(w.p10)}%;width:${pos(w.p90) - pos(w.p10)}%` : `left:${pos(s.p10)}%;width:${pos(s.p90) - pos(s.p10)}%`;
  viz.innerHTML = `<div class="rv">
    <div class="meta">${esc(ex.label[L])} — ${t("this_season")} (${t("per_fed_yr").split("/")[0].trim()}/feddan)</div>
    <div class="lbl"><span>${t("range_without")}</span><b>${num(w.p10, w.source)} – ${num(w.p90, w.source)}</b></div>
    <div class="range"><div class="band" style="left:${pos(w.p10)}%;width:${pos(w.p90) - pos(w.p10)}%"></div>${truthMark}</div>
    <div class="lbl"><span>${t("range_with")}</span><b>${num(s.p10, s.source)} – ${num(s.p90, s.source)}</b></div>
    <div class="range"><div class="band with" id="band-with" style="${startW}"></div>${truthMark}</div>
    ${tr ? `<div class="meta">▏${t("truth")} ${digits(tr.year)}: ${num(tr.season1_profit, tr.source)} — ${tr.season1_profit >= s.p10 && tr.season1_profit <= s.p90 ? "✓" : "✗"}</div>` : ""}
    <div class="narrow">${pct > 0 ? t("narrowed", { pct: digits(pct) }) : "≈"}</div></div>`;
  if (reason === "scout") requestAnimationFrame(() => setTimeout(() => {
    const b = $("#band-with"); if (b) { b.style.left = pos(s.p10) + "%"; b.style.width = pos(s.p90) - pos(s.p10) + "%"; }
  }, 120));
  const tc = f.trace, start = new Date(tc.start);
  const xs = tc.days.map((d) => new Date(start.getTime() + d * 864e5));
  Plotly.react("fusion-chart", [
    { x: xs, y: tc.predicted_p90, mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
    { x: xs, y: tc.predicted_p10, mode: "lines", fill: "tonexty", fillcolor: "rgba(43,108,176,.18)", line: { width: 0 }, name: t("pred_band") },
    { x: xs, y: tc.observed, mode: "markers", marker: { color: "#23704a", size: 5 }, name: `${t("obs")} (${t("mode_" + R.mode)})` },
  ], { margin: { t: 10, b: 36, l: 40, r: 10 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
       yaxis: { range: [0, 1], title: S.lang === "ar" ? "رطوبة نسبية" : "relative wetness" }, legend: { orientation: "h", y: -0.2 } },
     { displayModeBar: false, responsive: true });
}

async function sendScout() {
  const ty = +$("#sc-year").value, days = +$("#sc-days").value;
  S.truthYear = ty; S.scDays = days;
  busy(true);
  try {
    await api("/api/scout/simulate", { method: "POST", body: JSON.stringify({ lat: S.site.lat, lon: S.site.lon, truth_year: ty, days, existing: [$("#ex-w").value, $("#ex-s").value] }) });
    await simulate("scout");
    $(".scout").classList.add("flash"); setTimeout(() => $(".scout").classList.remove("flash"), 1500);
  } catch (e) { alert(e.message); } finally { busy(false); }
}

// ---------------------------------------------------------------------------
// robot + leaf camera
// ---------------------------------------------------------------------------
async function pollRobot() {
  if (!S.robotOn) return;
  try {
    const st = await api("/api/robot/state");
    const last = st.readings[st.readings.length - 1];
    $("#robot-mode").className = "mode " + ({ live: "LIVE", simulated: "SIMULATED" }[st.mode] || "NONE");
    $("#robot-mode").textContent = t("mode_" + ({ live: "LIVE", simulated: "SIMULATED" }[st.mode] || "NONE"));
    if (last) {
      $("#r-temp").innerHTML = num(last.temp, `${last.source} robot reading`, 1, "°");
      $("#r-hum").innerHTML = num(last.hum, `${last.source} robot reading`, 0, "%");
      $("#r-soil").innerHTML = num(last.soil, `${last.source} raw probe index (needs calibration)`, 0);
      $("#r-rain").innerHTML = num(last.rain, `${last.source} robot reading`, 0, "%");
      if (last.lat) {
        if (!S.robotMarker) S.robotMarker = L.marker([last.lat, last.lon], { icon: L.divIcon({ className: "", html: '<div class="robot-dot"></div>', iconSize: [14, 14] }) }).addTo(S.map);
        else S.robotMarker.setLatLng([last.lat, last.lon]);
      }
    }
    renderSightings(st.detections);
  } catch {}
}
function renderSightings(dets) {
  $("#sightings").innerHTML = (dets || []).slice().reverse().map((d) => {
    const info = S.diseaseClasses[d.label] || [null, d.label, false];
    return `<li class="${info[2] ? "dis" : ""}">${d.image ? `<img src="${d.image}" alt="">` : ""}<span><b>${esc(info[1])}</b> · ${num(d.confidence * 100, "Verdex leaf model v2_deit3", 0, "%")} · ${esc(d.source)}</span></li>`;
  }).join("");
}

// ---------------------------------------------------------------------------
// blind spots, council, field card
// ---------------------------------------------------------------------------
function renderBlind() {
  const L = S.lang;
  $("#blind").innerHTML = S.result.blind_spots.map((b) => `<li><b>${esc(b[L].title)}</b>${esc(b[L].why)}<div class="meta">${esc(b[L].check)}</div></li>`).join("");
}

function renderCouncil() {
  const c = S.council, box = $("#council");
  if (!c) { box.innerHTML = ""; return; }
  box.innerHTML = ["agronomist", "economist", "skeptic"].map((a) => `<div class="advisor"><h3>${t("adv_" + a)}</h3>${
    (c.advisors[a] || []).map((cl) => `<p>${esc(digits(cl.text))}</p>`).join("")}</div>`).join("") +
    `<span class="audit">${t("audit_ok", { n: digits(c.audit.claims), b: digits(c.audit.blocked_claims) })} · ${c.model === "templates" ? t("templates") : esc(c.model)}</span>`;
}

async function askCouncil() {
  busy(true);
  try { S.council = await api("/api/council", { method: "POST", body: JSON.stringify(body({ lang: S.lang, use_llm: true })) }); renderCouncil(); }
  catch (e) { alert(e.message); } finally { busy(false); }
}

async function fieldCard() {
  busy(true);
  try {
    const c = await api("/api/fieldcard", { method: "POST", body: JSON.stringify(body({ lang: S.lang })) });
    $("#wa-text").textContent = c.whatsapp;
    $("#card-open").href = c.print_url;
    $("#card-wa").href = "https://wa.me/?text=" + encodeURIComponent(c.whatsapp);
    $("#card-dlg").classList.remove("hidden");
  } catch (e) { alert(e.message); } finally { busy(false); }
}

// ---------------------------------------------------------------------------
// diagnosis
// ---------------------------------------------------------------------------
function renderDiag() {
  const d = S.siteData, tab = S.tab;
  if (!d) return;
  $$("#diag-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("#sources").classList.toggle("hidden", tab !== "sources");
  $("#diag-chart").classList.toggle("hidden", tab === "sources");
  const base = { margin: { t: 10, b: 40, l: 90, r: 40 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", legend: { orientation: "h", y: -0.2 } };
  const cfg = { displayModeBar: false, responsive: true };
  const c = d.climate;
  if (tab === "danger") {
    const kinds = Object.keys(d.danger.kinds);
    const colors = { heat: "#c0392b", dry_spell: "#e0a526", wet_spell: "#2b6cb0", dry_soil: "#8a5a2b", low_greenness: "#7a7f7a" };
    const traces = [];
    kinds.forEach((k, i) => d.danger.kinds[k].windows.forEach((w) => traces.push({
      x: [w.start, w.end], y: [t("danger_" + k), t("danger_" + k)], mode: "lines", line: { width: 16, color: colors[k] },
      hovertemplate: `${t("danger_" + k)}: ${w.start} → ${w.end} (${w.days} d, |z| ${w.peak_z})<extra>${d.danger.kinds[k].source}</extra>`, showlegend: false })));
    traces.push({ x: [d.danger.since, d.danger.until], y: kinds.map((k) => t("danger_" + k)).slice(0, 1), mode: "markers", marker: { opacity: 0 }, showlegend: false, hoverinfo: "skip" });
    Plotly.react("diag-chart", traces, { ...base, yaxis: { categoryorder: "array", categoryarray: kinds.map((k) => t("danger_" + k)) },
      xaxis: { range: [d.danger.since, d.danger.until] } }, cfg);
    $("#diag-note").textContent = `${d.danger.rule} (${d.danger.rule_source}) · ${d.danger.since} → ${d.danger.until}`;
  } else if (tab === "heat") {
    Plotly.react("diag-chart", [
      { x: c.years, y: c.hot_days, type: "bar", name: S.lang === "ar" ? "أيام > 35°" : "days > 35 °C", marker: { color: "#e9b38a" }, yaxis: "y2" },
      { x: c.years, y: c.tmax, mode: "lines+markers", name: "Tmax °C", line: { color: "#b4501a", width: 2.5 }, marker: { size: 4 } },
    ], { ...base, margin: { t: 10, b: 40, l: 45, r: 45 }, yaxis2: { overlaying: "y", side: "right", showgrid: false } }, cfg);
    $("#diag-note").textContent = `NASA POWER ${c.first} → ${c.last} · Tmax ${c.trend_per_decade.tmax > 0 ? "+" : ""}${c.trend_per_decade.tmax} °C/decade · hot days ${c.trend_per_decade.hot_days > 0 ? "+" : ""}${c.trend_per_decade.hot_days}/decade`;
  } else if (tab === "ndvi") {
    if (!d.ndvi) { Plotly.purge("diag-chart"); $("#diag-note").textContent = "NDVI —"; return; }
    const pk = d.ndvi.seasons.peaks;
    const tr = [{ x: d.ndvi.dates, y: d.ndvi.values, mode: "lines", name: "NDVI (MODIS)", line: { color: "#23704a", width: 2 } },
      { x: pk.map((p) => p.date), y: pk.map((p) => p.ndvi), mode: "markers", name: S.lang === "ar" ? "مواسم" : "seasons",
        marker: { size: 9, color: pk.map((p) => (p.season === "winter" ? "#2b6cb0" : "#b7791f")) } }];
    if (d.mod16) tr.push({ x: d.mod16.dates, y: d.mod16.values, mode: "lines", name: "MOD16 ET", yaxis: "y2", line: { color: "#9cc0e6", width: 1 } });
    Plotly.react("diag-chart", tr, { ...base, margin: { t: 10, b: 40, l: 45, r: 45 }, yaxis: { range: [0, 1] }, yaxis2: { overlaying: "y", side: "right", showgrid: false } }, cfg);
    $("#diag-note").textContent = "MODIS MOD13Q1 (250 m) + MOD16A2GF (500 m), ORNL DAAC";
  } else {
    $("#diag-note").textContent = "";
    $("#sources").innerHTML = d.sources.map((s) => `<li><span class="st ${s.status}">${s.status.toUpperCase()}</span><div><b>${esc(s.name)}</b><br><small>${esc(s.detail)} · <code>${esc(s.tag)}</code></small></div></li>`).join("");
  }
}

function ndviSuggest() {
  const sg = S.siteData?.ndvi?.seasons?.suggestion || [];
  if (!sg.length) { $("#ndvi-sugg").textContent = "—"; return; }
  $("#ndvi-sugg").innerHTML = sg.map((x) => `${t(x.season)} ${x.peak}: ${x.crops.map(cname).join(", ")}`).join("<br>");
  const w = sg.find((x) => x.season === "winter"), s = sg.find((x) => x.season === "summer");
  if (w) $("#ex-w").value = w.crops[0];
  if (s) $("#ex-s").value = s.crops[0];
  schedule();
}

// ---------------------------------------------------------------------------
// Scientist lens
// ---------------------------------------------------------------------------
function renderScience() {
  const V = S.validation || {}, R = S.result, f = R.fusion || {};
  const twin = (V.twin_experiment || []).map((tw) => tw.status !== "run" ? `<div class="meta">${t("val_not_run")}: ${esc(tw.why)}</div>` :
    `<b>${esc(tw.site)}</b> (${esc(tw.rotation)}, σ<sub>model</sub> = ${tw.sigma_model})
     <table class="t"><tr><th>days</th><th>coverage</th><th>unweighted</th><th>width ratio</th><th>ESS</th></tr>${tw.rows.map((x) =>
       `<tr><td>${x.reading_days}</td><td class="${x.in_band ? "pass" : "fail"}">${x.coverage}</td><td>${x.coverage_unweighted}</td><td>${x.width_ratio}</td><td>${x.ess_median}</td></tr>`).join("")}</table>
     <div class="meta">3-year: ${tw.three_year_check.coverage} vs ${tw.three_year_check.coverage_unweighted} → ${esc(tw.three_year_check.decision)}</div>`).join("<br>");
  const hind = (V.hindcast || []).map((h) => h.status !== "run" ? `<li>${t("val_not_run")}: ${esc(h.why)}</li>` :
    h.checks.map((c) => `<li><b>${esc(h.site)}</b> ${esc(h.crop)} vs ${esc(c.signal)}: n=${c.n}, ${c.applicable === false ? esc(c.expect) : Object.entries(c).filter(([k]) => k.startsWith("rho")).map(([k, v]) => `${k}=${v}`).join(", ")}</li>`).join("")).join("");
  const vis = V.vision?.status === "run" ? `${esc(V.vision.model)}: <b>${V.vision.test_accuracy}</b> on n=${V.vision.n_test} (${esc(V.vision.split_note)}). ${esc(V.vision.caveat)}` : t("val_not_run");
  const prov = V.provenance ? `${V.provenance.numbers_checked} numbers, ${V.provenance.untagged} untagged → <span class="${V.provenance.passed ? "pass" : "fail"}">${V.provenance.passed ? "PASS" : "FAIL"}</span>` : t("val_not_run");
  const san = V.sanity && !V.sanity.status ? Object.entries(V.sanity).map(([k, v]) => `<li><span class="${v.passed ? "pass" : "fail"}">${v.passed ? "PASS" : "FAIL"}</span> ${esc(k)}</li>`).join("") : "";
  const asm = S.assumptions.map((a) => `<tr><td><code>${esc(a.name)}</code></td><td>${esc(JSON.stringify(a.value))}</td><td>${esc(a.meaning)}</td></tr>`).join("");
  $("#science").innerHTML = `<h2>${t("sci_methods")}</h2>
    <div class="eq">ET0  = FAO-56 Penman-Monteith (NASA POWER T, RH, wind, solar; Hargreaves before 1984)
TAW  = 1000 (θFC − θWP) Zr      RAW = p·TAW,  p = p_table + 0.04 (5 − ETc)
Ks   = 1 if Dr ≤ RAW else (TAW − Dr) / ((1 − p) TAW)        ETa = Ks·Kc·ET0
Dr,i = Dr,i−1 − (P − RO) − I + ETa + DP          (daily, every window ${R.years[0]}–${R.years[R.years.length - 1] + 2})
1 − Ya/Ym = Ky (1 − ETa/ETc) × (1 − heat loss)  (FAO-33)
profit = Ya·P − cost − water·m³ + N-credit·P_N
w_k ∝ exp(−½ Σ_t ((y_t − h_k,t)/σ)² / τ),  σ = hypot(σ_sensor, σ_model),  ESS = 1/Σw²  ≥ ${S.assumptions.find((a) => a.name === "ess_min")?.value}
${f.used ? `this run: n=${f.n_points} days, τ=${f.tau_days} d, σ=${(+f.sigma_used).toFixed(3)}, ESS=${(+f.ess).toFixed(1)}, tempering=${(+f.temper).toFixed(2)}` : "no Scout run in this result"}</div>
    <h2 style="margin-top:14px">${t("sci_validation")} <span class="meta">${esc(V.generated_at || "")}</span></h2>
    <h3>${t("val_twin")}</h3>${twin || t("val_not_run")}
    <h3>${t("val_hind")}</h3><ul>${hind}</ul>
    <h3>${t("val_vision")}</h3><div>${vis}</div>
    <h3>${t("val_prov")}</h3><div>${prov}</div>
    <h3>${t("val_sanity")}</h3><ul>${san}</ul>
    <h2 style="margin-top:14px">${t("sci_assumptions")}</h2><table class="t">${asm}</table>`;
}

// ---------------------------------------------------------------------------
// source chip popover
// ---------------------------------------------------------------------------
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-src]");
  const pop = $("#chip-pop");
  if (!el) { pop.classList.add("hidden"); return; }
  const src = el.dataset.src;
  const link = src.startsWith("quoted:") && src.includes("http") ? src.slice(src.indexOf("http")) : null;
  pop.innerHTML = `<b>${t("source")}:</b> ${esc(src)}${link ? `<br><a href="${esc(link)}" target="_blank" rel="noopener" style="color:#9fe3b8">open</a>` : ""}`;
  pop.style.left = Math.min(e.clientX + 8, innerWidth - 440) + "px";
  pop.style.top = e.clientY + 12 + "px";
  pop.classList.remove("hidden");
});

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------
async function init() {
  const [en, ar, crops, sites] = await Promise.all([
    fetch("/static/i18n/en.json").then((r) => r.json()), fetch("/static/i18n/ar.json").then((r) => r.json()),
    api("/api/crops"), api("/api/sites")]);
  S.I = { en, ar };
  S.crops = crops.crops; S.prices = crops.prices; S.assumptions = crops.assumptions;
  S.diseaseClasses = crops.disease_classes; S.soilNames = crops.soil_classes;
  Object.keys(S.crops).forEach((k) => S.candidates.add(k));
  S.sites = sites;
  const q = new URLSearchParams(location.search);
  if (q.get("lang") === "ar") S.lang = "ar";
  if (["farmer", "investor", "scientist"].includes(q.get("lens"))) S.lens = q.get("lens");
  applyI18n();
  buildInputs();
  await initMap();
  let saved = null;
  try { saved = localStorage.getItem("agrotwin.mode"); } catch {}
  S.mode = q.get("mode") || saved || "simple";
  $$(".modes button").forEach((b) => (b.onclick = () => setMode(b.dataset.mode)));
  wizardBind();
  $("#btn-farm-save").onclick = saveFarm;
  $("#btn-canal").onclick = runCanal;
  $("#btn-layers").onclick = () => { $("#layer-panel").classList.toggle("hidden"); $("#btn-layers").classList.toggle("on"); };
  $$("[data-close]").forEach((b) => (b.onclick = () => { $("#" + b.dataset.close).classList.add("hidden"); $("#btn-layers").classList.remove("on"); }));
  $("#btn-plan-save").onclick = savePlan;
  loadFarms();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  $$(".lens button").forEach((b) => (b.onclick = () => setLens(b.dataset.lens)));
  setLens(S.lens);
  setMode(S.mode);
  $$(".slider input").forEach((i) => {
    const o = i.parentElement.querySelector("output");
    if (o) o.textContent = sliderOut(i.id);
    i.addEventListener("input", () => { if (o) o.textContent = sliderOut(i.id); if (i.id.startsWith("w-") || i.id.startsWith("x-")) schedule(); });
  });
  ["ex-w", "ex-s", "cap-on", "cap-w", "cap-s"].forEach((id) => ($("#" + id).onchange = () => { $("#sw-w").value = $("#ex-w").value; $("#sw-s").value = $("#ex-s").value; schedule(); }));
  $("#btn-lang").onclick = () => { S.lang = S.lang === "en" ? "ar" : "en"; applyI18n(); buildInputs(); wizardBind(); renderFarms(); siteMeta(); renderDiag(); if (S.result) render(); renderAhead(); renderPulse(); if (window.Chat) Chat.labels(); renderTM(); renderCanal(); renderInvest(); renderBacktest(); };
  $("#btn-digits").onclick = () => { S.arDigits = !S.arDigits; if (S.result) render(); siteMeta(); };
  $("#btn-card").onclick = fieldCard;
  $("#btn-dlg-close").onclick = () => $("#card-dlg").classList.add("hidden");
  $("#btn-wa").onclick = async () => { await navigator.clipboard.writeText($("#wa-text").textContent).catch(() => {}); $("#btn-wa").textContent = t("card_copied"); setTimeout(() => ($("#btn-wa").textContent = t("card_wa")), 1500); };
  $("#btn-council").onclick = askCouncil;
  $("#btn-ndvi").onclick = ndviSuggest;
  $$("#diag-tabs button").forEach((b) => (b.onclick = () => { S.tab = b.dataset.tab; renderDiag(); }));
  $("#btn-robot").onclick = async () => { await api("/api/robot/sim/start", { method: "POST", body: JSON.stringify({ lat: S.site.lat, lon: S.site.lon }) }); S.robotOn = true; pollRobot(); };
  $("#btn-robot-reset").onclick = async () => { await api("/api/robot/reset", { method: "POST" }); S.robotOn = false; renderSightings([]); simulate(); };
  $("#btn-leaf").onclick = async () => { await api("/api/robot/detect", { method: "POST", body: JSON.stringify({ label: $("#leaf-class").value, confidence: 0.93, source: "replay" }) }); S.robotOn = true; await pollRobot(); simulate("sighting"); };
  $("#leaf-file").onchange = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file); busy(true);
    try {
      const r = await fetch("/api/robot/diagnose", { method: "POST", body: fd }); const j = await r.json();
      if (!r.ok) throw new Error(j.detail);
      $("#leaf-status").textContent = j.known ? j.top3.map((x) => `${S.diseaseClasses[x.label]?.[1] || x.label} ${Math.round(x.p * 100)}%`).join(" · ") : t("leaf_unknown");
      S.robotOn = true; await pollRobot(); simulate("sighting");
    } catch (err) { $("#leaf-status").textContent = err.message; } finally { busy(false); e.target.value = ""; }
  };
  setInterval(pollRobot, 3000);
  api("/api/validation").then((v) => { S.validation = v; if (S.result) renderScience(); }).catch(() => {});
  api("/api/model").catch(() => {});
  const want = sites.find((s) => s.id === q.get("site")) || sites.find((s) => s.default) || sites[0];
  await selectSite(want);
}

function setLens(l) {
  S.lens = l;
  if (l === "investor") setTimeout(loadInvest, 0);
  if (l === "scientist") setTimeout(loadBacktest, 0);
  document.body.dataset.lens = l;
  $$(".lens button").forEach((b) => b.classList.toggle("on", b.dataset.lens === l));
  setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
}

init();
