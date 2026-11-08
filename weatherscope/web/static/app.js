// WeatherScope : interface web. Appelle l'API /api/* (mêmes services que la ligne de commande).
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const num = (v, d = 2) => (v === null || v === undefined ? "" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: d }));
const UNIT = { TMAX: "°C", TMIN: "°C", PRCP: "mm" };
const STATIONS = new Map(); // id -> station (pour les noms et la carte)

// ---------- Appels à l'API ----------
async function api(path, params = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => q.append(k, x));
    else if (v !== "" && v !== null && v !== undefined && v !== false) q.append(k, v);
  }
  const r = await fetch(`${path}?${q}`);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Erreur ${r.status} : ${JSON.stringify(body.detail)}`);
  return body;
}

function showError(msg) {
  const el = $("#error");
  el.textContent = msg || "";
  el.hidden = !msg;
}

// Exécute une requête : bouton désactivé, message d'attente, erreur explicite (aucun résultat partiel affiché).
async function runQuery(form, out, task) {
  const btn = $("button", form);
  btn.disabled = true;
  showError("");
  out.innerHTML = `<p class="loading">Calcul en cours</p>`;
  const t0 = performance.now();
  try {
    await task(((performance.now() - t0) / 1000));
  } catch (e) {
    out.innerHTML = "";
    showError(e.message);
  } finally {
    btn.disabled = false;
  }
}

function formData(form) {
  const fd = new FormData(form);
  const o = {};
  for (const [k, v] of fd.entries()) {
    if (k === "zone" && form.querySelector('input[type="checkbox"][name="zone"]')) (o.zone ||= []).push(v);
    else o[k] = v;
  }
  return o;
}

const elapsed = (t0) => `${num((performance.now() - t0) / 1000, 2)} s`;

// ---------- Carte des stations (SVG, projection équirectangulaire, sans fond de carte) ----------
const MAP = { lon0: -10, lon1: 16, lat0: 35.5, lat1: 55.5, w: 380 };
MAP.k = MAP.w / ((MAP.lon1 - MAP.lon0) * Math.cos((46 * Math.PI) / 180));
MAP.h = Math.round((MAP.lat1 - MAP.lat0) * MAP.k);
const px = (lon) => (lon - MAP.lon0) * MAP.k * Math.cos((46 * Math.PI) / 180);
const py = (lat) => (MAP.lat1 - lat) * MAP.k;

// points : [{id, lat, lon, r, cls, color, title}] ; onClick(id)
function drawMap(el, points, onClick) {
  let grid = "";
  for (let lon = -10; lon <= 15; lon += 5)
    grid += `<line x1="${px(lon)}" y1="0" x2="${px(lon)}" y2="${MAP.h}" stroke="var(--line)"/><text x="${px(lon) + 2}" y="${MAP.h - 4}" font-size="9" fill="var(--muted)">${lon}°</text>`;
  for (let lat = 40; lat <= 55; lat += 5)
    grid += `<line x1="0" y1="${py(lat)}" x2="${MAP.w}" y2="${py(lat)}" stroke="var(--line)"/><text x="2" y="${py(lat) - 2}" font-size="9" fill="var(--muted)">${lat}°</text>`;
  const dots = points
    .map((p) => `<circle data-id="${esc(p.id)}" cx="${px(p.lon).toFixed(1)}" cy="${py(p.lat).toFixed(1)}" r="${p.r ?? 2.2}" fill="${p.color}" fill-opacity="${p.opacity ?? 0.85}" ${p.stroke ? `stroke="${p.stroke}" stroke-width="1.5"` : ""}><title>${esc(p.title ?? p.id)}</title></circle>`)
    .join("");
  el.innerHTML = `<svg viewBox="0 0 ${MAP.w} ${MAP.h}" role="img" aria-label="Carte des stations">${grid}${dots}</svg>`;
  if (onClick) el.querySelectorAll("circle").forEach((c) => c.addEventListener("click", () => onClick(c.dataset.id)));
}

const zoneColor = (z) => (z === "GM" ? "var(--gm)" : "var(--sp)");
const stationTitle = (id) => {
  const s = STATIONS.get(id);
  return s ? `${id} ${s.name} (${s.zone}), ${s.elevation ?? "?"} m` : id;
};

// ---------- Onglets ----------
function openTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== name));
  showError("");
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => openTab(b.dataset.tab)));

// Remplit l'onglet Traçabilité à partir du champ « sources » d'un résultat, puis le lance.
function goTrace(src) {
  const f = $("#trace-form");
  let start = src.start, end = src.end;
  if (src.year && src.month) {
    const last = new Date(src.year, src.month, 0).getDate();
    const m = String(src.month).padStart(2, "0");
    start = `${src.year}-${m}-01`;
    end = `${src.year}-${m}-${last}`;
  }
  f.station.value = src.station || "";
  f.zone.value = src.station ? "" : src.zone || "";
  f.element.value = src.element || "";
  f.start.value = start;
  f.end.value = end;
  openTab("trace");
  f.requestSubmit();
}
const sourcesButton = (src, label = "sources") => `<button type="button" class="link" data-src='${esc(JSON.stringify(src))}'>${label}</button>`;
function wireSources(root) {
  root.querySelectorAll("button[data-src]").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      goTrace(JSON.parse(b.dataset.src));
    }));
}

// ---------- Petits graphiques SVG ----------
// F1 : moyennes mensuelles TMAX/TMIN (lignes, échelle de gauche) et cumuls PRCP (barres, échelle de droite).
function f1Chart(months) {
  const keys = [...new Set(months.map((m) => `${m.year}-${String(m.month).padStart(2, "0")}`))];
  if (!keys.length) return "";
  const W = 760, H = 230, L = 40, R = 44, T = 10, B = 26, iw = W - L - R, ih = H - T - B;
  const get = (el, k, f) => months.find((m) => m.element === el && `${m.year}-${String(m.month).padStart(2, "0")}` === k)?.[f];
  const temps = months.filter((m) => m.element !== "PRCP" && m.mean !== null).map((m) => m.mean);
  const rains = months.filter((m) => m.element === "PRCP" && m.total !== null).map((m) => m.total);
  const tmin = Math.min(0, ...temps), tmax = Math.max(1, ...temps), rmax = Math.max(1, ...rains);
  const x = (i) => L + (keys.length === 1 ? iw / 2 : (i * iw) / (keys.length - 1));
  const yt = (v) => T + ih - ((v - tmin) / (tmax - tmin)) * ih;
  const yr = (v) => T + ih - (v / rmax) * ih;
  const bw = Math.max(2, Math.min(24, (iw / keys.length) * 0.6));
  let s = "";
  keys.forEach((k, i) => {
    const r = get("PRCP", k, "total");
    if (r !== null && r !== undefined) s += `<rect x="${x(i) - bw / 2}" y="${yr(r)}" width="${bw}" height="${T + ih - yr(r)}" fill="var(--accent)" fill-opacity="0.25"><title>${k} : ${num(r, 1)} mm</title></rect>`;
  });
  for (const [el, color] of [["TMAX", "var(--warm)"], ["TMIN", "var(--cold)"]]) {
    let d = "", pen = false;
    keys.forEach((k, i) => {
      const v = get(el, k, "mean");
      if (v === null || v === undefined) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${yt(v).toFixed(1)}`;
      pen = true;
      s += `<circle cx="${x(i)}" cy="${yt(v)}" r="2.5" fill="${color}"><title>${el} ${k} : ${num(v)} °C</title></circle>`;
    });
    s += `<path d="${d}" fill="none" stroke="${color}" stroke-width="2"/>`;
  }
  const step = Math.ceil(keys.length / 12);
  keys.forEach((k, i) => { if (i % step === 0) s += `<text x="${x(i)}" y="${H - 8}" font-size="10" text-anchor="middle" fill="var(--muted)">${k}</text>`; });
  for (const v of [tmin, (tmin + tmax) / 2, tmax])
    s += `<text x="${L - 4}" y="${yt(v) + 3}" font-size="10" text-anchor="end" fill="var(--muted)">${num(v, 0)}°</text><line x1="${L}" x2="${W - R}" y1="${yt(v)}" y2="${yt(v)}" stroke="var(--line)"/>`;
  s += `<text x="${W - R + 4}" y="${T + 8}" font-size="10" fill="var(--muted)">${num(rmax, 0)} mm</text>`;
  return `<div class="chart"><svg viewBox="0 0 ${W} ${H}">${s}</svg></div>
    <div class="legend"><span><i style="background:var(--warm)"></i>TMAX moyenne</span><span><i style="background:var(--cold)"></i>TMIN moyenne</span><span><i style="background:var(--accent);opacity:.35"></i>PRCP cumul du mois</span></div>`;
}

