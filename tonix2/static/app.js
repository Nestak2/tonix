"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const VIEWS = ["start", "papers", "citations", "save", "summary"];

const state = { config: null, papers: [], staff: [], sonix: false, blocks: [], paperChoice: {}, citeChoice: {}, polling: null };

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `The program answered with an error (${res.status}).`);
  return data;
}

function flash(msg) {
  const el = $("#flash");
  el.hidden = !msg;
  el.textContent = msg || "";
  if (msg) el.scrollIntoView({ block: "nearest" });
}

function show(view) {
  for (const v of VIEWS) $(`#view-${v}`).hidden = v !== view;
  const idx = VIEWS.indexOf(view);
  $$("#rail li").forEach((li, i) => {
    li.classList.toggle("done", i < idx);
    li.classList.toggle("current", i === idx);
    if (i === idx) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
  });
  window.scrollTo(0, 0);
}

function setBusy(on) {
  $("#busy").hidden = !on;
  $$("button").forEach((b) => { if (b.id !== "quit") b.disabled = on; });
}

function renderLog(lines, warnings) {
  $("#log-lines").innerHTML = lines.map((l) => `<li class="${l.level}">${esc(l.t)}  ${esc(l.msg)}</li>`).join("");
  $("#log-warn").textContent = warnings ? `(${plural(warnings, "warning", "warnings")})` : "";
  const box = $("#log-lines");
  box.scrollTop = box.scrollHeight;
}

function poll(onDone) {
  clearInterval(state.polling);
  setBusy(true);
  state.polling = setInterval(async () => {
    let st;
    try { st = await api("/api/status"); } catch (e) { return; }
    const p = st.progress;
    $("#busy-label").textContent = p.label || "Working…";
    const bar = $("#busy-bar");
    if (p.total) { bar.max = p.total; bar.value = p.done; $("#busy-count").textContent = `${p.done} of ${p.total}`; }
    else { bar.removeAttribute("value"); $("#busy-count").textContent = ""; }
    renderLog(st.log, st.warnings);
    if (!st.running) {
      clearInterval(state.polling);
      setBusy(false);
      if (st.error) { flash(`Stopped: ${st.error}`); onDone(st, st.error); }
      else onDone(st);
    }
  }, 700);
}

const opts = (map, current, order) => (order || Object.keys(map)).map((k) => `<option value="${esc(k)}" ${String(current) === String(k) ? "selected" : ""}>${esc(map[k])}</option>`).join("");

// ------------------------------------------------------------------ 1 start
async function loadConfig() {
  state.config = await api("/api/config");
  const c = state.config;
  if (c.ads_saved) { $("#ads-input").placeholder = "Using the saved token"; $("#ads-note").textContent = `A token was found in ${c.ads_saved}. Leave this empty to use it.`; }
  if (c.openalex_saved) { $("#oa-input").placeholder = "Using the saved key"; $("#oa-note").textContent = `A key was found in ${c.openalex_saved}. Leave this empty to use it.`; }
  $("#scimago-note").textContent = c.scimago.loaded
    ? `Scopus check: using ${c.scimago.file} (${c.scimago.journals.toLocaleString()} sources).`
    : "Scopus check: no Scimago list in the data folder, so citing journals are assumed to be indexed and SJR values aren’t filled in. See the README to add one.";
}

$("#start-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  flash("");
  const f = new FormData(ev.target);
  const body = Object.fromEntries(f.entries());
  body.refresh = f.has("refresh");
  body.show_browser = f.has("show_browser");
  try {
    await api("/api/start", body);
    $("#start-form [name=sonix_password]").value = "";
    $("#busy-label").textContent = body.sonix_email ? "Signing in to Sonix" : "Reading your ORCID record";
    poll((st, err) => { if (!err) loadPapers(); });
  } catch (e) { flash(e.message); }
});

// ------------------------------------------------------------------ 2 papers
async function loadPapers() {
  const d = await api("/api/papers");
  state.papers = d.papers;
  state.staff = d.staff;
  state.sonix = d.sonix;
  state.paperChoice = {};
  for (const p of d.papers) {
    state.paperChoice[p.id] = { add: p.add, unit_report: p.unit_report, cite: p.cite, form: p.form ? JSON.parse(JSON.stringify(p.form)) : null };
  }
  const s = d.stats;
  const dup = s.orcid_duplicates ? `, after merging ${plural(s.orcid_duplicates, "duplicate entry", "duplicate entries")}` : "";
  const sonix = d.sonix
    ? ` Signed in to Sonix as ${d.sonix_user || "you"}: ${plural(s.in_sonix, "paper is", "papers are")} already there${s.sonix_only ? `, ${s.sonix_only} of them only in Sonix` : ""}.`
    : " Not signed in to Sonix, so nothing can be compared or saved.";
  $("#papers-lede").textContent = `${d.person}: ${plural(s.papers, "paper", "papers")} in ORCID${dup}.${sonix}`;
  renderPapers();
  show("papers");
}

