/* Diagram view: a WMATA-style schematic of the same network.
   The layout (positions, bends, line order in corridors, waterways) is computed
   at build time by dfwt/schematic.py and embedded as D.schem; this file only
   draws it, and reuses the page's state (S, scenKey, yi, hidden, pick) and
   functions (choose, fmt) so the plan switcher, year slider, line toggles and
   trip planner behave exactly as in the map view. Hooks in map.html call
   Schem.draw() and Schem.trip().
   There are several versions of the diagram (D.schem.versions: Rail, BRT, All),
   each with its own layout (D.schem.sets[key]); the toggle next to Map/Diagram
   picks one, remembered per viewer and kept in the URL (#diagram/rail). */
(function () {
'use strict';
const SDS = D.schem;
if (!SDS || !SDS.sets) return;
const VERS = SDS.versions.filter(([k]) => SDS.sets[k]);     // [[key, label, modes or null]]
let SD = null, setKey = null;      // the version showing and its layout
const NS = 'http://www.w3.org/2000/svg';
const W = {metro: 0.24, commuter: 0.2, streetcar: 0.14, brt: 0.12};     // stroke widths, layout units (1 = min station spacing); BRT: solid, half weight
const R_ST = 0.17;
const el = (tag, attrs, parent) => {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) if (attrs[k] !== null) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
};
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');

// lineColor (the colour guard) is defined in map.html
// On the BRT diagram every route shares one colour in the data (#00838f), so the routes get
// tints by area (Fort Worth green-teal, Dallas teal, Collin blue, other indigo), each route a
// little lighter or darker than its neighbours in the list, so one can be followed by eye.
const TINT = {fw: 152, dal: 186, col: 208, other: 232};
const hex = (h, sat, l) => {
  const f = n => { const k = (n + h / 30) % 12, a = sat * Math.min(l, 1 - l); return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))).toString(16).padStart(2, '0'); };
  return '#' + f(0) + f(8) + f(4);
};
let tints = new Map();
function makeTints() {
  tints = new Map();
  if (setKey !== 'brt') return;
  const by = {};
  for (const ln of S.lines) if (ln.mode === 'brt') (by[TINT[ln.region] ? ln.region : 'other'] ||= []).push(ln.id);
  for (const [r, ids] of Object.entries(by)) [...new Set(ids)].sort().forEach((id, i) =>
    tints.set(id, hex(TINT[r] + [0, 14, -14, 7, -7][i % 5], 0.85, [0.3, 0.4, 0.25, 0.36, 0.45][(i * 2) % 5])));
}
const colorOf = ln => lineColor(tints.get(ln.id) || ln.color, ln.mode);

const nodeOf = new Map(), eidx = new Map();
const edgeOf = (u, w) => eidx.get(Math.min(u, w) + ',' + Math.max(u, w));
const P = i => SD.nodes[i];
// lines this version lays out (in any plan): a line it leaves out has no path in it
const inSet = lid => Object.values(SD.paths).some(p => p[lid]);

// ---------------------------------------------------------------- DOM
const panel = $('panel');
const host = document.createElement('div');
host.id = 'schem'; host.tabIndex = 0;
host.setAttribute('role', 'application'); host.setAttribute('aria-label', 'Diagram of the DFW transit network');
$('map').after(host);
const svg = el('svg', {'aria-hidden': 'true'}, host);
const vp = el('g', {}, svg);
const G = {};
for (const k of ['water', 'city', 'future', 'glow', 'lines', 'trip', 'walk', 'conn', 'st', 'ring', 'lbl']) G[k] = el('g', {id: 'sch-' + k}, vp);
const pop = document.createElement('div'); pop.id = 'schPop'; host.appendChild(pop);
const tip = document.createElement('div'); tip.id = 'schTip'; host.appendChild(tip);
const zoomBox = document.createElement('div'); zoomBox.id = 'schZoom';
zoomBox.innerHTML = '<button type="button" aria-label="Zoom in">+</button><button type="button" aria-label="Zoom out">−</button><button type="button" aria-label="Fit to screen" style="font-size:.8rem">⤢</button>';
document.body.appendChild(zoomBox);

// view toggle in the panel, right under the title; beside it (diagram view only) the
// version toggle: which modes the diagram shows, each version its own layout
const togs = document.createElement('div');
togs.className = 'togs';
const tog = document.createElement('div');
tog.className = 'viewtog'; tog.setAttribute('role', 'group'); tog.setAttribute('aria-label', 'View');
tog.innerHTML = '<button type="button" data-v="map">Map</button><button type="button" data-v="diagram">Diagram</button>';
const modeTitle = m => m ? m.map(x => D.modes[x] || x).join(', ') : "Rail and the plan's main BRT corridors (every BRT route is on the BRT diagram)";
const vtog = document.createElement('div');
vtog.className = 'viewtog vtog'; vtog.setAttribute('role', 'group'); vtog.setAttribute('aria-label', 'Diagram shows');
vtog.innerHTML = VERS.map(([k, label, m]) => `<button type="button" data-s="${k}" title="${modeTitle(m)}">${label.replace(/ (corridors)$/, ' <span class="vx">$1</span>')}</button>`).join('');
togs.append(tog, vtog);
panel.children[0].after(togs);
if (VERS.length < 2) vtog.hidden = true;
// a note on the diagram when the trip rides a line this version leaves out
const note = document.createElement('div'); note.id = 'schNote'; note.setAttribute('role', 'status'); host.appendChild(note);

// phone bottom sheet: in the diagram view it starts collapsed to the view toggle and
// the year slider, so the diagram gets most of the screen; the handle opens it.
const phone = matchMedia('(max-width: 640px)');
const handle = document.createElement('button');
handle.type = 'button'; handle.className = 'sheet-handle';
handle.innerHTML = '<span aria-hidden="true"></span><b></b>';
panel.prepend(handle);
let sheetChosen = false;          // the reader opened or closed the sheet themselves
function setSheet(min) {
  panel.classList.toggle('min', min);
  handle.setAttribute('aria-expanded', String(!min));
  handle.lastChild.textContent = min ? 'Show details' : 'Hide details';
  if (active && !userMoved) requestAnimationFrame(fit);
  if (note.style.display === 'flex') requestAnimationFrame(placeNote);
}
handle.addEventListener('click', () => { sheetChosen = true; setSheet(!panel.classList.contains('min')); });

// legend (styles of whichever view is showing)
const legend = document.createElement('details'); legend.id = 'legend';
legend.open = !matchMedia('(max-width: 640px)').matches;
legend.innerHTML = '<summary>Legend</summary><div></div>';
document.body.appendChild(legend);

// ---------------------------------------------------------------- version: layout lookups and the static water layer
function loadSet(k) {
  setKey = k; SD = SDS.sets[k];
  nodeOf.clear(); eidx.clear();
  SD.nodes.forEach((n, i) => n[2].forEach(s => nodeOf.set(s, i)));
  SD.edges.forEach((e, i) => eidx.set(e[0] + ',' + e[1], i));
  G.water.textContent = '';
  for (const lk of SD.lakes) el('path', {class: 'lake', d: 'M' + lk.p.map(p => p.join(',')).join('L') + 'Z'}, G.water);
  for (const r of SD.rivers) el('path', {class: 'river', d: 'M' + r.p.map(p => p.join(',')).join('L')}, G.water);
  vtog.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.s === k)));
}

