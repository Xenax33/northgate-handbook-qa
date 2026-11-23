// The page: ask a question, show the answer and its sources, open a source with the quote highlighted.
"use strict";

const $ = (id) => document.getElementById(id);
const STATUS_LABEL = { answer: "Answer", refuse: "Not in the handbook", clarify: "Needs more detail" };
const STATE_LABEL = { superseded: "Superseded", deprecated: "Deprecated", "not yet in force": "Not yet in force" };

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Markdown emphasis is dropped for display, so "**16 days**" reads as "16 days" (and quotes match it).
function plain(text) {
  return String(text ?? "").replace(/\*\*|`/g, "");
}

// A quote as shown in the source list: Markdown table pipes and "| --- |" rows turned into readable text.
function readableQuote(quote) {
  return plain(quote).replace(/\|\s*-{3,}[\s|-]*/g, "| ").replace(/(\s*\|\s*)+/g, " · ").replace(/^[\s·]+|[\s·]+$/g, "");
}

function squash(text) {
  return plain(text).replace(/[|]/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
}

// Passage text as HTML: Markdown table lines become a real table; the quote is highlighted, in text with
// <mark> and in a table by marking each row whose cells appear in the quote.
function renderPassage(text, quote) {
  const lines = plain(text).split("\n");
  const quoteText = quote ? squash(quote) : "";
  const textParts = quote ? plain(quote).split(/\s*(?:\.\.\.|…|\|)\s*/).filter((p) => p.trim().split(/\s+/).length >= 3) : [];
  let html = "", table = [];
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter((row) => !/^\|?[\s|:-]+\|?$/.test(row));  // drop the "| --- |" separator
    html += "<table>" + rows.map((row, i) => {
      const cells = row.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const hit = quoteText && cells.join(" ").trim() && quoteText.includes(squash(cells.join(" ")));
      const tag = i === 0 ? "th" : "td";
      return `<tr${hit ? ' class="hit"' : ""}>${cells.map((c) => `<${tag}>${escapeHtml(c)}</${tag}>`).join("")}</tr>`;
    }).join("") + "</table>";
    table = [];
  };
  for (const line of lines) {
    if (line.trim().startsWith("|")) { table.push(line.trim()); continue; }
    flushTable();
    html += `<p>${textParts.length ? highlight(line, textParts.join(" ... ")).html : escapeHtml(line)}</p>`;
  }
  flushTable();
  return html;
}

// Wrap every part of the quote (parts are separated by "...") in <mark>. Whitespace and case are ignored.
function highlight(text, quote) {
  const parts = plain(quote).split(/\s*(?:\.\.\.|…)\s*/).map((p) => p.trim().replace(/[.\s]+$/, "")).filter(Boolean);
  const ranges = [];
  for (const part of parts) {
    const pattern = part.split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+");
    const match = new RegExp(pattern, "i").exec(text);
    if (match) ranges.push([match.index, match.index + match[0].length]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  let html = "", at = 0;
  for (const [start, end] of ranges) {
    if (start < at) continue;
    html += escapeHtml(text.slice(at, start)) + "<mark>" + escapeHtml(text.slice(start, end)) + "</mark>";
    at = end;
  }
  return { html: html + escapeHtml(text.slice(at)), found: ranges.length > 0 };
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail)  // FastAPI's field validation errors
      ? "Some of what was sent is missing or too long: " + body.detail.map((d) => (d.loc || []).slice(-1)[0]).join(", ") + "."
      : body.detail;
    throw new Error(detail || `The server answered ${response.status}.`);
  }
  return body;
}

// Header line and document list ---------------------------------------------------------------------

let health = null;

async function loadOverview() {
  try {
    health = await getJson("/api/health");
    $("meta").textContent = `${health.documents} documents · answers by ${health.model} · today ${health.today}`;
    $("no-key").hidden = health.api_key_set;
    $("upload-box").hidden = !health.uploads_enabled;
    $("token-row").hidden = !health.upload_token_required;
    $("upload-file").accept = health.upload_formats.map((f) => "." + f).join(",");
    $("upload-hint").textContent = `Upload a ${health.upload_formats.join(", ")} file of up to ${health.max_upload_mb} MB; ` +
      "questions can use it straight away. If it replaces a document, that one stops being used for answers.";
    if (!$("upload-date").value) $("upload-date").value = health.today;
    const docs = (await getJson("/api/documents")).sort((a, b) => a.title.localeCompare(b.title));
    $("doc-list").innerHTML = docs.map((d) => `<li><button type="button" class="link-button" data-doc="${escapeHtml(d.doc_id)}">${escapeHtml(d.title)}</button>
        <span class="meta">${escapeHtml(d.format)}</span>${STATE_LABEL[d.state] ? `<span class="badge state">${STATE_LABEL[d.state]}</span>` : ""}${
        d.source === "upload" ? `<span class="badge uploaded">Uploaded</span><button type="button" class="link-button remove" data-remove="${escapeHtml(d.doc_id)}">Remove</button>` : ""}</li>`)
      .join("");
    const choosable = docs.filter((d) => d.state !== "superseded" && d.state !== "deprecated");
    $("upload-replaces").innerHTML = `<option value="">Nothing (a new document)</option>` +
      choosable.map((d) => `<option value="${escapeHtml(d.doc_id)}">${escapeHtml(d.title)}</option>`).join("");
  } catch (error) {
    $("meta").textContent = `Couldn't load the handbook: ${error.message}`;
  }
}