// F3 : une frise par zone, une barre par mois (rouge au-dessus de la normale, bleu en dessous).
function f3Chart(rows, y0, y1, unit) {
  const zones = [...new Set(rows.map((r) => r.zone))].sort();
  const n = (y1 - y0 + 1) * 12, W = 1100, L = 40, rowH = 120, gap = 40, iw = W - L - 6;
  const amax = Math.max(0.5, ...rows.map((r) => Math.abs(r.anomaly)));
  let s = "";
  zones.forEach((z, zi) => {
    const top = zi * (rowH + gap) + 16, mid = top + rowH / 2;
    s += `<text x="0" y="${top - 4}" font-size="13" font-weight="600" fill="var(--fg)">${z === "GM" ? "Allemagne (GM)" : z === "SP" ? "Espagne (SP)" : z}</text>`;
    s += `<line x1="${L}" x2="${W - 6}" y1="${mid}" y2="${mid}" stroke="var(--muted)" stroke-width="0.5"/>`;
    s += `<text x="${L - 4}" y="${top + 8}" font-size="9" text-anchor="end" fill="var(--muted)">+${num(amax, 1)}</text><text x="${L - 4}" y="${top + rowH}" font-size="9" text-anchor="end" fill="var(--muted)">−${num(amax, 1)}</text>`;
    for (const r of rows.filter((r) => r.zone === z)) {
      const i = (r.year - y0) * 12 + r.month - 1, h = (Math.abs(r.anomaly) / amax) * (rowH / 2);
      s += `<rect x="${L + (i * iw) / n}" y="${r.anomaly >= 0 ? mid - h : mid}" width="${Math.max(1, iw / n - 0.5)}" height="${h}" fill="${r.anomaly >= 0 ? "var(--warm)" : "var(--cold)"}"><title>${z} ${r.year}-${String(r.month).padStart(2, "0")} : ${r.anomaly > 0 ? "+" : ""}${num(r.anomaly)} ${unit} (rang ${r.rank})</title></rect>`;
    }
    for (let y = y0; y <= y1; y++) s += `<line x1="${L + ((y - y0) * 12 * iw) / n}" x2="${L + ((y - y0) * 12 * iw) / n}" y1="${top}" y2="${top + rowH}" stroke="var(--line)"/><text x="${L + ((y - y0) * 12 * iw) / n + 2}" y="${top + rowH + 13}" font-size="11" fill="var(--muted)">${y}</text>`;
  });
  return `<div class="chart"><svg viewBox="0 0 ${W} ${zones.length * (rowH + gap) + 4}">${s}</svg></div>`;
}

