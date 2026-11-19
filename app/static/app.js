"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (p, d) => (p * 100).toFixed(d ?? (p >= 0.995 || p < 0.1 ? 1 : 0)) + "%";

const STATUS = {
  confident: { tone: "ok",   badge: "Confident match" },
  tentative: { tone: "warn", badge: "Possible match" },
  uncertain: { tone: "bad",  badge: "Inconclusive" },
  no_leaf:   { tone: "bad",  badge: "No plant detected" },
};
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage full or blocked */ } },
};

/* ───────────────────────── Theme ───────────────────────── */
const isDark = () => {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
};
function syncThemeButton() {
  const b = $("theme-btn"), dark = isDark();
  b.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
  b.title = b.getAttribute("aria-label");
}
$("theme-btn").addEventListener("click", () => {
  document.documentElement.dataset.theme = isDark() ? "light" : "dark";
  try { localStorage.setItem("pd-theme", document.documentElement.dataset.theme); } catch {}
  syncThemeButton();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", syncThemeButton);
syncThemeButton();

/* ───────────────────────── Model info ───────────────────────── */
fetch("/api/info").then((r) => r.json()).then((d) => {
  const pill = $("model-status");
  pill.classList.add("online");
  pill.querySelector(".st-long").textContent = `Model online · ${d.gpu ? "GPU" : "CPU"}`;
  pill.querySelector(".st-short").textContent = "Online";
  $("samples-block").hidden = !(d.samples || []).length;
  pill.title = d.gpu ? `Running on ${d.gpu}` : "Running on CPU";

  const crops = Object.entries(d.crops).sort(([a], [b]) => a.localeCompare(b));
  const nDiseases = crops.reduce((n, [, v]) => n + v.filter((x) => x !== "Healthy").length, 0);
  const na = (id) => { $(id).textContent = "N/A"; $(id).classList.add("na"); $(id).title = "Metrics not available — run train.py / tools/eval_field.py"; };
  d.test_acc ? ($("kpi-acc").textContent = pct(d.test_acc, 1)) : na("kpi-acc");
  $("kpi-classes").textContent = d.classes;
  $("kpi-crops").textContent = crops.length;
  $("cov-sub").textContent = `${crops.length} crops · ${nDiseases} diseases · healthy reference for each crop`;

  $("crops").innerHTML = crops.map(([crop, list]) => {
    const dis = list.filter((x) => x !== "Healthy");
    return `<div class="crop-card"><header><strong>${esc(crop)}</strong><span class="count">${dis.length ? `${dis.length} disease${dis.length === 1 ? "" : "s"}` : "reference only"}</span></header>
      <div class="chips">${dis.map((x) => `<span class="chip">${esc(x)}</span>`).join("")}<span class="chip healthy">Healthy</span></div></div>`;
  }).join("");

  $("samples").innerHTML = (d.samples || []).map((s) => `
    <button type="button" class="sample" data-src="/static/samples/${esc(s.file)}"
      aria-label="Try sample: ${esc(s.crop)} ${esc(s.disease.toLowerCase())}, ${s.source === "field" ? "field" : "lab"} photo"
      title="${esc(s.crop)} · ${esc(s.disease)} (${s.source === "field" ? "field photo" : "lab photo"})">
      <img src="/static/samples/${esc(s.file)}" alt="" loading="lazy">
      <span class="tag" aria-hidden="true">${s.source === "field" ? "Field" : "Lab"}</span>
    </button>`).join("");

  if (!d.test_acc) { na("mc-lab"); $("mc-lab-note").textContent = "Lab metrics not available yet — run train.py."; }
  if (!d.field) { na("mc-field"); $("mc-field-note").textContent = "Field evaluation not run yet — run tools/eval_field.py."; }
  if (d.test_acc) {
    $("mc-lab").textContent = pct(d.test_acc, 1);
    $("mc-lab-note").textContent = `Held-out test split (${d.n_test.toLocaleString()} images): lab leaves plus field, fruit and vegetable photos.`;
  }
  if (d.field) {
    $("mc-field").textContent = pct(d.field.top1_acc, 1);
    $("mc-field-note").textContent = `Independent PlantDoc set (${d.field.n_images} images): ${pct(d.field.top5_acc, 0)} correct within top-5, ${pct(d.field.crop_acc, 0)} correct crop.`;
  }
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return;
    $("mc-lab-bar").style.width = (d.test_acc || 0) * 100 + "%";
    $("mc-field-bar").style.width = (d.field?.top1_acc || 0) * 100 + "%";
    io.disconnect();
  }), { threshold: 0.3 });
  io.observe($("model"));
}).catch(() => {
  const pill = $("model-status");
  pill.classList.add("offline");
  pill.querySelector(".st-long").textContent = "Model offline";
  pill.querySelector(".st-short").textContent = "Offline";
  $("offline-note").hidden = false;
  ["kpi-acc", "kpi-classes", "kpi-crops"].forEach((id) => { $(id).textContent = "N/A"; $(id).classList.add("na"); });
  $("cov-sub").textContent = "Coverage unavailable while the model server is offline.";
});

