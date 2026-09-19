import { createVirtualTable } from "/static/js/vtable.js";

const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];
const stage = $("#stage");
const drawer = $("#drawer");
let selected = new Set();
let page = { urls: 0, domains: 0, sources: 0, queue: 0 };
let lastSearch = {};

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}

function fmt(n) { return Number(n||0).toLocaleString(); }
function esc(s) {
  return String(s ?? "").replace(/[&<>"'`]/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;","`":"&#96;"
  }[c]));
}

const views = {
  dashboard: renderDashboard,
  import: renderImport,
  search: renderSearch,
  domains: renderDomains,
  sources: renderSources,
  export: renderExport,
  queue: renderQueue,
  settings: renderSettings,
};

$$("nav button").forEach(b => b.onclick = () => show(b.dataset.view));
$("#burger").onclick = () => $("#rail").classList.toggle("open");

function show(name) {
  $$("nav button").forEach(b => b.classList.toggle("on", b.dataset.view === name));
  $("#view-title").textContent = name.replace("-", " ").toUpperCase();
  views[name]();
}

function statCard(k, v) {
  return `<div class="card"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>`;
}

async function renderDashboard() {
  stage.innerHTML = "Loading library…";
  const [s, act, src] = await Promise.all([
    api("/api/stats"),
    api("/api/activity"),
    api("/api/sources?limit=8"),
  ]);
  const maxT = Math.max(1, ...s.tld_breakdown.map(t => t.count));
  const maxG = Math.max(1, ...s.growth.map(g => g.count));
  stage.innerHTML = `
    <div class="grid stats">
      ${statCard("TOTAL URLS", fmt(s.total_urls))}
      ${statCard("DOMAINS", fmt(s.total_domains))}
      ${statCard("REGISTERED DOMAINS", fmt(s.registered_domains))}
      ${statCard("SOURCE FILES", fmt(s.source_files))}
      ${statCard("LAST IMPORT", s.last_import ? s.last_import.filename : "—")}
      ${statCard("HARVEST QUEUE", fmt(s.queued))}
    </div>
    <div class="grid two" style="margin-top:14px">
      <div class="card">
        <div class="k">DOMAIN BREAKDOWN</div>
        <div class="bars">
          ${s.tld_breakdown.map(t => `
            <div class="row" data-tld="${esc(t.label)}">
              <span>${esc(t.label)}</span>
              <div class="bar"><i style="width:${Math.round(t.count/maxT*100)}%"></i></div>
              <span>${fmt(t.count)}</span>
            </div>`).join("") || "<p class='k'>No corpus yet.</p>"}
        </div>
      </div>
      <div class="card">
        <div class="k">URL LIBRARY GROWTH</div>
        <div class="spark">
          ${s.growth.map(g => `<i title="${esc(g.month)} ${fmt(g.count)}" style="height:${Math.round(g.count/maxG*100)}%"></i>`).join("") || ""}
        </div>
      </div>
    </div>
    <div class="grid two" style="margin-top:14px">
      <div class="card">
        <div class="k">RECENT IMPORTS</div>
        <table><thead><tr><th>FILE</th><th>IMPORTED</th><th>FOUND</th><th>NEW</th><th>DUPE</th><th>STATUS</th></tr></thead>
        <tbody>
          ${src.items.map(r => `<tr data-source="${r.id}">
            <td>${esc(r.filename)}</td><td>${esc((r.imported_at||"").slice(0,10))}</td>
            <td>${fmt(r.urls_discovered)}</td><td>${fmt(r.urls_inserted)}</td>
            <td>${fmt(r.duplicates)}</td><td>${esc(r.status)}</td>
          </tr>`).join("") || "<tr><td colspan=6>None</td></tr>"}
        </tbody></table>
      </div>
      <div class="card">
        <div class="k">RECENT ACTIVITY</div>
        <table><tbody>
          ${(act.items||[]).map(a => `<tr><td class="badge">${esc(a.event)}</td><td>${esc(a.detail||"")}</td><td>${esc(a.created_at)}</td></tr>`).join("") || "<tr><td>Quiet.</td></tr>"}
        </tbody></table>
      </div>
    </div>`;
  $$(".bars .row").forEach(r => r.onclick = () => {
    lastSearch = { q: "", tldHint: r.dataset.tld };
    show("domains");
  });
  $$("[data-source]").forEach(r => r.onclick = () => openSource(r.dataset.source));
}