// Uploading (D24-D26) ----------------------------------------------------------------------------------

function uploadHeaders() {
  const token = $("upload-token").value;
  return token ? { "X-Upload-Token": token } : {};
}

function showUploadError(message) {
  $("upload-error").textContent = message;
  $("upload-error").hidden = false;
  $("upload-done").hidden = true;
}

async function upload(event) {
  event.preventDefault();
  const file = $("upload-file").files[0];
  $("upload-error").hidden = true;
  if (!file) return showUploadError("Choose a file first.");
  if (file.size > health.max_upload_mb * 1_000_000) return showUploadError(`The file is larger than ${health.max_upload_mb} MB.`);
  if (!$("upload-title").value.trim()) return showUploadError("Give the document a title.");
  if (health.upload_token_required && !$("upload-token").value) return showUploadError("Enter the upload token.");
  const form = new FormData($("upload-form"));
  const button = $("upload-button");
  button.setAttribute("aria-busy", "true");
  button.textContent = "Adding…";
  try {
    const added = await getJson("/api/documents", { method: "POST", body: form, headers: uploadHeaders() });
    $("upload-done").textContent = `Added “${added.title}”` +
      (added.state === "not yet in force" ? ` (in force from ${added.effective_date})` : "") +
      (added.supersedes ? `; it replaces ${added.supersedes}` : "") + ". Ask a question about it now.";
    $("upload-done").hidden = false;
    $("upload-file").value = "";
    $("upload-title").value = "";
    await loadOverview();
  } catch (error) {
    showUploadError(error.message);
  } finally {
    button.removeAttribute("aria-busy");
    button.textContent = "Add document";
  }
}

async function removeUpload(docId) {
  if (!confirm(`Remove the uploaded document ${docId}? Questions will stop using it.`)) return;
  try {
    await getJson(`/api/documents/${encodeURIComponent(docId)}`, { method: "DELETE", headers: uploadHeaders() });
    await loadOverview();
  } catch (error) {
    alert(error.message);
  }
}

// Asking ---------------------------------------------------------------------------------------------

let lastAnswer = null;

