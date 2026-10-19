/* Diagram view: a WMATA-style schematic of the same network.
   The layout (positions, bends, line order in corridors, waterways) is computed
   at build time by dfwt/schematic.py and embedded as D.schem; this file only
   draws it, and reuses the page's state (S, scenKey, yi, hidden, pick) and
   functions (choose, fmt) so the plan switcher, year slider, line toggles and
   trip planner behave exactly as in the map view. Hooks in map.html call
   Schem.draw() and Schem.trip(). */
(function () {
'use strict';
const SD = D.schem;
if (!SD) return;
const NS = 'http://www.w3.org/2000/svg';
const W = {metro: 0.24, commuter: 0.2, brt: 0.13};     // stroke widths, layout units (1 = min station spacing)
const R_ST = 0.17, PITCH = SD.pitch;
const el = (tag, attrs, parent) => {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
};
const nodeOf = new Map();
SD.nodes.forEach((n, i) => n[2].forEach(s => nodeOf.set(s, i)));
const eidx = new Map();
SD.edges.forEach((e, i) => eidx.set(e[0] + ',' + e[1], i));
const edgeOf = (u, w) => eidx.get(Math.min(u, w) + ',' + Math.max(u, w));
const P = i => SD.nodes[i];

// ---------------------------------------------------------------- DOM
const panel = $('panel');
const host = document.createElement('div');
host.id = 'schem'; host.tabIndex = 0;
host.setAttribute('role', 'application'); host.setAttribute('aria-label', 'Diagram of the DFW transit network');
$('map').after(host);
const svg = el('svg', {'aria-hidden': 'true'}, host);
const vp = el('g', {}, svg);
const G = {};
for (const k of ['water', 'city', 'future', 'lines', 'trip', 'conn', 'st', 'ring', 'lbl']) G[k] = el('g', {id: 'sch-' + k}, vp);
const pop = document.createElement('div'); pop.id = 'schPop'; host.appendChild(pop);
const tip = document.createElement('div'); tip.id = 'schTip'; host.appendChild(tip);
const zoomBox = document.createElement('div'); zoomBox.id = 'schZoom';
zoomBox.innerHTML = '<button type="button" aria-label="Zoom in">+</button><button type="button" aria-label="Zoom out">−</button><button type="button" aria-label="Fit to screen" style="font-size:.8rem">⤢</button>';
document.body.appendChild(zoomBox);

// view toggle in the panel, right under the title
const tog = document.createElement('div');
tog.className = 'viewtog'; tog.setAttribute('role', 'group'); tog.setAttribute('aria-label', 'View');
tog.innerHTML = '<button type="button" data-v="map">Map</button><button type="button" data-v="diagram">Diagram</button>';
panel.children[0].after(tog);

// legend (styles of whichever view is showing)
const legend = document.createElement('details'); legend.id = 'legend';
legend.open = !matchMedia('(max-width: 640px)').matches;
legend.innerHTML = '<summary>Legend</summary><div></div>';
document.body.appendChild(legend);

// ---------------------------------------------------------------- static layers: water, cities
for (const lk of SD.lakes) el('path', {class: 'lake', d: 'M' + lk.p.map(p => p.join(',')).join('L') + 'Z'}, G.water);
for (const r of SD.rivers) el('path', {class: 'river', 'stroke-width': 0.55, d: 'M' + r.p.map(p => p.join(',')).join('L')}, G.water);
for (const [t, x, y] of SD.labels) {
  const e = el('text', {class: 'city', x, y, 'font-size': 1.35}, G.city);
  e.textContent = t.toUpperCase();
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

// slots: line order within each corridor, among the lines showing in this plan
let slots = new Map();
function computeSlots() {
  const present = new Set(S.lines.filter(l => !hidden.has(l.id)).map(l => l.id));
  slots = new Map();
  SD.edges.forEach((e, i) => {
    const ls = e[3].filter(l => present.has(l));
    slots.set(i, ls);
  });
}
function slotOffset(ei, lid) {
  const ls = slots.get(ei) || [], k = ls.indexOf(lid);
  if (k < 0) return 0;
  return (k - (ls.length - 1) / 2) * PITCH;
}
function linePath(lid) {
  const pr = SD.paths[scenKey] && SD.paths[scenKey][lid];
  if (!pr) return null;
  const [path, stopAt] = pr, pieces = [];
  for (let i = 0; i + 1 < path.length; i++) {
    const u = path[i], w = path[i + 1], ei = edgeOf(u, w);
    if (ei === undefined) continue;
    const E = SD.edges[ei], fwd = E[0] === u, off = slotOffset(ei, lid), d = fwd ? off : -off;
    const pts = [[P(u)[0], P(u)[1]]];
    if (E[2]) pts.push(E[2]);
    pts.push([P(w)[0], P(w)[1]]);
    for (let k = 0; k + 1 < pts.length; k++) pieces.push({p: pts[k], q: pts[k + 1], d, node: k + 1 === pts.length - 1});
  }
  if (!pieces.length) return null;
  const r = offsetPolyline(pieces);
  return {pts: r.pts, at: r.at, path, stopAt};
}

// ---------------------------------------------------------------- state & drawing
let active = false, dirty = true, cache = new Map(), drawnNodes = [];
const sidLines = new Map();     // sid -> served line indices this year
function draw() {
  if (!active) { dirty = true; return; }
  dirty = false;
  const Y = D.years[yi], yd = S.years[Y];
  computeSlots();
  for (const g of [G.future, G.lines, G.conn, G.st]) g.textContent = '';
  cache = new Map();
  sidLines.clear();
  for (const [li, stops] of yd.runs) for (const s of stops) {
    if (!sidLines.has(s)) sidLines.set(s, []);
    sidLines.get(s).push(li);
  }
  const order = {brt: 0, commuter: 1, metro: 2};
  const lines = S.lines.map((ln, li) => [ln, li]).filter(([ln]) => !hidden.has(ln.id))
    .sort((a, b) => order[a[0].mode] - order[b[0].mode]);
  const nodeState = new Map();     // node -> {open:Set(line idx), fut:Set}
  const ns = i => { if (!nodeState.has(i)) nodeState.set(i, {open: new Set(), fut: new Set(), term: false}); return nodeState.get(i); };
  for (const [ln, li] of lines) {
    const lp = linePath(ln.id);
    if (!lp) continue;
    cache.set(ln.id, lp);
    // group stop-to-stop segments into open / future runs
    let runStart = 0, state = null;
    const flush = (k, st) => {
      if (st === null || k <= runStart) return;
      const a = lp.at[lp.stopAt[runStart]], b = lp.at[lp.stopAt[k]];
      if (a === undefined || b === undefined) return;
      stroke(st ? G.future : G.lines, ln, lp.pts.slice(a, b + 1), st);
    };
    for (let k = 0; k < ln.segs.length; k++) {
      const fut = ln.segs[k][0] > Y;
      if (state === null) { state = fut; runStart = k; }
      else if (fut !== state) { flush(k, state); state = fut; runStart = k; }
    }
    flush(ln.segs.length, state);
    lp.stopAt.forEach((j, k) => {
      const v = lp.path[j], st = ns(v);
      const open = SD.nodes[v][2].some(s => (sidLines.get(s) || []).includes(li));
      (open ? st.open : st.fut).add(li);
      if (k === 0 || k === lp.stopAt.length - 1) st.term = true;
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
  for (const [a, b] of SD.transfers) {
    const A = drawnNodes.find(n => n.v === a), B = drawnNodes.find(n => n.v === b);
    if (!A || !B) continue;
    const cls = A.open && B.open ? '' : ' fut', xy = [P(a)[0], P(a)[1], P(b)[0], P(b)[1]];
    el('line', {class: 'conn-o' + cls, x1: xy[0], y1: xy[1], x2: xy[2], y2: xy[3], 'stroke-width': 0.24}, G.conn);
    el('line', {class: 'conn-i' + cls, x1: xy[0], y1: xy[1], x2: xy[2], y2: xy[3], 'stroke-width': 0.12}, G.conn);
  }
  for (const n of drawnNodes) drawMarker(n, G.st);
  placeLabels();
  if (pick.length) rings();
  legendDraw();
}
function stroke(g, ln, pts, fut) {
  const d = dstr(pts), w = W[ln.mode] || W.metro, cls = 'ln' + (fut ? ' fut' : '');
  if (ln.mode === 'brt') {
    el('path', {class: cls, d, stroke: ln.color, style: sw(w), 'stroke-dasharray': '0.34 0.16', 'stroke-linecap': 'butt'}, g);
  } else if (ln.mode === 'commuter') {
    const grp = el('g', {class: fut ? 'fut' : ''}, g);
    el('path', {class: 'ln', d, stroke: ln.color, style: sw(w)}, grp);
    el('path', {class: 'case', d, style: sw(w * 0.36), 'stroke-dasharray': '0.5 0.3'}, grp);
  } else {
    el('path', {class: cls, d, stroke: ln.color, style: sw(w)}, g);
  }
}
// marker at node v: the rounded convex hull of the points where the lines cross
// the station, so a straight bundle gets a capsule and a junction a compact blob
function hull(pts) {
  const P2 = [...pts].sort((a, b) => a[0] - b[0] || a[1] - b[1]), cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], hi = [];
  for (const p of P2) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 1e-9) lo.pop(); lo.push(p); }
  for (const p of P2.reverse()) { while (hi.length >= 2 && cr(hi[hi.length - 2], hi[hi.length - 1], p) <= 1e-9) hi.pop(); hi.push(p); }
  return lo.slice(0, -1).concat(hi.slice(0, -1));
}
function marker(v) {
  const pts = [[P(v)[0], P(v)[1]]];
  for (const lp of cache.values()) lp.path.forEach((u, j) => { const k = lp.at[j]; if (u === v && k !== undefined) pts.push(lp.pts[k]); });
  // miter joins can sit away from the node; keep the marker close to it
  let h = hull(pts.filter(p => Math.hypot(p[0] - P(v)[0], p[1] - P(v)[1]) < 0.62));
  if (h.length > 2) {
    // nearly collinear -> capsule along the farthest pair; otherwise a round interchange
    let a = h[0], b = h[1], best = -1;
    for (const p of h) for (const q of h) { const d = Math.hypot(p[0] - q[0], p[1] - q[1]); if (d > best) { best = d; a = p; b = q; } }
    const ux = (b[0] - a[0]) / best, uy = (b[1] - a[1]) / best;
    const wide = Math.max(...h.map(p => Math.abs((p[0] - a[0]) * uy - (p[1] - a[1]) * ux)));
    if (wide < 0.1) h = [a, b];
    else {
      const cx = h.reduce((t, p) => t + p[0], 0) / h.length, cy = h.reduce((t, p) => t + p[1], 0) / h.length;
      const r = Math.max(...h.map(p => Math.hypot(p[0] - cx, p[1] - cy)));
      h = [[cx, cy]];
      const R = r + 0.035;
      return {hull: h, rad: r, x: cx, y: cy, box: [cx - R - R_ST, cy - R - R_ST, cx + R + R_ST, cy + R + R_ST]};
    }
  }
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of h) { x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); }
  const r = R_ST + 0.035;
  return {hull: h, x: (x0 + x1) / 2, y: (y0 + y1) / 2, box: [x0 - r, y0 - r, x1 + r, y1 + r]};
}
function drawMarker(n, g) {
  const s = n.shape, big = n.st.open.size + n.st.fut.size > 1 || SD.nodes[n.v][2].length > 1, ow = big ? 0.07 : 0.05;
  const d = 'M' + s.hull.map(p => p[0].toFixed(3) + ',' + p[1].toFixed(3)).join('L') + (s.hull.length > 2 ? 'Z' : (s.hull.length === 1 ? 'l0,0' : ''));
  const grp = el('g', {class: n.open ? '' : 'fut'}, g);
  if (s.rad) {          // round interchange
    el('circle', {cx: s.x, cy: s.y, r: s.rad + R_ST, fill: 'var(--st-fill)', stroke: 'var(--st-ink)', 'stroke-width': ow * 1.3}, grp);
    return;
  }
  el('path', {d, fill: 'var(--st-ink)', stroke: 'var(--st-ink)', style: `stroke-width:calc(var(--f) * ${2 * R_ST} + ${2 * ow})`, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, grp);
  el('path', {d, fill: 'var(--st-fill)', stroke: 'var(--st-fill)', style: sw(2 * R_ST), 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, grp);
}

// ---------------------------------------------------------------- labels (greedy, 8 positions, redone per zoom)
const meas = document.createElement('canvas').getContext('2d');
let lblK = -1;
function placeLabels() {
  G.lbl.textContent = '';
  lblK = view.k;
  const small = host.clientWidth <= 640;
  const k = view.k, px = Math.max(9.5, Math.min(small ? 11.5 : 13, (small ? 8 : 9) + Math.log2(k / (fitK || k)) * 1.6 + 1.5)), fs = px / k;
  meas.font = `500 ${px}px Barlow, "Helvetica Neue", Arial, sans-serif`;
  const cell = fs * 1.2, grid = new Map(), lineGrid = new Set();
  const key = (i, j) => i + ',' + j;
  const boxes = [];
  const addBox = b => { boxes.push(b); for (let i = Math.floor(b[0] / cell); i <= Math.floor(b[2] / cell); i++) for (let j = Math.floor(b[1] / cell); j <= Math.floor(b[3] / cell); j++) { const kk = key(i, j); if (!grid.has(kk)) grid.set(kk, []); grid.get(kk).push(b); } };
  const hits = b => { for (let i = Math.floor(b[0] / cell); i <= Math.floor(b[2] / cell); i++) for (let j = Math.floor(b[1] / cell); j <= Math.floor(b[3] / cell); j++) for (const o of grid.get(key(i, j)) || []) if (o[0] < b[2] && b[0] < o[2] && o[1] < b[3] && b[1] < o[3]) return true; return false; };
  const lineCost = b => { let c = 0; for (let i = Math.floor(b[0] / cell); i <= Math.floor(b[2] / cell); i++) for (let j = Math.floor(b[1] / cell); j <= Math.floor(b[3] / cell); j++) if (lineGrid.has(key(i, j))) c++; return c; };
  // rasterize drawn lines into the coarse grid (cost only), markers as hard boxes
  for (const lp of cache.values()) for (let i = 0; i + 1 < lp.pts.length; i++) {
    const [a, b] = [lp.pts[i], lp.pts[i + 1]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.ceil(L / (cell / 2)) + 1;
    for (let s = 0; s <= n; s++) lineGrid.add(key(Math.floor((a[0] + (b[0] - a[0]) * s / n) / cell), Math.floor((a[1] + (b[1] - a[1]) * s / n) / cell)));
  }
  for (const n of drawnNodes) addBox(n.shape.box);
  // viewport (in layout units) so off-screen labels don't block on-screen ones
  const fa = freeArea(), x0 = (fa[0] - view.tx) / k, y0 = (fa[1] - view.ty) / k, x1 = (Math.min(fa[2] + 44, host.clientWidth - 4) - view.tx) / k, y1 = (fa[3] - view.ty) / k, m = 6;
  const showFut = k > (fitK || k) * 2.2;
  const cand = drawnNodes.filter(n => { const s = n.shape; return (n.open || showFut) && s.x > x0 - m && s.x < x1 + m && s.y > y0 - m && s.y < y1 + m; });
  cand.sort((a, b) => (b.open - a.open) || ((b.st.open.size + b.st.fut.size) - (a.st.open.size + a.st.fut.size)) || (b.st.term - a.st.term) || (a.v - b.v));
  const gap = 3 / k;
  for (const n of cand) {
    const name = SD.nodes[n.v][3], w = meas.measureText(name).width / k, h = fs * 1.05, s = n.shape, bx = s.box;
    const ex = (bx[2] - bx[0]) / 2, ey = (bx[3] - bx[1]) / 2;
    const dx = ex + gap, dy = ey + gap, dd = Math.min(ex, ey) * 0.72 + gap;
    const opts = [[s.x + dx, s.y - h / 2], [s.x - dx - w, s.y - h / 2], [s.x + dd, s.y - dd - h], [s.x + dd, s.y + dd],
      [s.x - dd - w, s.y - dd - h], [s.x - dd - w, s.y + dd], [s.x - w / 2, s.y - dy - h], [s.x - w / 2, s.y + dy]];
    let best = null, bc = 1e9;
    opts.forEach(([bx, by], i) => {
      const b = [bx, by, bx + w, by + h];
      if (hits(b)) return;
      const out = (b[0] < x0 ? x0 - b[0] : 0) + (b[2] > x1 ? b[2] - x1 : 0) + (b[1] < y0 ? y0 - b[1] : 0) + (b[3] > y1 ? b[3] - y1 : 0);
      if (out > 0) return;
      const c = lineCost(b) * 2 + i * 0.25;
      if (c < bc) { bc = c; best = b; }
    });
    if (!best) continue;
    addBox(best);
    const t = el('text', {class: 'lbl' + (n.open ? '' : ' fut') + (n.st.open.size + n.st.fut.size > 1 ? ' x' : ''), x: best[0].toFixed(3),
      y: (best[1] + h * 0.8).toFixed(3), 'font-size': fs.toFixed(4), 'stroke-width': (2.6 / k).toFixed(4)}, G.lbl);
    t.textContent = name;
  }
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
function trip(legs, yd) {
  lastTrip = legs ? [legs, yd] : null;
  if (!active) return;
  G.trip.textContent = '';
  rings();
  if (!legs) return;
  const sidOf = n => n[0] === 'P' ? n.slice(1) : yd.runs[+n.slice(1).split(':')[0]][1][+n.split(':')[1]];
  for (const l of legs) {
    if (l.t === 'ride') {
      const ln = S.lines[yd.runs[l.ri][0]], f = nodeOf.get(sidOf(l.from)), t = nodeOf.get(sidOf(l.to));
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

// ---------------------------------------------------------------- popup / tooltip
let popNode = null;
function popupHtml(v) {
  // mirrors the map popup in map.html: name, serving lines, residents/jobs, boardings
  const sids = SD.nodes[v][2], served = sids.filter(s => sidLines.has(s));
  const sid = served[0] || sids[0], st = D.stations[sid];
  const lis = [...new Set(sids.flatMap(s => sidLines.get(s) || []))].filter(li => !hidden.has(S.lines[li].id));
  const chips = lis.map(li => `<span class="chip" style="background:${S.lines[li].color}">${S.lines[li].name}</span>`).join('');
  const b = sids.reduce((a, s) => a + (S.boardings[s] || 0), 0);
  return `<div class="pop"><b>${SD.nodes[v][3]}</b><div>${chips}</div><div class="m">${fmt(st[3])} residents · ${fmt(st[4])} jobs within 1 km` +
    (b ? `<br>${fmt(b)} competitive commuters board here in 2070` : '') + `</div></div>`;
}
function showPop(v) {
  popNode = v;
  pop.innerHTML = '<button type="button" class="x" aria-label="Close">×</button>' + popupHtml(v);
  pop.querySelector('.x').onclick = e => { e.stopPropagation(); hidePop(); };
  pop.style.display = 'block';
  posPop();
}
function hidePop() { popNode = null; pop.style.display = 'none'; }
function posPop() {
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
  if (!n) { hidePop(); return; }
  const sids = SD.nodes[n.v][2], sid = sids.find(s => sidLines.has(s)) || sids[0];
  showPop(n.v);
  choose(sid);
}

// ---------------------------------------------------------------- zoom & pan
const view = {k: 1, tx: 0, ty: 0};
let fitK = 0, userMoved = false, lblTimer = null;
function apply(relabel) {
  vp.setAttribute('transform', `translate(${view.tx.toFixed(2)},${view.ty.toFixed(2)}) scale(${view.k.toFixed(5)})`);
  G.city.style.opacity = Math.max(0, Math.min(1, 2.6 - view.k / (fitK || view.k)));
  vp.style.setProperty('--f', Math.max(1, Math.min(1.35, 3.3 / (W.metro * view.k))).toFixed(3));
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
  const [x0, y0, x1, y1] = bounds(), [a0, b0, a1, b1] = freeArea();
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
  if (e.target.closest('#schPop')) return;
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
  if (!ptrs.has(e.pointerId)) {        // hover tooltip
    const n = e.pointerType === 'mouse' ? nearest(e.clientX - r.left, e.clientY - r.top, 10, false) : null;
    if (n) { tip.textContent = SD.nodes[n.v][3]; tip.style.left = (n.shape.x * view.k + view.tx) + 'px'; tip.style.top = (n.shape.y * view.k + view.ty) + 'px'; tip.style.display = 'block'; }
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
host.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
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
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="5" stroke-linecap="round"/><circle cx="19" cy="6" r="3.6" fill="${fill}" stroke="${ink}" stroke-width="1.1"/>`, D.modes.metro);
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="4.2" stroke-linecap="round"/><line x1="1" y1="6" x2="37" y2="6" stroke="${fill}" stroke-width="1.5" stroke-dasharray="10 6"/>`, D.modes.commuter);
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="2.8" stroke-dasharray="7 3.4"/>`, D.modes.brt);
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="5" stroke-linecap="round" opacity=".22"/>`, 'Not yet open');
    h += sample(`<line x1="1" y1="3" x2="37" y2="3" stroke="${grey}" stroke-width="2.6"/><line x1="1" y1="9" x2="37" y2="9" stroke="${grey}" stroke-width="2.6"/><rect x="15" y="-1" width="8" height="14" rx="4" fill="${fill}" stroke="${ink}" stroke-width="1.2"/>`, 'Interchange');
  } else {
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="4.5" stroke-linecap="round"/>`, D.modes.metro);
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="3" stroke-dasharray="8 5"/>`, D.modes.commuter);
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="3" stroke-dasharray="2 5" stroke-linecap="round"/>`, D.modes.brt);
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="${grey}" stroke-width="4.5" stroke-linecap="round" opacity=".2"/>`, 'Not yet open');
    h += sample(`<line x1="1" y1="6" x2="37" y2="6" stroke="var(--water)" stroke-width="4" stroke-linecap="round"/>`, 'Waterways');
  }
  legend.lastElementChild.innerHTML = h;
}

// ---------------------------------------------------------------- waterways on the geographic map (toggleable overlay)
if (typeof map !== 'undefined' && window.L && SD.geoWater) {
  map.createPane('water').style.zIndex = 350;
  const water = getComputedStyle(document.documentElement).getPropertyValue('--water').trim() || '#d3e6f3';
  const rend = L.canvas({pane: 'water'}), wl = L.layerGroup();
  for (const p of SD.geoWater.lakes) L.polygon(p, {renderer: rend, pane: 'water', stroke: false, fillColor: water, fillOpacity: 0.9, interactive: false}).addTo(wl);
  for (const p of SD.geoWater.rivers) L.polyline(p, {renderer: rend, pane: 'water', color: water, weight: 3.5, opacity: 0.95, interactive: false}).addTo(wl);
  wl.addTo(map);
  if (typeof layerCtl !== 'undefined') layerCtl.addOverlay(wl, 'Waterways');
}

// ---------------------------------------------------------------- view switching (remembered; #diagram / #map in the URL)
let fitted = false;
function setView(v, save) {
  active = v === 'diagram';
  document.body.classList.toggle('diagram', active);
  tog.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === v)));
  if (save) {
    try { localStorage.setItem('dfwt.view', v); } catch (e) { /* storage unavailable */ }
    try { history.replaceState(null, '', '#' + v); } catch (e) { /* file:// or sandboxed */ }
  }
  if (active) {
    if (!fitted) { fitted = true; fit(); }
    draw();
    if (lastTrip) trip(...lastTrip); else rings();
  } else {
    hidePop(); tip.style.display = 'none';
    map.invalidateSize();
    legendDraw();
  }
}
tog.addEventListener('click', e => { const b = e.target.closest('button'); if (b) setView(b.dataset.v, true); });
window.addEventListener('hashchange', () => { const h = location.hash.slice(1); if (h === 'diagram' || h === 'map') setView(h, false); });
let initial = 'map';
try { initial = localStorage.getItem('dfwt.view') || 'map'; } catch (e) { /* storage unavailable */ }
const h0 = location.hash.slice(1);
if (h0 === 'diagram' || h0 === 'map') initial = h0;
// locate(sid): screen position of a station in the diagram (used by the screenshot checks)
const locate = sid => { const v = nodeOf.get(sid); return v === undefined ? null : [P(v)[0] * view.k + view.tx, P(v)[1] * view.k + view.ty]; };
window.Schem = {draw, trip: (legs, yd) => trip(legs, yd), setView, locate, zoomAt};
setView(initial === 'diagram' ? 'diagram' : 'map', false);
})();
