// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Michael Schertz
//
// Thin client over the JSON API. No framework, no build step.
//   POST /api/validate  -> render the repair run
//   POST /api/report    -> file download in the chosen format

"use strict";

const $ = (id) => document.getElementById(id);

// Broken samples, embedded by the server from x12_tidy_web/samples.py.
let SAMPLES = [];
try {
  SAMPLES = JSON.parse($("samples-data").textContent);
} catch {
  /* no samples embedded — the button just won't do anything */
}
let lastSampleSlug = null;

// { feedbackEmail, x12TidyRelease } from the server.
let CONFIG = {};
try {
  CONFIG = JSON.parse($("app-config").textContent);
} catch {
  /* no config — feature links stay hidden */
}

const form = $("edi-form");
const ediInput = $("edi");
const maxIterInput = $("max-iterations");
const formError = $("form-error");
const sampleNote = $("sample-note");
const results = $("results");
const verdictEl = $("verdict");
const feedbackPrompt = $("feedback-prompt");
const reportLink = $("report-link");
const correctedEl = $("corrected");
const correctedTitle = $("corrected-title");
const correctedWarning = $("corrected-warning");
const isaPadNote = $("isa-pad-note");
const explodedWrap = $("exploded-wrap");
const explodedEl = $("exploded");
const factsBody = $("facts").querySelector("tbody");
const factsEmpty = $("facts-empty");
const passesEl = $("passes");
const copyBtn = $("copy-btn");
const useBtn = $("use-btn");
const downloadBtn = $("download-btn");
const formatSelect = $("format-select");
const validateBtn = $("validate-btn");

let lastRun = null;

// --------------------------------------------------------------------------- //
// helpers
// --------------------------------------------------------------------------- //
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function showError(msg) {
  formError.textContent = msg;
  formError.hidden = false;
}
function clearError() {
  formError.hidden = true;
  formError.textContent = "";
}

const SEVERITIES = ["fatal", "error", "warning"];

function countsSummary(counts) {
  const parts = SEVERITIES.filter((s) => counts[s] > 0).map((s) => `${counts[s]} ${s}`);
  return parts.length ? parts.join(", ") : "no findings";
}

// --------------------------------------------------------------------------- //
// rendering
// --------------------------------------------------------------------------- //
function renderVerdict(run) {
  // The verdict — its wording, its style, and the rule that any residual fatal
  // finding means "cannot be repaired" — is computed once, server-side, in the
  // engine (RepairRun.verdict). This just paints it.
  verdictEl.className = "verdict";
  verdictEl.classList.add(run.verdict.css_class);
  // The headline already says *why* the run ended the way it did; this sub-line
  // is just the compact facts. (The full "why it stopped" wording is in the
  // downloaded report, which has room for it.)
  verdictEl.replaceChildren(
    document.createTextNode(run.verdict.headline),
    el("small", {
      text:
        `${run.iteration_count} pass${run.iteration_count === 1 ? "" : "es"} · ` +
        `output ${run.changed ? "differs from" : "matches"} the input · ` +
        `final findings: ${countsSummary(run.residual_severity_counts)}`,
    })
  );
}

// Each row: label, a getter for the value, and a plain-language note on what the
// value is and where x12-tidy got it — either an ISA element it reads straight
// out of the corrected header, or a tally it counts while walking the payload.
const FACT_ROWS = [
  [
    "Sender",
    (f) => `${f.sender_qualifier} / ${f.sender_id}`.replace(/^ \/ | \/ $/g, ""),
    "The interchange sender — from ISA05 (ID qualifier) and ISA06 (sender ID).",
  ],
  [
    "Receiver",
    (f) => `${f.receiver_qualifier} / ${f.receiver_id}`.replace(/^ \/ | \/ $/g, ""),
    "The interchange receiver — from ISA07 (ID qualifier) and ISA08 (receiver ID).",
  ],
  [
    "Usage indicator",
    (f) => f.usage_indicator,
    "ISA15 — P = production, T = test, I = information.",
  ],
  [
    "Interchange version",
    (f) => f.interchange_version,
    "ISA12 — the interchange control version number (e.g. 00401).",
  ],
  [
    "Date / time",
    (f) => `${f.interchange_date} ${f.interchange_time}`.trim(),
    "ISA09 and ISA10 — when the interchange was prepared (YYMMDD, HHMM).",
  ],
  [
    "Functional groups",
    (f) => f.functional_group_count,
    "GS segments found while walking the payload. IEA01 must equal this — a mismatch is a fatal finding.",
  ],
  [
    "Transaction sets",
    (f) => f.transaction_set_count,
    "ST segments found across all groups. Each group's GE01 must equal its own count.",
  ],
  [
    "Segments",
    (f) => f.segment_count,
    "Total segments in the cleansed payload. Each transaction set's SE01 must equal its own segment count.",
  ],
];

