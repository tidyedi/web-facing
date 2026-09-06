// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Michael Schertz
//
// Thin client over the JSON API. No framework, no build step.
//   POST /api/validate  -> render the repair run
//   POST /api/report    -> file download in the chosen format

"use strict";

const SAMPLE_EDI =
  "Subject: FW: your order\r\n\r\n" +
  "ISA*00*   *00*   *ZZ*ACME*ZZ*WIDGETCO*240101*1200*U*00401*000000001*0*P*:~" +
  "GS*PO*ACME*WIDGET*20240101*1200*1*X*004010~" +
  "ST*850*0001~BEG*00*NE*PO123**20240101~SE*3*0001~" +
  "GE*1*1~IEA*2*000000001~";

const $ = (id) => document.getElementById(id);

const form = $("edi-form");
const ediInput = $("edi");
const maxIterInput = $("max-iterations");
const formError = $("form-error");
const results = $("results");
const verdictEl = $("verdict");
const correctedEl = $("corrected");
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
  verdictEl.className = "verdict";
  let headline;
  if (!run.recovered) {
    verdictEl.classList.add("fail");
    headline = "Unrecoverable — no ISA line could be located.";
  } else if (run.clean) {
    verdictEl.classList.add("ok");
    headline = "Clean — the interchange is conformant.";
  } else if (run.converged) {
    verdictEl.classList.add("residual");
    headline = "Repaired, with findings x12-tidy cannot fix automatically.";
  } else {
    verdictEl.classList.add("fail");
    headline = "Did not converge within the pass limit — treat the output with care.";
  }
  verdictEl.replaceChildren(
    document.createTextNode(headline),
    el("small", {
      text:
        `${run.iteration_count} pass${run.iteration_count === 1 ? "" : "es"} · ` +
        `stop reason: ${run.stop_reason} · ` +
        `corrected text ${run.changed ? "differs from" : "matches"} the input · ` +
        `final findings: ${countsSummary(run.residual_severity_counts)}`,
    })
  );
}

const FACT_ROWS = [
  ["Sender", (f) => `${f.sender_qualifier} / ${f.sender_id}`.replace(/^ \/ | \/ $/g, "")],
  ["Receiver", (f) => `${f.receiver_qualifier} / ${f.receiver_id}`.replace(/^ \/ | \/ $/g, "")],
  ["Usage indicator", (f) => f.usage_indicator],
  ["Interchange version", (f) => f.interchange_version],
  ["Date / time", (f) => `${f.interchange_date} ${f.interchange_time}`.trim()],
  ["Functional groups", (f) => f.functional_group_count],
  ["Transaction sets", (f) => f.transaction_set_count],
  ["Segments", (f) => f.segment_count],
];

function renderFacts(facts) {
  factsBody.replaceChildren();
  if (!facts) {
    factsEmpty.hidden = false;
    return;
  }
  factsEmpty.hidden = true;
  for (const [label, getter] of FACT_ROWS) {
    const value = getter(facts);
    factsBody.append(
      el("tr", {}, el("th", { text: label }), el("td", { text: value === "" || value == null ? "—" : String(value) }))
    );
  }
}

function pill(text, kind) {
  return el("span", { class: `pill ${kind}`, text });
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

  const summary = el("summary", {}, `Pass ${iter.index}`);
  const counts = iter.severity_counts;
  if (iter.was_clean) summary.append(pill("clean", "clean"));
  for (const s of SEVERITIES) {
    if (counts[s] > 0) summary.append(pill(`${counts[s]} ${s}`, s));
  }
  summary.append(pill(iter.changed ? "changed the interchange" : "no change", "neutral"));
  details.append(summary);

  const body = el("div", { class: "pass-body" });
  const outBytes = iter.output_byte_length == null ? "—" : `${iter.output_byte_length} bytes`;
  body.append(
    el("p", { class: "hint", text: `${iter.input_byte_length} bytes in → ${outBytes} out.` })
  );
  if (iter.diagnostics.length) {
    body.append(renderFindingsTable(iter.diagnostics));
  } else {
    body.append(el("p", { class: "hint", text: "No findings on this pass." }));
  }
  details.append(body);
  return details;
}

function renderRun(run) {
  lastRun = run;
  renderVerdict(run);

  correctedEl.value = run.final_text || "";
  const hasCorrected = Boolean(run.final_text);
  copyBtn.disabled = !hasCorrected;
  useBtn.disabled = !hasCorrected;
  downloadBtn.disabled = false;

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
  ediInput.scrollIntoView({ behavior: "smooth", block: "center" });
}

function loadFile(ev) {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    ediInput.value = reader.result;
    clearError();
  };
  reader.onerror = () => showError("Could not read that file.");
  reader.readAsText(file, "latin1");
}

// --------------------------------------------------------------------------- //
// wiring
// --------------------------------------------------------------------------- //
form.addEventListener("submit", validate);
$("sample-btn").addEventListener("click", () => {
  ediInput.value = SAMPLE_EDI;
  clearError();
});
$("file").addEventListener("change", loadFile);
copyBtn.addEventListener("click", copyCorrected);
useBtn.addEventListener("click", useCorrected);
downloadBtn.addEventListener("click", download);