// ---------------------------------------------------------------- geometry
function offsetPolyline(pieces) {
  // pieces: [{p:[x,y], q:[x,y], d}] consecutive; d = offset to the left of travel (y-down: n = (ty, -tx))
  const out = [], at = [];
  const T = pc => { const dx = pc.q[0] - pc.p[0], dy = pc.q[1] - pc.p[1], L = Math.hypot(dx, dy) || 1; return [dx / L, dy / L, L]; };
  for (let i = 0; i < pieces.length; i++) {
    const pc = pieces[i], [tx, ty] = T(pc), nx = ty, ny = -tx;
    if (i === 0) { at.push(out.length); out.push([pc.p[0] + nx * pc.d, pc.p[1] + ny * pc.d]); }
    if (i === pieces.length - 1) { if (pc.node) at.push(out.length); out.push([pc.q[0] + nx * pc.d, pc.q[1] + ny * pc.d]); break; }
    const nx2 = pieces[i + 1], [ux, uy, L2] = T(nx2), mx = uy, my = -ux;
    const a = [pc.q[0] + nx * pc.d, pc.q[1] + ny * pc.d], b = [nx2.p[0] + mx * nx2.d, nx2.p[1] + my * nx2.d];
    if (pc.node) at.push(out.length);
    const cr = tx * uy - ty * ux;
    if (Math.abs(cr) < 1e-6) {
      if (Math.abs(pc.d - nx2.d) < 1e-6) out.push(a);
      else {           // corridor slot changes on a straight run: short diagonal jog
        const s = Math.min(0.35, T(pc)[2] / 3, L2 / 3);
        out.push([a[0] - tx * s, a[1] - ty * s], [b[0] + ux * s, b[1] + uy * s]);
      }
    } else {
      const s = ((b[0] - a[0]) * uy - (b[1] - a[1]) * ux) / cr;   // intersection of the two offset lines
      const ix = a[0] + tx * s, iy = a[1] + ty * s;
      if (Math.hypot(ix - pc.q[0], iy - pc.q[1]) > 4 * Math.max(Math.abs(pc.d), Math.abs(nx2.d)) + 0.05) out.push(a, b);
      else out.push([ix, iy]);
    }
  }
  return {pts: out, at};
}
// stroke widths scale with --f, which thickens lines and ticks a little when zoomed out
const sw = w => `stroke-width:calc(var(--f) * ${w})`;
const dstr = pts => 'M' + pts.map(p => p[0].toFixed(3) + ',' + p[1].toFixed(3)).join('L');

// which routings a line draws this year. A rerouted line (ln.pre = {until, segs}) runs its old
// routing (layout paths[plan + '#pre']) until the new track opens; meanwhile the new track's
// own stretch (stop-to-stop hops the old routing doesn't have: `only`) shows as future.
const PRE = '#pre';
function routings(ln) {
  const cur = SD.paths[scenKey] && SD.paths[scenKey][ln.id];
  const pp = ln.pre && SD.paths[scenKey + PRE] && SD.paths[scenKey + PRE][ln.id];
  if (!pp || D.years[yi] >= ln.pre.until) return cur ? [{key: scenKey, segs: ln.segs}] : [];
  const out = [{key: scenKey + PRE, segs: ln.pre.segs}];
  if (cur) {
    const have = new Set(), only = new Set();
    for (let k = 0; k + 1 < pp[1].length; k++) { const a = pp[0][pp[1][k]], b = pp[0][pp[1][k + 1]]; have.add(a + ',' + b).add(b + ',' + a); }
    for (let k = 0; k + 1 < cur[1].length; k++) if (!have.has(cur[0][cur[1][k]] + ',' + cur[0][cur[1][k + 1]])) only.add(k);
    if (only.size) out.push({key: scenKey, segs: ln.segs, only});
  }
  return out;
}
// slots: line order within each corridor, among the lines drawn on it this year
let slots = new Map();
function computeSlots() {
  const on = new Map();     // edge -> lines drawn on it
  for (const ln of S.lines) {
    if (hidden.has(ln.id)) continue;
    for (const r of routings(ln)) {
      const [path, st] = SD.paths[r.key][ln.id];
      for (let k = 0; k + 1 < st.length; k++) {
        if (r.only && !r.only.has(k)) continue;
        for (let i = st[k]; i < st[k + 1]; i++) {
          const ei = edgeOf(path[i], path[i + 1]);
          if (ei === undefined) continue;
          if (!on.has(ei)) on.set(ei, new Set());
          on.get(ei).add(ln.id);
        }
      }
    }
  }
  slots = new Map();
  SD.edges.forEach((e, i) => slots.set(i, e[3].filter(l => on.has(i) && on.get(i).has(l))));
}
function slotOffset(ei, lid) {
  const ls = slots.get(ei) || [], k = ls.indexOf(lid);
  if (k < 0) return 0;
  return (k - (ls.length - 1) / 2) * SD.pitch;
}
function linePath(lid, key = scenKey) {
  const pr = SD.paths[key] && SD.paths[key][lid];
  if (!pr) return null;
  const [path, stopAt] = pr, pieces = [];
  // ports[i]: where this line's stroke crosses node path[i], on each adjacent leg (offset
  // from the node centre by its corridor slot) -- what the station marker has to cover
  const ports = path.map(() => []);
  const offAt = (a, b, d, at) => { const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1; return [at[0] + dy / L * d, at[1] - dx / L * d]; };
  for (let i = 0; i + 1 < path.length; i++) {
    const u = path[i], w = path[i + 1], ei = edgeOf(u, w);
    if (ei === undefined) continue;
    const E = SD.edges[ei], fwd = E[0] === u, off = slotOffset(ei, lid), d = fwd ? off : -off;
    const pts = [[P(u)[0], P(u)[1]]];
    if (E[2]) pts.push(E[2]);
    pts.push([P(w)[0], P(w)[1]]);
    for (let k = 0; k + 1 < pts.length; k++) pieces.push({p: pts[k], q: pts[k + 1], d, node: k + 1 === pts.length - 1});
    ports[i].push(offAt(pts[0], pts[1], d, pts[0]));
    ports[i + 1].push(offAt(pts[pts.length - 2], pts[pts.length - 1], d, pts[pts.length - 1]));
  }
  if (!pieces.length) return null;
  const r = offsetPolyline(pieces);
  return {pts: r.pts, at: r.at, path, stopAt, ports};
}