function renderFacts(facts) {
  factsBody.replaceChildren();
  if (!facts) {
    factsEmpty.hidden = false;
    return;
  }
  factsEmpty.hidden = true;
  for (const [label, getter, source] of FACT_ROWS) {
    const value = getter(facts);
    factsBody.append(
      el(
        "tr",
        {},
        el("th", { text: label }),
        el(
          "td",
          {},
          el("span", { text: value === "" || value == null ? "—" : String(value) }),
          el("span", { class: "fact-src", text: source })
        )
      )
    );
  }
}

function pill(text, kind) {
  return el("span", { class: `pill ${kind}`, text });
}

// --------------------------------------------------------------------------- //
// "read it segment by segment" — a display-only re-layout of the corrected
// bytes. Segment boundaries come from x12-tidy's output (the ISA line fixes the
// segment terminator at byte 105); indentation and the per-transaction-set
// numbering are just formatting.
// --------------------------------------------------------------------------- //
const _INDENT = { 0: "", 1: "  ", 2: "     " }; // depth -> leading space

function segTag(segment) {
  const m = segment.match(/^\s*([A-Za-z0-9]+)/);
  return m ? m[1].toUpperCase() : "";
}

function explodeSegments(text) {
  if (!text || text.length < 106 || segTag(text) !== "ISA") return null;
  const term = text[105];
  const raw = text
    .split(term)
    .map((s) => s.replace(/[\r\n]+/g, "").trim())
    .filter(Boolean);

  // show a visible terminator (~, |, …); a whitespace one is already implied by
  // the line break in this view.
  const shownTerm = /\S/.test(term) ? term : "";

  const lines = [];
  let depth = 0;
  let inSet = false;
  let n = 0;
  for (const seg of raw) {
    const tag = segTag(seg);
    let num = null;
    if (tag === "ISA" || tag === "IEA") {
      depth = 0;
      inSet = false;
    } else if (tag === "GS") {
      depth = 1;
    } else if (tag === "GE") {
      depth = 1;
      inSet = false;
    } else if (tag === "ST") {
      depth = 2;
      inSet = true;
      n = 1;
      num = n;
    } else if (tag === "SE") {
      depth = 2;
      n += 1;
      num = n;
      inSet = false;
    } else if (inSet) {
      depth = 2;
      n += 1;
      num = n;
    }
    const label = num == null ? "    " : String(num).padStart(3) + " ";
    lines.push(_INDENT[depth] + label + seg + shownTerm);
  }
  return lines.join("\n");
}

function renderExploded(run) {
  const text = explodeSegments(run.final_text || "");
  explodedWrap.hidden = text === null;
  if (text !== null) explodedEl.textContent = text;
}

function renderFindingsTable(diagnostics) {
  const table = el("table", { class: "findings" });
  table.append(
    el(
      "thead",
      {},
      el(
        "tr",
        {},
        el("th", { text: "Severity" }),
        el("th", { text: "Code" }),
        el("th", { text: "Byte" }),
        el("th", { text: "Finding" })
      )
    )
  );
  const tbody = el("tbody");
  for (const d of diagnostics) {
    tbody.append(
      el(
        "tr",
        {},
        el("td", {}, el("span", { class: `sev ${d.severity}`, text: d.severity.toUpperCase() })),
        el("td", {}, el("code", { text: d.code })),
        el("td", { text: d.offset == null ? "—" : String(d.offset) }),
        el(
          "td",
          {},
          el("strong", { text: d.title }),
          el("span", { class: "finding-msg", text: d.message }),
          el("p", { class: "finding-expl", text: d.explanation })
        )
      )
    );
  }
  table.append(tbody);
  return table;
}

