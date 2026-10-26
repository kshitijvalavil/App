from flask import Blueprint, jsonify, render_template_string, request

from token_usage import analyze, load_limits, save_limits

bp = Blueprint("tokens", __name__)

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Token Usage</title>
<style>
  :root {
    color-scheme: light;
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --grid: #e1e0d9; --axis: #c3c2b7; --ring: rgba(11,11,11,0.10);
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100;
    --good: #0ca30c; --warning: #fab219; --critical: #d03b3b; --accent: #4f46e5;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10);
      --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --accent: #8b85f0;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10);
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --accent: #8b85f0;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: var(--page); color: var(--ink); padding: 24px 16px 48px; }
  main { max-width: 1180px; margin: 0 auto; display: grid; gap: 16px; }
  header { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }
  h1 { font-size: 1.5rem; }
  h2 { font-size: 1rem; margin-bottom: 12px; }
  .sub { color: var(--ink-2); font-size: 13px; margin-top: 4px; overflow-wrap: anywhere; }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 14px; }
  select, button { font: inherit; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--ring); background: var(--surface); color: var(--ink); }
  button.primary { background: var(--accent); color: #fff; border: none; font-weight: 600; cursor: pointer; }
  button.primary[disabled] { opacity: .6; cursor: progress; }
  .card { background: var(--surface); border: 1px solid var(--ring); border-radius: 12px; padding: 16px; min-width: 0; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
  .tile .label { color: var(--ink-2); font-size: 13px; }
  .tile .value { font-size: 1.6rem; font-weight: 650; margin-top: 4px; }
  .tile .note { color: var(--muted); font-size: 12px; margin-top: 2px; }
  .two { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; }
  @media (max-width: 860px) { .two { grid-template-columns: 1fr; } }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--ink-2); margin-bottom: 8px; }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
  svg { display: block; width: 100%; height: auto; overflow: visible; }
  svg text { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
  .bar:hover, .hbar:hover { opacity: .8; }
  #tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--ring); border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,.15); display: none; z-index: 10; font-variant-numeric: tabular-nums; }
  #tip b { display: block; margin-bottom: 4px; }
  #tip i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 6px; }
  ul.insights { list-style: none; display: grid; gap: 10px; }
  ul.insights li { display: flex; gap: 10px; font-size: 14px; line-height: 1.45; }
  .badge { flex: none; font-size: 11px; font-weight: 700; border-radius: 999px; padding: 2px 8px; height: fit-content; border: 1px solid currentColor; }
  .badge.good { color: var(--good); } .badge.warning { color: var(--warning); } .badge.critical { color: var(--critical); } .badge.info { color: var(--muted); }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: right; padding: 6px 8px; border-bottom: 1px solid var(--grid); white-space: nowrap; font-variant-numeric: tabular-nums; }
  th { color: var(--ink-2); font-weight: 600; }
  th:first-child, td:first-child { text-align: left; }
  td.mono { font-family: ui-monospace, monospace; }
  .empty { color: var(--ink-2); padding: 24px 0; text-align: center; }
  .card-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  .card-head h2 { margin: 0; }
  .hint { color: var(--muted); font-size: 12px; }
  .limits { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
  .limit h3 { font-size: 14px; margin-bottom: 8px; }
  .meter { margin-bottom: 10px; font-size: 13px; }
  .meter .row { display: flex; justify-content: space-between; gap: 8px; color: var(--ink-2); margin-bottom: 4px; }
  .meter .row b { color: var(--ink); font-weight: 650; }
  .track { height: 8px; border-radius: 4px; background: var(--grid); overflow: hidden; }
  .fill { height: 100%; border-radius: 4px; background: var(--s1); }
  .fill.warning { background: var(--warning); } .fill.critical { background: var(--critical); }
  .meter .left { margin-top: 4px; font-size: 12px; color: var(--muted); }
  .meter .left.warning { color: var(--ink); } .meter .left.critical { color: var(--critical); font-weight: 600; }
  .unset { color: var(--muted); font-size: 13px; }
  form.limits-form { display: none; margin-top: 16px; border-top: 1px solid var(--grid); padding-top: 16px; gap: 12px; }
  form.limits-form.open { display: grid; }
  .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
  .form-grid fieldset { border: 1px solid var(--ring); border-radius: 8px; padding: 10px; display: grid; gap: 8px; font-size: 13px; }
  .form-grid legend { font-weight: 600; padding: 0 4px; }
  .form-grid label { display: grid; gap: 4px; color: var(--ink-2); }
  input[type=number] { font: inherit; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--ring); background: var(--page); color: var(--ink); width: 100%; }
  .lifetime { display: flex; flex-wrap: wrap; gap: 8px 32px; }
  .lifetime div { font-size: 13px; color: var(--ink-2); }
  .lifetime b { display: block; font-size: 1.25rem; color: var(--ink); font-weight: 650; }
  .scope { display: none; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; border-color: var(--accent); }
  .scope.on { display: flex; }
  tr.clickable { cursor: pointer; } tr.clickable:hover td { background: var(--grid); }
  tr.selected td { font-weight: 650; }
  button.link { background: none; border: none; color: var(--accent); cursor: pointer; padding: 0; font-weight: 600; }
  .err { color: var(--critical); }