// ---------------------------------------------------------------- state & drawing
let active = false, dirty = true, cache = new Map(), drawnNodes = [];
let lastY = null, lastOpen = new Set(), drawnRuns = [];   // year and open stations of the previous draw (for the year-change animation)
const sidLines = new Map();     // sid -> served line indices this year
const openLines = new Set();    // lines with open track this year
function draw() {
  if (!active) { dirty = true; return; }
  dirty = false;
  // prevY: start of this interval; in the first year nothing counts as newly opened
  const Y = D.years[yi], yd = S.years[Y], prevY = yi ? D.years[yi - 1] : Y;
  // stepping forward in time: newly opened track draws itself in, new stations fade in
  const anim = lastY !== null && Y > lastY && !reduceMotion.matches;
  computeSlots();
  for (const g of [G.future, G.glow, G.lines, G.conn, G.st]) g.textContent = '';
  cache = new Map();
  drawnRuns = [];
  openLines.clear();
  makeTints();
  sidLines.clear();
  for (const [li, stops] of yd.runs) for (const s of stops) {
    if (!sidLines.has(s)) sidLines.set(s, []);
    sidLines.get(s).push(li);
  }
  const order = {brt: 0, streetcar: 1, commuter: 2, metro: 3};
  const lines = S.lines.map((ln, li) => [ln, li]).filter(([ln]) => !hidden.has(ln.id))
    .sort((a, b) => order[a[0].mode] - order[b[0].mode]);
  const nodeState = new Map();     // node -> {open:Set(line idx), fut:Set}
  const ns = i => { if (!nodeState.has(i)) nodeState.set(i, {open: new Set(), fut: new Set(), term: false}); return nodeState.get(i); };
  for (const [ln, li] of lines) for (const [ri, r] of routings(ln).entries()) {
    const lp = linePath(ln.id, r.key);
    if (!lp) continue;
    lp.only = r.only;
    cache.set(ri ? ln.id + '#' + ri : ln.id, lp);     // the running routing under the line's id (trip overlay)
    // group stop-to-stop segments into runs: open, opened this interval ('new', as on the map), future
    let runStart = 0, state = null;
    const flush = (k, st) => {
      if (st === null || st === 'skip' || k <= runStart) return;
      const a = lp.at[lp.stopAt[runStart]], b = lp.at[lp.stopAt[k]];
      if (a === undefined || b === undefined) return;
      const pts = lp.pts.slice(a, b + 1);
      drawnRuns.push({pts, fut: st === 'fut'});
      if (st === 'new') el('path', {class: 'glow' + (anim ? ' fadein' : ''), d: dstr(pts), style: sw(2.7 * (W[ln.mode] || W.metro)), 'data-l': ln.id}, G.glow);
      if (st !== 'fut') openLines.add(ln.id);
      stroke(st === 'fut' ? G.future : G.lines, ln, pts, st === 'fut', st === 'new' && anim);
    };
    for (let k = 0; k < r.segs.length; k++) {
      const yr = r.segs[k][0], s = r.only && !r.only.has(k) ? 'skip' : yr > Y ? 'fut' : yr > prevY ? 'new' : 'open';
      if (state === null) { state = s; runStart = k; }
      else if (s !== state) { flush(k, state); state = s; runStart = k; }
    }
    flush(r.segs.length, state);
    lp.stopAt.forEach((j, k) => {
      if (r.only && !r.only.has(k) && !r.only.has(k - 1)) return;
      const v = lp.path[j], st = ns(v);
      const open = SD.nodes[v][2].some(s => (sidLines.get(s) || []).includes(li));
      (open ? st.open : st.fut).add(li);
      if (!r.only && (k === 0 || k === lp.stopAt.length - 1) && lp.path[0] !== lp.path[lp.path.length - 1]) st.term = true;   // a ring has no terminus
    });
  }
  // stations
  drawnNodes = [];
  const R = new Map();
  for (const [v, st] of nodeState) {
    const open = st.open.size > 0;
    const shape = marker(v);
    R.set(v, shape);
    drawnNodes.push({v, open, st, shape});
  }
  // walk links the model uses (SD.transfers: stations within the walk radius, or linked in
  // transfers.csv) that the layout keeps as two markers: a short one (the two side by side,
  // flag 0) is one solid connector, straight across when the markers overlap along an axis;
  // a longer one is not drawn (it would only cross the core), except faintly around the
  // station that is selected or hovered (walks)
  byNode = new Map(drawnNodes.map(n => [n.v, n]));
  for (const [a, b, far] of SD.transfers) {
    const A = byNode.get(a), B = byNode.get(b);
    if (!A || !B || far) continue;
    const cls = A.open && B.open ? '' : ' fut', xy = connector(A.shape, B.shape);
    el('line', {class: 'conn-o' + cls, x1: xy[0], y1: xy[1], x2: xy[2], y2: xy[3], 'stroke-width': 0.24}, G.conn);
    el('line', {class: 'conn-i' + cls, x1: xy[0], y1: xy[1], x2: xy[2], y2: xy[3], 'stroke-width': 0.12}, G.conn);
  }
  walks();
  for (const n of drawnNodes) drawMarker(n, G.st, anim && n.open && !lastOpen.has(n.v));
  lastY = Y;
  lastOpen = new Set(drawnNodes.filter(n => n.open).map(n => n.v));
  placeLabels();
  if (pick.length) rings();
  legendDraw();
  if (popNode !== null) {      // an open popup follows the year, plan and hidden lines
    if (byNode.has(popNode)) showPop(popNode); else hidePop();
  } else if (popLine) {
    if (cache.has(popLine.id)) showLinePop(popLine.id, popLine.x, popLine.y); else hidePop();
  }
  if (hlLine && !cache.has(hlLine)) highlight(null); else if (hlLine) highlight(hlLine);
}
// future track: a thin, faint grey hairline (no colour, casing or dashes; schematic.css),
// so the network still to come reads as a quiet plan behind the open one
function stroke(g, ln, pts, fut, grow) {
  const d = dstr(pts), w = (W[ln.mode] || W.metro) * (setKey === 'brt' ? 1.35 : 1), col = colorOf(ln), l = ln.id;
  if (fut) {
    el('path', {class: 'ln fut', d, stroke: col, style: sw(w * 0.45), 'data-l': l}, g);
  } else if (ln.mode === 'commuter') {
    const grp = el('g', {class: grow ? 'fadein' : '', 'data-l': l}, g);
    el('path', {class: 'ln', d, stroke: col, style: sw(w)}, grp);
    el('path', {class: 'case', d, style: sw(w * 0.36), 'stroke-dasharray': '0.5 0.3'}, grp);
  } else {
    el('path', {class: 'ln' + (grow ? ' grow' : ''), d, stroke: col, style: sw(w), pathLength: grow ? 1 : null, 'data-l': l}, g);
  }
}
// marker at node v: the smallest rounded rectangle, aligned to one of the four
// octilinear axes, around the points where the stopping lines cross the station.
// One line -> a dot; a bundle -> a capsule across it (WMATA); lines meeting from
// several directions -> a compact rounded box, never a disc wider than the bundle.
const AXES = [0, 1, 2, 3].map(k => [Math.cos(k * Math.PI / 4), Math.sin(k * Math.PI / 4)]);
function marker(v) {
  const pts = [];
  for (const lp of cache.values()) lp.stopAt.forEach((j, k) => {
    if (lp.path[j] === v && !(lp.only && !(lp.only.has(k) && lp.only.has(k - 1)))) pts.push(...lp.ports[j]);   // future stretch: its own stops only
  });
  if (!pts.length) pts.push([P(v)[0], P(v)[1]]);
  let best = null;
  AXES.forEach(([ux, uy], k) => {
    let a0 = Infinity, a1 = -Infinity, b0 = Infinity, b1 = -Infinity;
    for (const [x, y] of pts) { const a = x * ux + y * uy, b = -x * uy + y * ux; a0 = Math.min(a0, a); a1 = Math.max(a1, a); b0 = Math.min(b0, b); b1 = Math.max(b1, b); }
    // snap sub-pixel spreads (rounding, miter noise) to a clean dot or capsule
    if (a1 - a0 < 0.04) a0 = a1 = (a0 + a1) / 2;
    if (b1 - b0 < 0.04) b0 = b1 = (b0 + b1) / 2;
    const area = (a1 - a0 + 2 * R_ST) * (b1 - b0 + 2 * R_ST) + (k % 2) * 1e-3;     // ties -> horizontal/vertical
    if (!best || area < best.area - 1e-9) best = {area, ux, uy, a0, a1, b0, b1};
  });
  const {ux, uy, a0, a1, b0, b1} = best;
  const at = (a, b) => [a * ux - b * uy, a * uy + b * ux];
  const corners = [at(a0, b0), at(a1, b0), at(a1, b1), at(a0, b1)];
  // drop repeated corners: 1 point (dot), 2 (capsule) or 4 (box)
  const hull = corners.filter((p, i) => corners.findIndex(q => Math.abs(q[0] - p[0]) + Math.abs(q[1] - p[1]) < 1e-6) === i);
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of hull) { x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); }
  const r = R_ST + 0.035;
  return {hull, x: (x0 + x1) / 2, y: (y0 + y1) / 2, box: [x0 - r, y0 - r, x1 + r, y1 + r]};
}
function drawMarker(n, g, fadeIn) {
  const s = n.shape, big = n.st.open.size + n.st.fut.size > 1 || SD.nodes[n.v][2].length > 1, ow = big ? 0.075 : 0.05;
  const d = 'M' + s.hull.map(p => p[0].toFixed(3) + ',' + p[1].toFixed(3)).join('L') + (s.hull.length > 2 ? 'Z' : (s.hull.length === 1 ? 'l0,0' : ''));
  const grp = el('g', {class: n.open ? (fadeIn ? 'fadein' : '') : 'fut'}, g);
  // a station that only opens later: a small faint dot, not a full white marker
  const r = n.open ? R_ST : R_ST * 0.62;
  el('path', {d, fill: 'var(--st-ink)', stroke: 'var(--st-ink)', style: `stroke-width:calc(var(--f) * ${2 * r} + ${2 * ow})`, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, grp);
  el('path', {d, fill: 'var(--st-fill)', stroke: 'var(--st-fill)', style: sw(2 * r), 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, grp);
}

// a connector between two markers: vertical or horizontal where their boxes overlap across
// (at the middle of the overlap), else from centre to centre
function connector(A, B) {
  const a = A.box, b = B.box, ox0 = Math.max(a[0], b[0]), ox1 = Math.min(a[2], b[2]), oy0 = Math.max(a[1], b[1]), oy1 = Math.min(a[3], b[3]);
  if (ox1 - ox0 > 0.05) { const x = (ox0 + ox1) / 2; return [x, A.y, x, B.y]; }
  if (oy1 - oy0 > 0.05) { const y = (oy0 + oy1) / 2; return [A.x, y, B.x, y]; }
  return [A.x, A.y, B.x, B.y];
}
// the longer walk links of one station (the one selected, or hovered with a mouse), drawn
// faintly while it is: where else one can walk to from here
let byNode = new Map(), hoverNode = null;
function walks() {
  G.walk.textContent = '';
  const v = hoverNode !== null ? hoverNode : popNode;
  if (v === null || !byNode.has(v)) return;
  for (const [a, b, far, longWalk] of SD.transfers) {
    if (!far || (a !== v && b !== v)) continue;
    const A = byNode.get(a), B = byNode.get(b);
    if (!A || !B) continue;
    el('line', {class: 'conn-w' + (longWalk ? ' lw' : ''), x1: A.shape.x, y1: A.shape.y, x2: B.shape.x, y2: B.shape.y,
      'stroke-width': 0.08, 'stroke-dasharray': '0.01 0.2'}, G.walk);
  }
}
// the name shown for a node: the stations it stands for that this plan serves this year (a
// merged interchange, "Akard · Metro Center"), or its own name
function nodeName(v) {
  const sids = SD.nodes[v][2];
  if (sids.length < 2) return SD.nodes[v][3];
  const names = [...new Set(sids.filter(s => sidLines.has(s)).map(s => D.stations[s] ? D.stations[s][0] : null).filter(Boolean))];
  return names.length ? names.join(' · ') : SD.nodes[v][3];
}

// ---------------------------------------------------------------- labels (greedy, 8 positions, redone per zoom)
// Station markers are hard obstacles, other labels are hard obstacles with a
// little air around them, drawn lines are a cost (zoomed out, a minor station
// whose label would sit on lines is left for the hover tooltip). Stations sharing a name
// (SD.lead groups "Uptown", "Uptown", "Irving W3", ...) are labelled once while
// they are close together on screen. Area names are placed first, at the
// overview only, in the nearest clear space to their spot.
const meas = document.createElement('canvas').getContext('2d');
let lblK = -1;
function placeLabels() {
  G.lbl.textContent = '';
  G.city.textContent = '';
  lblK = view.k;
  const small = host.clientWidth <= 640;
  const k = view.k, kf = k / (fitK || k), px = Math.max(9.5, Math.min(small ? 11.5 : 13, (small ? 8 : 9) + Math.log2(kf) * 1.6 + 1.5)), fs = px / k;
  meas.font = `500 ${px}px Barlow, "Helvetica Neue", Arial, sans-serif`;
  const cell = fs * 1.2, grid = new Map(), lineGrid = new Set(), openGrid = new Set(), lc = fs * 0.5;
  const key = (i, j) => i + ',' + j;
  const addBox = b => { for (let i = Math.floor(b[0] / cell); i <= Math.floor(b[2] / cell); i++) for (let j = Math.floor(b[1] / cell); j <= Math.floor(b[3] / cell); j++) { const kk = key(i, j); if (!grid.has(kk)) grid.set(kk, []); grid.get(kk).push(b); } };
  const hits = b => { for (let i = Math.floor(b[0] / cell); i <= Math.floor(b[2] / cell); i++) for (let j = Math.floor(b[1] / cell); j <= Math.floor(b[3] / cell); j++) for (const o of grid.get(key(i, j)) || []) if (o[0] < b[2] && b[0] < o[2] && o[1] < b[3] && b[1] < o[3]) return true; return false; };
  const lineCost = (b, g = lineGrid) => { let c = 0; for (let i = Math.floor(b[0] / lc); i <= Math.floor(b[2] / lc); i++) for (let j = Math.floor(b[1] / lc); j <= Math.floor(b[3] / lc); j++) if (g.has(key(i, j))) c++; return c; };
  // rasterize drawn lines into a fine grid (cost only): all of them, and the open ones
  for (const {pts, fut} of drawnRuns) for (let i = 0; i + 1 < pts.length; i++) {
    const [a, b] = [pts[i], pts[i + 1]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.ceil(L / (lc / 2)) + 1;
    for (let s = 0; s <= n; s++) {
      const kk = key(Math.floor((a[0] + (b[0] - a[0]) * s / n) / lc), Math.floor((a[1] + (b[1] - a[1]) * s / n) / lc));
      lineGrid.add(kk);
      if (!fut) openGrid.add(kk);
    }
  }
  for (const n of drawnNodes) addBox(n.shape.box);
  // viewport (in layout units) so off-screen labels don't block on-screen ones; labels may run
  // past the free area on the right, but not under the zoom buttons
  const fa = freeArea(), x0 = (fa[0] - view.tx) / k, y0 = (fa[1] - view.ty) / k, x1 = (host.clientWidth - 6 - view.tx) / k, y1 = (fa[3] - view.ty) / k, m = 6;
  const inView = b => b[0] >= x0 && b[2] <= x1 && b[1] >= y0 && b[3] <= y1;
  if (zoomBox.offsetParent) {
    const zr = zoomBox.getBoundingClientRect(), hr = host.getBoundingClientRect(), g = 6;
    addBox([(zr.left - hr.left - g - view.tx) / k, (zr.top - hr.top - g - view.ty) / k, (zr.right - hr.left + g - view.tx) / k, (zr.bottom - hr.top + g - view.ty) / k]);
  }
  // area names: overview only, nearest spot (spiral search) clear of stations and lines
  if (kf < 2.4) {
    const cpx = small ? 12 : 14.5, cfs = cpx / k;
    meas.font = `700 ${cpx}px "Barlow Condensed", "Arial Narrow", Arial, sans-serif`;
    for (const [t, cx, cy] of SD.labels) {
      const T = t.toUpperCase(), w = (meas.measureText(T).width + 0.14 * cpx * T.length) / k, h = cfs;
      // nearest spot clear of open lines (faint future ones may pass under it) within ~9% of the view's diagonal (an area name labels an
      // area, not a point); failing that, one crossing a line or two (the label has a
      // halo); failing that, no label rather than a misleading one
      // (cx, cy) is the area's core station (schematic.py): the name stands beside it
      let best = null;
      const reach = Math.max(45, Math.min(92, 0.06 * Math.hypot(fa[2] - fa[0], fa[3] - fa[1])));
      for (const [maxR, maxCost] of [[reach * 0.6, 0], [reach * 0.6, 3], [reach, 0], [reach, 4], [reach, 8], [reach, 14], [reach * 2.2, 1e9]]) {
        for (const r of [0, 8, 16, 24, 34, 45, 60, 75, 92, 110, 130]) {
          if (best || r > maxR) break;
          const nA = r ? 16 : 1;
          for (let q = 0; q < nA && !best; q++) {
            const ang = q / nA * 2 * Math.PI, x = cx + Math.cos(ang) * r / k, y = cy + Math.sin(ang) * r * 0.8 / k;
            const bx = [x - w / 2 - cfs * 0.3, y - h * 0.85, x + w / 2 + cfs * 0.3, y + h * 0.3];
            if (inView(bx) && !hits(bx) && lineCost(bx, openGrid) <= maxCost) best = [x, y, bx];
          }
        }
      }
      if (!best) continue;
      addBox(best[2]);
      const e = el('text', {class: 'city', x: best[0].toFixed(3), y: best[1].toFixed(3), 'font-size': cfs.toFixed(4), 'stroke-width': (3 / k).toFixed(4)}, G.city);
      e.textContent = T;
    }
    meas.font = `500 ${px}px Barlow, "Helvetica Neue", Arial, sans-serif`;
  }
  const showFut = kf > 2.2;
  const lead = v => SD.lead ? SD.lead[v] : v;
  const lines = n => n.st.open.size + n.st.fut.size;
  const cand = drawnNodes.filter(n => { const s = n.shape; return (n.open || showFut) && s.x > x0 - m && s.x < x1 + m && s.y > y0 - m && s.y < y1 + m; });
  cand.sort((a, b) => (b.open - a.open) || (lines(b) - lines(a)) || (b.st.term - a.st.term) || ((lead(a.v) !== a.v) - (lead(b.v) !== b.v)) || (a.v - b.v));
  // route names at the ends of the BRT routes (they share one colour on the map): placed
  // before the minor stations' names, after the interchanges' and termini's
  const pills = routePills(k, fs);
  const nMajor = cand.filter(n => lines(n) > 1 || n.st.term).length;
  // a repeated name is skipped within 190 px; a variant ("Irving W3" near "Irving")
  // only while zoomed out, so every distinct name shows when zoomed well in
  // air kept around a placed name: a word space across, a third of a line above and below
  const gap = 3 / k, padX = fs * 0.6, padY = fs * 0.32, near = 190 / k, nearVariant = near * Math.max(0, Math.min(1, (4 - kf) / 3));
  const lm = fs * 0.12;          // a label just touching a line counts as on it
  const placed = new Map();       // group lead -> [[x, y, name]] of its placed labels
  cand.forEach((n, ci) => {
    if (ci === nMajor) placePills(pills);
    const s = n.shape, g = lead(n.v), name = nodeName(n.v);
    if ((placed.get(g) || []).some(([x, y, nm]) => Math.hypot(x - s.x, y - s.y) < (nm === name ? near : nearVariant))) return;
    const bx = s.box, ex = (bx[2] - bx[0]) / 2, ey = (bx[3] - bx[1]) / 2;
    const dx = ex + gap, dy = ey + gap, dd = Math.min(ex, ey) * 0.72 + gap, f = fs * 0.9;
    let best = null, bc = 1e9, bl = 0;
    // a long name may also be set on two lines
    for (const rows of wrapName(name)) {
      const w = Math.max(...rows.map(r => meas.measureText(r).width)) / k, h = fs * 1.05 * rows.length;
      const opts = [[s.x + dx, s.y - h / 2], [s.x - dx - w, s.y - h / 2], [s.x + dd, s.y - dd - h], [s.x + dd, s.y + dd],
        [s.x - dd - w, s.y - dd - h], [s.x - dd - w, s.y + dd], [s.x - w / 2, s.y - dy - h], [s.x - w / 2, s.y + dy],
        // a little further off, still clearly its own
        [s.x + dx + f, s.y - h / 2], [s.x - dx - w - f, s.y - h / 2], [s.x - w / 2, s.y - dy - h - f * 0.6], [s.x - w / 2, s.y + dy + f * 0.6],
        [s.x + dd + f * 0.7, s.y - dd - h - f * 0.7], [s.x + dd + f * 0.7, s.y + dd + f * 0.7], [s.x - dd - w - f * 0.7, s.y - dd - h - f * 0.7], [s.x - dd - w - f * 0.7, s.y + dd + f * 0.7]];
      opts.forEach(([ox, oy], i) => {
        const b = [ox, oy, ox + w, oy + h];
        if (hits(b) || !inView(b)) return;
        const lcost = lineCost([b[0] - lm, b[1] - lm, b[2] + lm, b[3] + lm]);
        const c = lcost * 3 + i * 0.25 + (i >= 8 ? 2.5 : 0) + (rows.length > 1 ? 1.5 : 0);
        if (c < bc) { bc = c; best = {b, rows, h}; bl = lcost; }
      });
    }
    if (!best) return;
    const minor = lines(n) <= 1 && !n.st.term;
    if (minor && bl > (kf < 2.5 ? 2 : 6)) return;      // zoomed well in, a name is worth crossing a line
    const b = best.b;
    addBox([b[0] - padX, b[1] - padY, b[2] + padX, b[3] + padY]);
    if (!placed.has(g)) placed.set(g, []);
    placed.get(g).push([s.x, s.y, name]);
    const t = el('text', {class: 'lbl' + (n.open ? '' : ' fut') + (lines(n) > 1 ? ' x' : ''), x: b[0].toFixed(3),
      y: (b[1] + fs * 1.05 * 0.8).toFixed(3), 'font-size': fs.toFixed(4), 'stroke-width': (2.6 / k).toFixed(4)}, G.lbl);
    if (best.rows.length === 1) t.textContent = name;
    else best.rows.forEach((r, i) => { const ts = el('tspan', {x: b[0].toFixed(3), dy: i ? (fs * 1.05).toFixed(4) : 0}, t); ts.textContent = r; });
  });
  if (nMajor >= cand.length) placePills(pills);

  // ---- route pills: candidates per open BRT route end, placed greedily where clear
  function routePills(k, fs) {
    const out = [];
    if (kf < 1.25 && setKey !== 'brt') return out;
    const pf = fs * 0.86;
    meas.font = `700 ${pf * k}px Barlow, "Helvetica Neue", Arial, sans-serif`;
    for (const [key, lp] of cache) {
      const id = key.split('#')[0], ln = lineOf(id);
      if (key.includes('#') || !ln || ln.mode !== 'brt' || !openLines.has(id) || hidden.has(id)) continue;
      const txt = shortName(ln), w = meas.measureText(txt).width / k + pf * 0.8, h = pf * 1.35;
      for (const end of lp.path[0] === lp.path[lp.path.length - 1] ? [0] : [0, 1]) {     // a ring: one name
        const pts = end ? lp.pts.slice().reverse() : lp.pts, v = end ? lp.path[lp.path.length - 1] : lp.path[0];
        const nd = drawnNodes.find(d => d.v === v);
        if (!nd) continue;
        let j = 1; while (j < pts.length - 1 && Math.hypot(pts[j][0] - pts[0][0], pts[j][1] - pts[0][1]) < 1e-6) j++;
        const ux = pts[0][0] - pts[j][0], uy = pts[0][1] - pts[j][1], L = Math.hypot(ux, uy) || 1;
        out.push({id, ln, txt, w, h, pf, x: nd.shape.x, y: nd.shape.y, box: nd.shape.box, ux: ux / L, uy: uy / L});
      }
    }
    meas.font = `500 ${px}px Barlow, "Helvetica Neue", Arial, sans-serif`;
    return out;
  }
  function placePills(list) {
    const done = new Set();
    for (const p of list) {
      if (done.has(p.id + (p.ux > 0) + (p.uy > 0) + p.x)) continue;
      const ex = (p.box[2] - p.box[0]) / 2 + gap * 2, ey = (p.box[3] - p.box[1]) / 2 + gap * 2;
      const cands = [];
      // straight on past the terminus first, then round it, then stacked a row further out
      for (let r = 0; r < 3; r++) {
        const cx = p.x + p.ux * (ex + p.w / 2 + r * p.w * 0.3), cy = p.y + p.uy * (ey + p.h / 2 + r * p.h);
        cands.push([cx, cy]);
        for (const [sx, sy] of [[1, 0], [-1, 0], [0, -1], [0, 1]]) cands.push([p.x + sx * (ex + p.w / 2) + sx * r * p.w * 0.2, p.y + sy * (ey + p.h / 2 + r * p.h * 1.1) + (sx ? (r - 1) * p.h * 1.1 : 0)]);
      }
      for (const [cx, cy] of cands) {
        const b = [cx - p.w / 2, cy - p.h / 2, cx + p.w / 2, cy + p.h / 2];
        if (!inView(b) || hits(b) || lineCost(b) > 1) continue;
        addBox([b[0] - gap, b[1] - gap, b[2] + gap, b[3] + gap]);
        const g = el('g', {class: 'pill', 'data-l': p.id}, G.lbl), col = colorOf(p.ln);
        el('rect', {x: b[0], y: b[1], width: p.w, height: p.h, rx: p.h / 2, fill: col, 'stroke-width': (1.2 / k).toFixed(4)}, g);
        const t = el('text', {x: cx, y: cy + p.pf * 0.36, 'font-size': p.pf.toFixed(4), fill: inkOn(col)}, g);
        t.textContent = p.txt;
        done.add(p.id + (p.ux > 0) + (p.uy > 0) + p.x);
        break;
      }
    }
  }
}
// a station name as one row, and (over WRAP characters) as two rows broken at the slash or
// space nearest its middle ("Southwestern Medical / District/Parkland")
const WRAP = 20;
function wrapName(name) {
  const out = [[name]];
  if (name.length <= WRAP) return out;
  let best = -1, bd = 1e9;
  for (let i = 1; i < name.length - 1; i++) {
    const c = name[i];
    if (c !== ' ' && c !== '/') continue;
    const d = Math.abs(i - name.length / 2) - (c === '/' ? 2 : 0);
    if (d < bd) { bd = d; best = i; }
  }
  if (best < 0) return out;
  const a = name.slice(0, best + (name[best] === '/' ? 1 : 0)).trim(), b = name.slice(best + 1).trim();
  if (a && b) out.push([a, b]);
  return out;
}

// ---------------------------------------------------------------- trip overlay
let lastTrip = null;
function rings() {
  G.ring.textContent = '';
  for (const s of pick) {
    const v = nodeOf.get(s);
    if (v === undefined) continue;
    const d = drawnNodes.find(n => n.v === v), sh = d ? d.shape : {x: P(v)[0], y: P(v)[1], box: [P(v)[0] - R_ST, P(v)[1] - R_ST, P(v)[0] + R_ST, P(v)[1] + R_ST]};
    const r = Math.hypot(sh.box[2] - sh.box[0], sh.box[3] - sh.box[1]) / 2 + 0.25;
    el('circle', {class: 'ring', cx: sh.x, cy: sh.y, r, 'stroke-width': 0.13}, G.ring);
  }
}
// the trip rides a line this version leaves out: say so, and offer the version showing most of it
function tripNote(legs, yd) {
  const rides = legs ? legs.filter(l => l.t === 'ride').map(l => S.lines[yd.runs[l.ri][0]]) : [];
  const off = rides.filter(ln => !inSet(ln.id));
  if (!off.length) { note.style.display = 'none'; return; }
  const shows = k => rides.filter(ln => Object.values(SDS.sets[k].paths).some(p => p[ln.id])).length;
  let best = setKey;
  for (const [k] of VERS) if (shows(k) > shows(best)) best = k;
  const label = k => VERS.find(v => v[0] === k)[1];
  const modes = [...new Set(off.map(ln => (D.modes[ln.mode] || ln.mode).toLowerCase()))].join(' and ');
  note.innerHTML = `<span>This trip also rides ${modes}, not on the ${label(setKey)} diagram.</span>` +
    (best !== setKey ? `<button type="button" data-s="${best}">Show ${label(best)}</button>` : '') +
    '<button type="button" class="x" aria-label="Dismiss">×</button>';
  note.style.display = 'flex';
  placeNote();
}
function placeNote() {     // phone: just above the bottom sheet
  note.style.bottom = phone.matches ? (host.clientHeight - panel.getBoundingClientRect().top + 10) + 'px' : '';
}
note.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.s) setVersion(b.dataset.s, true); else note.style.display = 'none';
});
function trip(legs, yd) {
  lastTrip = legs ? [legs, yd] : null;
  if (!active) return;
  G.trip.textContent = '';
  rings();
  tripNote(legs, yd);
  if (!legs) return;
  const sidOf = n => n[0] === 'P' ? n.slice(1) : yd.runs[+n.slice(1).split(':')[0]][1][+n.split(':')[1]];
  for (const l of legs) {
    if (l.t === 'ride') {
      const ln = S.lines[yd.runs[l.ri][0]], f = nodeOf.get(sidOf(l.from)), t = nodeOf.get(sidOf(l.to));
      if (!inSet(ln.id)) continue;      // not in this version (tripNote says so)
      const lp = cache.get(ln.id) || linePath(ln.id);
      if (!lp) continue;
      let best = null;
      lp.path.forEach((u, i) => { if (u !== f) return; lp.path.forEach((w, j) => { if (w === t && (!best || Math.abs(j - i) < Math.abs(best[1] - best[0]))) best = [i, j]; }); });
      if (!best) continue;
      let [i, j] = best; if (i > j) [i, j] = [j, i];
      const a = lp.at[i], b = lp.at[j];
      if (a === undefined || b === undefined) continue;
      el('path', {class: 'trip', d: dstr(lp.pts.slice(a, b + 1)), stroke: ln.color, 'stroke-width': 0.85}, G.trip);
    } else if (l.t === 'walk') {
      const f = nodeOf.get(sidOf(l.from)), t = nodeOf.get(sidOf(l.to));
      if (f === undefined || t === undefined) continue;
      el('line', {class: 'walk', x1: P(f)[0], y1: P(f)[1], x2: P(t)[0], y2: P(t)[1], 'stroke-width': 0.12, 'stroke-dasharray': '0.05 0.25'}, G.trip);
    }
  }
}

