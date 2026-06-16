"use strict";

const els = {
  picker: document.getElementById("buildPicker"),
  meta: document.getElementById("buildMeta"),
  filter: document.getElementById("filter"),
  slots: document.getElementById("slots"),
  status: document.getElementById("status"),
  source: document.getElementById("sourceLink"),
};

const LAST_BUILD_KEY = "d4gear:lastBuild";
let currentBuild = null;

// ---- URL hash helpers (#build=<id>&slot=<name>) ----
function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  return { build: h.get("build"), slot: h.get("slot") };
}
function writeHash(buildId, slotName) {
  const p = new URLSearchParams();
  if (buildId) p.set("build", buildId);
  if (slotName) p.set("slot", slotName);
  const next = "#" + p.toString();
  if (next !== location.hash) history.replaceState(null, "", next);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---- Data loading ----
async function loadJson(url) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${res.status} loading ${url}`);
  return res.json();
}

async function init() {
  let index;
  try {
    index = await loadJson("builds/index.json");
  } catch (e) {
    els.status.textContent = "Could not load build list. " + e.message;
    return;
  }

  els.picker.innerHTML = "";
  for (const b of index) {
    const opt = document.createElement("option");
    opt.value = b.id;
    opt.textContent = b.name;
    els.picker.appendChild(opt);
  }

  const hash = readHash();
  const wanted = hash.build || localStorage.getItem(LAST_BUILD_KEY) || index[0]?.id;
  if (wanted && index.some((b) => b.id === wanted)) els.picker.value = wanted;

  els.picker.addEventListener("change", () => selectBuild(els.picker.value));
  els.filter.addEventListener("input", applyFilter);
  window.addEventListener("hashchange", () => {
    const h = readHash();
    if (h.build && h.build !== currentBuild?.id) {
      els.picker.value = h.build;
      selectBuild(h.build, h.slot);
    }
  });

  await selectBuild(els.picker.value, hash.slot);
}

async function selectBuild(id, openSlot) {
  if (!id) return;
  els.status.textContent = "Loading…";
  els.slots.innerHTML = "";
  try {
    currentBuild = await loadJson(`builds/${id}.json`);
  } catch (e) {
    els.status.textContent = "Could not load build. " + e.message;
    return;
  }
  localStorage.setItem(LAST_BUILD_KEY, id);
  writeHash(id, null);
  renderBuild(currentBuild, openSlot);
  els.status.textContent = "";
}

function renderBuild(build, openSlot) {
  const updated = build.updated ? ` · updated ${escapeHtml(build.updated)}` : "";
  const patch = build.patch ? ` · patch ${escapeHtml(build.patch)}` : "";
  els.meta.innerHTML = `<span class="cls">${escapeHtml(build.class || "")}</span>${patch}${updated}`;

  if (build.source) {
    els.source.href = build.source;
    els.source.classList.remove("hidden");
  } else {
    els.source.classList.add("hidden");
  }

  els.slots.innerHTML = "";
  for (const slot of build.slots || []) {
    els.slots.appendChild(renderSlot(slot, openSlot));
  }
  applyFilter();
}

function renderSlot(slot, openSlot) {
  const det = document.createElement("details");
  det.className = "slot type-" + (slot.type || "rare");
  det.dataset.name = (slot.slot || "").toLowerCase();
  det.dataset.search = [slot.slot, slot.item, slot.aspect, ...(slot.affixes || [])]
    .join(" ").toLowerCase();
  if (openSlot && slot.slot === openSlot) det.open = true;

  det.addEventListener("toggle", () => {
    if (det.open) writeHash(currentBuild.id, slot.slot);
  });

  // Summary line: item or aspect name
  let itemHtml;
  if (slot.type === "legendary" && slot.aspect) {
    itemHtml = `<span class="aspect-name">${escapeHtml(slot.aspect)}</span>`;
  } else if (slot.item) {
    itemHtml = `<span class="item-name">${escapeHtml(slot.item)}</span>`;
  } else {
    itemHtml = `<span class="empty">Rare — see affixes</span>`;
  }
  const warnDot = slot.verify ? `<span class="warn-dot" title="Needs verification"></span>` : "";

  const summary = document.createElement("summary");
  summary.innerHTML =
    `<span class="slot-name">${escapeHtml(slot.slot)}</span>` +
    `<span class="slot-item">${itemHtml}</span>` +
    warnDot +
    `<span class="chev">›</span>`;
  det.appendChild(summary);

  const detail = document.createElement("div");
  detail.className = "detail";
  detail.innerHTML = renderDetail(slot);
  det.appendChild(detail);
  return det;
}

function listField(title, items, extraClass = "") {
  if (!items || !items.length) return "";
  const tags = items.map((t) => `<span class="tag ${extraClass}">${escapeHtml(t)}</span>`).join("");
  return `<div class="field"><h3>${escapeHtml(title)}</h3><div class="taglist">${tags}</div></div>`;
}

function renderDetail(slot) {
  let html = "";

  if (slot.aspect && slot.type === "legendary") {
    html += `<div class="field aspect"><h3>Aspect</h3><div class="taglist"><span class="tag">${escapeHtml(slot.aspect)}</span></div></div>`;
  } else if (slot.item) {
    html += `<div class="field"><h3>Item</h3><div class="taglist"><span class="tag">${escapeHtml(slot.item)}</span></div></div>`;
  }

  // Affix priority (ordered)
  if (slot.affixes && slot.affixes.length) {
    const lis = slot.affixes.map((a) => `<li>${escapeHtml(a)}</li>`).join("");
    html += `<div class="field"><h3>Affix priority</h3><ol class="affixes">${lis}</ol></div>`;
  } else {
    html += `<div class="field"><h3>Affix priority</h3><p class="empty">Not filled in yet — add from the planner.</p></div>`;
  }

  html += listField("Tempering", slot.tempering);
  html += listField("Masterwork", slot.masterwork);
  if (slot.gem) html += listField("Gem", [slot.gem], "gem-tag");

  if (slot.verify) {
    html += `<p class="verify-banner">⚠ Verify this slot against the maxroll guide.</p>`;
  }
  return html;
}

function applyFilter() {
  const q = els.filter.value.trim().toLowerCase();
  let visible = 0;
  for (const det of els.slots.children) {
    const match = !q || (det.dataset.search || "").includes(q);
    det.classList.toggle("hidden", !match);
    if (match) visible++;
  }
  els.status.textContent = visible === 0 ? "No slots match." : "";
}

init();

// ---- PWA service worker ----
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  });
}