function paperMeta(p) {
  const vp = [p.volume, p.pages].filter(Boolean).join(":");
  const where = [p.journal, vp].filter(Boolean).join(" ");
  let m = [p.authors, where].filter(Boolean).join(", ");
  if (p.year) m += ` (${p.year})`;
  if (p.author_count) m += `. ${plural(p.author_count, "author", "authors")}`;
  return m;
}

function staffSelect(current, idx) {
  const o = [`<option value="">Not from the unit</option>`].concat(state.staff.map((s) => `<option value="${esc(s.id)}" ${s.id === current ? "selected" : ""}>${esc(s.label)}</option>`));
  return `<select data-a="${idx}" data-af="staff" aria-label="Person in your unit">${o.join("")}</select>`;
}

function formPanel(p) {
  const f = state.paperChoice[p.id].form;
  const c = state.config;
  const yn = (cur) => `<option value="Y" ${cur === "Y" ? "selected" : ""}>Да</option><option value="N" ${cur === "N" ? "selected" : ""}>Не</option>`;
  const statusOrder = ["", "1", "2", "3", "4", "5", "11", "21", "22", "31", "32", "33", "34", "51", "99"];
  const authors = f.authors.map((a, i) => `<li><input data-a="${i}" data-af="name" value="${esc(a.name)}" maxlength="30" aria-label="Author name">${staffSelect(a.staff, i)}</li>`).join("");
  return `<details class="sform" ${f.pubstatusID ? "" : "open"}>
    <summary>Sonix fields${f.pubstatusID ? "" : " (status needed)"}</summary>
    <div class="fgrid">
      <label>Type<select data-f="pubtypeID">${opts(c.pubtypes, f.pubtypeID)}</select></label>
      <label>Status of the journal<select data-f="pubstatusID">${opts(c.statuses, f.pubstatusID, statusOrder)}</select></label>
      <label>Indexed in<select data-f="refID">${opts(c.refs, f.refID, ["0", "5", "4", "25", "6", "9999"])}</select></label>
      <label>JCR-IF (Web of Science)<input data-f="isiif" value="${esc(f.isiif)}" maxlength="7" inputmode="decimal"></label>
      <label>SJR (Scopus)<input data-f="sjr" value="${esc(f.sjr)}" maxlength="7" inputmode="decimal"></label>
      <label>Total number of authors<input data-f="authorsNum" value="${esc(f.authorsNum)}" maxlength="4" inputmode="numeric"></label>
      <label>Corresponding author is from BAS<select data-f="corBAS">${yn(f.corBAS)}</select></label>
      <label>Has a foreign co-author<select data-f="fauthor">${yn(f.fauthor)}</select></label>
      <label class="wide">Journal or proceedings<input data-f="description" value="${esc(f.description)}" maxlength="500"></label>
      <label>Volume<input data-f="volume" value="${esc(f.volume)}" maxlength="20"></label>
      <label>First page or article number<input data-f="page_bgn" value="${esc(f.page_bgn)}" maxlength="10"></label>
      <label>ISSN<input data-f="issn" value="${esc(f.issn)}" maxlength="250"></label>
    </div>
    ${f.sjr_quartile ? `<p class="hint">Status suggested from the Scimago quartile (${esc(f.sjr_quartile)}). If your unit counts by the Web of Science (JCR) quartile, check it.</p>` : ""}
    <p class="flabel">Authors as Sonix will list them${Number(f.authorsNum) > f.authors.length ? `: ${f.authors.length} of ${f.authorsNum}, the rest are counted in the total` : ""}</p>
    <ol class="alist">${authors}</ol>
  </details>`;
}