function renderImport() {
  stage.innerHTML = `
    <div class="card drop" id="drop"><div>
      DROP FILES HERE<br/><br/>TXT / CSV CORPORA<br/><br/>
      <button class="act primary" id="pick">Select files</button>
      <input id="file" type="file" accept=".txt,.csv" multiple hidden />
    </div></div>
    <div class="card" style="margin-top:14px">
      <table><thead><tr><th>FILE</th><th>SIZE</th><th>TYPE</th><th>STATUS</th></tr></thead>
      <tbody id="filelist"></tbody></table>
      <p><button class="act primary" id="go">Start Import</button></p>
      <pre id="prog" class="k"></pre>
    </div>`;
  const files = [];
  const list = $("#filelist");
  function add(listFiles) {
    for (const f of listFiles) {
      if (!/\.(txt|csv)$/i.test(f.name)) continue;
      files.push(f);
      list.insertAdjacentHTML("beforeend", `<tr><td>${esc(f.name)}</td><td>${fmt(f.size)}</td><td>${esc(f.name.split(".").pop())}</td><td>READY</td></tr>`);
    }
  }
  const drop = $("#drop");
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("hot"); };
  drop.ondragleave = () => drop.classList.remove("hot");
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove("hot"); add(e.dataTransfer.files); };
  $("#pick").onclick = () => $("#file").click();
  $("#file").onchange = e => add(e.target.files);
  $("#go").onclick = async () => {
    if (!files.length) return;
    const fd = new FormData();
    files.forEach(f => fd.append("files", f));
    await fetch("/api/import", { method: "POST", body: fd });
    const es = new EventSource("/api/import/stream");
    es.onmessage = ev => {
      const s = JSON.parse(ev.data);
      $("#prog").textContent =
        `${s.status}  ${s.file||""}\nscanned/discovered ${fmt(s.discovered)}\nnew ${fmt(s.inserted)}  dupes ${fmt(s.duplicates)}`;
      if (!s.running) es.close();
    };
  };
}