/* ───────────────────────── Input ───────────────────────── */
const dz = $("dropzone"), input = $("file");
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
input.addEventListener("change", () => { if (input.files[0]) diagnose(input.files[0]); input.value = ""; });
["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("dragover"); }));
["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("dragover"); }));
dz.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) diagnose(f); });
window.addEventListener("paste", (e) => {
  const f = [...(e.clipboardData?.files || [])].find((x) => x.type.startsWith("image/"));
  if (f) diagnose(f);
});
$("samples").addEventListener("click", async (e) => {
  const b = e.target.closest(".sample"); if (!b) return;
  const blob = await (await fetch(b.dataset.src)).blob();
  diagnose(new File([blob], b.dataset.src.split("/").pop(), { type: blob.type }));
});

/* ───────────────────────── States ───────────────────────── */
let current = null; // last successful report, kept so an error never destroys it
function show(state) {
  ["empty", "loading", "result", "error"].forEach((s) => ($("state-" + s).hidden = s !== state));
  $("report").setAttribute("aria-busy", state === "loading");
}
function announce(msg) { $("sr-status").textContent = ""; requestAnimationFrame(() => ($("sr-status").textContent = msg)); }
function showError(msg) {
  $("error-msg").textContent = msg;
  $("btn-back").hidden = !current;
  show("error");
  announce("Analysis failed. " + msg);
}
$("btn-retry").onclick = () => input.click();
$("btn-back").onclick = () => current && render(current);
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 4000);
}
function scrollToReport() {
  if (matchMedia("(max-width: 900px)").matches) $("report").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ───────────────────────── Diagnose ───────────────────────── */
async function diagnose(file) {
  if (!file.type.startsWith("image/")) return showError(`"${file.name}" isn't an image. Choose a JPG, PNG or WebP photo of a leaf or fruit.`);
  if (file.size > 15 * 1024 * 1024) return showError("That image is larger than 15 MB. Resize it or choose a smaller photo.");
  const url = URL.createObjectURL(file);
  $("loading-img").src = url;
  show("loading"); scrollToReport(); announce("Analysing image…");

  const fd = new FormData(); fd.append("file", file);
  try {
    const [res] = await Promise.all([
      fetch("/api/predict", { method: "POST", body: fd }),
      new Promise((r) => setTimeout(r, 450)), // keep the transition perceptible
    ]);
    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || "The server could not analyse this image.");
    const thumb = await makeThumb(url);
    const rec = { id: nextId(), time: Date.now(), photo: url, thumb, ...d };
    render(rec);
    saveHistory(rec);
  } catch (err) {
    const msg = err instanceof TypeError
      ? "The model server isn't responding. Check that ./run.sh is running, then try again."
      : err.message;
    showError(msg);
  }
}

function nextId() {
  const n = store.get("pd-counter", 0) + 1; store.set("pd-counter", n);
  return "PD-" + String(n).padStart(4, "0");
}

function makeThumb(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas"), s = 96, m = Math.min(img.width, img.height);
      c.width = c.height = s;
      c.getContext("2d").drawImage(img, (img.width - m) / 2, (img.height - m) / 2, m, m, 0, 0, s, s);
      resolve(c.toDataURL("image/jpeg", 0.8));
    };
    img.onerror = () => resolve("");
    img.src = url;
  });
}