function renderPass(iter, isLast) {
  const details = el("details", { class: "pass" });
  if (isLast || iter.diagnostics.length) details.open = true;

  const counts = iter.severity_counts;
  const active = new Set(); // severities being filtered to; empty === show all

  const summary = el("summary", {});
  summary.append(el("span", { class: "caret", "aria-hidden": "true" }));
  summary.append(el("span", { class: "pass-label", text: `Pass ${iter.index}` }));

  const body = el("div", { class: "pass-body" });
  const outBytes = iter.output_byte_length == null ? "—" : `${iter.output_byte_length} bytes`;
  body.append(
    el("p", { class: "hint", text: `${iter.input_byte_length} bytes in → ${outBytes} out.` })
  );

  const filterNote = el("p", { class: "hint" });
  filterNote.hidden = true;
  const showAllBtn = el("button", { type: "button", class: "linklike", text: "show all" });
  showAllBtn.addEventListener("click", () => {
    active.clear();
    syncPills();
    redraw();
  });
  const tableSlot = el("div");
  body.append(filterNote, tableSlot);

  // The severity chips ARE the filter. Clicking one narrows this pass's findings
  // to that severity; click more to combine, click again to drop. Empty = all.
  const sevButtons = [];
  for (const s of SEVERITIES) {
    if (counts[s] <= 0) continue;
    const b = el(
      "button",
      {
        type: "button",
        class: `pill ${s}`,
        "aria-pressed": "false",
        title: `Show only ${s} findings — click more than one to combine`,
      },
      `${counts[s]} ${s}`
    );
    b.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation(); // don't toggle the <details>
      if (active.has(s)) active.delete(s);
      else active.add(s);
      if (!details.open) details.open = true;
      syncPills();
      redraw();
    });
    sevButtons.push([s, b]);
    summary.append(b);
  }

  if (iter.was_clean) summary.append(el("span", { class: "pass-status ok", text: "clean" }));
  summary.append(
    el("span", {
      class: "pass-status",
      text: iter.changed ? "changed the interchange" : "no change",
    })
  );
  details.append(summary, body);

  function syncPills() {
    for (const [s, b] of sevButtons) {
      const on = active.has(s);
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.classList.toggle("dim", active.size > 0 && !on);
    }
  }

  function redraw() {
    if (!iter.diagnostics.length) {
      filterNote.hidden = true;
      tableSlot.replaceChildren(
        el("p", {
          class: "hint",
          text: iter.was_clean
            ? "No findings — the corrected interchange is conformant."
            : "No findings on this pass.",
        })
      );
      return;
    }
    const shown = active.size
      ? iter.diagnostics.filter((d) => active.has(d.severity))
      : iter.diagnostics;
    if (active.size) {
      filterNote.replaceChildren(
        document.createTextNode(
          `Showing ${shown.length} of ${iter.diagnostics.length} — ${[...active].join(" + ")}. `
        ),
        showAllBtn
      );
      filterNote.hidden = false;
    } else {
      filterNote.hidden = true;
    }
    tableSlot.replaceChildren(renderFindingsTable(shown));
  }

  redraw();
  return details;
}

function verdictHeadline(run) {
  return run.verdict.state; // e.g. "clean", "unfixable", "residual-error"
}

function updateReportLink(run) {
  if (!CONFIG.feedbackEmail) return; // no address configured — leave it hidden
  const subject = `[x12-tidy-web] feedback: ${verdictHeadline(run)}`;
  const body =
    `x12-tidy ${CONFIG.x12TidyRelease || "?"}\n` +
    `verdict: ${verdictHeadline(run)} (stop reason: ${run.stop_reason})\n` +
    `final findings: ${countsSummary(run.residual_severity_counts)}\n\n` +
    "What did you expect, and what did you get? Paste the relevant part of your " +
    "interchange below — remove anything you can't share.\n";
  reportLink.href = `mailto:${CONFIG.feedbackEmail}?subject=${encodeURIComponent(
    subject
  )}&body=${encodeURIComponent(body)}`;
  feedbackPrompt.hidden = false;
}