async function renderSearch() {
  stage.innerHTML = `
    <input class="search" id="q" placeholder="SEARCH THE URL LIBRARY..." />
    <div class="filters">
      <input id="f-domain" placeholder="Domain" />
      <input id="f-reg" placeholder="Registered domain" />
      <select id="f-scheme"><option value="">Scheme</option><option>https</option><option>http</option></select>
      <input id="f-ext" placeholder="Extension pdf" />
      <input id="f-src" placeholder="Source file" />
      <input id="f-status" placeholder="Status" />
      <button class="act primary" id="go">Search</button>
      <button class="act" id="adv">Advanced</button>
      <button class="act" id="save">Save search</button>
    </div>
    <div id="advp" class="card hidden" style="margin-bottom:12px">
      <div class="filters">
        <input id="f-path" placeholder="path contains" />
        <input id="f-from" placeholder="date from YYYY-MM-DD" />
        <input id="f-to" placeholder="date to" />
        <button class="act" id="clear">Clear</button>
      </div>
    </div>
    <div class="k" id="sel">SELECTED: 0</div>
    <div class="filters">
      <button class="act" data-act="queue">Add to harvest queue</button>
      <button class="act" data-act="copy">Copy URLs</button>
      <button class="act" data-act="export">Export selected</button>
    </div>
    <div id="vtable"></div>
    <div class="k" id="meta"></div>`;
  $("#adv").onclick = () => $("#advp").classList.toggle("hidden");
  $("#clear").onclick = () => { $$("input,select", stage).forEach(i => { if (i.id !== "q") i.value=""; }); };
  const params = () => new URLSearchParams({
    q: $("#q").value, domain: $("#f-domain").value, registered_domain: $("#f-reg").value,
    scheme: $("#f-scheme").value, extension: $("#f-ext").value, source: $("#f-src").value,
    status: $("#f-status").value, path_contains: $("#f-path").value,
    date_from: $("#f-from").value, date_to: $("#f-to").value
  });
  const table = createVirtualTable({
    mount: $("#vtable"),
    pageSize: 80,
    columns: [
      { label: "", flex: "0 0 28px" },
      { label: "URL", flex: "2.4" },
      { label: "DOMAIN", flex: "1.1" },
      { label: "PATH", flex: "1.2" },
      { label: "SOURCE", flex: ".9" },
      { label: "DISCOVERED", flex: ".7" },
      { label: "STATUS", flex: ".6" },
    ],
    fetchPage: async ({ limit, after }) => {
      const p = params();
      p.set("limit", String(limit));
      p.set("include_total", after ? "false" : "true");
      if (after) p.set("after", String(after));
      lastSearch = Object.fromEntries(p);
      const data = await api("/api/urls?" + p);
      $("#meta").textContent = `${fmt(data.total ?? data.items.length)} in library · keyset pages`;
      return data;
    },
    renderRow: (r) => `<div class="vt-row" data-id="${r.id}">
      <div style="flex:0 0 28px"><input type="checkbox" data-id="${r.id}" ${selected.has(r.id)?"checked":""}/></div>
      <div style="flex:2.4">${esc(r.normalized_url)}</div>
      <div style="flex:1.1">${esc(r.hostname)}</div>
      <div style="flex:1.2">${esc(r.path)}</div>
      <div style="flex:.9">${esc(r.source_file)}</div>
      <div style="flex:.7">${esc((r.first_seen||"").slice(0,10))}</div>
      <div style="flex:.6">${esc(r.status)}</div>
    </div>`,
    onRowClick: (id, ev) => {
      if (ev.target.type === "checkbox") {
        if (ev.target.checked) selected.add(+id); else selected.delete(+id);
        $("#sel").textContent = "SELECTED: " + fmt(selected.size);
        return;
      }
      openUrl(id);
    },
  });
  const run = () => table.reset();
  $("#go").onclick = run;
  $("#q").onkeydown = e => { if (e.key === "Enter") run(); };
  $("#save").onclick = async () => {
    const name = prompt("Search name?");
    if (!name) return;
    await api("/api/saved-searches", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ name, query: $("#q").value, filters: lastSearch }) });
  };
  $("[data-act=queue]").onclick = async () => {
    await api("/api/queue", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ link_ids: [...selected], priority: "NORMAL" }) });
    alert("Queued " + selected.size);
  };
  $("[data-act=copy]").onclick = async () => {
    const urls = [];
    for (const id of selected) {
      const u = await api("/api/urls/" + id);
      urls.push(u.normalized_url);
    }
    await navigator.clipboard.writeText(urls.join("\n"));
  };
  $("[data-act=export]").onclick = () => show("export");
  run();
}