async function ask(question) {
  const button = $("ask-button");
  const result = $("result");
  if (!question.trim()) {
    $("question-error").textContent = "Type a question first.";
    $("question-error").hidden = false;
    $("question").focus();
    return;
  }
  button.setAttribute("aria-busy", "true");
  button.textContent = "Asking…";
  result.hidden = false;
  result.innerHTML = `<p class="note">Searching the handbook and checking sources…</p>`;
  try {
    lastAnswer = await getJson("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    renderAnswer(lastAnswer);
  } catch (error) {
    result.innerHTML = `<span class="badge error">Couldn't answer</span><p class="answer-text">${escapeHtml(error.message)}</p>`;
  } finally {
    button.removeAttribute("aria-busy");
    button.textContent = "Ask";
  }
}

function renderAnswer(a) {
  const sources = a.citations.map((c, i) => {
    const where = c.title ? escapeHtml(c.title) + (c.heading ? ` › ${escapeHtml(c.heading)}` : "") : `Unknown passage ${escapeHtml(c.key)}`;
    const uploaded = c.source === "upload" ? `<span class="badge uploaded">Uploaded, not from the handbook</span>` : "";
    const state = STATE_LABEL[c.state] ? `<span class="badge state">${STATE_LABEL[c.state]}${c.state === "not yet in force" ? ` from ${escapeHtml(c.effective_date)}` : ""}</span>` : "";
    const check = c.verified
      ? `<span class="verified">✓ Quote found in the document</span>`
      : `<span class="unverified">✗ ${escapeHtml(c.problem || "Quote not verified")}</span>`;
    const open = c.doc_id ? `<button type="button" class="link-button" data-cite="${i}">Open source</button>` : "";
    return `<div class="source"><div class="source-title">${where}${state}${uploaded}</div>
      <blockquote>${escapeHtml(readableQuote(c.quote))}</blockquote>
      <div class="source-foot">${check}${open}</div></div>`;
  }).join("");
  $("result").innerHTML = `
    <span class="badge ${escapeHtml(a.status)}">${STATUS_LABEL[a.status] || "Answer"}</span>
    <p class="answer-text">${escapeHtml(a.answer)}</p>
    ${a.warnings.map((w) => `<div class="warning">${escapeHtml(w)}</div>`).join("")}
    ${a.searched_again_with ? `<p class="note">Your wording didn't match the handbook at first, so it was searched again for “${escapeHtml(a.searched_again_with)}”.</p>` : ""}
    ${sources ? `<div class="sources"><h3>Sources</h3>${sources}</div>` : ""}
    <p class="note">Answered for ${escapeHtml(a.today)} in ${escapeHtml(a.seconds)} s.</p>`;
}

// Source viewer --------------------------------------------------------------------------------------

async function openDocument(docId, passageId, quote) {
  const viewer = $("viewer");
  $("viewer-title").textContent = "Loading…";
  $("viewer-meta").textContent = "";
  $("viewer-body").innerHTML = "";
  viewer.showModal();
  try {
    const doc = await getJson(`/api/documents/${encodeURIComponent(docId)}`);
    $("viewer-title").textContent = doc.title;
    const state = STATE_LABEL[doc.state] ? ` · ${STATE_LABEL[doc.state]}${doc.superseded_by ? ` by ${doc.superseded_by}` : ""}` : " · Current";
    $("viewer-meta").innerHTML = `Effective ${escapeHtml(doc.effective_date)}${escapeHtml(state)} · ${escapeHtml(doc.owner)} · ` +
      `<a href="/api/documents/${encodeURIComponent(doc.doc_id)}/file">Download the original ${escapeHtml(doc.format.toUpperCase())}</a>`;
    let target = null;
    $("viewer-body").innerHTML = doc.passages.map((p) => {
      const cited = p.id === passageId;
      return `<section class="passage${cited ? " cited" : ""}" id="p-${escapeHtml(p.id)}">
        ${p.heading ? `<h4>${escapeHtml(p.heading)}</h4>` : ""}${renderPassage(p.text, cited ? quote : null)}</section>`;
    }).join("");
    if (passageId) target = document.getElementById(`p-${passageId}`);
    (target?.querySelector("mark, tr.hit") || target)?.scrollIntoView({ block: "center" });
  } catch (error) {
    $("viewer-title").textContent = "Couldn't open the document";
    $("viewer-body").innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

// Wiring ---------------------------------------------------------------------------------------------

$("ask-form").addEventListener("submit", (event) => {
  event.preventDefault();
  ask($("question").value);
});
$("question").addEventListener("input", () => { $("question-error").hidden = true; });
document.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
  $("question").value = chip.textContent;
  ask(chip.textContent);
}));
$("result").addEventListener("click", (event) => {
  const index = event.target.dataset?.cite;
  if (index === undefined || !lastAnswer) return;
  const c = lastAnswer.citations[Number(index)];
  openDocument(c.doc_id, c.passage_id, c.quote);
});
$("doc-list").addEventListener("click", (event) => {
  if (event.target.dataset?.doc) openDocument(event.target.dataset.doc, null, null);
  if (event.target.dataset?.remove) removeUpload(event.target.dataset.remove);
});
$("upload-form").addEventListener("submit", upload);
$("upload-file").addEventListener("change", () => {
  const file = $("upload-file").files[0];
  if (file && !$("upload-title").value) $("upload-title").value = file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
});
$("viewer-close").addEventListener("click", () => $("viewer").close());
$("viewer").addEventListener("click", (event) => { if (event.target === $("viewer")) $("viewer").close(); });

loadOverview();
