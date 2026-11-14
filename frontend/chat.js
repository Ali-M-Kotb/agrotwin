/* AgroTwin voice assistant — AI-generated (Claude, Anthropic) under human review.
 * Talk → text (the browser's recogniser, or local faster-whisper on the laptop) → /api/chat, which calls
 * AgroTwin's own engines → the reply is read aloud in Egyptian Arabic (/api/speak) or the browser voice. */
const Chat = (() => {
  const C = { open: false, history: [], rec: null, media: null, listening: false };
  const $c = (s) => document.querySelector(s);

  function el() {
    if ($c("#chat")) return;
    document.body.insertAdjacentHTML("beforeend", `
      <button id="chat-fab" class="chat-fab" aria-label="Ask AgroTwin"><svg><use href="#i-mic"/></svg><span></span></button>
      <aside id="chat" class="chat hidden" aria-live="polite">
        <header><div><b class="ct"></b><div class="cs meta"></div></div><button class="cx" aria-label="close">×</button></header>
        <div class="log"></div>
        <div class="suggest"></div>
        <form class="cbar">
          <button type="button" class="mic" aria-label="talk"><svg><use href="#i-mic"/></svg></button>
          <input type="text" autocomplete="off">
          <button type="submit" class="send">→</button>
        </form>
      </aside>`);
    $c("#chat-fab").onclick = toggle;
    $c("#chat .cx").onclick = toggle;
    $c("#chat .mic").onclick = talk;
    $c("#chat form").onsubmit = (e) => { e.preventDefault(); const v = $c("#chat input").value.trim(); if (v) { $c("#chat input").value = ""; ask(v); } };
    labels();
  }

  function labels() {
    if (!$c("#chat")) return;
    const ar = S.lang === "ar";
    $c("#chat-fab span").textContent = t("chat_fab");
    $c("#chat .ct").textContent = t("chat_title");
    $c("#chat .cs").textContent = t("chat_sub");
    $c("#chat input").placeholder = t("chat_ph");
    $c("#chat").dir = ar ? "rtl" : "ltr";
    const qs = ar ? ["أزرع إيه السنة الجاية؟", "أروي امتى؟", "أرضي عاملة إيه؟", "الجو هيعمل إيه؟", "سعر القمح بكام؟"]
                  : ["What should I plant?", "When should I irrigate?", "How is my field doing?", "Weather ahead?", "Price of wheat?"];
    $c("#chat .suggest").innerHTML = qs.map((q) => `<button type="button">${esc(q)}</button>`).join("");
    document.querySelectorAll("#chat .suggest button").forEach((b) => (b.onclick = () => ask(b.textContent)));
    if (!C.history.length) $c("#chat .log").innerHTML = `<div class="msg bot">${esc(t("chat_hello"))}</div>`;
  }

  function toggle() {
    el(); labels();
    C.open = !C.open;
    $c("#chat").classList.toggle("hidden", !C.open);
    $c("#chat-fab").classList.toggle("on", C.open);
    if (C.open) $c("#chat input").focus();
  }

  function add(role, text, extra = "") {
    const log = $c("#chat .log");
    log.insertAdjacentHTML("beforeend", `<div class="msg ${role}" dir="auto">${esc(text)}${extra}</div>`);
    log.scrollTop = log.scrollHeight;
  }

  const TOOL_NAMES = {
    recommend_rotation: ["replay since 1991", "إعادة تشغيل من ١٩٩١"], irrigation_plan: ["16-day water balance", "ميزان المية ١٦ يوم"],
    weather_forecast: ["16-day forecast", "توقّعات ١٦ يوم"], field_pulse: ["Field Pulse model", "موديل نبض الأرض"],
    crop_price: ["quoted prices", "أسعار بمصدر"], field_history: ["time machine (MODIS)", "آلة الزمن (MODIS)"], robot_status: ["Scout robot", "الروبوت"],
  };

  async function ask(text) {
    el(); if (!C.open) toggle();
    if (!C.history.length) labels();
    add("me", text);
    add("bot pending", "…");
    const ctx = { lat: S.site.lat, lon: S.site.lon, winter: ($("#ex-w") || {}).value, summer: ($("#ex-s") || {}).value };
    let r;
    try {
      r = await api("/api/chat", { method: "POST", body: JSON.stringify({ text, lang: S.lang, ...ctx, history: C.history.slice(-6) }) });
    } catch (e) {
      document.querySelector("#chat .pending").remove();
      add("bot", e.message); return;
    }
    document.querySelector("#chat .pending").remove();
    const ar = r.lang === "ar";
    const used = (r.tools || []).map((x) => (TOOL_NAMES[x.tool] || [x.tool, x.tool])[ar ? 1 : 0]);
    const extra = `<div class="used">${used.length ? (ar ? "استخدمت: " : "used: ") + used.map(esc).join(" · ") : ""}${r.engine === "claude" ? " · Claude" : ""}</div>`;
    add("bot", r.reply, extra);
    C.history.push({ role: "user", text }, { role: "assistant", text: r.reply });
    if (r.ctx_update && (r.ctx_update.winter || r.ctx_update.summer)) {
      if (r.ctx_update.winter && $("#ex-w")) $("#ex-w").value = r.ctx_update.winter;
      if (r.ctx_update.summer && $("#ex-s")) $("#ex-s").value = r.ctx_update.summer;
      if (typeof simulate === "function") simulate("chat");
    }
    say(r.reply, ar);
  }

  async function say(text, ar) {
    if (S.audio && !S.audio.paused) S.audio.pause();
    try {
      const res = await fetch("/api/speak", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang: ar ? "ar" : "en", voice: ar ? (S.voice === "m" ? "ar-EG-ShakirNeural" : "ar-EG-SalmaNeural") : "en-GB-SoniaNeural" }) });
      if (!res.ok) throw new Error("voice");
      S.audio = new Audio(URL.createObjectURL(await res.blob()));
      await S.audio.play();
    } catch {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = ar ? "ar-EG" : "en-GB";
      speechSynthesis.cancel(); speechSynthesis.speak(u);
    }
  }

  // ---- listening: browser recogniser first, local whisper as the fallback ---------------
  function talk() {
    if (C.listening) return stop();
    if (S.audio && !S.audio.paused) S.audio.pause();
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SR && !C.noBrowserSR) {
      const rec = new SR();
      rec.lang = S.lang === "ar" ? "ar-EG" : "en-US";
      rec.interimResults = true;
      rec.maxAlternatives = 1;
      let final = "";
      rec.onresult = (e) => {
        let interim = "";
        for (const r of e.results) (r.isFinal ? (final = r[0].transcript) : (interim += r[0].transcript));
        $c("#chat input").value = final || interim;
      };
      rec.onerror = (e) => {
        if (["network", "not-allowed", "service-not-allowed", "language-not-supported"].includes(e.error)) {
          C.noBrowserSR = true; listening(false); record();          // fall back to the laptop's own recogniser
        }
      };
      rec.onend = () => {
        listening(false);
        const v = (final || $c("#chat input").value).trim();
        if (v && !C.noBrowserSR) { $c("#chat input").value = ""; ask(v); }
      };
      C.rec = rec; rec.start(); listening(true);
    } else record();
  }

  async function record() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      const mr = new MediaRecorder(stream);
      mr.ondataavailable = (e) => chunks.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((x) => x.stop());
        listening(false);
        $c("#chat input").placeholder = "…";
        const fd = new FormData();
        fd.append("file", new Blob(chunks, { type: mr.mimeType }), "speech.webm");
        try {
          const r = await fetch(`/api/stt?lang=${S.lang}`, { method: "POST", body: fd });
          if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
          const j = await r.json();
          if (j.text) ask(j.text);
        } catch (e) { add("bot", (S.lang === "ar" ? "مقدرتش أسمع: " : "Couldn't hear: ") + e.message); }
        labels();
      };
      C.media = mr; mr.start(); listening(true);
      setTimeout(() => mr.state === "recording" && mr.stop(), 12000);
    } catch (e) { add("bot", (S.lang === "ar" ? "محتاج إذن الميكروفون." : "Microphone permission needed.")); }
  }

  function stop() {
    if (C.rec) try { C.rec.stop(); } catch {}
    if (C.media && C.media.state === "recording") C.media.stop();
  }
  function listening(on) {
    C.listening = on;
    $c("#chat .mic").classList.toggle("on", on);
    $c("#chat input").placeholder = on ? t("chat_listening") : t("chat_ph");
  }

  return { init: el, labels, ask, toggle };
})();