/* ───────────────────────── Render ───────────────────────── */
function render(r) {
  const best = r.top[0], s = STATUS[r.status];
  $("r-id").textContent = r.id;
  $("r-time").textContent = new Date(r.time).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  $("r-time").dateTime = new Date(r.time).toISOString();
  $("r-ms").textContent = r.ms != null ? `${r.ms} ms` : "";

  current = r;
  const hasPhoto = !!r.photo;
  $("r-photo").src = r.photo || r.heatmap;
  $("r-heat").src = r.heatmap;
  $("view-photo").disabled = !hasPhoto;
  setView(hasPhoto ? "photo" : "heat");
  if (!hasPhoto) $("viewer-cap").textContent = "Reopened from history: the original photo isn't stored, so only the heatmap is shown. Re-upload the image for the full view.";

  const badge = $("r-badge");
  badge.className = "badge " + s.tone;
  badge.textContent = r.status === "confident" && r.healthy ? "Healthy" : s.badge;

  const noLeaf = r.status === "no_leaf";
  $("r-crop").textContent = noLeaf ? "Image check" : best.crop;
  $("r-title").textContent = noLeaf ? "No plant found in this image"
    : r.status === "uncertain" ? `Inconclusive — closest match: ${best.disease.toLowerCase()}`
    : best.disease;

  $("meter").className = "meter " + s.tone;
  $("r-conf").textContent = pct(best.prob, 1);
  $("r-fill").style.width = "0";
  requestAnimationFrame(() => requestAnimationFrame(() => ($("r-fill").style.width = best.prob * 100 + "%")));

  $("r-cause").textContent = r.info.cause || "—";
  $("r-crop2").textContent = noLeaf ? "—" : best.crop;

  const notice = $("r-notice");
  const notes = {
    tentative: ["warn", "Moderate confidence.", "Compare with the alternatives below and retake a close-up photo of one leaf or fruit to confirm."],
    uncertain: ["bad", "The model is not confident.", "Treat this as unknown. Retake the photo on a plain background, or the condition may be outside what the model knows."],
    no_leaf: ["bad", "No plant detected.", "Frame a single leaf or fruit so it fills most of the photo."],
  }[r.status];
  notice.hidden = !notes;
  if (notes) { notice.className = "notice " + notes[0]; notice.innerHTML = `<div><strong>${notes[1]}</strong> <span>${notes[2]}</span></div>`; }

  $("r-symptoms").textContent = r.info.symptoms || "—";
  $("r-actions").innerHTML = (r.info.actions || []).map((a) => `<li>${esc(a)}</li>`).join("");

  $("r-dx").innerHTML = r.top.map((p, i) => `
    <tr class="${i === 0 ? "top" : ""}">
      <td class="rank">${i + 1}</td>
      <td>${esc(p.crop === "—" ? "No plant in image" : p.disease)}</td>
      <td class="crop-col muted">${esc(p.crop === "—" ? "—" : p.crop)}</td>
      <td class="num"><div class="pbar"><i><b style="width:${Math.max(p.prob * 100, 0.8)}%"></b></i><span>${pct(p.prob, 1)}</span></div></td>
    </tr>`).join("");

  show("result");
  announce(`Diagnosis complete. ${s.badge}: ${noLeaf ? "no plant found" : `${best.crop}, ${best.disease}`}, ${pct(best.prob, 1)} confidence.`);
}

/* ───────────────────────── Heatmap view ───────────────────────── */
function setView(v) {
  const heat = v === "heat";
  $("view-photo").setAttribute("aria-pressed", !heat);
  $("view-heat").setAttribute("aria-pressed", heat);
  $("opacity-wrap").hidden = !heat;
  $("r-heat").style.opacity = heat ? $("opacity").value / 100 : 0;
  $("viewer-cap").textContent = heat
    ? "Grad-CAM: warmer regions had more influence on the prediction. Check that it focuses on the symptoms, not the background."
    : "Original image as uploaded (center-cropped for analysis).";
}
$("view-photo").onclick = () => setView("photo");
$("view-heat").onclick = () => setView("heat");
$("opacity").addEventListener("input", (e) => ($("r-heat").style.opacity = e.target.value / 100));

$("btn-new").onclick = () => { show("empty"); dz.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: "smooth" }); };
$("btn-print").onclick = () => window.print();

/* ───────────────────────── History ───────────────────────── */
const HKEY = "pd-history";
function saveHistory(r) {
  const { photo, ...keep } = r; // object URLs don't survive reloads; the thumbnail does
  const list = [keep, ...store.get(HKEY, [])].slice(0, 6);
  store.set(HKEY, list);
  renderHistory();
}
function renderHistory() {
  const list = store.get(HKEY, []);
  $("history-block").hidden = !list.length;
  $("history").innerHTML = list.map((r, i) => {
    const b = r.top[0];
    const title = r.status === "no_leaf" ? "No plant" : b.disease;
    return `<li><button data-i="${i}">
      <img src="${r.thumb}" alt="">
      <div><div class="h-title">${esc(title)}</div><div class="h-sub">${esc(b.crop === "—" ? "" : b.crop)} · ${esc(r.id)}</div></div>
      <span class="h-conf">${pct(b.prob, 0)}</span></button></li>`;
  }).join("");
}
$("history").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-i]"); if (!b) return;
  const r = store.get(HKEY, [])[+b.dataset.i];
  if (r) { render({ ...r, photo: null }); scrollToReport(); }
});
$("history-clear").onclick = () => { store.set(HKEY, []); renderHistory(); };
renderHistory();

/* Highlight nav item for the section in view */
const links = [...document.querySelectorAll(".nav a")];
const spy = new IntersectionObserver((es) => es.forEach((e) => {
  if (e.isIntersecting) links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + e.target.id));
}), { rootMargin: "-45% 0px -50% 0px" });
["workspace", "coverage", "model"].forEach((id) => spy.observe($(id)));