</style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Claude token usage</h1>
      <div class="sub" id="meta">Loading…</div>
    </div>
    <div class="controls">
      <label>Range
        <select id="days">
          <option value="">All time</option><option value="1">Last 24h</option>
          <option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option>
        </select>
      </label>
      <label>Project
        <select id="project"><option value="">All projects</option></select>
      </label>
      <label>Auto-refresh
        <select id="auto">
          <option value="0">Off</option><option value="30">30s</option><option value="60">1 min</option><option value="300">5 min</option>
        </select>
      </label>
      <button class="primary" id="refresh">Refresh</button>
    </div>
  </header>

  <section class="card">
    <div class="card-head">
      <h2>Limits &amp; what's left</h2>
      <button class="link" id="editLimits" type="button">Edit limits</button>
    </div>
    <div class="limits" id="limits"></div>
    <form class="limits-form" id="limitsForm">
      <div class="form-grid" id="limitsFields"></div>
      <label class="hint"><input type="checkbox" id="countCacheReads"> Count cache reads toward token limits (they are ~95% of raw tokens but bill at a fraction of input)</label>
      <div><button class="primary" type="submit">Save limits</button> <button type="button" id="cancelLimits">Cancel</button> <span class="hint">Leave blank for no limit.</span></div>
    </form>
  </section>

  <section class="card">
    <div class="card-head"><h2>Lifetime</h2><span class="hint" id="lifetimeSince"></span></div>
    <div class="lifetime" id="lifetime"></div>
  </section>

  <section class="card scope" id="scope">
    <div><b id="scopeName"></b><div class="hint">Project deep dive: everything below is filtered to this project.</div></div>
    <button type="button" id="clearProject">&larr; All projects</button>
  </section>

  <section class="tiles" id="tiles"></section>

  <section class="card">
    <h2>Insights</h2>
    <ul class="insights" id="insights"></ul>
  </section>

  <section class="two">
    <div class="card">
      <h2>Tokens per day</h2>
      <div class="legend" id="dayLegend"></div>
      <div id="dayChart"></div>
    </div>
    <div class="card">
      <h2>Estimated cost by token type</h2>
      <div id="costChart"></div>
    </div>
  </section>

  <section class="two">
    <div class="card">
      <h2>Requests by hour of day</h2>
      <div id="hourChart"></div>
    </div>
    <div class="card">
      <h2>Cost by model</h2>
      <div id="modelChart"></div>
    </div>
  </section>

  <section class="card">
    <div class="card-head"><h2>Usage by project</h2><span class="hint">Click a project to deep dive</span></div>
    <div id="projectShare"></div>
    <div class="table-wrap" id="projects"></div>
  </section>
  <section class="card"><h2>Sessions (most expensive first)</h2><div class="table-wrap" id="sessions"></div></section>
  <section class="card"><h2>Tools (by text returned into context)</h2><div class="table-wrap" id="tools"></div></section>
  <section class="card"><h2>Most expensive requests</h2><div class="table-wrap" id="top"></div></section>
</main>
<div id="tip"></div>