function renderPapers() {
  const sonix = state.sonix;
  $("#papers-head").innerHTML = `<tr>
      ${sonix ? `<th scope="col">In Sonix</th><th scope="col" class="c">Add to Sonix</th>` : ""}
      <th scope="col" class="c">In unit report</th><th scope="col" class="c">Find citations</th>
      <th scope="col">Paper</th><th scope="col">Found in</th></tr>`;
  $("#papers-body").innerHTML = state.papers.map((p) => {
    const ch = state.paperChoice[p.id];
    const ids = [p.doi ? `<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">doi:${esc(p.doi)}</a>` : "",
                 p.arxiv ? `<a href="https://arxiv.org/abs/${esc(p.arxiv)}" target="_blank" rel="noopener">arXiv:${esc(p.arxiv)}</a>` : ""].filter(Boolean).join("  ");
    const sjr = p.sjr ? `<span class="chip">SJR ${esc(p.sjr.value)} ${esc(p.sjr.quartile)}</span>` : "";
    const sonixCell = p.in_sonix
      ? `<td><a href="${esc(p.sonix_url || "#")}" target="_blank" rel="noopener">Yes</a><div class="meta">${plural(p.sonix_cites, "citation", "citations")}</div></td>`
      : `<td class="meta">Not yet</td>`;
    const active = ch.add || ch.cite || p.in_sonix;
    return `<tr class="${active ? "" : "off"}" data-id="${p.id}">
      ${sonix ? sonixCell + `<td class="c"><input type="checkbox" data-k="add" ${ch.add ? "checked" : ""} ${p.in_sonix ? "disabled" : ""} aria-label="Add to Sonix"></td>` : ""}
      <td class="c"><input type="checkbox" data-k="unit_report" ${ch.unit_report ? "checked" : ""} ${(p.in_sonix || (sonix && !ch.add)) ? "disabled" : ""} aria-label="In unit report"></td>
      <td class="c"><input type="checkbox" data-k="cite" ${ch.cite ? "checked" : ""} ${p.searchable ? "" : "disabled"} aria-label="Find citations"></td>
      <td>
        <div class="ptitle">${p.link ? `<a href="${esc(p.link)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)}</div>
        <div class="meta">${esc(paperMeta(p))}</div>
        <div class="meta">${ids}</div>
        ${p.notes.length ? `<ul class="notes">${p.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
        ${sonix && ch.add && ch.form ? formPanel(p) : ""}
      </td>
      <td><div class="kind">${esc(p.kind_label)}</div><div class="chips">${p.sources.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}${sjr}</div></td>
    </tr>`;
  }).join("") || `<tr><td colspan="6" class="empty">No papers were found in this ORCID record.</td></tr>`;
}

$("#papers-body").addEventListener("change", (ev) => {
  const t = ev.target;
  const row = t.closest("tr");
  if (!row) return;
  const ch = state.paperChoice[row.dataset.id];
  if (t.matches("input[type=checkbox][data-k]")) {
    ch[t.dataset.k] = t.checked;
    const open = $$("#papers-body details.sform").map((d) => [d.closest("tr").dataset.id, d.open]);
    renderPapers();
    for (const [id, o] of open) { const d = $(`#papers-body tr[data-id="${id}"] details.sform`); if (d) d.open = o; }
  } else updateForm(ch, t);
});
$("#papers-body").addEventListener("input", (ev) => {
  const row = ev.target.closest("tr");
  if (row && !ev.target.matches("input[type=checkbox]")) updateForm(state.paperChoice[row.dataset.id], ev.target);
});
function updateForm(ch, t) {
  if (!ch.form) return;
  if (t.dataset.f) ch.form[t.dataset.f] = t.value;
  if (t.dataset.a !== undefined) ch.form.authors[Number(t.dataset.a)][t.dataset.af] = t.value;
  if (t.dataset.f === "pubstatusID") { const s = t.closest("details").querySelector("summary"); if (s) s.textContent = "Sonix fields"; }
}

$$("[data-bulk]").forEach((b) => b.addEventListener("click", () => {
  const all = b.dataset.bulk === "published";
  for (const p of state.papers) {
    const pub = !["preprint", "thesis", "erratum", "other"].includes(p.kind);
    if (!p.in_sonix) state.paperChoice[p.id].add = all && pub && state.sonix;
    state.paperChoice[p.id].cite = all && (pub || p.in_sonix) && p.searchable;
  }
  renderPapers();
}));

$("#go-citations").addEventListener("click", async () => {
  flash("");
  try {
    const r = await api("/api/citations", { papers: state.paperChoice });
    $("#busy-label").textContent = `Finding citations for ${plural(r.count, "paper", "papers")}`;
    poll((st, err) => { if (!err) loadCitations(); });
  } catch (e) { flash(e.message); }
});
$("#back-start").addEventListener("click", () => show("start"));

// ------------------------------------------------------------------ 3 citations
async function loadCitations() {
  const d = await api("/api/citations");
  state.blocks = d.blocks;
  state.citeChoice = {};
  let total = 0, already = 0, selfs = 0, updates = 0;
  for (const b of d.blocks) {
    already += b.already; selfs += b.self_excluded; updates += b.updates || 0;
    for (const it of b.items) { state.citeChoice[it.id] = { selected: it.selected, type: it.type }; if (!it.replace) total++; }
  }
  const bits = [`${plural(total, "new citing work", "new citing works")} for ${plural(d.blocks.length, "paper", "papers")}`];
  if (updates) bits.push(`${plural(updates, "Sonix entry", "Sonix entries")} to update from the arXiv preprint to the journal version`);
  if (state.sonix) bits.push(`${already} already in Sonix and not shown`);
  bits.push(`${plural(selfs, "self-citation", "self-citations")} left out`);
  $("#cites-lede").textContent = `${bits.join(", ")}. The text is in the format Sonix asks for. Check the type of each one.`;
  renderCitations();
  show("citations");
}

function typeSelect(it) {
  const order = ["8", "1", "2", "3", "4", "9", "0"];
  return `<select data-k="type" aria-label="Type in Sonix">${opts(state.config.types, state.citeChoice[it.id].type, order)}</select>`;
}

function renderCitations() {
  $("#cites-body").innerHTML = state.blocks.map((b) => {
    const counts = Object.entries(b.counts).map(([s, n]) => `${s} ${n}`).join(", ") || "no source answered";
    const chosen = b.items.filter((it) => state.citeChoice[it.id].selected).length;
    const parts = [`${chosen} of ${b.new + (b.updates || 0)} ticked`];
    if (b.updates) parts.push(`${plural(b.updates, "update", "updates")} from arXiv to journal`);
    if (state.sonix) parts.push(`${b.already} already in Sonix`);
    parts.push(`${plural(b.self_excluded, "self-citation", "self-citations")} left out`);
    const items = b.items.map((it) => {
      const ch = state.citeChoice[it.id];
      return `<li class="citem ${ch.selected ? "" : "off"} ${it.replace ? "upd" : ""}" data-id="${it.id}">
        <input type="checkbox" data-k="selected" ${ch.selected ? "checked" : ""} aria-label="${it.replace ? "Update this Sonix entry" : "Include this citation"}">
        <div>
          ${it.replace ? `<p class="old"><span class="tag-upd">Update in Sonix</span> Now: ${esc(it.old_text)}</p>` : ""}
          <p class="ctext">${it.replace ? "New: " : ""}${esc(it.text)}</p>
          <div class="cmeta">
            ${typeSelect(it)}
            <span>${esc(it.sources.join(", "))}</span>
            ${it.link ? `<a href="${esc(it.link)}" target="_blank" rel="noopener">Open</a>` : ""}
            ${it.notes.map((n) => `<span class="cnote">${esc(n)}</span>`).join("")}
          </div>
        </div>
      </li>`;
    }).join("");
    return `<details class="block" open>
      <summary><h2>${esc(b.paper.title)}</h2>
        <span class="counts">${parts.join(", ")}. ${b.raw} records read (${esc(counts)}).</span>
        ${b.sonix_unmatched ? `<span class="counts">${plural(b.sonix_unmatched, "Sonix entry wasn’t", "Sonix entries weren’t")} found in the databases; ${b.sonix_unmatched === 1 ? "it stays" : "they stay"} as is.</span>` : ""}
        ${b.notes.map((n) => `<span class="counts cnote">${esc(n)}</span>`).join("")}
      </summary>
      ${b.items.length ? `<ul class="clist">${items}</ul>` : `<p class="empty">No new citations for this paper.</p>`}
    </details>`;
  }).join("");
}

$("#cites-body").addEventListener("change", (ev) => {
  const el = ev.target.closest("[data-k]");
  if (!el) return;
  const id = el.closest(".citem").dataset.id;
  if (el.dataset.k === "selected") {
    state.citeChoice[id].selected = el.checked;
    el.closest(".citem").classList.toggle("off", !el.checked);
  } else state.citeChoice[id].type = el.value;
});

$$("[data-cbulk]").forEach((b) => b.addEventListener("click", () => {
  const on = b.dataset.cbulk === "all";
  for (const bl of state.blocks) for (const it of bl.items) state.citeChoice[it.id].selected = on;
  renderCitations();
}));

const choices = () => ({ papers: state.paperChoice, citations: state.citeChoice });

$("#go-save").addEventListener("click", async () => {
  flash("");
  try { renderPlan(await api("/api/plan", choices())); show("save"); } catch (e) { flash(e.message); }
});
$("#back-papers").addEventListener("click", () => show("papers"));

// ------------------------------------------------------------------ 4 save
function renderPlan(plan) {
  const nP = plan.publications.length, nC = plan.citations_total, nU = plan.updates_total || 0;
  $("#do-save").hidden = !plan.sonix;
  $("#do-save").disabled = !plan.can_save;
  $("#do-save").textContent = `Save ${plural(nP, "publication", "publications")}, ${plural(nC, "citation", "citations")}` + (nU ? ` and ${plural(nU, "update", "updates")}` : "");
  if (!plan.sonix) {
    $("#save-lede").textContent = "You didn’t sign in to Sonix, so nothing can be saved. Finish to get the summary and the files.";
    $("#save-body").innerHTML = "";
    return;
  }
  $("#save-lede").textContent = nP + nC + nU
    ? "This is what will be entered in Sonix, the same way you would type it. Entries are saved one by one with a short pause, so a long list takes a while."
    : "Nothing is ticked, so there is nothing to save.";
  const pubs = plan.publications.map((p) => `<li>${esc(p.title)}</li>`).join("");
  const cites = plan.citations.map((c) => `<li>${[c.count ? plural(c.count, "new citation", "new citations") : "", c.updates ? `${plural(c.updates, "entry", "entries")} updated from arXiv to journal` : ""].filter(Boolean).join(" and ")} for ${esc(c.title)}${c.new_paper ? " (added above first)" : ""}</li>`).join("");
  $("#save-body").innerHTML = `
    ${plan.problems.length ? `<div class="problems"><h2>Fix these first</h2><ul>${plan.problems.map((p) => `<li>${esc(p)}</li>`).join("")}</ul><p class="hint">Use “Back to citations” and then “Back to papers” to change the Sonix fields.</p></div>` : ""}
    ${plan.warnings.length ? `<div class="problems warnbox"><h2>Check these</h2><ul>${plan.warnings.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>` : ""}
    <h2 class="sub">New publications</h2>${pubs ? `<ul class="plain">${pubs}</ul>` : `<p class="empty">None.</p>`}
    <h2 class="sub">New citations</h2>${cites ? `<ul class="plain">${cites}</ul>` : `<p class="empty">None.</p>`}
    ${plan.skipped_not_in_sonix ? `<p class="cnote">${plural(plan.skipped_not_in_sonix, "ticked citation belongs", "ticked citations belong")} to papers that aren’t in Sonix and aren’t being added, so ${plan.skipped_not_in_sonix === 1 ? "it is" : "they are"} not saved.</p>` : ""}`;
}

$("#do-save").addEventListener("click", async () => {
  flash("");
  try {
    await api("/api/save", choices());
    $("#busy-label").textContent = "Saving to Sonix";
    poll(async () => { await finish({}); });
  } catch (e) { flash(e.message); }
});
$("#skip-save").addEventListener("click", () => finish(choices()));
$("#back-cites").addEventListener("click", () => show("citations"));

async function finish(body) {
  try { renderSummary(await api("/api/finish", body)); show("summary"); } catch (e) { flash(e.message); }
}

// ------------------------------------------------------------------ 5 summary
const kv = (rows) => `<dl class="kv">${rows.filter(Boolean).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;

function renderSummary(s) {
  const P = s.papers, C = s.citations, R = s.saved;
  const mins = Math.floor(s.elapsed_s / 60), secs = s.elapsed_s % 60;
  const wrote = R ? `Saved to Sonix: ${plural(R.pubs_added.length, "publication", "publications")}, ${plural(R.cites_added, "new citation", "new citations")}${R.cites_updated ? ` and ${plural(R.cites_updated, "citation", "citations")} updated to the journal version` : ""}.` : "Nothing was saved to Sonix.";
  $("#sum-lede").textContent = `${s.person}, ORCID ${s.orcid}. Finished in ${mins ? `${mins} min ` : ""}${secs} s. ${wrote}`;
  const bySource = Object.entries(C.by_source).map(([k, v]) => [`Records from ${k}`, v]);
  const byType = Object.entries(C.by_type);
  const years = Object.entries(C.years);
  const disabled = Object.entries(s.disabled_sources);
  const reqs = Object.entries(s.requests).map(([h, n]) => [`Requests to ${h}`, n]);
  const fails = R ? [...R.pubs_failed.map((f) => `Publication “${f.title}”: ${f.error}`), ...R.cites_failed.map((f) => `Citation for “${f.paper}”: ${f.error}`)] : [];
  const perPaper = s.per_paper.map((r) => `<tr><td>${esc(r.paper)}</td><td class="c">${esc(r.year ?? "")}</td><td class="c">${r.new}</td><td class="c">${r.chosen}</td>${R ? `<td class="c">${r.saved}</td>` : ""}${s.sonix_connected ? `<td class="c">${r.already}</td>` : ""}<td class="c">${r.self}</td></tr>`).join("");
  $("#sum-body").innerHTML = `
    <div class="stats">
      ${R ? `<section><h2>Saved to Sonix</h2>${kv([["Publications added", R.pubs_added.length], ["Publications failed", R.pubs_failed.length], ["Citations added", R.cites_added], ["Updated from arXiv to journal", R.cites_updated || 0], ["Citations failed", R.cites_failed.length], ["Citations skipped", R.cites_skipped]])}</section>` : ""}
      <section><h2>Papers</h2>${kv([["ORCID entries", P.orcid_entries], ["Distinct papers in ORCID", P.distinct], ["Duplicates merged", P.duplicates_merged], ["Preprints without journal version", P.preprint_only], s.sonix_connected && ["Already in Sonix", P.in_sonix_before], s.sonix_connected && ["Only in Sonix, not in ORCID", P.sonix_only], ["Searched for citations", P.searched]])}</section>
      <section><h2>Citations</h2>${kv([["Records read", C.records], ...bySource, ["Found in more than one source", C.multi_source], s.sonix_connected && ["Already in Sonix", C.already_in_sonix], s.sonix_connected && ["arXiv entries to update", C.updates], ["Self-citations left out", C.self_excluded], ["New citing works", C.new], ["Ticked", C.chosen], ["Unticked", C.left_out]])}</section>
      <section><h2>Ticked by type</h2>${byType.length ? kv(byType) : `<p class="empty">None ticked.</p>`}<h2 class="sub">Ticked by year</h2>${years.length ? kv(years) : `<p class="empty">None ticked.</p>`}</section>
    </div>
    ${fails.length ? `<h2>What Sonix refused</h2><ul class="warnlist">${fails.map((f) => `<li class="error">${esc(f)}</li>`).join("")}</ul>` : ""}
    <h2 class="sub">Per paper</h2>
    <div class="scroll"><table><thead><tr><th>Paper</th><th class="c">Year</th><th class="c">New</th><th class="c">Ticked</th>${R ? `<th class="c">Saved</th>` : ""}${s.sonix_connected ? `<th class="c">Already in Sonix</th>` : ""}<th class="c">Self-citations</th></tr></thead><tbody>${perPaper || `<tr><td colspan="7" class="empty">No papers searched.</td></tr>`}</tbody></table></div>
    <h2 class="sub">Warnings and errors</h2>
    ${s.warnings.length ? `<ul class="warnlist">${s.warnings.map((w) => `<li class="${w.level}">${esc(w.msg)}</li>`).join("")}</ul>` : `<p class="empty">None.</p>`}
    ${disabled.length ? `<p class="cnote">Sources switched off during the run: ${esc(disabled.map(([k, v]) => `${k} (${v})`).join("; "))}</p>` : ""}
    ${reqs.length ? `<details><summary class="meta">Network requests</summary>${kv(reqs)}</details>` : ""}
    <h2 class="sub">Files</h2>
    <p class="meta">Saved in <span class="path">${esc(s.folder)}</span></p>
    <div class="files">${s.files.map((f) => `<a href="/api/export/${encodeURIComponent(f)}">Download ${esc(f)}</a>`).join("")}</div>`;
}

$("#again").addEventListener("click", () => { flash(""); show("start"); });
$("#quit").addEventListener("click", async () => {
  try { await api("/api/quit", {}); } catch (e) { /* server is closing */ }
  document.body.innerHTML = `<main><h1>tonix is closed</h1><p class="lede">You can close this tab. Run <code>python run.py</code> to start again.</p></main>`;
});

loadConfig().catch((e) => flash(e.message));
show("start");