// ---------------------------------------------------------------- route highlight
// Hovering a line (mouse) or tapping it lights that route up and fades the rest; a tap also
// opens a small card with its name and ends. A tap elsewhere clears it.
let hlLine = null, hoverLine = null;
function highlight(id) {
  hlLine = id;
  const on = hoverLine || hlLine;
  host.classList.toggle('hl', !!on);
  vp.querySelectorAll('[data-l]').forEach(e => e.classList.toggle('on', e.getAttribute('data-l') === on));
}
function setHover(id) {
  if (id === hoverLine) return;
  hoverLine = id; highlight(hlLine);
}
function nearestLine(px, py, maxPx) {
  const x = (px - view.tx) / view.k, y = (py - view.ty) / view.k, lim = maxPx / view.k;
  let best = null, bd = lim;
  for (const [key, lp] of cache) {
    const id = key.split('#')[0];
    if (hidden.has(id)) continue;
    const pts = lp.pts;
    for (let i = 0; i + 1 < pts.length; i++) {
      const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
      if (Math.min(ax, bx) - lim > x || Math.max(ax, bx) + lim < x || Math.min(ay, by) - lim > y || Math.max(ay, by) + lim < y) continue;
      const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / L2));
      const d = Math.hypot(x - ax - t * dx, y - ay - t * dy);
      if (d < bd) { bd = d; best = id; }
    }
  }
  return best;
}
const lineOf = id => S.lines.find(l => l.id === id);
const shortName = ln => ln.name.replace(/\s+(BRT|Line)$/i, '');