<script>
const $ = id => document.getElementById(id);
const SERIES = [
  ["input", "Input", "--s1"], ["cache_write", "Cache write", "--s2"],
  ["cache_read", "Cache read", "--s3"], ["output", "Output", "--s4"],
];
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt = n => {
  n = Number(n) || 0;
  for (const [u, s] of [["B", 1e9], ["M", 1e6], ["K", 1e3]]) if (Math.abs(n) >= s) return (n / s).toFixed(1) + u;
  return Math.round(n).toString();
};
const usd = n => n == null ? "—" : "$" + (n < 1 ? n.toFixed(3) : n.toFixed(2));
const pct = n => n.toFixed(1) + "%";
const when = ts => ts ? new Date(ts).toLocaleString() : "—";
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const tip = $("tip");
function showTip(e, html) {
  tip.innerHTML = html; tip.style.display = "block";
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
  const y = Math.min(e.clientY + 14, innerHeight - tip.offsetHeight - 8);
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
document.addEventListener("mouseout", e => { if (e.target.dataset && e.target.dataset.tip !== undefined) tip.style.display = "none"; });
document.addEventListener("mousemove", e => {
  const t = e.target.closest && e.target.closest("[data-tip]");
  if (t) showTip(e, t.dataset.tip); else tip.style.display = "none";
});

function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v))), m = v / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
}

// Rounded-top rect anchored to its baseline.
function bar(x, y, w, h, r, fill, tipHtml, top = true) {
  r = Math.min(r, w / 2, h);
  const d = top
    ? `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
    : `M${x},${y}H${x + w}V${y + h}H${x}Z`;
  return `<path class="bar" d="${d}" fill="${fill}" data-tip="${esc(tipHtml)}"/>`;
}

function stackedDays(days) {
  $("dayLegend").innerHTML = SERIES.map(([, l, c]) => `<span><i style="background:var(${c})"></i>${l}</span>`).join("");
  if (!days.length) { $("dayChart").innerHTML = '<div class="empty">No data in range</div>'; return; }
  const W = 720, H = 260, L = 48, B = 24, T = 8, gap = 2;
  const max = niceMax(Math.max(...days.map(d => SERIES.reduce((a, [k]) => a + d[k], 0))));
  const bw = Math.max(2, Math.min(40, (W - L) / days.length - 4));
  const step = (W - L) / days.length;
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const y = T + (H - T - B) * (1 - i / 4);
    g += `<line x1="${L}" x2="${W}" y1="${y}" y2="${y}" stroke="var(${i ? "--grid" : "--axis"})"/><text x="${L - 6}" y="${y + 4}" text-anchor="end">${fmt(max * i / 4)}</text>`;
  }
  const every = Math.ceil(days.length / 8);
  days.forEach((d, i) => {
    const x = L + i * step + (step - bw) / 2;
    let y0 = H - B;
    const tipHtml = `<b>${d.day}</b>` + SERIES.map(([k, l, c]) => `<div><i style="background:var(${c})"></i>${l}: ${fmt(d[k])}</div>`).join("")
      + `<div>Requests: ${d.requests}</div><div>Cost: ${usd(d.cost)}</div>`;
    const segs = SERIES.filter(([k]) => d[k] > 0);
    segs.forEach(([k, , c], j) => {
      const h = (H - T - B) * d[k] / max;
      const isTop = j === segs.length - 1;
      const hh = Math.max(0, h - (isTop ? 0 : gap));
      g += bar(x, y0 - h + (isTop ? 0 : gap), bw, hh, 4, `var(${c})`, tipHtml, isTop);
      y0 -= h;
    });
    if (i % every === 0) g += `<text x="${x + bw / 2}" y="${H - 6}" text-anchor="middle">${d.day.slice(5)}</text>`;
  });
  $("dayChart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Stacked tokens per day">${g}</svg>`;
}

function hbars(el, rows, color, W = 360) {
  if (!rows.length) { el.innerHTML = '<div class="empty">No data</div>'; return; }
  const rowH = 34, L = 0;
  const max = Math.max(...rows.map(r => r.value)) || 1;
  let g = "";
  rows.forEach((r, i) => {
    const y = i * rowH, w = Math.max(2, (W - 130) * r.value / max);
    g += `<text x="0" y="${y + 11}" style="fill:var(--ink-2);font-size:12px">${esc(r.label)}</text>`;
    g += `<rect class="hbar" x="${L}" y="${y + 16}" width="${w}" height="12" rx="4" fill="var(${r.color || color})" data-tip="${esc(r.tip)}"/>`;
    g += `<text x="${w + 6}" y="${y + 26}" style="fill:var(--ink);font-size:12px">${esc(r.text)}</text>`;
  });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${rows.length * rowH}" role="img">${g}</svg>`;
}