async function renderDomains() {
  const tld = lastSearch.tldHint && lastSearch.tldHint !== "other" ? lastSearch.tldHint : "";
  stage.innerHTML = `
    <div class="filters">
      <input id="dq" placeholder="Search domains" />
      ${"[\"\",\".gov\",\".edu\",\".org\",\".com\",\".net\",\"other\"]".length && ["",".gov",".edu",".org",".com",".net","other"].map(t => `<button class="act tld" data-t="${t}">${t||"ALL"}</button>`).join("")}
    </div>
    <div id="vtable"></div>
    <div class="k" id="meta"></div>`;
  let curT = tld;
  const table = createVirtualTable({
    mount: $("#vtable"),
    pageSize: 80,
    columns: [
      { label: "DOMAIN", flex: "2" },
      { label: "URLS", flex: ".6" },
      { label: "SOURCES", flex: ".6" },
      { label: "FIRST", flex: ".7" },
      { label: "LAST", flex: ".7" },
    ],
    fetchPage: async ({ limit, offset }) => {
      const data = await api(`/api/domains?q=${encodeURIComponent($("#dq").value)}&tld=${encodeURIComponent(curT)}&limit=${limit}&offset=${offset||0}`);
      $("#meta").textContent = fmt(data.total) + " domains · virtualized";
      return data;
    },
    renderRow: (d) => `<div class="vt-row" data-id="${esc(d.hostname)}">
      <div style="flex:2">${esc(d.hostname)}</div>
      <div style="flex:.6">${fmt(d.link_count)}</div>
      <div style="flex:.6">${fmt(d.source_count)}</div>
      <div style="flex:.7">${esc((d.first_seen||"").slice(0,10))}</div>
      <div style="flex:.7">${esc((d.last_seen||"").slice(0,10))}</div>
    </div>`,
    onRowClick: (host) => {
      show("search");
      setTimeout(() => { const el = $("#f-domain"); if (el) { el.value = host; $("#go").click(); } }, 0);
    },
  });
  $$(".tld").forEach(b => b.onclick = () => { curT = b.dataset.t; table.reset(); });
  $("#dq").onkeydown = e => { if (e.key==="Enter") table.reset(); };
  table.reset();
}

async function renderSources() {
  const data = await api("/api/sources?limit=50&offset=0");
  stage.innerHTML = `<div class="card"><table>
    <thead><tr><th>SOURCE</th><th>SIZE</th><th>HASH</th><th>IMPORTED</th><th>URLS</th><th>NEW</th><th>DUPES</th><th>STATUS</th></tr></thead>
    <tbody>${data.items.map(s => `<tr data-id="${s.id}">
      <td>${esc(s.filename)}</td><td>${fmt(s.file_size)}</td><td>${esc((s.file_hash||"").slice(0,12))}</td>
      <td>${esc(s.imported_at)}</td><td>${fmt(s.urls_discovered)}</td><td>${fmt(s.urls_inserted)}</td>
      <td>${fmt(s.duplicates)}</td><td>${esc(s.status)}</td></tr>`).join("")}</tbody></table></div>`;
  $$("[data-id]").forEach(r => r.onclick = () => openSource(r.dataset.id));
}

function renderExport() {
  stage.innerHTML = `<div class="card">
    <div class="k">EXPORT CONTROL</div>
    <div class="filters">
      <label>MODE <select id="mode"><option value="all">All URLs</option><option value="selected">Selected</option>
        <option value="domain">Domain</option><option value="source">Source</option><option value="queue">Queue</option></select></label>
      <label>FORMAT <select id="fmt"><option>txt</option><option>csv</option><option>json</option></select></label>
      <input id="ex-domain" placeholder="domain if mode=domain" />
      <input id="ex-source" placeholder="source filename" />
    </div>
    <label><input type="checkbox" id="i-src" checked /> Include source</label>
    <label><input type="checkbox" id="i-dom" checked /> Include domain</label>
    <label><input type="checkbox" id="i-time" /> Include timestamps</label>
    <label><input type="checkbox" id="i-norm" checked /> Include normalized URL</label>
    <label><input type="checkbox" id="i-orig" /> Include original URL</label>
    <p><button class="act primary" id="go">Export</button></p>
  </div>`;
  $("#go").onclick = async () => {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: $("#mode").value, fmt: $("#fmt").value,
        link_ids: [...selected], domain: $("#ex-domain").value, source: $("#ex-source").value,
        include_source: $("#i-src").checked, include_domain: $("#i-dom").checked,
        include_timestamps: $("#i-time").checked, include_normalized: $("#i-norm").checked,
        include_original: $("#i-orig").checked
      })
    });
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "purple-export." + $("#fmt").value;
    a.click();
  };
}

