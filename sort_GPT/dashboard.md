```dataviewjs
/***** CONFIG *****/
const SCOPE = "";             // e.g., '"Chats_MD"' to restrict to a folder
const REQUIRE_SUMMARY = true; // set false to include files without frontmatter summary
/******************/

// --- styles (clamps, widths, inputs, chips) ---
const style = document.createElement('style');
style.textContent = `
.dvjs-dash {
  display: grid;
  grid-template-columns: 1fr 1fr 2fr;          /* first row: start | end | title */
  grid-template-areas:
    "start end title"
    "tag   summary content"
    "go go go";                   /* second row: tag | summary | content */
  gap: 8px;
  margin: 0 0 10px 0;
}

/* map each input to its grid area */
.dvjs-start   { grid-area: start; }
.dvjs-end     { grid-area: end; }
.dvjs-title   { grid-area: title; }
.dvjs-tag     { grid-area: tag; }
.dvjs-summary { grid-area: summary; }
.dvjs-content { grid-area: content; }
.dvjs-go { grid-area: go; }
.dvjs-input { padding: 6px 8px; border: 1px solid var(--background-modifier-border); border-radius: 6px; }


.dvjs-table thead th {
  position: sticky;
  top: 0;
  background: var(--background-primary);
  z-index: 1;
}