function renderRun(run) {
  lastRun = run;
  renderVerdict(run);
  updateReportLink(run);

  correctedEl.value = run.final_text || "";
  const hasCorrected = Boolean(run.final_text);
  copyBtn.disabled = !hasCorrected;
  useBtn.disabled = !hasCorrected;
  downloadBtn.disabled = false;

  // Label the payload honestly (it is only a "corrected interchange" when the
  // run came out clean) and carry the caveat right here, not only in the
  // verdict box above. Both strings come from the engine's verdict.
  correctedTitle.textContent = run.verdict.output_label;
  const caveat = run.verdict.output_caveat;
  correctedWarning.hidden = !caveat;
  correctedWarning.textContent = caveat;
  correctedWarning.classList.toggle(
    "is-fatal",
    run.verdict.state === "unfixable" || run.verdict.state === "notconverged"
  );

  const touchedIsa = run.iterations.some((it) =>
    it.diagnostics.some((d) => d.code.startsWith("isa."))
  );
  isaPadNote.hidden = !(hasCorrected && touchedIsa);

  renderExploded(run);

  renderFacts(run.final_facts);

  passesEl.replaceChildren();
  run.iterations.forEach((iter, i) => {
    passesEl.append(renderPass(iter, i === run.iterations.length - 1));
  });

  results.hidden = false;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

// --------------------------------------------------------------------------- //
// actions
// --------------------------------------------------------------------------- //
async function validate(ev) {
  ev.preventDefault();
  clearError();
  const edi = ediInput.value;
  if (!edi.trim()) {
    showError("Paste an EDI interchange first.");
    return;
  }
  const payload = { edi, max_iterations: Number(maxIterInput.value) || 5 };

  validateBtn.disabled = true;
  form.classList.add("busy");
  try {
    const resp = await fetch("/api/validate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      showError(formatApiError(detail, resp.status));
      return;
    }
    renderRun(await resp.json());
  } catch (err) {
    showError(`Request failed: ${err.message}`);
  } finally {
    validateBtn.disabled = false;
    form.classList.remove("busy");
  }
}

function formatApiError(detail, status) {
  if (Array.isArray(detail.detail)) {
    return detail.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  }
  if (typeof detail.detail === "string") return detail.detail;
  return `Server returned ${status}.`;
}

async function download() {
  if (!lastRun) return;
  const payload = {
    edi: ediInput.value,
    max_iterations: Number(maxIterInput.value) || 5,
    format: formatSelect.value,
  };
  downloadBtn.disabled = true;
  try {
    const resp = await fetch("/api/report", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      showError(formatApiError(detail, resp.status));
      return;
    }
    const blob = await resp.blob();
    const disposition = resp.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : `x12-tidy-report.${formatSelect.value}`;
    triggerDownload(blob, filename);
  } catch (err) {
    showError(`Download failed: ${err.message}`);
  } finally {
    downloadBtn.disabled = false;
  }
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function copyCorrected() {
  try {
    await navigator.clipboard.writeText(correctedEl.value);
    copyBtn.textContent = "Copied";
    setTimeout(() => (copyBtn.textContent = "Copy"), 1500);
  } catch {
    correctedEl.select();
    document.execCommand("copy");
  }
}

function useCorrected() {
  if (!correctedEl.value) return;
  ediInput.value = correctedEl.value;
  saveDraft();
  ediInput.scrollIntoView({ behavior: "smooth", block: "center" });
}

function loadFile(ev) {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    ediInput.value = reader.result;
    saveDraft();
    clearError();
  };
  reader.onerror = () => showError("Could not read that file.");
  reader.readAsText(file, "latin1");
}

// --------------------------------------------------------------------------- //
// draft persistence
//
// Keep what's in the form for the life of this browser tab, so leaving for the
// /codes page and coming back doesn't wipe it. sessionStorage (not local) is
// per-tab and cleared on close, and never leaves the browser.
// --------------------------------------------------------------------------- //
const DRAFT_KEY = "x12-tidy-web:draft";

function saveDraft() {
  try {
    sessionStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ edi: ediInput.value, maxIter: maxIterInput.value })
    );
  } catch {
    /* private mode / quota / disabled — the form just won't be remembered */
  }
}

function restoreDraft() {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return;
    const d = JSON.parse(raw);
    if (typeof d.edi === "string" && d.edi && !ediInput.value) ediInput.value = d.edi;
    if (d.maxIter) maxIterInput.value = d.maxIter;
  } catch {
    /* ignore malformed / unavailable storage */
  }
}

// --------------------------------------------------------------------------- //
// wiring
// --------------------------------------------------------------------------- //
form.addEventListener("submit", validate);

function loadSample(sample) {
  lastSampleSlug = sample.slug;
  ediInput.value = sample.edi;
  sampleNote.textContent = `${sample.title} — ${sample.blurb}`;
  sampleNote.hidden = false;
  saveDraft();
  clearError();
}

$("sample-select").addEventListener("change", (ev) => {
  const v = ev.target.value;
  ev.target.value = ""; // reset so the same pick can be chosen again
  if (!v || !SAMPLES.length) return;
  if (v === "__random__") {
    const pool = SAMPLES.length > 1 ? SAMPLES.filter((s) => s.slug !== lastSampleSlug) : SAMPLES;
    loadSample(pool[Math.floor(Math.random() * pool.length)]);
  } else {
    const sample = SAMPLES.find((s) => s.slug === v);
    if (sample) loadSample(sample);
  }
});
ediInput.addEventListener("input", () => {
  if (!sampleNote.hidden) sampleNote.hidden = true;
  saveDraft();
});
maxIterInput.addEventListener("change", saveDraft);
$("file").addEventListener("change", loadFile);
copyBtn.addEventListener("click", copyCorrected);
useBtn.addEventListener("click", useCorrected);
downloadBtn.addEventListener("click", download);

restoreDraft();
