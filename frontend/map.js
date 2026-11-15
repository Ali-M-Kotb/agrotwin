/* AgroTwin map
 * Leaflet + NASA GIBS WMTS layers (no login), field-boundary drawing, inspector, saved farms,
 * offline place search. Exposes window.MapUI; app.js wires it to the rest of the product. */
"use strict";
(function () {
  const GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";
  // Overlays shown in Advanced mode. step = days between frames for the time-lapse.
  const OVERLAYS = {
    none: null,
    ndvi16: { id: "MODIS_Terra_L3_NDVI_16Day", step: 16, label: { en: "Vegetation (NDVI, 16-day)", ar: "الغطاء النباتي (NDVI، 16 يوماً)" } },
    ndvi8: { id: "MODIS_Terra_NDVI_8Day", step: 8, label: { en: "Vegetation (NDVI, 8-day)", ar: "الغطاء النباتي (NDVI، 8 أيام)" } },
    smap: { id: "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture", step: 3, label: { en: "Root-zone soil moisture (SMAP L4)", ar: "رطوبة منطقة الجذور (SMAP)" } },
    imerg: { id: "IMERG_Precipitation_Rate", step: 1, label: { en: "Rain (GPM IMERG)", ar: "الأمطار (GPM IMERG)" } },
    lst: { id: "MODIS_Terra_Land_Surface_Temp_Day", step: 1, label: { en: "Land surface temperature (MODIS)", ar: "حرارة سطح الأرض (MODIS)" } },
  };
  const BASES = {
    sat: { label: { en: "Satellite", ar: "قمر صناعي" } },
    streets: { label: { en: "Streets", ar: "شوارع" } },
    nasa: { label: { en: "NASA true colour (by date)", ar: "صورة ناسا الحقيقية (بالتاريخ)" } },
  };
  // Offline place search: governorate centroids (approximate) + the demo regions abroad.
  const PLACES = [
    ["Kafr El-Sheikh", "كفر الشيخ", 31.11, 30.94], ["Dakahlia", "الدقهلية", 31.04, 31.38], ["Beheira", "البحيرة", 30.85, 30.34],
    ["Gharbia", "الغربية", 30.87, 31.03], ["Sharqia", "الشرقية", 30.73, 31.72], ["Menoufia", "المنوفية", 30.52, 30.99],
    ["Qalyubia", "القليوبية", 30.33, 31.21], ["Damietta", "دمياط", 31.42, 31.81], ["Alexandria", "الإسكندرية", 31.20, 29.92],
    ["Matrouh", "مطروح", 31.35, 27.24], ["Ismailia", "الإسماعيلية", 30.60, 32.27], ["Port Said", "بورسعيد", 31.26, 32.30],
    ["Giza", "الجيزة", 29.99, 31.13], ["Fayoum", "الفيوم", 29.31, 30.84], ["Beni Suef", "بني سويف", 29.07, 31.10],
    ["Minya", "المنيا", 28.11, 30.75], ["Assiut", "أسيوط", 27.18, 31.18], ["Sohag", "سوهاج", 26.56, 31.69],
    ["Qena", "قنا", 26.16, 32.72], ["Luxor", "الأقصر", 25.69, 32.64], ["Aswan", "أسوان", 24.09, 32.90],
    ["New Valley (Kharga)", "الوادي الجديد (الخارجة)", 25.44, 30.55], ["North Sinai (El Arish)", "شمال سيناء (العريش)", 31.13, 33.80],
    ["Saïs plain, Morocco", "سهل سايس، المغرب", 33.90, -5.45],
  ];

  const M = {
    map: null, base: null, overlay: null, overlayKey: "none", opacity: 0.75, date: null, playing: null,
    meta: {}, lang: () => "en", onPick: null, onInspect: null, onFarmOpen: null,
    drawing: false, pts: [], drawLayer: null, drawLine: null, field: null, farmLayer: null, legendEl: null,
  };

  const iso = (d) => d.toISOString().slice(0, 10);
  const addDays = (s, n) => { const d = new Date(s + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return iso(d); };

  function baseLayer(key) {
    if (key === "streets") return L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" });
    if (key === "nasa") {
      const m = M.meta.MODIS_Terra_CorrectedReflectance_TrueColor || { tms: "GoogleMapsCompatible_Level9", ext: "jpg", maxzoom: 9 };
      return L.tileLayer(`${GIBS}/MODIS_Terra_CorrectedReflectance_TrueColor/default/${M.date}/${m.tms}/{z}/{y}/{x}.${m.ext}`,
        { maxZoom: 18, maxNativeZoom: m.maxzoom, attribution: "NASA GIBS · MODIS Terra" });
    }
    return L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19, attribution: "Imagery © Esri" });
  }

  function overlayUrl(key) {
    const o = OVERLAYS[key], m = M.meta[o.id];
    return `${GIBS}/${o.id}/default/${M.date}/${m.tms}/{z}/{y}/{x}.${m.ext}`;
  }

  function setBase(key) {
    M.baseKey = key;
    if (M.base) M.map.removeLayer(M.base);
    M.base = baseLayer(key).addTo(M.map);
    M.base.bringToBack();
  }

  function setOverlay(key) {
    M.overlayKey = key;
    if (M.overlay) { M.map.removeLayer(M.overlay); M.overlay = null; }
    const o = OVERLAYS[key];
    const leg = document.getElementById("map-legend");
    if (!o) { leg.innerHTML = ""; return; }
    const m = M.meta[o.id];
    if (M.date < m.first) M.date = m.first;
    if (M.date > m.latest) M.date = m.latest;
    syncDate();
    M.overlay = L.tileLayer(overlayUrl(key), { maxZoom: 18, maxNativeZoom: m.maxzoom, opacity: M.opacity,
      attribution: `NASA GIBS · ${m.title}` }).addTo(M.map);
    leg.innerHTML = `<div class="leg-title">${o.label[M.lang()]} · <span id="leg-date">${M.date}</span></div>` +
      (m.legend ? `<img src="/static/vendor/legends/${m.legend}" alt="legend">` : "");
  }

  function syncDate() {
    const inp = document.getElementById("map-date");
    if (!inp) return;
    const o = OVERLAYS[M.overlayKey];
    const m = o ? M.meta[o.id] : M.meta.MODIS_Terra_CorrectedReflectance_TrueColor;
    if (m) { inp.min = m.first; inp.max = m.latest; }
    inp.value = M.date;
    const d = document.getElementById("leg-date");
    if (d) d.textContent = M.date;
  }

  function setDate(s) {
    M.date = s;
    syncDate();
    if (M.overlay) M.overlay.setUrl(overlayUrl(M.overlayKey));
    if (M.baseKey === "nasa") setBase("nasa");
  }

  function togglePlay() {
    const btn = document.getElementById("map-play");
    if (M.playing) { clearInterval(M.playing); M.playing = null; btn.textContent = "▶"; return; }
    const o = OVERLAYS[M.overlayKey] || OVERLAYS.ndvi16;
    if (!M.overlay) { document.getElementById("map-overlay").value = "ndvi16"; setOverlay("ndvi16"); }
    const m = M.meta[(OVERLAYS[M.overlayKey] || o).id];
    // start a year back so one press shows a full cropping cycle
    if (M.date >= m.latest) setDate(addDays(m.latest, -365));
    btn.textContent = "❚❚";
    M.playing = setInterval(() => {
      const step = (OVERLAYS[M.overlayKey] || o).step;
      let n = addDays(M.date, Math.max(step, 8));
      if (n > m.latest) n = addDays(m.latest, -365);
      setDate(n);
    }, 1400);
  }

  // ---------------------------------------------------------------- drawing
  function geodesicAreaHa(latlngs) {
    // spherical excess on a 6,378,137 m sphere (same as Leaflet.draw's geodesicArea)
    const R = 6378137, rad = Math.PI / 180;
    let a = 0;
    for (let i = 0; i < latlngs.length; i++) {
      const p1 = latlngs[i], p2 = latlngs[(i + 1) % latlngs.length];
      a += (p2[1] - p1[1]) * rad * (2 + Math.sin(p1[0] * rad) + Math.sin(p2[0] * rad));
    }
    return Math.abs((a * R * R) / 2) / 10000;
  }

  function startDraw() {
    clearDraw(false);
    M.drawing = true;
    M.pts = [];
    document.getElementById("map").classList.add("drawing");
    document.getElementById("draw-bar").classList.remove("hidden");
    document.getElementById("btn-draw").classList.add("on");
    document.getElementById("btn-draw-finish").disabled = true;
  }
  function addPoint(ll) {
    M.pts.push([+ll.lat.toFixed(6), +ll.lng.toFixed(6)]);
    if (M.drawLine) M.map.removeLayer(M.drawLine);
    M.drawLine = L.polyline(M.pts, { color: "#c9972b", weight: 2.5, dashArray: "6 4" }).addTo(M.map);
    L.circleMarker(M.pts[M.pts.length - 1], { radius: 4, color: "#1b1f1a", weight: 1.5, fillColor: "#c9972b", fillOpacity: 1 }).addTo(M.drawLayerGroup);
    document.getElementById("btn-draw-finish").disabled = M.pts.length < 3;
    if (M.pts.length >= 3) document.getElementById("draw-area").textContent = areaText(geodesicAreaHa(M.pts));
  }
  function finishDraw() {
    if (M.pts.length < 3) return;
    M.drawing = false;
    document.getElementById("map").classList.remove("drawing");
    document.getElementById("draw-bar").classList.add("hidden");
    document.getElementById("btn-draw").classList.remove("on");
    if (M.drawLine) { M.map.removeLayer(M.drawLine); M.drawLine = null; }
    M.drawLayerGroup.clearLayers();
    setField(M.pts);
    const c = centroid(M.pts);
    if (M.onPick) M.onPick({ lat: +c[0].toFixed(3), lon: +c[1].toFixed(3), polygon: M.pts, area_ha: M.field.area_ha });
  }
  function clearDraw(alsoField = true) {
    M.drawing = false;
    M.pts = [];
    document.getElementById("map").classList.remove("drawing");
    document.getElementById("draw-bar").classList.add("hidden");
    document.getElementById("btn-draw").classList.remove("on");
    if (M.drawLine) { M.map.removeLayer(M.drawLine); M.drawLine = null; }
    if (M.drawLayerGroup) M.drawLayerGroup.clearLayers();
    if (alsoField && M.fieldLayer) { M.map.removeLayer(M.fieldLayer); M.fieldLayer = null; M.field = null; document.getElementById("draw-area").textContent = ""; }
  }
  function centroid(pts) {
    const n = pts.length;
    return [pts.reduce((s, p) => s + p[0], 0) / n, pts.reduce((s, p) => s + p[1], 0) / n];
  }
  function areaText(ha) {
    const fed = ha / 0.42;
    return M.lang() === "ar" ? `${fed.toFixed(2)} فدان · ${ha.toFixed(2)} هكتار` : `${fed.toFixed(2)} feddan · ${ha.toFixed(2)} ha`;
  }
  function setField(pts) {
    if (M.fieldLayer) M.map.removeLayer(M.fieldLayer);
    if (!pts || pts.length < 3) { M.field = null; return; }
    const ha = geodesicAreaHa(pts);
    M.field = { polygon: pts, area_ha: ha };
    M.fieldLayer = L.polygon(pts, { color: "#f4f1ea", weight: 2.5, dashArray: "6 4", fillColor: "#c9972b", fillOpacity: 0.15 }).addTo(M.map);
    document.getElementById("draw-area").textContent = areaText(ha);
  }

  // ---------------------------------------------------------------- inspector
  async function inspect(ll) {
    const lat = +ll.lat.toFixed(3), lon = +ll.lng.toFixed(3);
    const pop = L.popup({ maxWidth: 300 }).setLatLng(ll).setContent(`<div class="insp">${M.lang() === "ar" ? "جارٍ تحميل بيانات ناسا…" : "Loading NASA POWER…"}</div>`).openOn(M.map);
    try {
      const r = await fetch(`/api/point?lat=${lat}&lon=${lon}`);
      const p = await r.json();
      if (!r.ok) throw new Error(p.detail);
      const ar = M.lang() === "ar";
      const f = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString("en-US", { maximumFractionDigits: d }));
      pop.setContent(`<div class="insp"><b>${lat}, ${lon}</b>
        <table>
          <tr><td>${ar ? "المطر السنوي" : "Rain"}</td><td>${f(p.rain.value)} mm</td></tr>
          <tr><td>${ar ? "البخر-نتح المرجعي" : "Reference ET"}</td><td>${f(p.et0.value)} mm</td></tr>
          <tr><td>${ar ? "مؤشر الجفاف" : "Rain ÷ ET"}</td><td>${f(p.aridity.value, 2)}</td></tr>
          <tr><td>${ar ? "اتجاه الحرارة" : "Tmax trend"}</td><td>${p.tmax_trend.value > 0 ? "+" : ""}${f(p.tmax_trend.value, 2)} °C/10y</td></tr>
          <tr><td>${ar ? "التربة" : "Soil"}</td><td>${({ sand: ["Sand", "رملية"], sandy_loam: ["Sandy loam", "رملية طميية"], loam: ["Loam", "طميية"], clay_loam: ["Clay loam", "طينية طميية"], clay: ["Clay", "طينية"] }[p.soil_class] || [p.soil_class, p.soil_class])[ar ? 1 : 0]} (${f(p.clay.value)}% ${ar ? "طين" : "clay"})</td></tr>
          <tr><td>${ar ? "الارتفاع" : "Elevation"}</td><td>${f(p.elev.value)} m</td></tr>
        </table>
        <div class="insp-note">${p.likely_irrigated ? (ar ? "المطر لا يكفي للزراعة بدون ري." : "Too dry to farm without irrigation.") : (ar ? "زراعة مطرية ممكنة في الشتاء." : "Winter rain-fed farming is possible.")}
          <br><small>NASA POWER · SoilGrids</small></div>
        <div class="insp-btns"><button class="insp-go">${ar ? "حلّل هذا الحقل" : "Analyse this field"}</button></div></div>`);
      setTimeout(() => {
        const b = document.querySelector(".insp-go");
        if (b) b.onclick = () => { M.map.closePopup(); if (M.onPick) M.onPick({ lat, lon }); };
      }, 0);
      if (M.onInspect) M.onInspect(p);
    } catch (e) {
      pop.setContent(`<div class="insp">${e.message}</div>`);
    }
  }

  // ---------------------------------------------------------------- farms
  function showFarms(farms) {
    M.farmLayer.clearLayers();
    farms.forEach((f) => {
      const lyr = f.polygon && f.polygon.length >= 3
        ? L.polygon(f.polygon, { color: "#2d5f8b", weight: 2, fillOpacity: 0.08 })
        : L.circleMarker([f.lat, f.lon], { radius: 6, color: "#fff", weight: 2, fillColor: "#2d5f8b", fillOpacity: 1 });
      lyr.bindTooltip(f.name, { direction: "top" });
      lyr.on("click", (e) => { L.DomEvent.stopPropagation(e); if (M.onFarmOpen) M.onFarmOpen(f); });
      lyr.addTo(M.farmLayer);
    });
  }

  // ---------------------------------------------------------------- search
  function search(q) {
    const box = document.getElementById("map-results");
    q = q.trim().toLowerCase();
    if (!q) { box.innerHTML = ""; box.classList.add("hidden"); return; }
    const hits = PLACES.filter((p) => p[0].toLowerCase().includes(q) || p[1].includes(q)).slice(0, 7);
    box.innerHTML = hits.map((p, i) => `<button data-i="${PLACES.indexOf(p)}">${M.lang() === "ar" ? p[1] : p[0]}</button>`).join("") || "<span>—</span>";
    box.classList.remove("hidden");
    box.querySelectorAll("button").forEach((b) => (b.onclick = () => {
      const p = PLACES[+b.dataset.i];
      M.map.flyTo([p[2], p[3]], 10, { duration: 0.8 });
      box.classList.add("hidden");
      document.getElementById("map-search").value = M.lang() === "ar" ? p[1] : p[0];
    }));
  }

  function locate() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => { const ll = L.latLng(pos.coords.latitude, pos.coords.longitude); M.map.flyTo(ll, 14); L.circleMarker(ll, { radius: 8, color: "#2b6cb0" }).addTo(M.map); },
      () => alert(M.lang() === "ar" ? "تعذّر تحديد موقعك." : "Could not get your location."), { enableHighAccuracy: true, timeout: 8000 });
  }

  // ---------------------------------------------------------------- public
  M.init = async function (opts) {
    Object.assign(M, opts);
    try { M.meta = await (await fetch("/static/vendor/legends/layers.json")).json(); } catch { M.meta = {}; }
    M.date = (M.meta.MODIS_Terra_L3_NDVI_16Day || {}).latest || iso(new Date(Date.now() - 864e5 * 20));
    M.map = L.map("map", { zoomControl: false, worldCopyJump: true }).setView([30.9, 30.0], 6);
    L.control.zoom({ position: "bottomright" }).addTo(M.map);
    L.control.scale({ position: "bottomleft", imperial: false }).addTo(M.map);
    // The map's box changes with the Simple/Advanced layout: re-measure whenever it does.
    if ("ResizeObserver" in window) new ResizeObserver(() => M.map.invalidateSize()).observe(document.getElementById("map"));
    setTimeout(() => M.map.invalidateSize(), 300);
    setBase("sat");
    M.farmLayer = L.layerGroup().addTo(M.map);
    M.drawLayerGroup = L.layerGroup().addTo(M.map);
    M.map.on("click", (e) => {
      if (M.drawing) return addPoint(e.latlng);
      if (document.body.dataset.mode === "advanced") return inspect(e.latlng);
      if (M.onPick) M.onPick({ lat: +e.latlng.lat.toFixed(3), lon: +e.latlng.lng.toFixed(3) });
    });
    M.map.on("dblclick", (e) => { if (M.drawing) { L.DomEvent.stop(e); finishDraw(); } });
    // controls
    const $ = (id) => document.getElementById(id);
    $("map-base").innerHTML = Object.entries(BASES).map(([k, v]) => `<option value="${k}">${v.label[M.lang()]}</option>`).join("");
    $("map-overlay").innerHTML = Object.entries(OVERLAYS).map(([k, v]) => `<option value="${k}">${v ? v.label[M.lang()] : (M.lang() === "ar" ? "بدون طبقة" : "No NASA layer")}</option>`).join("");
    $("map-base").onchange = (e) => setBase(e.target.value);
    $("map-overlay").onchange = (e) => setOverlay(e.target.value);
    $("map-opacity").oninput = (e) => { M.opacity = +e.target.value; if (M.overlay) M.overlay.setOpacity(M.opacity); };
    $("map-date").onchange = (e) => e.target.value && setDate(e.target.value);
    $("map-prev").onclick = () => setDate(addDays(M.date, -((OVERLAYS[M.overlayKey] || { step: 8 }).step)));
    $("map-next").onclick = () => setDate(addDays(M.date, (OVERLAYS[M.overlayKey] || { step: 8 }).step));
    $("map-play").onclick = togglePlay;
    $("btn-draw").onclick = startDraw;
    $("btn-draw-finish").onclick = finishDraw;
    $("btn-draw-clear").onclick = () => clearDraw(true);
    $("btn-locate").onclick = locate;
    $("map-search").oninput = (e) => search(e.target.value);
    syncDate();
    return M;
  };
  M.relabel = function () {
    const sel = (id, opts) => { const v = document.getElementById(id).value; document.getElementById(id).innerHTML = opts; document.getElementById(id).value = v; };
    sel("map-base", Object.entries(BASES).map(([k, v]) => `<option value="${k}">${v.label[M.lang()]}</option>`).join(""));
    sel("map-overlay", Object.entries(OVERLAYS).map(([k, v]) => `<option value="${k}">${v ? v.label[M.lang()] : (M.lang() === "ar" ? "بدون طبقة" : "No NASA layer")}</option>`).join(""));
    if (M.overlayKey !== "none") setOverlay(M.overlayKey);
    if (M.field) document.getElementById("draw-area").textContent = areaText(M.field.area_ha);
  };
  M.setField = setField;
  M.showFarms = showFarms;
  M.getField = () => M.field;
  M.setOverlay = (k) => { document.getElementById("map-overlay").value = k; setOverlay(k); };
  M.setDate = setDate;
  window.MapUI = M;
})();