.dvjs-tags-preview {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.dvjs-chip { margin: 2px 6px 2px 0; }

.dvjs-dash .dvjs-btn {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--background-modifier-border);
  border-radius: 6px;
  background: #8A5CF4;
  color: #FFFFFF;
  cursor: pointer;
}
.dvjs-btn:hover { background: #A78AF9; }

.dvjs-table th, .dvjs-table td { padding: 4px 6px; }
.dvjs-table tbody tr:hover { background: var(--background-modifier-hover); }

/* column 1: Date */
.dvjs-table thead th:nth-child(1) { font-size: 24px; }
.dvjs-table tbody td:nth-child(1) { font-size: 12px; }

/* column 2: Title */
.dvjs-table thead th:nth-child(2) { font-size: 24px; }
.dvjs-table tbody td:nth-child(2) { font-size: 12px; }

/* column 3: Summary */
.dvjs-table thead th:nth-child(3) { font-size: 24px; }
.dvjs-table tbody td:nth-child(3) { font-size: 12px; }

/* column 4: Tags */
.dvjs-table thead th:nth-child(4) { font-size: 24px; }
.dvjs-table tbody td:nth-child(4) { font-size: 12px; }

.dvjs-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.dvjs-table th, .dvjs-table td { text-align: left; padding: 6px; vertical-align: top; }

/* column widths via colgroup */
.dvjs-col-date   { width: 72px; }   /* narrower */
.dvjs-col-title  { width: 13%; }    /* ~20% less than before (was 30%) */
.dvjs-col-summary{ width: 60%; }    /* wider */
.dvjs-col-tags   { width: 27%; }    /* unchanged */

.dvjs-summary, .dvjs-tags-preview {
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;            /* clamp to 2 lines */
  -webkit-box-orient: vertical;
}
.dvjs-summary.expanded, .dvjs-tags-preview.expanded { display: block; overflow: visible; }

.dvjs-toggle { display: inline-block; margin-left: 8px; font-size: 0.9em; opacity: 0.8; cursor: pointer; }

.dvjs-chip {
  display: inline-block;
  margin: 2px 6px 2px 0;
  padding: 2px 6px;
  border: 1px solid var(--background-modifier-border);
  border-radius: 10px;
  font-size: 0.9em;
  white-space: nowrap;
}

.dvjs-tags-editor { margin-top: 6px; }
.dvjs-tags-textarea {
  width: 100%;
  min-height: 84px;
  padding: 6px 8px;
  border: 1px solid var(--background-modifier-border);
  border-radius: 6px;
  background: var(--background-primary);
  font-family: var(--font-monospace), ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  resize: vertical;
}
.dvjs-help { grid-column: 1 / -1; font-size: 12px; opacity: 0.75; }
`;
dv.container.appendChild(style);

// --- load pages ---
let pages = dv.pages(SCOPE);
if (REQUIRE_SUMMARY) pages = pages.where(p => p.summary);

// --- UI: filters ---
const ui = document.createElement('div');
ui.className = 'dvjs-dash';

const startInput   = Object.assign(document.createElement('input'), { type: 'date', title: 'Start date', placeholder: 'Start date' });
const endInput     = Object.assign(document.createElement('input'), { type: 'date', title: 'End date', placeholder: 'End date' });
const titleInput   = Object.assign(document.createElement('input'), { type: 'text', placeholder: 'Title Filter' });
const tagInput     = Object.assign(document.createElement('input'), { type: 'text', placeholder: 'Tag Filter' });
const summaryInput = Object.assign(document.createElement('input'), { type: 'text', placeholder: 'Summary Filter' });
const contentInput = Object.assign(document.createElement('input'), { type: 'text', placeholder: 'Content Filter' });

startInput.classList.add('dvjs-input', 'area-start');
endInput.classList.add('dvjs-input', 'area-end');
titleInput.classList.add('dvjs-input', 'area-title');
tagInput.classList.add('dvjs-input', 'area-tag');
summaryInput.classList.add('dvjs-input', 'area-summary');
contentInput.classList.add('dvjs-input', 'area-content');

/* ▼ NEW: a Search button that triggers filtering */
const searchBtn = document.createElement('button');
searchBtn.className = 'dvjs-input dvjs-btn dvjs-go';
searchBtn.textContent = 'Search';

[startInput, endInput, titleInput, tagInput, summaryInput, contentInput].forEach(i => i.className = 'dvjs-input');
ui.append(startInput, endInput, titleInput, tagInput, summaryInput, contentInput, searchBtn);

dv.container.appendChild(ui);

/* =========================
   ▼ NEW: persistence helpers
   ========================= */
const STORAGE_KEY = "dvjs_dash_filters_v1";

function loadFilters() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}
function saveFilters(markApplied = false) {
  const prev = loadFilters();
  const payload = {
    start:   startInput.value || "",
    end:     endInput.value || "",
    title:   titleInput.value || "",
    tag:     tagInput.value || "",
    summary: summaryInput.value || "",
    content: contentInput.value || "",
    applied: markApplied ? "1" : (prev.applied || "0"),
  };
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(payload)); } catch {}
}
function restoreFiltersIntoInputs() {
  const s = loadFilters();
  if (s.start   != null) startInput.value   = s.start;
  if (s.end     != null) endInput.value     = s.end;
  if (s.title   != null) titleInput.value   = s.title;
  if (s.tag     != null) tagInput.value     = s.tag;
  if (s.summary != null) summaryInput.value = s.summary;
  if (s.content != null) contentInput.value = s.content;
}
// restore any previous values into the inputs
restoreFiltersIntoInputs();

// table holder
const tableHolder = document.createElement('div');
dv.container.appendChild(tableHolder);

// --- helpers ---
function parseFromName(name) {
  const m = name.match(/^(\d{4}-\d{2}-\d{2})\s*-\s*(.+?)(?:\s*-\s*[A-Za-z0-9]+)?$/);
  if (!m) return { dateStr: null, title: name };
  return { dateStr: m[1], title: m[2].trim() };
}
function toDate(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr + "T00:00:00");
  return isNaN(d) ? null : d;
}
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtDate(d) {
  if (!d) return "";
  const dd = d.getDate();
  const mon = MONTHS[d.getMonth()];
  const yy = String(d.getFullYear()).slice(-2);
  return `${dd} ${mon} ${yy}`;   // e.g., 25 Sep 24
}
function normalizeTag(t) {
  if (!t) return null;
  t = String(t).trim().toLowerCase();
  if (!t) return null;
  if (!t.startsWith("misc/")) t = "misc/" + t.replace(/^#|^\//, "").replace(/\s+/g, "-");
  return t;
}
function dedupe(arr) {
  const out = [], seen = new Set();
  for (const x of arr) if (x && !seen.has(x)) { seen.add(x); out.push(x); }
  return out;
}
function parseTagsTextarea(raw) {
  let parts = (raw || "").split(/\n/).map(s => s.trim()).filter(Boolean);
  parts = parts.flatMap(s => s.split(/[,\s]+/));
  parts = parts.map(x => x.replace(/^#/, "")).map(normalizeTag).filter(Boolean);
  return dedupe(parts);
}

// NEW: quoted AND/NEG helpers (minimal additions)
function parseQuotedTermsSigned(input) {
  const pos = [], neg = [];
  const re = /(-?)"([^"]+)"/g;
  let m;
  while ((m = re.exec(input)) !== null) {
    const term = (m[2] || "").trim().toLowerCase();
    if (!term) continue;
    (m[1] === "-" ? neg : pos).push(term);
  }
  return { pos, neg };
}
function containsAll(text, terms) {
  if (!terms.length) return true;
  if (!text) return false;
  const hay = String(text).toLowerCase();
  return terms.every(t => hay.includes(t));
}
function containsNone(text, terms) {
  if (!terms.length) return true;
  if (!text) return true;
  const hay = String(text).toLowerCase();
  return terms.every(t => !hay.includes(t));
}
function tagsContainAll(tagsArr, terms) {
  if (!terms.length) return true;
  const tags = (tagsArr || []).map(t => String(t).toLowerCase());
  return terms.every(term => tags.some(tag => tag.includes(term)));
}
function tagsContainNone(tagsArr, terms) {
  if (!terms.length) return true;
  const tags = (tagsArr || []).map(t => String(t).toLowerCase());
  return terms.every(term => tags.every(tag => !tag.includes(term)));
}

// precompute derived fields
const rows = pages.array().map(p => {
  const { dateStr, title } = parseFromName(p.file.name);
  let parsed = null;
  if (p.created) {
    const c = (typeof p.created === "string" ? p.created : p.created?.toString()) ?? "";
    parsed = toDate(c.slice(0,10));
  }
  if (!parsed) parsed = toDate(dateStr);

  const tags = Array.isArray(p.tags) ? p.tags : (p.tags ? [p.tags] : []);
  return {
    page: p,
    path: p.file.path,
    title: title,
    date: parsed,
    dateLabel: fmtDate(parsed),
    summary: p.summary ?? "",
    tags: tags.map(t => String(t))
  };
});

// cache for content when needed
const contentCache = new Map();
async function getContent(path) {
  if (contentCache.has(path)) return contentCache.get(path);
  let text = "";
  try {
    if (dv.io?.load) text = await dv.io.load(path);
    else text = await app.vault.cachedRead(app.vault.getAbstractFileByPath(path));
  } catch (e) { text = ""; }
  text = text.replace(/^---\n[\s\S]*?\n---\n/, ""); // strip frontmatter
  contentCache.set(path, text);
  return text;
}

// frontmatter update (REPLACE tags)
async function replaceTagsInFrontmatter(path, newTags) {
  const file = app.vault.getAbstractFileByPath(path);
  if (!file) { new Notice("File not found: " + path); return false; }
  await app.fileManager.processFrontMatter(file, (fm) => { fm.tags = newTags; });
  return true;
}

// --- render table ---
function renderTable(list) {
  tableHolder.innerHTML = "";
  const tbl = document.createElement('table');
  tbl.className = 'dvjs-table';

  // colgroup to enforce widths
  const colgroup = document.createElement('colgroup');
  ["dvjs-col-date","dvjs-col-title","dvjs-col-summary","dvjs-col-tags"].forEach(cls=>{
    const col = document.createElement('col'); col.className = cls; colgroup.appendChild(col);
  });
  tbl.appendChild(colgroup);

  tbl.innerHTML += `
    <thead>
      <tr>
        <th>Date</th>
        <th>Title</th>
        <th>Summary</th>
        <th>Tags</th>
      </tr>
    </thead>
    <tbody></tbody>`;
  const body = tbl.querySelector('tbody');

  for (const r of list) {
    const tr = document.createElement('tr');

    // date
    const tdDate = document.createElement('td');
    tdDate.textContent = r.dateLabel || "";

    // title (internal link)
    const tdTitle = document.createElement('td');
    const a = document.createElement('a');
    a.href = r.path;
    a.dataset.href = r.path;
    a.className = "internal-link";
    a.textContent = r.title || r.page.file.name;
    tdTitle.appendChild(a);

    // summary (collapsed with toggle)
    const tdSummary = document.createElement('td');
    const sumDiv = document.createElement('div');
    sumDiv.className = 'dvjs-summary';
    sumDiv.textContent = r.summary || "";
    const sumToggle = document.createElement('span');
    sumToggle.className = 'dvjs-toggle';
    sumToggle.textContent = 'Show more';
    sumToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      const expanded = sumDiv.classList.toggle('expanded');
      sumToggle.textContent = expanded ? 'Show less' : 'Show more';
    });
    tdSummary.append(sumDiv);
    if ((r.summary || "").trim().length > 0) tdSummary.append(sumToggle);

    // tags cell: preview + click-to-edit textarea
    const tdTags = document.createElement('td');

    // Preview (chips), clamped to 2 lines
    const preview = document.createElement('div');
    preview.className = 'dvjs-tags-preview';
    function renderPreview() {
      preview.innerHTML = "";
      (r.tags || []).forEach(t => {
        const chip = document.createElement('span');
        chip.className = 'dvjs-chip';
        chip.textContent = "#" + (t.startsWith("misc/") ? t : t);
        preview.appendChild(chip);
      });
    }
    renderPreview();

    const tagsToggle = document.createElement('span');
    tagsToggle.className = 'dvjs-toggle';
    tagsToggle.textContent = 'Show more';
    tagsToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      const expanded = preview.classList.toggle('expanded');
      tagsToggle.textContent = expanded ? 'Show less' : 'Show more';
    });

    // Inline editor (textarea)
    const editorWrap = document.createElement('div');
    editorWrap.className = 'dvjs-tags-editor';
    editorWrap.style.display = 'none';

    const textarea = document.createElement('textarea');
    textarea.className = 'dvjs-tags-textarea';
    textarea.value = (r.tags || []).map(t => (t.startsWith("misc/") ? "#" + t : "#" + t)).join("\n");
    editorWrap.appendChild(textarea);

    function openEditor() {
      preview.style.display = 'none';
      tagsToggle.style.display = 'none';
      editorWrap.style.display = '';
      textarea.focus();
      textarea.selectionStart = textarea.selectionEnd = textarea.value.length;
    }
    function closeEditor(cancel = true) {
      editorWrap.style.display = 'none';
      preview.style.display = '';
      tagsToggle.style.display = '';
      if (cancel) textarea.value = (r.tags || []).map(t => "#" + t).join("\n");
    }

    // NEW: save helper – only writes if the set actually changed
    async function saveTagsIfChanged() {
      const parsed = parseTagsTextarea(textarea.value);
      const same = JSON.stringify(parsed) === JSON.stringify((r.tags || []).map(String));
      if (same) { closeEditor(false); return; }
      try {
        saveFilters(true); // <-- NEW: persist current filters before saving tags
        const ok = await replaceTagsInFrontmatter(r.path, parsed);
        if (ok) {
          r.tags = parsed;
          renderPreview();
          new Notice("Tags saved.");
          closeEditor(false);
        } else {
          new Notice("Failed to save tags.");
          closeEditor(true);
        }
      } catch (e) {
        console.error(e);
        new Notice("Error saving tags.");
        closeEditor(true);
      }
    }

    tdTags.addEventListener('click', (e) => {
      if (editorWrap.style.display !== 'none') return;
      if (e.target === tagsToggle) return;
      openEditor();
    });
    tdTags.addEventListener('keydown', (e) => {
      if (editorWrap.style.display === 'none' && e.key === 'Enter') {
        e.preventDefault();
        openEditor();
      }
    });

    // Save on Cmd/Ctrl+Enter; Esc cancels
    textarea.addEventListener('keydown', async (ev) => {
      if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') {
        ev.preventDefault();
        await saveTagsIfChanged();
      } else if (ev.key === 'Escape') {
        ev.preventDefault();
        closeEditor(true);
      }
    });

    // clicking elsewhere now SAVES if changed (was cancel)
    document.addEventListener('click', async (evt) => {
      if (editorWrap.style.display === 'none') return;
      const within = tdTags.contains(evt.target);
      if (!within) await saveTagsIfChanged();
    });

    tdTags.append(preview, tagsToggle, editorWrap);

    tr.append(tdDate, tdTitle, tdSummary, tdTags);
    body.appendChild(tr);
  }

  tableHolder.appendChild(tbl);
}

// --- filtering (with optional content load + quoted AND/NEG) ---
async function applyFilters() {
  const qTitleRaw   = titleInput.value || "";
  const qTagRaw     = tagInput.value || "";
  const qSummaryRaw = summaryInput.value || "";
  const qContentRaw = contentInput.value || "";

  // date range (declare ONCE here)
  const qStart = startInput.value ? toDate(startInput.value) : null;
  const qEnd   = endInput.value ? toDate(endInput.value) : null;

  // EMPTY BY DEFAULT: if no filters at all, clear table and bail
  if (!qTitleRaw && !qTagRaw && !qSummaryRaw && !qContentRaw && !qStart && !qEnd) {
    tableHolder.innerHTML = "";
    return;
  }

  // keep your old simple substrings
  const qTitle   = qTitleRaw.toLowerCase();
  const qTag     = qTagRaw.toLowerCase();
  const qSummary = qSummaryRaw.toLowerCase();
  const qContent = qContentRaw.toLowerCase();

  // signed quoted terms per field (for AND/NEG)
  const tSigned = parseQuotedTermsSigned(qTitleRaw);
  const gSigned = parseQuotedTermsSigned(qTagRaw);
  const sSigned = parseQuotedTermsSigned(qSummaryRaw);
  const cSigned = parseQuotedTermsSigned(qContentRaw);

  let filtered = rows.filter(r => true);

  // Title
  if (tSigned.pos.length || tSigned.neg.length) {
    filtered = filtered.filter(r =>
      containsAll(r.title || "", tSigned.pos) &&
      containsNone(r.title || "", tSigned.neg)
    );
  } else if (qTitle) {
    filtered = filtered.filter(r => (r.title || "").toLowerCase().includes(qTitle));
  }

  // Tags
  if (gSigned.pos.length || gSigned.neg.length) {
    filtered = filtered.filter(r =>
      tagsContainAll(r.tags, gSigned.pos) &&
      tagsContainNone(r.tags, gSigned.neg)
    );
  } else if (qTag) {
    filtered = filtered.filter(r => (r.tags || []).some(t => (t || "").toLowerCase().includes(qTag)));
  }

  // Summary
  if (sSigned.pos.length || sSigned.neg.length) {
    filtered = filtered.filter(r =>
      containsAll(r.summary || "", sSigned.pos) &&
      containsNone(r.summary || "", sSigned.neg)
    );
  } else if (qSummary) {
    filtered = filtered.filter(r => (r.summary || "").toLowerCase().includes(qSummary));
  }

  // Date range
  if (qStart) filtered = filtered.filter(r => r.date && r.date >= qStart);
  if (qEnd)   filtered = filtered.filter(r => r.date && r.date <= qEnd);

  // Content (lazy)
  if (cSigned.pos.length || cSigned.neg.length || qContent) {
    const results = [];
    for (const r of filtered) {
      const text = await getContent(r.path);
      if (cSigned.pos.length || cSigned.neg.length) {
        if (containsAll(text, cSigned.pos) && containsNone(text, cSigned.neg)) results.push(r);
      } else if (qContent) {
        if (text.toLowerCase().includes(qContent)) results.push(r);
      }
    }
    filtered = results;
  }

  filtered.sort((a,b) =>
    (b.date?.getTime() || 0) - (a.date?.getTime() || 0) ||
    a.title.localeCompare(b.title)
  );

  renderTable(filtered);
}

/* ▼ CHANGED WIRING: only run when clicking Search (and on Enter) */
searchBtn.addEventListener('click', () => { 
  saveFilters(true); // NEW: remember values & that user applied them
  applyFilters(); 
});

// Optional: allow pressing Enter in any field to trigger the same as clicking Search
[startInput, endInput, titleInput, tagInput, summaryInput, contentInput]
  .forEach(el => el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); saveFilters(true); applyFilters(); }
  }));

/* Only auto-apply if a search was previously applied; otherwise keep empty */
const _persisted = loadFilters();
if (_persisted.applied === "1") {
  applyFilters();
} else {
  tableHolder.innerHTML = "";
}
```