function hours(rows) {
  const W = 720, H = 180, L = 36, B = 22, T = 8;
  const max = niceMax(Math.max(...rows.map(r => r.requests), 1));
  const step = (W - L) / 24, bw = step - 4;
  let g = "";
  for (let i = 0; i <= 2; i++) {
    const y = T + (H - T - B) * (1 - i / 2);
    g += `<line x1="${L}" x2="${W}" y1="${y}" y2="${y}" stroke="var(${i ? "--grid" : "--axis"})"/><text x="${L - 6}" y="${y + 4}" text-anchor="end">${fmt(max * i / 2)}</text>`;
  }
  rows.forEach((r, i) => {
    const h = (H - T - B) * r.requests / max, x = L + i * step + 2;
    if (h > 0) g += bar(x, H - B - h, bw, h, 4, "var(--s1)", `<b>${String(r.hour).padStart(2, "0")}:00</b><div>Requests: ${r.requests}</div><div>Tokens: ${fmt(r.total)}</div><div>Cost: ${usd(r.cost)}</div>`);
    if (i % 3 === 0) g += `<text x="${x + bw / 2}" y="${H - 6}" text-anchor="middle">${String(r.hour).padStart(2, "0")}</text>`;
  });
  $("hourChart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Requests by hour, local time">${g}</svg>`;
}

function table(el, cols, rows, rowAttrs = () => "") {
  if (!rows.length) { el.innerHTML = '<div class="empty">No data</div>'; return; }
  el.innerHTML = `<table><thead><tr>${cols.map(c => `<th>${c[0]}</th>`).join("")}</tr></thead><tbody>`
    + rows.map(r => `<tr ${rowAttrs(r)}>${cols.map(c => `<td class="${c[2] || ""}">${c[1](r)}</td>`).join("")}</tr>`).join("") + "</tbody></table>";
}

const level = p => p >= 90 ? "critical" : p >= 75 ? "warning" : "";
const until = ts => {
  if (!ts) return "";
  const ms = new Date(ts) - Date.now();
  if (ms <= 0) return "now";
  const h = Math.floor(ms / 3.6e6), m = Math.round((ms % 3.6e6) / 6e4);
  return h >= 48 ? `in ${Math.round(h / 24)} days` : h ? `in ${h}h ${m}m` : `in ${m}m`;
};
function meter(name, used, limit, left, show) {
  const p = Math.min(100, 100 * used / limit), lv = level(p);
  return `<div class="meter"><div class="row"><span>${name}</span><span><b>${show(used)}</b> / ${show(limit)}</span></div>
    <div class="track" role="progressbar" aria-valuenow="${p.toFixed(0)}" aria-valuemin="0" aria-valuemax="100"><div class="fill ${lv}" style="width:${p}%"></div></div>
    <div class="left ${lv}">${lv === "critical" ? "✕ " : lv === "warning" ? "! " : ""}${show(left)} left · ${p.toFixed(0)}% used</div></div>`;
}

let limitsCfg = null;
function renderLimits(lim) {
  $("limits").innerHTML = lim.windows.map(w => {
    const parts = [];
    if (w.token_limit) parts.push(meter("Tokens", w.tokens, w.token_limit, w.tokens_left, fmt));
    if (w.cost_limit) parts.push(meter("Cost", w.cost, w.cost_limit, w.cost_left, usd));
    if (!parts.length) parts.push(`<div class="unset">No limit set · used ${fmt(w.tokens)} tokens, ${usd(w.cost)}</div>`);
    const reset = w.requests ? `<div class="hint">${w.window === "month" ? "Resets" : "Oldest usage rolls off"} ${until(w.resets)}</div>` : "";
    return `<div class="limit"><h3>${w.label}</h3>${parts.join("")}${reset}</div>`;
  }).join("");
}
function openLimitsForm() {
  const c = limitsCfg, labels = {"5h": "Last 5 hours", "7d": "Last 7 days", "month": "This month"};
  $("limitsFields").innerHTML = Object.keys(labels).map(w => `<fieldset><legend>${labels[w]}</legend>
    <label>Token limit<input type="number" min="0" step="1000" name="${w}.tokens" value="${c.limits[w].tokens ?? ""}" placeholder="e.g. 2000000"></label>
    <label>Cost limit ($)<input type="number" min="0" step="0.01" name="${w}.cost" value="${c.limits[w].cost ?? ""}" placeholder="e.g. 50"></label></fieldset>`).join("");
  $("countCacheReads").checked = c.count_cache_reads;
  $("limitsForm").classList.add("open");
}
$("editLimits").onclick = async () => {
  limitsCfg = await (await fetch("/api/limits", {cache: "no-store"})).json();
  openLimitsForm();
};
$("cancelLimits").onclick = () => $("limitsForm").classList.remove("open");
$("limitsForm").onsubmit = async e => {
  e.preventDefault();
  const body = {count_cache_reads: $("countCacheReads").checked, limits: {}};
  for (const input of $("limitsFields").querySelectorAll("input")) {
    const [w, k] = input.name.split(".");
    (body.limits[w] ||= {})[k] = input.value === "" ? null : Number(input.value);
  }
  await fetch("/api/limits", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  $("limitsForm").classList.remove("open");
  load();
};

function setProject(p) {
  $("project").value = p;
  schedule();
  load();
  scrollTo({top: 0, behavior: "smooth"});
}

function render(d) {
  const s = d.summary;
  $("meta").innerHTML = `Reading <code>${esc(d.logs_dir)}</code> · ${s.requests} requests · ${when(s.first)} → ${when(s.last)} · updated ${new Date(d.generated_at).toLocaleTimeString()}`;
  const tiles = [
    ["Total tokens", fmt(s.total), `${fmt(s.prompt)} prompt · ${fmt(s.output)} output`],
    ["Estimated cost", usd(s.cost), `vs ${usd(s.uncached_cost)} without caching`],
    ["Cache hit rate", pct(s.cache_hit_rate), `${fmt(s.cache_read)} tokens read from cache`],
    ["Requests", s.requests.toLocaleString(), `${s.sessions} session${s.sessions === 1 ? "" : "s"} · ${s.projects} project${s.projects === 1 ? "" : "s"}`],
    ["Avg context / request", fmt(s.avg_context), `max ${fmt(s.max_context)}`],
    ["Avg output / request", fmt(s.avg_output), `${fmt(s.thinking)} thinking tokens total`],
  ];
  $("tiles").innerHTML = tiles.map(([l, v, n]) => `<div class="card tile"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${n}</div></div>`).join("");
  $("insights").innerHTML = d.insights.map(i => {
    const icon = {good: "✓ Good", warning: "! Watch", critical: "✕ Fix", info: "i Note"}[i.level];
    return `<li><span class="badge ${i.level}">${icon}</span><span>${esc(i.text)}</span></li>`;
  }).join("");

  stackedDays(d.by_day);
  const cbt = s.cost_by_type, ctot = Object.values(cbt).reduce((a, b) => a + b, 0) || 1;
  hbars($("costChart"), SERIES.map(([k, l, c]) => ({label: l, color: c, value: cbt[k], text: `${usd(cbt[k])} · ${pct(100 * cbt[k] / ctot)}`, tip: `<b>${l}</b>${fmt(s[k])} tokens<br>${usd(cbt[k])}`})), "--s2");
  hours(d.by_hour);
  hbars($("modelChart"), d.by_model.map(m => ({label: m.model, value: m.cost, text: `${usd(m.cost)} · ${m.requests} req`, tip: `<b>${esc(m.model)}</b>${fmt(m.total)} tokens<br>${m.requests} requests<br>${usd(m.cost)}`})), "--s1");

  const tok = [["Input", r => fmt(r.input)], ["Cache write", r => fmt(r.cache_write)], ["Cache read", r => fmt(r.cache_read)], ["Output", r => fmt(r.output)]];
  table($("sessions"), [["Session", r => esc(r.session.slice(0, 8)), "mono"], ["Project", r => esc(r.project)], ["Started", r => when(r.start)], ["Requests", r => r.requests],
    ...tok, ["Peak context", r => fmt(r.max_context)], ["Cost", r => usd(r.cost)]], d.sessions);
  table($("tools"), [["Tool", r => esc(r.tool), "mono"], ["Calls", r => r.calls], ["Errors", r => r.errors], ["Est. tokens returned", r => fmt(r.result_tokens_est)], ["Avg / call", r => fmt(r.avg_result_tokens)]], d.tools);
  table($("top"), [["Time", r => when(r.timestamp)], ["Session", r => esc(r.session.slice(0, 8)), "mono"], ["Model", r => esc(r.model)], ["Context", r => fmt(r.context)],
    ["Output", r => fmt(r.output)], ["Tools", r => esc([...new Set(r.tools)].join(", ") || "—")], ["Cost", r => usd(r.cost)]], d.top_requests);
  const sel = d.project || "";
  hbars($("projectShare"), d.projects.slice(0, 8).map(p => ({label: p.project, value: p.cost, color: p.project === sel ? "--s2" : "--s1",
    text: `${usd(p.cost)} · ${pct(p.share)}`, tip: `<b>${esc(p.project)}</b>${fmt(p.total)} tokens<br>${p.sessions} sessions · ${p.requests} requests<br>${usd(p.cost)} (${pct(p.share)} of spend)`})), "--s1", 1100);
  table($("projects"), [["Project", r => esc(r.project)], ["Sessions", r => r.sessions], ["Requests", r => r.requests],
    ["Tokens", r => fmt(r.total)], ["Output", r => fmt(r.output)], ["Cache hit", r => pct(r.cache_hit_rate)], ["Avg context", r => fmt(r.avg_context)],
    ["Peak context", r => fmt(r.max_context)], ["Top model", r => esc(r.top_model || "—")], ["Top tool", r => esc(r.top_tool || "—")],
    ["Last active", r => when(r.last)], ["$/session", r => usd(r.cost_per_session)], ["Cost", r => usd(r.cost)], ["Share", r => pct(r.share)]],
    d.projects, r => `class="clickable${r.project === sel ? " selected" : ""}" data-project="${esc(r.project)}"`);
  $("projects").querySelectorAll("tr[data-project]").forEach(tr => tr.onclick = () => setProject(tr.dataset.project === sel ? "" : tr.dataset.project));

  const ps = $("project"), keep = ps.value;
  ps.innerHTML = '<option value="">All projects</option>' + d.projects.map(p => `<option value="${esc(p.project)}">${esc(p.project)}</option>`).join("");
  if (sel && !d.projects.some(p => p.project === sel)) ps.innerHTML += `<option value="${esc(sel)}">${esc(sel)}</option>`;
  ps.value = keep;
  $("scope").classList.toggle("on", !!sel);
  $("scopeName").textContent = sel;

  renderLimits(d.limits);
  const L = d.lifetime;
  $("lifetimeSince").textContent = L.first ? "since " + new Date(L.first).toLocaleDateString() : "";
  $("lifetime").innerHTML = [
    ["Total tokens", fmt(L.total)], [d.limits.count_cache_reads ? "Counted toward limits" : "Counted toward limits (excl. cache reads)", fmt(L.limit_tokens)],
    ["Output tokens", fmt(L.output)], ["Estimated cost", usd(L.cost)], ["Requests", L.requests.toLocaleString()],
    ["Sessions", L.sessions], ["Projects", L.projects],
  ].map(([l, v]) => `<div>${l}<b>${v}</b></div>`).join("");
}

let timer = null;
async function load() {
  const btn = $("refresh");
  btn.disabled = true; btn.textContent = "Refreshing…";
  try {
    const q = new URLSearchParams();
    if ($("days").value) q.set("days", $("days").value);
    if ($("project").value) q.set("project", $("project").value);
    const res = await fetch("/api/tokens?" + q, {cache: "no-store"});
    if (!res.ok) throw new Error(res.status + " " + res.statusText);
    render(await res.json());
  } catch (e) {
    $("meta").innerHTML = `<span class="err">Refresh failed: ${esc(e.message)}</span>`;
  } finally {
    btn.disabled = false; btn.textContent = "Refresh";
  }
}
function schedule() {
  clearInterval(timer);
  const s = Number($("auto").value);
  try { localStorage.setItem("tokens.auto", s); localStorage.setItem("tokens.days", $("days").value); localStorage.setItem("tokens.project", $("project").value); } catch (e) {}
  if (s) timer = setInterval(load, s * 1000);
}
try {
  $("auto").value = localStorage.getItem("tokens.auto") || "0";
  $("days").value = localStorage.getItem("tokens.days") || "";
  const p = localStorage.getItem("tokens.project");
  if (p) $("project").innerHTML += `<option value="${esc(p)}">${esc(p)}</option>`, $("project").value = p;
} catch (e) {}
$("project").onchange = () => setProject($("project").value);
$("clearProject").onclick = () => setProject("");
$("refresh").onclick = load;
$("auto").onchange = schedule;
$("days").onchange = () => { schedule(); load(); };
schedule();
load();
</script>
</body>
</html>
"""


@bp.route("/tokens")
def dashboard():
    return render_template_string(HTML)


@bp.route("/api/tokens")
def tokens_api():
    days = request.args.get("days", type=int)
    project = request.args.get("project") or None
    return jsonify(analyze(days=days, project=project))


@bp.route("/api/limits", methods=["GET", "POST"])
def limits_api():
    if request.method == "POST":
        return jsonify(save_limits(request.get_json(force=True) or {}))
    return jsonify(load_limits())