async function renderQueue() {
  const data = await api("/api/queue");
  stage.innerHTML = `
    <div class="filters">
      <button class="act" id="clear">Clear queue</button>
      <button class="act" id="exq">Export queue</button>
    </div>
    <div class="card"><table>
      <thead><tr><th>URL</th><th>DOMAIN</th><th>STATUS</th><th>PRIORITY</th><th>ADDED</th><th></th></tr></thead>
      <tbody>${data.items.map(q => `<tr>
        <td>${esc(q.normalized_url)}</td><td>${esc(q.hostname)}</td>
        <td>${esc(q.status)}</td><td>${esc(q.priority)}</td><td>${esc(q.added_at)}</td>
        <td><button class="act rm" data-id="${q.id}">Remove</button></td>
      </tr>`).join("") || "<tr><td>Queue empty — librarian only, no auto-download.</td></tr>"}</tbody>
    </table></div>`;
  $$(".rm").forEach(b => b.onclick = async () => { await api("/api/queue/"+b.dataset.id, {method:"DELETE"}); renderQueue(); });
  $("#clear").onclick = async () => { await api("/api/queue/clear", {method:"POST"}); renderQueue(); };
  $("#exq").onclick = () => show("export");
}

function renderSettings() {
  stage.innerHTML = `<div class="card">
    <div class="k">CONTROL PLANE</div>
    <p>Purple indexes. It does not fetch URLs.</p>
    <p>Database: configured via purple.yaml / --db</p>
    <p>Statuses supported: DISCOVERED, REVIEWED, QUEUED, DOWNLOADING, DOWNLOADED, FAILED, SKIPPED, ARCHIVED</p>
    <p>Harvesting is a downstream system. This queue is a handoff list only.</p>
  </div>`;
}

async function openUrl(id) {
  const u = await api("/api/urls/" + id);
  drawer.classList.remove("hidden");
  drawer.innerHTML = `<button class="act" id="close">Close</button>
    <h2>URL DETAIL</h2>
    <div class="kv">
      <b>FULL</b><span>${esc(u.original_url)}</span>
      <b>NORMALIZED</b><span>${esc(u.normalized_url)}</span>
      <b>SCHEME</b><span>${esc(u.scheme)}</span>
      <b>HOST</b><span>${esc(u.hostname)}</span>
      <b>REGISTERED</b><span>${esc(u.registered_domain)}</span>
      <b>PORT</b><span>${esc(u.port)}</span>
      <b>PATH</b><span>${esc(u.path)}</span>
      <b>QUERY</b><span>${esc(u.query)}</span>
      <b>FRAGMENT</b><span>${esc(u.fragment)}</span>
      <b>SOURCE</b><span>${esc(u.source_file)}</span>
      <b>FIRST</b><span>${esc(u.first_seen)}</span>
      <b>LAST</b><span>${esc(u.last_seen)}</span>
      <b>STATUS</b><span>${esc(u.status)}</span>
    </div>
    <h3>SOURCE HISTORY</h3>
    <ul>${(u.source_history||[]).map(s => `<li>${esc(s.filename)} row ${esc(s.source_row)}</li>`).join("")}</ul>`;
  $("#close", drawer).onclick = () => drawer.classList.add("hidden");
}

async function openSource(id) {
  const s = await api("/api/sources/" + id);
  drawer.classList.remove("hidden");
  drawer.innerHTML = `<button class="act" id="close">Close</button>
    <h2>SOURCE DETAILS</h2>
    <div class="kv">
      <b>FILE</b><span>${esc(s.filename)}</span>
      <b>SHA-256</b><span>${esc(s.file_hash)}</span>
      <b>SIZE</b><span>${fmt(s.file_size)}</span>
      <b>IMPORTED</b><span>${esc(s.imported_at)}</span>
      <b>STATUS</b><span>${esc(s.status)}</span>
      <b>URLS</b><span>${fmt(s.urls_discovered)}</span>
      <b>DOMAINS</b><span>${fmt(s.domain_count)}</span>
    </div>
    <h3>URLS</h3>
    <table><tbody>${(s.urls||[]).map(u => `<tr data-id="${u.id}"><td>${esc(u.normalized_url)}</td></tr>`).join("")}</tbody></table>`;
  $("#close", drawer).onclick = () => drawer.classList.add("hidden");
  $$("tr[data-id]", drawer).forEach(tr => tr.onclick = () => openUrl(tr.dataset.id));
}

show("dashboard");