const table = (head, rows) => `<div class="tablewrap"><table><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;

// ---------- F1 : stations ----------
function f1Search(params) {
  return runQuery($("#f1-search"), $("#f1-count"), async () => {
    const r = await api("/api/stations", params);
    $("#f1-count").textContent = `${r.stations.length} stations`;
    const ids = new Set(r.stations.map((s) => s.id));
    const pts = [...STATIONS.values()].map((s) => ids.has(s.id)
      ? { ...s, color: zoneColor(s.zone), title: stationTitle(s.id), r: 2.6 }
      : { ...s, color: "var(--muted)", opacity: 0.2, r: 1.6 });
    drawMap($("#f1-map"), pts, pickStation);
    $("#f1-list").innerHTML = r.stations.map((s) => `<li data-id="${esc(s.id)}">${esc(s.name)}<span>${esc(s.id)}</span></li>`).join("");
    $("#f1-list").querySelectorAll("li").forEach((li) => li.addEventListener("click", () => pickStation(li.dataset.id)));
  });
}

function pickStation(id) {
  const f = $("#f1-summary");
  f.station.value = id;
  $("#f1-list").querySelectorAll("li").forEach((li) => li.classList.toggle("sel", li.dataset.id === id));
  f.requestSubmit();
}

$("#f1-search").addEventListener("submit", (e) => {
  e.preventDefault();
  const d = formData(e.target);
  f1Search({ zone: d.zone ? [d.zone] : [], name: d.name, bbox: d.bbox });
});

$("#f1-summary").addEventListener("submit", (e) => {
  e.preventDefault();
  const d = formData(e.target), out = $("#f1-out"), t0 = performance.now();
  runQuery(e.target, out, async () => {
    const r = await api(`/api/station/${encodeURIComponent(d.station.trim())}`, { start: d.start, end: d.end });
    const st = r.station;
    const cards = Object.entries(r.totals).map(([el, t]) => `<div class="card"><h3>${el}</h3>
      <div class="big">${num(t.availability * 100, 0)} %</div>
      <div class="small">${t.n_valid} jours valides sur ${t.expected} attendus</div>
      <div class="small">${t.n_flagged ? `<span class="flag">${t.n_flagged} invalides (qflag)</span>` : "0 invalide"} · ${t.n_trace} traces · ${t.n_presumed} P</div></div>`).join("");
    const rows = r.months.map((m) => `<tr><td>${m.element}</td><td>${m.year}-${String(m.month).padStart(2, "0")}</td>
      <td class="num">${m.expected}</td><td class="num">${m.n_valid}</td><td class="num ${m.n_flagged ? "flag" : ""}">${m.n_flagged}</td>
      <td class="num">${m.availability === null ? "" : num(m.availability * 100, 0) + " %"}</td>
      <td class="num">${num(m.mean)}</td><td class="num">${num(m.total, 1)}</td><td class="num">${num(m.min, 1)}</td><td class="num">${num(m.max, 1)}</td><td>${m.unit}</td></tr>`);
    out.innerHTML = `<div class="box"><h2>${esc(st.id)} · ${esc(st.name)} (${st.zone})</h2>
        <p class="note">lat ${num(st.lat, 4)}, lon ${num(st.lon, 4)}, altitude ${st.elevation ?? "?"} m · ${d.start} → ${d.end} · ${elapsed(t0)} ·
        ${sourcesButton(r.sources, "voir les observations sources")}</p></div>
      <div class="cards">${cards}</div>
      <div class="box">${f1Chart(r.months)}</div>
      <div class="box"><h2>Résumé mensuel</h2>${table(["Élément", "Mois", "Attendus", "Valides", "Invalides", "Dispo.", "Moyenne", "Cumul", "Min", "Max", ""], rows)}</div>`;
    wireSources(out);
  });
});

// ---------- F2 : épisodes ----------
$("#f2-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const d = formData(e.target), out = $("#f2-out"), t0 = performance.now();
  runQuery(e.target, out, async () => {
    const r = await api("/api/episodes", d);
    const per = new Map();
    r.episodes.forEach((x) => per.set(x.station, (per.get(x.station) || 0) + 1));
    const zones = new Set(d.zone || []);
    drawMap($("#f2-map"), [...STATIONS.values()].filter((s) => zones.has(s.zone)).map((s) => per.has(s.id)
      ? { ...s, color: zoneColor(s.zone), r: 2 + 1.6 * Math.sqrt(per.get(s.id)), opacity: 0.7, title: `${stationTitle(s.id)} : ${per.get(s.id)} épisodes` }
      : { ...s, color: "var(--muted)", opacity: 0.25, r: 1.6 }));
    const longest = [...r.episodes].sort((a, b) => b.days - a.days)[0];
    const rows = r.episodes.map((x) => `<tr class="click" data-src='${esc(JSON.stringify(x.sources))}'><td>${esc(x.station)}</td>
      <td>${esc(STATIONS.get(x.station)?.name ?? "")}</td><td>${x.start}</td><td>${x.end}</td><td class="num">${x.days}</td>
      <td class="num">+${num(x.mean_excess)}</td><td class="num">${num(x.max_value, 1)}</td></tr>`);
    out.innerHTML = `<div class="cards"><div class="card"><h3>Épisodes</h3><div class="big">${r.count}</div><div class="small">${per.size} stations · ${elapsed(t0)}</div></div>
      ${longest ? `<div class="card"><h3>Le plus long</h3><div class="big">${longest.days} jours</div><div class="small">${esc(longest.station)} ${esc(STATIONS.get(longest.station)?.name ?? "")}, ${longest.start} → ${longest.end}</div></div>` : ""}</div>
      <div class="box"><h2>Épisodes (${r.params.element} ≥ ${num(r.params.threshold, 1)} ${r.unit}, au moins ${r.params.min_days} jours)</h2>
      <p class="note">Cliquer sur une ligne pour voir les observations de l'épisode.</p>
      ${table(["Station", "Nom", "Début", "Fin", "Jours", `Dépassement moyen (${r.unit})`, `Max (${r.unit})`], rows)}</div>`;
    out.querySelectorAll("tr[data-src]").forEach((tr) => tr.addEventListener("click", () => goTrace(JSON.parse(tr.dataset.src))));
  });
});

// ---------- F3 : anomalies ----------
$("#f3-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const d = formData(e.target), out = $("#f3-out"), t0 = performance.now();
  runQuery(e.target, out, async () => {
    const r = await api("/api/anomalies", d);
    const [y0, y1] = r.params.years;
    const rows = r.months.slice(0, 40).map((m) => `<tr><td class="num">${m.rank}</td><td>${m.zone}</td><td>${m.year}-${String(m.month).padStart(2, "0")}</td>
      <td class="num ${m.anomaly >= 0 ? "pos" : "neg"}">${m.anomaly > 0 ? "+" : ""}${num(m.anomaly)}</td><td class="num">${m.cells}</td><td class="num">${m.stations}</td>
      <td>${sourcesButton(m.sources)}</td></tr>`);
    out.innerHTML = `<div class="box"><h2>Écart à la normale 1991–2020 (${r.params.element}, ${r.unit})</h2>${f3Chart(r.months, y0, y1, r.unit)}
        <p class="note">${r.months.length} mois classés · ${elapsed(t0)} · survoler une barre pour le détail.</p></div>
      <div class="box"><h2>Mois les plus anormaux</h2>${table(["Rang", "Zone", "Mois", `Anomalie (${r.unit})`, "Mailles", "Stations", ""], rows)}
      ${r.months.length > 40 ? `<p class="note">40 premiers sur ${r.months.length}.</p>` : ""}</div>`;
    wireSources(out);
  });
});

// ---------- F4 : événements régionaux ----------
let f4Last = null;
function f4Show(item, label) {
  const ev = item.evidence || [];
  const hit = new Set(ev.map((x) => x.station));
  const zones = new Set(f4Last.params.zones || ["GM", "SP"]);
  drawMap($("#f4-map"), [...STATIONS.values()].filter((s) => zones.has(s.zone)).map((s) => hit.has(s.id)
    ? { ...s, color: "var(--hit)", stroke: "var(--warm)", r: 3.6, title: stationTitle(s.id) }
    : { ...s, color: "var(--muted)", opacity: 0.25, r: 1.6 }));
  $("#f4-map-note").textContent = `${label} : ${hit.size} stations au-dessus de leur seuil.`;
  const rows = ev.map((x) => `<tr><td>${x.date}</td><td>${esc(x.station)}</td><td>${esc(STATIONS.get(x.station)?.name ?? "")}</td>
    <td class="num">${num(x.value, 1)}</td><td class="num">${num(x.threshold, 1)}</td><td>${x.cell.join(", ")}</td>
    <td>${sourcesButton({ station: x.station, element: f4Last.params.element, start: x.date, end: x.date })}</td></tr>`);
  const box = $("#f4-evidence");
  box.innerHTML = `<h2>Preuves : ${esc(label)}</h2>${table(["Date", "Station", "Nom", `Valeur (${f4Last.unit})`, "Seuil", "Maille", ""], rows)}`;
  wireSources(box);
}

$("#f4-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const d = formData(e.target), out = $("#f4-out"), t0 = performance.now();
  runQuery(e.target, out, async () => {
    const r = (f4Last = await api("/api/events", d));
    const rows = r.events.map((x, i) => `<tr class="click" data-i="${i}"><td>${x.start}</td><td>${x.end}</td><td class="num">${x.days}</td>
      <td class="num">${num(x.severity)}</td><td>${x.peak_date}</td><td class="num">${num(x.peak_share * 100, 0)} %</td>
      <td class="num">${x.peak_cells_hit}</td><td class="num">${x.stations_hit}</td></tr>`);
    const iso = r.isolated.top.map((x, i) => `<tr class="click" data-iso="${i}"><td>${x.date}</td><td class="num">${x.cells_reporting}</td>
      <td class="num">${x.stations_hit}</td><td class="num">${num(x.excess, 1)}</td>
      <td>${(x.evidence || []).map((v) => esc(`${v.station} ${STATIONS.get(v.station)?.name ?? ""}`)).join(", ")}</td></tr>`);
    out.innerHTML = `<div class="cards"><div class="card"><h3>Événements régionaux</h3><div class="big">${r.count}</div><div class="small">${elapsed(t0)}</div></div>
      <div class="card"><h3>Jours d'extrême isolé</h3><div class="big">${r.isolated.days}</div><div class="small">une seule maille touchée</div></div></div>
      <div class="box"><h2>Événements, du plus sévère au moins sévère</h2><p class="note">Sévérité = somme des parts de mailles touchées sur les jours de l'événement. Cliquer pour voir les stations.</p>
      ${table(["Début", "Fin", "Jours", "Sévérité", "Pic", "Part au pic", "Mailles au pic", "Stations"], rows)}</div>
      <div class="box" id="f4-evidence"><p class="empty">Choisir un événement ou un extrême isolé.</p></div>
      <div class="box"><h2>Extrêmes isolés les plus marqués</h2>${table(["Date", "Mailles qui rapportent", "Stations", `Dépassement (${r.unit})`, "Stations touchées"], iso)}</div>`;
    out.querySelectorAll("tr[data-i]").forEach((tr) => tr.addEventListener("click", () => {
      out.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
      tr.classList.add("sel");
      const x = r.events[+tr.dataset.i];
      f4Show(x, `événement du ${x.start} au ${x.end}`);
    }));
    out.querySelectorAll("tr[data-iso]").forEach((tr) => tr.addEventListener("click", () => {
      out.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
      tr.classList.add("sel");
      const x = r.isolated.top[+tr.dataset.iso];
      f4Show(x, `extrême isolé du ${x.date}`);
    }));
    if (r.events.length) out.querySelector("tr[data-i]").click();
  });
});

// ---------- Traçabilité ----------
$("#trace-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const d = formData(e.target), out = $("#trace-out"), t0 = performance.now();
  runQuery(e.target, out, async () => {
    const r = await api("/api/trace", { ...d, flagged_only: d.flagged_only ? "true" : "" });
    const rows = r.records.map((o) => `<tr><td>${esc(o.station)}</td><td>${o.date}</td><td>${o.element}</td>
      <td class="num">${o.value}</td><td class="num">${num(o.value / 10, 1)} ${UNIT[o.element] ?? ""}</td>
      <td class="${o.mflag ? "flag" : ""}">${o.mflag ?? ""}</td><td class="${o.qflag ? "flag" : ""}">${o.qflag ?? ""}</td><td>${o.sflag ?? ""}</td>
      <td>${o.obs_time ?? ""}</td><td class="num">${o.batch_id}</td></tr>`);
    out.innerHTML = `<div class="box"><h2>${r.count} observation${r.count > 1 ? "s" : ""} source${r.count > 1 ? "s" : ""}</h2>
      <p class="note">Valeur brute NOAA en dixièmes, convertie à côté. Lot = import qui a écrit la ligne (table batches : fichier, URL, SHA-256). ${elapsed(t0)}
      ${r.truncated ? ` · <span class="flag">affichage limité aux 5 000 premières lignes</span>` : ""}</p>
      ${table(["Station", "Date", "Élément", "Brut", "Valeur", "mflag", "qflag", "sflag", "Heure", "Lot"], rows)}</div>`;
  });
});

// ---------- Démarrage ----------
(async () => {
  try {
    const info = await api("/api/info");
    $("#db").textContent = info.citus ? `Citus ${info.citus.replace("Citus ", "")} · ${info.workers.length} workers` : `${info.postgres.split(" (")[0]} local`;
    const r = await api("/api/stations");
    r.stations.forEach((s) => STATIONS.set(s.id, s));
    f1Search({});
    for (const id of ["f2-map", "f4-map"]) drawMap($(`#${id}`), [...STATIONS.values()].map((s) => ({ ...s, color: zoneColor(s.zone), opacity: 0.35, r: 1.6 })));
  } catch (e) {
    $("#db").textContent = "base indisponible";
    showError(e.message);
  }
})();