// ---------------------------------------------------------------- popup / tooltip
let popNode = null, popLine = null;
function popupHtml(v) {
  // mirrors the map popup in map.html: name, serving lines, residents/jobs, boardings
  const sids = SD.nodes[v][2], served = sids.filter(s => sidLines.has(s));
  const sid = served[0] || sids[0], st = D.stations[sid];
  const lis = [...new Set(sids.flatMap(s => sidLines.get(s) || []))].filter(li => !hidden.has(S.lines[li].id));
  const chips = lis.map(li => `<span class="chip" style="background:${S.lines[li].color};color:${inkOn(S.lines[li].color)}">${S.lines[li].name}</span>`).join('');
  const b = sids.reduce((a, s) => a + (S.boardings[s] || 0), 0);
  return `<div class="pop"><b>${nodeName(v)}</b><div>${chips}</div><div class="m">${fmt(st[3])} residents · ${fmt(st[4])} jobs within 1 km` +
    (b ? `<br>${fmt(b)} competitive commuters board here by ${D.years[D.years.length - 1]} (end of plan)` : '') + `</div></div>`;
}
function lineHtml(id) {
  const ln = lineOf(id), lp = cache.get(id);
  if (!ln || !lp) return '';
  const ends = [lp.path[0], lp.path[lp.path.length - 1]].map(nodeName);
  const Y = D.years[yi], open = openLines.has(id);
  return `<div class="pop"><span class="chip" style="background:${colorOf(ln)};color:${inkOn(colorOf(ln))}">${ln.name}</span>` +
    `<div class="m">${D.modes[ln.mode] || ln.mode} · ${ends[0]} – ${ends[1]}` +
    (open ? '' : `<br>Not open in ${Y}${ln.first ? ` (opens ${ln.first})` : ''}`) + `</div></div>`;
}
function showLinePop(id, x, y) {
  popNode = null; popLine = {id, x, y};
  walks();
  pop.innerHTML = '<button type="button" class="x" aria-label="Close">×</button>' + lineHtml(id);
  pop.querySelector('.x').onclick = e => { e.stopPropagation(); hidePop(); highlight(null); };
  pop.style.display = 'block';
  posPop();
}
function showPop(v) {
  popNode = v; popLine = null;
  walks();
  pop.innerHTML = '<button type="button" class="x" aria-label="Close">×</button>' + popupHtml(v);
  pop.querySelector('.x').onclick = e => { e.stopPropagation(); hidePop(); };
  pop.style.display = 'block';
  posPop();
}
function hidePop() { popNode = null; popLine = null; pop.style.display = 'none'; walks(); }
function posPop() {
  if (popLine) { pop.style.left = (popLine.x * view.k + view.tx) + 'px'; pop.style.top = (popLine.y * view.k + view.ty) + 'px'; return; }
  if (popNode === null) return;
  const n = drawnNodes.find(d => d.v === popNode);
  if (!n) { hidePop(); return; }
  pop.style.left = (n.shape.x * view.k + view.tx) + 'px';
  pop.style.top = (n.shape.y * view.k + view.ty) + 'px';
}
function nearest(px, py, maxPx, openOnly) {
  const x = (px - view.tx) / view.k, y = (py - view.ty) / view.k;
  let best = null, bd = Infinity;
  for (const n of drawnNodes) {
    if (openOnly && !n.open) continue;
    const b = n.shape.box, d = Math.hypot(Math.max(b[0] - x, 0, x - b[2]), Math.max(b[1] - y, 0, y - b[3]));
    if (d < bd) { bd = d; best = n; }
  }
  return best && bd * view.k <= maxPx ? best : null;
}
function clickAt(px, py) {
  const n = nearest(px, py, 14, true);
  if (!n) {
    const id = nearestLine(px, py, 12);
    if (id) {   // a line: highlighted, and its diagram in the panel
      highlight(id); hidePop();
      const li = S.lines.findIndex(l => l.id === id);
      if (li >= 0 && window.openLine) openLine(li); else showLinePop(id, (px - view.tx) / view.k, (py - view.ty) / view.k);
    }
    else { hidePop(); highlight(null); }
    return;
  }
  const sids = SD.nodes[n.v][2], sid = sids.find(s => sidLines.has(s)) || sids[0];
  showPop(n.v);
  choose(sid);
  // a finished trip is read in the sheet: open it
  if (pick.length === 2 && panel.classList.contains('min')) { sheetChosen = true; setSheet(false); }
}

// ---------------------------------------------------------------- zoom & pan
const view = {k: 1, tx: 0, ty: 0};
let fitK = 0, userMoved = false, lblTimer = null;
function apply(relabel) {
  vp.setAttribute('transform', `translate(${view.tx.toFixed(2)},${view.ty.toFixed(2)}) scale(${view.k.toFixed(5)})`);
  G.city.style.opacity = Math.max(0, Math.min(1, 2.6 - view.k / (fitK || view.k)));
  vp.style.setProperty('--f', Math.max(1, Math.min(1.35, 3.3 / (W.metro * view.k))).toFixed(3));
  // rivers: a soft band at the overview, never wider than ~8 px when zoomed in
  vp.style.setProperty('--rw', Math.min(0.55, 8 / view.k).toFixed(4));
  posPop();
  if (relabel !== false) { clearTimeout(lblTimer); lblTimer = setTimeout(() => { if (active) placeLabels(); }, 140); }
}
function bounds() {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const n of SD.nodes) { x0 = Math.min(x0, n[0]); y0 = Math.min(y0, n[1]); x1 = Math.max(x1, n[0]); y1 = Math.max(y1, n[1]); }
  return [x0 - 1.5, y0 - 1.5, x1 + 1.5, y1 + 1.5];
}
function freeArea() {
  const w = host.clientWidth, h = host.clientHeight, r = panel.getBoundingClientRect();
  if (w <= 640) return [8, 8, w - 8, Math.max(r.top, h * 0.4) - 8];
  return [r.right + 12, 12, w - 56, h - 12];
}
function fit() {
  let [x0, y0, x1, y1] = bounds();
  const [a0, b0, a1, b1] = freeArea();
  // a tall, narrow screen (phone): let the long east-west tails run off the sides
  // (pan to reach them) so the two downtowns get room; the height still fits
  if ((b1 - b0) / (a1 - a0) > 1.3 * (y1 - y0) / (x1 - x0)) {
    const xs = SD.nodes.map(n => n[0]).sort((a, b) => a - b), q = p => xs[Math.round(p * (xs.length - 1))];
    x0 = Math.max(x0, q(0.03) - 1.5); x1 = Math.min(x1, q(0.97) + 1.5);
  }
  view.k = fitK = Math.min((a1 - a0) / (x1 - x0), (b1 - b0) / (y1 - y0));
  view.tx = (a0 + a1) / 2 - (x0 + x1) / 2 * view.k;
  view.ty = (b0 + b1) / 2 - (y0 + y1) / 2 * view.k;
  userMoved = false;
  apply();
}
function zoomAt(px, py, f) {
  const k = Math.max(fitK * 0.6, Math.min(fitK * 10, view.k * f));
  f = k / view.k;
  view.tx = px - (px - view.tx) * f; view.ty = py - (py - view.ty) * f; view.k = k;
  userMoved = true;
  apply();
}
host.addEventListener('wheel', e => {
  e.preventDefault();
  const r = host.getBoundingClientRect();
  zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0018)));
}, {passive: false});
const ptrs = new Map();
let down = null, pinch = null;
host.addEventListener('pointerdown', e => {
  if (e.target.closest('#schPop, #schNote')) return;
  host.setPointerCapture(e.pointerId);
  ptrs.set(e.pointerId, [e.clientX, e.clientY]);
  if (ptrs.size === 1) down = {x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty, moved: false};
  if (ptrs.size === 2) {
    const [a, b] = [...ptrs.values()];
    pinch = {d: Math.hypot(a[0] - b[0], a[1] - b[1]), k: view.k, tx: view.tx, ty: view.ty, mx: (a[0] + b[0]) / 2, my: (a[1] + b[1]) / 2};
    if (down) down.moved = true;
  }
});
host.addEventListener('pointermove', e => {
  const r = host.getBoundingClientRect();
  if (!ptrs.has(e.pointerId)) {        // hover tooltip: a station's name, or a line's (lit up)
    if (e.pointerType !== 'mouse') return;
    const px = e.clientX - r.left, py = e.clientY - r.top, n = nearest(px, py, 10, false);
    const id = n ? null : nearestLine(px, py, 7);
    setHover(id);
    if ((n ? n.v : null) !== hoverNode) { hoverNode = n ? n.v : null; walks(); }
    if (n) { tip.textContent = nodeName(n.v); tip.style.left = (n.shape.x * view.k + view.tx) + 'px'; tip.style.top = (n.shape.y * view.k + view.ty) + 'px'; tip.style.display = 'block'; }
    else if (id) { tip.textContent = lineOf(id).name; tip.style.left = px + 'px'; tip.style.top = py + 'px'; tip.style.display = 'block'; }
    else tip.style.display = 'none';
    return;
  }
  ptrs.set(e.pointerId, [e.clientX, e.clientY]);
  if (pinch && ptrs.size >= 2) {
    const [a, b] = [...ptrs.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
    const k = Math.max(fitK * 0.6, Math.min(fitK * 10, pinch.k * d / pinch.d)), f = k / pinch.k;
    const mx = (a[0] + b[0]) / 2 - r.left, my = (a[1] + b[1]) / 2 - r.top, ox = pinch.mx - r.left, oy = pinch.my - r.top;
    view.k = k; view.tx = mx - (ox - pinch.tx) * f; view.ty = my - (oy - pinch.ty) * f;
    userMoved = true; apply();
  } else if (down) {
    const dx = e.clientX - down.x, dy = e.clientY - down.y;
    if (Math.hypot(dx, dy) > 4) { down.moved = true; host.classList.add('drag'); tip.style.display = 'none'; }
    if (down.moved) { view.tx = down.tx + dx; view.ty = down.ty + dy; userMoved = true; apply(false); }
  }
});
const up = e => {
  if (!ptrs.has(e.pointerId)) return;
  ptrs.delete(e.pointerId);
  if (ptrs.size < 2) pinch = null;
  if (ptrs.size === 0) {
    host.classList.remove('drag');
    if (down && !down.moved && e.type === 'pointerup') { const r = host.getBoundingClientRect(); clickAt(e.clientX - r.left, e.clientY - r.top); }
    else if (down && down.moved) apply();
    down = null;
  }
};
host.addEventListener('pointerup', up);
host.addEventListener('pointercancel', up);
host.addEventListener('pointerleave', () => { tip.style.display = 'none'; setHover(null); if (hoverNode !== null) { hoverNode = null; walks(); } });
host.addEventListener('dblclick', e => { const r = host.getBoundingClientRect(); zoomAt(e.clientX - r.left, e.clientY - r.top, 2); });
host.addEventListener('keydown', e => {
  const c = [host.clientWidth / 2, host.clientHeight / 2], step = 60;
  if (e.key === '+' || e.key === '=') zoomAt(...c, 1.4);
  else if (e.key === '-') zoomAt(...c, 1 / 1.4);
  else if (e.key.startsWith('Arrow')) { view.tx += e.key === 'ArrowLeft' ? step : e.key === 'ArrowRight' ? -step : 0; view.ty += e.key === 'ArrowUp' ? step : e.key === 'ArrowDown' ? -step : 0; apply(); }
  else return;
  e.preventDefault();
});
const zb = zoomBox.querySelectorAll('button');
zb[0].onclick = () => zoomAt(host.clientWidth / 2, host.clientHeight / 2, 1.5);
zb[1].onclick = () => zoomAt(host.clientWidth / 2, host.clientHeight / 2, 1 / 1.5);
zb[2].onclick = () => fit();
window.addEventListener('resize', () => { if (active && !userMoved) fit(); else if (active) apply(); });

// ---------------------------------------------------------------- legend
const sample = (h, label) => `<div class="r"><svg viewBox="0 0 38 12">${h}</svg><span>${label}</span></div>`;
function legendDraw() {
  const ink = 'var(--st-ink)', fill = 'var(--st-fill)', grey = 'var(--muted)';
  let h = '';
  if (active) {
    const vm = (VERS.find(v => v[0] === setKey) || [])[2], has = m => !vm || vm.includes(m);   // the version's modes
    if (has('metro')) h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="5" stroke-linecap="round"/><circle cx="19" cy="6" r="3.6" fill="${fill}" stroke="${ink}" stroke-width="1.1"/>`, D.modes.metro);
    if (has('commuter')) h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="4.2" stroke-linecap="round"/><line x1="1" y1="6" x2="37" y2="6" stroke="${fill}" stroke-width="1.5" stroke-dasharray="10 6"/>`, D.modes.commuter);
    if (has('brt')) h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="2.4" stroke-linecap="round"/>${has('metro') ? '' : `<circle cx="19" cy="6" r="3" fill="${fill}" stroke="${ink}" stroke-width="1"/>`}`, D.modes.brt);
    if (setKey === 'brt') h += sample(['fw', 'dal', 'col', 'other'].map((r, i) => `<line x1="${1 + i * 9.5}" y1="6" x2="${8 + i * 9.5}" y2="6" stroke="${lineColor(hex(TINT[r], 0.85, 0.36), 'brt')}" stroke-width="3.2" stroke-linecap="round"/>`).join(''),
      'BRT by area: Fort Worth, Dallas, Collin, other');
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="var(--glow)" stroke-width="11" stroke-linecap="round" opacity=".5"/><line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="5" stroke-linecap="round"/>`, 'Opened this interval');
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="2.2" stroke-linecap="round" opacity=".4"/><circle cx="19" cy="6" r="2.2" fill="${fill}" stroke="${ink}" stroke-width=".9" opacity=".5"/>`, 'Not yet open');
    h += sample(`<line x1="1" y1="3" x2="37" y2="3" stroke="${grey}" stroke-width="2.6"/><line x1="1" y1="9" x2="37" y2="9" stroke="${grey}" stroke-width="2.6"/><rect x="15" y="-1" width="8" height="14" rx="4" fill="${fill}" stroke="${ink}" stroke-width="1.3"/>`, 'Interchange');
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="var(--water)" stroke-width="4" stroke-linecap="round"/>`, 'Waterways');
  } else {
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="4.5" stroke-linecap="round"/>`, D.modes.metro);
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="4"/><line x1="1" y1="6" x2="37" y2="6" stroke="var(--bg)" stroke-width="1.3" stroke-dasharray="6 4"/>`, D.modes.commuter);
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="2.4" stroke-linecap="round"/>`, D.modes.brt);
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="var(--glow)" stroke-width="10" opacity=".45"/><line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="4.5"/>`, 'Opened this interval');
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="6" stroke-dasharray="1 8" stroke-linecap="round" opacity=".7"/>`, 'Under construction');
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="4.5" stroke-linecap="round" opacity=".2"/>`, 'Not yet open');
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="var(--water)" stroke-width="4" stroke-linecap="round"/>`, 'Waterways');
    if (window.layerKey) h += layerKey();   // the data layer's colour key (map.html)
  }
  legend.lastElementChild.innerHTML = h;
}

// ---------------------------------------------------------------- waterways on the geographic map (toggleable overlay)
if (typeof map !== 'undefined' && window.L && SDS.geoWater) {
  map.createPane('water').style.zIndex = 350;
  const water = getComputedStyle(document.documentElement).getPropertyValue('--water').trim() || '#d3e6f3';
  const rend = L.canvas({pane: 'water'}), wl = L.layerGroup();
  for (const p of SDS.geoWater.lakes) L.polygon(p, {renderer: rend, pane: 'water', stroke: false, fillColor: water, fillOpacity: 0.9, interactive: false}).addTo(wl);
  for (const p of SDS.geoWater.rivers) L.polyline(p, {renderer: rend, pane: 'water', color: water, weight: 3.5, opacity: 0.95, interactive: false}).addTo(wl);
  wl.addTo(map);
  if (typeof layerCtl !== 'undefined') layerCtl.addOverlay(wl, 'Waterways');
}

// ---------------------------------------------------------------- view switching (remembered; #map, #diagram or #diagram/<version> in the URL)
let fitted = false;
const hasSet = k => VERS.some(v => v[0] === k);
function saveHash() {
  try { history.replaceState(null, '', active ? '#diagram/' + setKey : '#map'); } catch (e) { /* file:// or sandboxed */ }
}
function setView(v, save) {
  active = v === 'diagram';
  document.body.classList.toggle('diagram', active);
  tog.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === v)));
  if (save) {
    try { localStorage.setItem('dfwt.view', v); } catch (e) { /* storage unavailable */ }
    saveHash();
  }
  if (!sheetChosen) setSheet(active && phone.matches);
  if (active) {
    if (!fitted) { fitted = true; fit(); }
    draw();
    if (lastTrip) trip(...lastTrip); else rings();
  } else {
    hidePop(); tip.style.display = 'none'; note.style.display = 'none';
    map.invalidateSize();
    legendDraw();
  }
}
// another version: its own layout, so the view is fitted afresh
function setVersion(k, save) {
  if (!hasSet(k)) return;
  if (save) {
    try { localStorage.setItem('dfwt.diagram', k); } catch (e) { /* storage unavailable */ }
  }
  if (k !== setKey) {
    loadSet(k);
    hidePop(); tip.style.display = 'none'; hoverLine = null; highlight(null);
    dirty = true; lastY = null;
    if (active) { fit(); draw(); if (lastTrip) trip(...lastTrip); else { rings(); note.style.display = 'none'; } }
    else fitted = false;
  }
  if (save) saveHash();
}
tog.addEventListener('click', e => { const b = e.target.closest('button'); if (b) setView(b.dataset.v, true); });
vtog.addEventListener('click', e => { const b = e.target.closest('button'); if (b) setVersion(b.dataset.s, true); });
function fromHash() {      // [view, version or null]
  const [v, s] = location.hash.slice(1).split('/');
  return v === 'diagram' || v === 'map' ? [v, hasSet(s) ? s : null] : [null, null];
}
window.addEventListener('hashchange', () => {
  const [v, s] = fromHash();
  if (s) setVersion(s, false);
  if (v) setView(v, false);
});
let initial = 'map', set0 = SDS.default;
try {
  initial = localStorage.getItem('dfwt.view') || 'map';
  const s = localStorage.getItem('dfwt.diagram');
  if (hasSet(s)) set0 = s;
} catch (e) { /* storage unavailable */ }
const [hv, hs] = fromHash();
if (hv) initial = hv;
if (hs) set0 = hs;
loadSet(hasSet(set0) ? set0 : VERS[0][0]);
// locate(sid): screen position of a station in the diagram (used by the screenshot checks)
const locate = sid => { const v = nodeOf.get(sid); return v === undefined ? null : [P(v)[0] * view.k + view.tx, P(v)[1] * view.k + view.ty]; };
// focus(sid, z): centre a station in the free area at z times the fitted zoom (screenshot checks)
const focus = (sid, z) => {
  const v = nodeOf.get(sid);
  if (v === undefined) return false;
  const fa = freeArea();
  view.k = fitK * z; view.tx = (fa[0] + fa[2]) / 2 - P(v)[0] * view.k; view.ty = (fa[1] + fa[3]) / 2 - P(v)[1] * view.k;
  userMoved = true; apply();
  return true;
};
window.Schem = {draw, trip: (legs, yd) => trip(legs, yd), setView, setVersion, version: () => setKey, locate, focus, zoomAt, sheet: setSheet, legend: legendDraw};
setView(initial === 'diagram' ? 'diagram' : 'map', false);
})();
