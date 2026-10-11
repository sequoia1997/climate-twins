"use strict";
/* Climate Twins: species page. Data: <data base>/index.json at start; a species' info + CTS files on demand; places.json when the place list is opened.
   The data base is the content of <meta name="species-data-base"> (relative to the page, or an absolute URL such as an R2 domain), so a move
   to another host is a one-line change in species.html. Files are fetched whole (no Range requests needed on the host). */
const $ = id => document.getElementById(id);
const BS = 256, NX = 8640, NY = 4320, LEVELS = [8, 4, 2, 1];
const MIN = "−", MODES = ["unlimited", "limited", "none"];
const meta = n => { const m = document.querySelector(`meta[name="${n}"]`); return m ? m.content : ""; };
const DATA = new URL(meta("species-data-base") || "species/data/", location.href).href.replace(/\/?$/, "/");
const LAND_URL = new URL(meta("species-land") || "species/land.cts", location.href).href;
const STYLES = { light: "https://tiles.openfreemap.org/styles/positron", dark: "https://tiles.openfreemap.org/styles/dark" };
const BLANK = { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#c7d5de" } }] };
const GROUPS = { tree: "Trees", bird: "Birds", mammal: "Mammals", insect_arachnid: "Insects and ticks", crop: "Crops", reptile: "Reptiles" };
const gname = g => GROUPS[g] || (g ? g[0].toUpperCase() + g.slice(1) : "");
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const phone = () => matchMedia("(max-width:820px) and (orientation:portrait)").matches;
let ST = null, INFO = {}, PL = null, map = null, gl = null, glr = null, useLand = false, COL = null;
const S = { sp: null, ssp: "ssp245", per: "2050", view: "change", disp: "unlimited", agree: false, novel: false, group: "All", q: "", figview: "abs", place: 0 };
const SHOWN = { sp: null, ssp: null };
const T = {};                                   // timings for tests and the page-load report
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ------------------------------------------------------------ CTS files, fetched whole */
class CTS {
  constructor(url) { this.url = url; this.ready = this.init(); }
  async init() {
    const r = await fetch(this.url);
    if (!r.ok) throw new Error(this.url + " " + r.status);
    this.buf = new Uint8Array(await r.arrayBuffer()); this.bytes = this.buf.length;
    const dv = new DataView(this.buf.buffer), n = dv.getUint32(4, true);
    this.H = JSON.parse(new TextDecoder().decode(this.buf.subarray(8, 8 + n)));
    let pos = 8 + n; this.idx = [];
    for (const lv of this.H.levels) { const e = []; for (let i = 0; i < lv.bx * lv.by; i++) { e.push([dv.getUint32(pos, true), dv.getUint32(pos + 4, true)]); pos += 8; } this.idx.push(e); }
  }
  level(f) { return this.H.levels.findIndex(l => l.f === f); }
  async block(f, bx, by) {
    await this.ready;
    const L = this.level(f), lv = this.H.levels[L];
    if (bx < 0 || by < 0 || bx >= lv.bx || by >= lv.by) return null;
    const [off, len] = this.idx[L][by * lv.bx + bx];
    if (!len) return null;
    const inf = new Uint8Array(await new Response(new Blob([this.buf.subarray(off, off + len)]).stream().pipeThrough(new DecompressionStream("deflate-raw"))).arrayBuffer());
    const nb = this.H.bands.length, out = new Uint8Array(BS * BS * 4);
    for (let k = 0; k < nb; k++) for (let r = 0; r < BS; r++) { let acc = 0; const o = k * BS * BS + r * BS; for (let q = 0; q < BS; q++) { acc = (acc + inf[o + q]) & 255; out[(r * BS + q) * 4 + k] = acc; } }
    return out;
  }
}
const files = {};
const file = url => files[url] || (files[url] = new CTS(url));
const rec = id => ST.byId[id];
const sceneFiles = (sp, ssp) => ({ land: useLand ? file(LAND_URL) : null, base: file(DATA + rec(sp).files.base[0]), scen: file(DATA + rec(sp).files[ssp][0]) });

/* ------------------------------------------------------------ GPU */
const cache = new Map();
let zeroTex = null;
const hex = c => { c = c.trim(); return [parseInt(c.slice(1, 3), 16) / 255, parseInt(c.slice(3, 5), 16) / 255, parseInt(c.slice(5, 7), 16) / 255]; };
function entry(f, level, bx, by) {
  const k = f.url + "|" + level + "|" + bx + "|" + by; let e = cache.get(k);
  if (e) { cache.delete(k); cache.set(k, e); return e; }
  e = { st: 0, tex: null }; cache.set(k, e);
  e.p = f.block(level, bx, by).then(d => { if (d && gl) { const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, BS, BS, 0, gl.RGBA, gl.UNSIGNED_BYTE, d); e.tex = t; } e.st = 1; map && map.triggerRepaint(); }).catch(() => { e.st = 1; });
  if (cache.size > 360) { let n = 0; for (const [kk, v] of cache) { if (n++ > 60) break; if (v.tex) gl.deleteTexture(v.tex); cache.delete(kk); } }
  return e;
}
function levelFor() { const wpx = 512 * Math.pow(2, map.getZoom()); for (const f of LEVELS) if (NX / f >= wpx) return f; return 1; }
function visible(f) {
  const b = map.getBounds(), cells = NX / f, rows = NY / f, out = [];
  const x0 = Math.max(0, Math.floor((b.getWest() + 180) / 360 * cells / BS)), x1 = Math.min(Math.ceil(cells / BS) - 1, Math.floor((Math.min(180, b.getEast()) + 180) / 360 * cells / BS));
  const y0 = Math.max(0, Math.floor((90 - Math.min(85, b.getNorth())) / 180 * rows / BS)), y1 = Math.min(Math.ceil(rows / BS) - 1, Math.floor((90 - Math.max(-85, b.getSouth())) / 180 * rows / BS));
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) out.push([x, y]);
  return out;
}
const merc = lat => 0.5 - Math.log(Math.tan(Math.PI / 4 + Math.max(-85.05, Math.min(85.05, lat)) * Math.PI / 360)) / (2 * Math.PI);
const VS = `#version 300 es
in vec2 a; uniform mat4 uM; out vec2 vm; void main(){ vm=a; gl_Position=uM*vec4(a,0.0,1.0); }`;
/* kinds: 0 land mask, 1 species (T0 = scenario file: S1 r, S2 g, agreement b, novel a; T1 = base file: now r), 2 novel-climate lines (T0 = scenario file) */
const FS = `#version 300 es
precision highp float; precision highp int;
uniform sampler2D uT0,uT1; uniform vec4 uBlk; uniform int uKind,uView,uPer,uDisp,uAgree,uPat; uniform float uDpr;
uniform vec3 uLand,uLost,uKept,uGain,uR1,uR2,uR3,uNov,uDot;
in vec2 vm; out vec4 o;
void main(){
  float lat=degrees(atan(sinh(3.14159265*(1.0-2.0*vm.y))));
  vec2 uv=vec2((vm.x-uBlk.x)/(uBlk.y-uBlk.x),(uBlk.z-lat)/uBlk.w);
  vec2 px=gl_FragCoord.xy/uDpr;
  ivec4 s=ivec4(floor(texture(uT0,uv)*255.0+0.5));
  if(uKind==0){ if(s.r>0) o=vec4(uLand,1.0); else o=vec4(0.0); return; }
  if(uKind==2){ int bit=(s.a>>uPer)&1; if(bit==1){ bool ln=mod(px.x-px.y,7.0)<1.6; o=ln?vec4(uNov*0.8,0.8):vec4(0.0);} else o=vec4(0.0); return; }
  int b=int(floor(texture(uT1,uv).r*255.0+0.5))&127;
  int fs=(uPer==0)?s.r:s.g; int cf=fs&127; bool reach=(fs>>7)==1;
  int ag=(uPer==0)?(s.b>>4):(s.b&15);
  bool nowB=b>=1, frB=cf>=1;
  bool fut=(uDisp==0)?frB:((uDisp==1)?(frB&&(nowB||reach)):(frB&&nowB));
  int fc=fut?max(cf,1):0;
  vec3 col=vec3(0.0); float al=0.0;
  bool stripe=mod(px.x+px.y,6.0)<2.4;
  bool dots=length(mod(px,6.0)-vec2(3.0))<1.5;
  if(uView==2){
    if(nowB&&!fut){ col=uLost; al=(uPat==1&&!stripe)?0.4:0.95; }
    else if(nowB&&fut){ col=uKept; al=0.85; }
    else if(!nowB&&fut){ col=uGain; al=(uPat==1&&!dots)?0.62:0.95; }
  } else {
    int c=(uView==0)?b:fc;
    if(c>=1){ col=(c==1)?uR1:((c==2)?uR2:uR3); al=0.92; }
  }
  if(al>0.0 && uAgree==1 && uView!=0 && fut && ag<11){ if(mod(floor(px.x/3.0)+floor(px.y/3.0),2.0)<1.0){ col=mix(col,uDot,0.7); } }
  o=vec4(col*al,al);
}`;
function initGL(g) {
  gl = g; if (glr) return;
  const mk = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(o)); return o; };
  const p = gl.createProgram(); gl.attachShader(p, mk(gl.VERTEX_SHADER, VS)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  glr = { p, buf: gl.createBuffer(), u: {} };
  for (const n of ["uM", "uT0", "uT1", "uBlk", "uKind", "uView", "uPer", "uDisp", "uAgree", "uPat", "uDpr", "uLand", "uLost", "uKept", "uGain", "uR1", "uR2", "uR3", "uNov", "uDot"]) glr.u[n] = gl.getUniformLocation(p, n);
  glr.a = gl.getAttribLocation(p, "a");
  zeroTex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, zeroTex); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
}
const tex = e => e && e.tex ? e.tex : zeroTex;
function setTex(unit, t) { gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, t); for (const k of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, k, gl.NEAREST); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE); }
function colours() { const cs = getComputedStyle(document.documentElement), g = n => hex(cs.getPropertyValue(n)); return { uLand: g("--land"), uLost: g("--lost"), uKept: g("--kept"), uGain: g("--gained"), uR1: g("--r1"), uR2: g("--r2"), uR3: g("--r3"), uNov: g("--nov"), uDot: g("--dot") }; }
function leaves(fs, f, bx, by, seen, out) {
  const need = fs.map(x => entry(x, f, bx, by));
  if (need.every(e => e.st === 1) || f === 8) { const k = f + "|" + bx + "|" + by; if (!seen.has(k)) { seen.add(k); out.push([f, bx, by, need]); } return; }
  leaves(fs, f * 2, bx >> 1, by >> 1, seen, out);
}
function drawPass(kind, fs, f, blocks) {
  const u = glr.u, seen = new Set(), out = [];
  for (const [bx, by] of blocks) leaves(fs, f, bx, by, seen, out);
  for (const [lf, bx, by, es] of out) {
    if (es.every(e => !e.tex)) continue;
    const dl = lf * 360 / NX, dla = lf * 180 / NY, lon0 = -180 + bx * BS * dl, latT = 90 - by * BS * dla, span = BS * dla;
    const x0 = (lon0 + 180) / 360, x1 = x0 + BS * dl / 360, y0 = merc(latT), y1 = merc(latT - span);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([x0, y0, x1, y0, x0, y1, x1, y1]), gl.DYNAMIC_DRAW);
    gl.vertexAttribPointer(glr.a, 2, gl.FLOAT, false, 0, 0);
    setTex(0, tex(es[0])); setTex(1, es[1] ? tex(es[1]) : zeroTex);
    gl.uniform4f(u.uBlk, x0, x1, latT, span); gl.uniform1i(u.uKind, kind);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }
}
const showNovel = () => S.novel || isWithheld();
function render(g, args) {
  if (!glr || !COL) return;
  const mat = args.defaultProjectionData.mainMatrix, u = glr.u;
  gl.useProgram(glr.p); gl.bindBuffer(gl.ARRAY_BUFFER, glr.buf); gl.enableVertexAttribArray(glr.a);
  gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); gl.disable(gl.DEPTH_TEST);
  gl.uniformMatrix4fv(u.uM, false, mat); gl.uniform1i(u.uT0, 0); gl.uniform1i(u.uT1, 1); gl.uniform1f(u.uDpr, devicePixelRatio);
  for (const k in COL) gl.uniform3fv(u[k], COL[k]);
  gl.uniform1i(u.uView, { now: 0, future: 1, change: 2 }[S.view]); gl.uniform1i(u.uPer, S.per === "2050" ? 0 : 1); gl.uniform1i(u.uDisp, MODES.indexOf(S.disp));
  gl.uniform1i(u.uAgree, S.agree ? 1 : 0); gl.uniform1i(u.uPat, map.getZoom() >= 3.2 ? 1 : 0);
  if (!SHOWN.sp && !useLand) return;
  const f = levelFor(), vis = visible(f), sc = sceneFiles(SHOWN.sp || S.sp, SHOWN.ssp || S.ssp);
  if (useLand) drawPass(0, [sc.land], f, vis);
  if (SHOWN.sp) { drawPass(1, [sc.scen, sc.base], f, vis); if (showNovel()) drawPass(2, [sc.scen], f, vis); }
  window.__drawn = (window.__drawn || 0) + 1;
}
let swapToken = 0;
async function loadScene(sp, ssp) {
  const tok = ++swapToken; $("busy").hidden = false; map.getContainer().setAttribute("aria-busy", "true");
  const t0 = performance.now(), sc = sceneFiles(sp, ssp), f = levelFor(), ps = [];
  try {
    for (const fs of [sc.scen, sc.base]) { await fs.ready; for (const [bx, by] of visible(f)) ps.push(entry(fs, f, bx, by).p); const lv = fs.H.levels[fs.level(8)]; for (let y = 0; y < lv.by; y++) for (let x = 0; x < lv.bx; x++) ps.push(entry(fs, 8, x, y).p); }
    await Promise.race([Promise.all(ps), new Promise(r => setTimeout(r, 8000))]);
  } catch (e) { if (tok === swapToken) { $("busy").hidden = true; $("live").textContent = "The map files for this species could not be loaded."; $("sp-err").hidden = false; } return; }
  if (tok !== swapToken) return;
  $("sp-err").hidden = true;
  SHOWN.sp = sp; SHOWN.ssp = ssp; $("busy").hidden = true; map.getContainer().removeAttribute("aria-busy"); map.triggerRepaint();
  T.scene = Math.round(performance.now() - t0); T.sceneBytes = sc.scen.bytes + sc.base.bytes; window.__sceneReady = (window.__sceneReady || 0) + 1;
}

/* ------------------------------------------------------------ text and numbers */
const key = (d = S.disp, per = S.per, ssp = S.ssp) => `${ssp}|${per}|${d}`;
const I = () => INFO[S.sp];
const cur = () => I().by[key()];
const isWithheld = () => !!(S.sp && INFO[S.sp] && INFO[S.sp].withheld[S.ssp + "|" + S.per]);
const fmtA = k => k >= 1e6 ? (k / 1e6).toFixed(k >= 1e7 ? 0 : 1) + " M km²" : k >= 1e3 ? Math.round(k / 1e3) + " k km²" : Math.round(k) + " km²";
const pct = (a, b) => b > 0 ? Math.round((a - b) / b * 100) : null;
const sgn = n => (n > 0 ? "+" : n < 0 ? MIN : "") + Math.abs(n);
const compass = b => ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][Math.round(b / 45) % 8];
const PERLAB = () => ST.periods[S.per];
const sspLabel = () => ST.ssps[S.ssp];
const FLAG = "Climate suitability, not a forecast.";
const KINDS = { bbs: "the North American Breeding Bird Survey", fia: "US Forest Inventory plots" };
const CVK = { presence_background: "presence records against a sample of background locations", presence_absence: "presence and absence records" };

function arrowSvg(b) { return `<svg width="44" height="44" viewBox="0 0 44 44" aria-hidden="true"><circle cx="22" cy="22" r="20" fill="none" stroke="var(--rule)" stroke-width="2"/><g transform="rotate(${b} 22 22)"><path d="M22 6v28M22 6l-7 9M22 6l7 9" fill="none" stroke="var(--ink)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g></svg>`; }
function seg(id, items, get, set) {
  const el = $(id); el.innerHTML = "";
  items.forEach(([v, t]) => { const b = document.createElement("button"); b.type = "button"; b.textContent = t; b.setAttribute("aria-pressed", String(get() === v)); b.addEventListener("click", () => set(v)); el.appendChild(b); });
}
function dispText() {
  const i = I(), r = i.dispersal.reach_km, g = gname(i.group).toLowerCase();
  if (S.disp === "unlimited") return "Any climatically suitable area can be reached, however far.";
  if (S.disp === "none") return "No spreading: only the part of today's range that stays suitable is kept.";
  return `New range counts only within about ${Math.round(r["2041-2060"])} km (2041–2060) or ${Math.round(r["2081-2100"])} km (2081–2100) of today's range. The distance is a rule of thumb for ${g}${i.dispersal.calibrated ? "" : ", uncalibrated and probably uncertain by a factor of about 10"}.`;
}
function renderControls() {
  seg("view", [["now", "Now"], ["future", "Future"], ["change", "Change"]], () => S.view, v => { S.view = v; update(); });
  const i = INFO[S.sp];
  seg("ssp", Object.entries(ST.ssps).filter(([k]) => !i || i.ssps.includes(k)), () => S.ssp, v => { S.ssp = v; update(true); });
  seg("per", Object.entries(ST.periods), () => S.per, v => { S.per = v; update(); });
  seg("disp", [["unlimited", "Unlimited"], ["limited", "Limited"], ["none", "None"]], () => S.disp, v => { S.disp = v; update(); });
  $("disp-d").textContent = i ? dispText() : "";
  $("o-agree").checked = S.agree; $("o-novel").checked = S.novel;
}
function renderResults() {
  const q = S.q.trim().toLowerCase(), ul = $("results"); ul.innerHTML = "";
  const list = ST.species.filter(s => (S.group === "All" || s.group === S.group) && (!q || (s.name + " " + s.sci + " " + gname(s.group)).toLowerCase().includes(q)));
  list.forEach(s => { const li = document.createElement("li"); li.setAttribute("role", "option"); li.id = "opt-" + s.id; li.tabIndex = -1; li.dataset.id = s.id; li.setAttribute("aria-selected", String(s.id === S.sp));
    li.innerHTML = `<span>${esc(s.name)}</span><span class="g">${esc(gname(s.group))} · Tier ${esc(s.tier)}</span>`; li.addEventListener("click", () => pick(s.id)); ul.appendChild(li); });
  if (!list.length) ul.innerHTML = '<li role="option" aria-selected="false" class="muted">No species match.</li>';
  $("chips").innerHTML = ["All", ...new Set(ST.species.map(s => s.group))].map(g => `<button type="button" aria-pressed="${S.group === g}" data-g="${esc(g)}">${esc(g === "All" ? "All groups" : gname(g))}</button>`).join("");
  $("chips").querySelectorAll("[data-g]").forEach(b => b.addEventListener("click", () => { S.group = b.dataset.g; renderResults(); }));
}
function badge(i) {
  const a = i.tier === "A";
  return `<span class="badge ${a ? "q-good" : "q-partial"}"><span aria-hidden="true">${a ? "●●" : "●○"}</span> Tier ${i.tier}</span>`;
}
function tierText(i) {
  const v = i.validation;
  if (i.tier === "A") return `Present-day skill checked against an independent survey (${KINDS[v && v.kind] || "an independent survey"}${v && v.auc != null ? `; AUC ${v.auc.toFixed(2)}, TSS ${v.tss == null ? "n/a" : v.tss.toFixed(2)}${v.n_presence ? `, ${v.n_presence} presence and ${v.n_absence} absence sites` : ""}` : ""}).`;
  return "Skill checked by spatial cross-validation only; no independent survey was available to check it against.";
}
function shiftsText(i) {
  if (i.range_shifts === "fail") return "We tested whether models like this one, fitted to earlier decades, could predict where these species actually moved by recent decades. For birds they could not do so reliably. So the future map shows where the climate may suit the species, not where it will be found.";
  if (i.range_shifts === "pass") return "Models like this one reproduced the range changes observed in our test.";
  return "There was not enough survey data on real range changes for this species, so this check has not been made.";
}
function head() {
  const i = I();
  $("sp-head").innerHTML = `<h2>${esc(i.name)}</h2><p class="small" style="margin:0 0 6px"><i>${esc(i.sci)}</i> &middot; ${esc(gname(i.group))}${i.season ? " &middot; breeding-season fit" : ""}${i.kind === "crop" ? " &middot; crop" : ""}</p>
  <p class="badges">${badge(i)}${i.confidence === "low" ? ' <span class="badge q-low"><span aria-hidden="true">!</span> Low confidence</span>' : ""}
    <span class="badge ${i.range_shifts === "pass" ? "q-good" : i.range_shifts === "fail" ? "q-low" : "q-partial"}"><span aria-hidden="true">${i.range_shifts === "pass" ? "✓" : i.range_shifts === "fail" ? "✗" : "?"}</span> Range shifts: ${esc(i.range_shifts)}</span></p>
  <p class="small tierline">${esc(tierText(i))}${i.confidence === "low" && i.soft_flags.length ? " Low confidence: " + esc(i.soft_flags.join("; ")) + "." : ""}</p>
  <p class="disc">${FLAG}</p><p class="small">${esc(i.wording[0].toUpperCase() + i.wording.slice(1))}.</p>`;
  $("sh-title").textContent = i.name;
  const dl = i.dois.map(d => `<a href="${esc(d)}" rel="noopener">${esc(d.replace("https://doi.org/", "doi:"))}</a>`).join(", ") || "none recorded";
  $("about").innerHTML = `<dl class="facts"><dt>Tier</dt><dd>${i.tier}</dd><dt>Confidence</dt><dd>${esc(i.confidence)}</dd><dt>Cross-validation</dt><dd>${esc(CVK[i.cv_kind] || i.cv_kind || "n/a")}</dd>
    <dt>Cross-validation AUC</dt><dd>${i.skill.auc == null ? "n/a" : i.skill.auc.toFixed(2)}</dd><dt>Records (grid cells)</dt><dd>${i.records.cells == null ? "n/a" : i.records.cells.toLocaleString("en")}</dd>
    <dt>Climate variables used</dt><dd>${esc(i.predictors.join(", "))}</dd><dt>Climate models</dt><dd>${i.n_models}</dd><dt>Range-shift test</dt><dd>${esc(i.range_shifts)}</dd></dl>
    <p class="small">${esc(shiftsText(i))}</p>
    <p class="small">Records: GBIF occurrence download ${dl} (CC0 and CC-BY records only).${i.season ? " Only records from the breeding months (May to July) are used, because the species migrates." : ""}
    <a href="species-methods.html#tiers">What the tiers mean</a>, <a href="species-methods.html#limits">limitations</a> and <a href="species-methods.html#credits">credits</a>.</p>`;
}
function bars(rows, max, signed) {
  return rows.map(([lab, v, col, txt]) => {
    const w = max > 0 ? Math.abs(v) / max * (signed ? 44 : 66) : 0;
    const pos = signed ? (v >= 0 ? `left:50%;width:${w}%` : `right:50%;width:${w}%`) : `left:0;width:${w}%`;
    return `<div class="crow"><div class="lab">${esc(lab)}</div><div class="trk">${signed ? '<span class="zero" style="left:50%"></span>' : ""}<span class="bar ${signed && v < 0 ? "end" : ""}" style="${pos};--c:${col}"><b>${esc(txt)}</b></span></div></div>`;
  }).join("");
}
function summary() {
  const i = I(), c = cur(), per = PERLAB(), el = $("summary");
  el.dataset.view = S.figview;
  if (!c || c.withheld) {
    const why = i.withheld[S.ssp + "|" + S.per] || "high share of novel climate";
    el.innerHTML = `<div class="stats"><div class="st s-now"><div class="k">Suitable now</div><div class="v">${fmtA(i.area_now_km2)}</div><div class="d">1991–2020</div></div>
      <div class="st s-fut"><div class="k">Suitable by ${per}</div><div class="v">Withheld</div><div class="d">${esc(sspLabel())}</div></div>
      <div class="st s-mat"><div class="k">Change</div><div class="v">Withheld</div><div class="d">&nbsp;</div></div></div>
      <p class="note withheld"><strong>Numbers withheld.</strong> ${esc(why[0].toUpperCase() + why.slice(1))}. Too much of the projected area has a climate that nothing in the training data resembles, so the model would be extrapolating. The map is still drawn, with those areas marked by diagonal lines.</p>`;
    const txt = `${i.name}: suitable climate now covers ${fmtA(i.area_now_km2)}. The numbers for ${per} under ${sspLabel()} are withheld: ${why}. ${FLAG}`;
    $("textdesc").textContent = txt; $("live").textContent = txt; return;
  }
  const ch = pct(c.fut, c.now);
  let shift = "";
  if (c.fut <= 0) shift = `<p class="answer">No suitable climate remains under this scenario${S.disp === "none" ? "" : ", even with spreading allowed"}.</p>`;
  else if (c.shift_km < 40) shift = `<div class="shift"><div><strong>The centre of the range hardly moves</strong> (${Math.round(c.shift_km)} km).</div></div>`;
  else shift = `<div class="shift">${arrowSvg(c.bearing)}<div><strong>Centre of the range moves about ${Math.round(c.shift_km / 10) * 10} km ${compass(c.bearing)}.</strong><p class="kicker">From ${c.c0[0].toFixed(1)}°, ${c.c0[1].toFixed(1)}° to ${c.c1[0].toFixed(1)}°, ${c.c1[1].toFixed(1)}° (area-weighted centre of the suitable climate).</p></div></div>`;
  const maxA = Math.max(c.now, c.fut, 1), maxC = Math.max(c.lost, c.gained, 1);
  el.innerHTML = `<div class="stats">
      <div class="st s-now"><div class="k">Suitable now</div><div class="v">${fmtA(c.now)}</div><div class="d">1991–2020</div></div>
      <div class="st s-fut"><div class="k">Suitable by ${per}</div><div class="v">${fmtA(c.fut)}</div><div class="d">${esc(sspLabel())}</div></div>
      <div class="st s-mat"><div class="k">Change</div><div class="v">${ch == null ? "n/a" : sgn(ch) + "%"}</div><div class="d">${ch == null ? "" : sgn(Math.round((c.fut - c.now) / 1e3)) + " k km²"}</div></div></div>
    ${shift}
    <div class="figbar"><h4>Where the suitable climate changes</h4><div class="vt" role="group" aria-label="Figure view"><button type="button" data-v="abs" aria-pressed="${S.figview === "abs"}">Values</button><button type="button" data-v="chg" aria-pressed="${S.figview === "chg"}">Change</button></div></div>
    <div class="v-abs" role="group" aria-label="Suitable area now and by ${per}">${bars([["Now", c.now, "var(--kept)", fmtA(c.now)], [per, c.fut, "var(--ink)", fmtA(c.fut)]], maxA, false)}</div>
    <div class="v-chg" role="group" aria-label="Area lost and gained by ${per}">${bars([["Lost", -c.lost, "var(--lost)", MIN + fmtA(c.lost)], ["Gained", c.gained, "var(--gained)", "+" + fmtA(c.gained)], ["Net", c.gained - c.lost, "var(--ink)", (c.gained >= c.lost ? "+" : MIN) + fmtA(Math.abs(c.gained - c.lost))]], maxC, true)}</div>
    <dl class="facts"><dt>Lost (suitable now, not later)</dt><dd>${fmtA(c.lost)}</dd><dt>Kept</dt><dd>${fmtA(c.kept)}</dd><dt>Gained</dt><dd>${fmtA(c.gained)}</dd>
      <dt>Climate models agreeing on the future area</dt><dd>${c.agree == null ? "n/a" : Math.round(c.agree * 100) + "%"}</dd><dt>Area with novel climate</dt><dd>${c.novel == null ? "n/a" : (c.novel * 100 < 1 ? "<1" : Math.round(c.novel * 100)) + "%"}</dd></dl>`;
  el.querySelectorAll(".vt button").forEach(b => b.addEventListener("click", () => { S.figview = b.dataset.v; summary(); }));
  const txt = `${i.name}: suitable climate now covers ${fmtA(c.now)}. By ${per} under ${sspLabel()} with ${S.disp} dispersal it covers ${fmtA(c.fut)} (${ch == null ? "n/a" : sgn(ch) + "%"}): ${fmtA(c.lost)} lost, ${fmtA(c.kept)} kept, ${fmtA(c.gained)} gained. ` +
    (c.fut > 0 ? `The centre moves ${Math.round(c.shift_km)} km ${compass(c.bearing)}. ` : "") + FLAG;
  $("textdesc").textContent = txt; $("live").textContent = txt;
}
/* place list */
const ICON = {
  lose: `<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M2 4h14L9 16z" fill="var(--lost)"/></svg>`,
  gain: `<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M2 14h14L9 2z" fill="var(--gained)"/></svg>`,
  keep: `<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><rect x="3" y="3" width="12" height="12" rx="2" fill="var(--kept)"/></svg>`
};
async function placeCard() {
  const box = $("place-body");
  if (!$("place-det").open) return;
  if (!PL) { box.innerHTML = '<p class="small">Loading the place table…</p>'; try { PL = await (await fetch(DATA + ST.places[0])).json(); } catch (e) { box.innerHTML = '<p class="small" role="alert">The place table could not be loaded.</p>'; return; } }
  const k = key(), per = PERLAB(), P = PL.places[S.place];
  const rows = ST.species.map(s => ({ s, c: (PL.sp[s.id][k] || "")[S.place] || "0" }));
  const lose = rows.filter(r => r.c === "1"), gain = rows.filter(r => r.c === "3"), keep = rows.filter(r => r.c === "2"), wh = rows.filter(r => r.c === "9");
  const li = (r, kind, word) => `<li>${ICON[kind]}<span><button class="linkbtn" data-sp="${r.s.id}">${esc(r.s.name)}</button> <span class="w">Tier ${r.s.tier}</span></span><span class="w">${word}</span></li>`;
  const list = [...lose.map(r => li(r, "lose", "loses")), ...gain.map(r => li(r, "gain", "gains")), ...keep.map(r => li(r, "keep", "keeps"))];
  box.innerHTML = `<label class="small" for="place">City</label><select id="place">${PL.places.map((p, i) => `<option value="${i}"${i === S.place ? " selected" : ""}>${esc(p[0])}</option>`).join("")}</select>
    <p class="answer"><strong>${lose.length}</strong> of ${rows.length} modelled species are projected to lose suitable climate at ${esc(P[0])} by ${per}, and <strong>${gain.length}</strong> to gain it. <span class="small">${keep.length} keep it${wh.length ? `; ${wh.length} not shown because their numbers are withheld for this scenario` : ""}. ${esc(sspLabel())}, ${S.disp} dispersal. Read from the map cell at the city centre (and its neighbours); this is climate suitability, not a forecast.</span></p>
    <ul class="pl">${list.join("") || '<li class="muted" style="grid-template-columns:1fr">No modelled species has suitable climate here now or later.</li>'}</ul>`;
  $("place").addEventListener("change", e => { S.place = +e.target.value; placeCard(); placeMarker(); });
  box.querySelectorAll("[data-sp]").forEach(b => b.addEventListener("click", () => pick(b.dataset.sp)));
}
let pm = null;
function placeMarker() {
  if (!map || !PL || !$("place-det").open) { if (pm) { pm.remove(); pm = null; } return; }
  const P = PL.places[S.place];
  if (!pm) { const el = document.createElement("div"); el.className = "pmark"; el.setAttribute("aria-hidden", "true"); pm = new maplibregl.Marker({ element: el }); pm.setLngLat([P[2], P[1]]).addTo(map); } else pm.setLngLat([P[2], P[1]]);
}
const SW = {
  lost: `<svg width="28" height="14" aria-hidden="true"><defs><pattern id="pl" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="2.4" height="6" fill="var(--lost)"/></pattern></defs><rect width="28" height="14" rx="2" fill="url(#pl)" stroke="var(--lost)"/></svg>`,
  kept: `<svg width="28" height="14" aria-hidden="true"><rect width="28" height="14" rx="2" fill="var(--kept)"/></svg>`,
  gain: `<svg width="28" height="14" aria-hidden="true"><defs><pattern id="pg" width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="3" cy="3" r="1.5" fill="var(--gained)"/></pattern></defs><rect width="28" height="14" rx="2" fill="url(#pg)" stroke="var(--gained)"/></svg>`,
  ramp: `<svg width="28" height="14" aria-hidden="true"><rect width="9.4" height="14" fill="var(--r1)"/><rect x="9.4" width="9.4" height="14" fill="var(--r2)"/><rect x="18.8" width="9.2" height="14" fill="var(--r3)"/></svg>`,
  agree: `<svg width="28" height="14" aria-hidden="true"><defs><pattern id="pa" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="3" height="3" fill="var(--dot)"/><rect x="3" y="3" width="3" height="3" fill="var(--dot)"/></pattern></defs><rect width="28" height="14" rx="2" fill="var(--kept)"/><rect width="28" height="14" rx="2" fill="url(#pa)" opacity=".7"/></svg>`,
  nov: `<svg width="28" height="14" aria-hidden="true"><defs><pattern id="pn" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><rect width="1.6" height="7" fill="var(--nov)"/></pattern></defs><rect width="28" height="14" rx="2" fill="var(--land)" stroke="var(--line)"/><rect width="28" height="14" rx="2" fill="url(#pn)"/></svg>`,
  ctr: `<svg width="28" height="14" aria-hidden="true"><circle cx="5" cy="7" r="4" fill="none" stroke="var(--ink)" stroke-width="2"/><path d="M10 7h8" stroke="var(--ink)" stroke-width="2"/><circle cx="23" cy="7" r="4" fill="var(--ink)"/></svg>`
};
function legend() {
  if (!legend.init) { legend.init = 1; $("legend").open = !phone(); }
  const per = PERLAB(), k = [];
  if (S.view === "change") k.push([SW.lost, `Lost: suitable now, not by ${per}`], [SW.kept, "Kept: suitable now and later"], [SW.gain, `Gained: suitable by ${per} only`]);
  else k.push([SW.ramp, `${S.view === "now" ? "Now" : "By " + per}: suitability, lower to higher (3 classes)`]);
  if (S.agree && S.view !== "now") k.push([SW.agree, `Dotted: fewer than 3 in 4 of the ${S.sp ? I().n_models : 14} climate models agree`]);
  if (showNovel()) k.push([SW.nov, `Diagonal lines: climate with no present-day match by ${per}`]);
  if (S.view !== "now") k.push([SW.ctr, "Centre of range, now to later"]);
  $("lg").innerHTML = `<div class="key">${k.map(([s, t]) => `${s}<span>${esc(t)}</span>`).join("")}</div><div class="small" style="margin-top:6px">${FLAG}</div>`;
}
function shiftLayer() {
  const src = map && map.getSource("shift"); if (!src || !S.sp || !INFO[S.sp]) return;
  const c = cur(), f = [];
  if (c && !c.withheld && S.view !== "now" && c.fut > 0 && c.shift_km > 40) {
    f.push({ type: "Feature", properties: { k: "l" }, geometry: { type: "LineString", coordinates: [[c.c0[1], c.c0[0]], [c.c1[1], c.c1[0]]] } },
      { type: "Feature", properties: { k: "a" }, geometry: { type: "Point", coordinates: [c.c0[1], c.c0[0]] } }, { type: "Feature", properties: { k: "b" }, geometry: { type: "Point", coordinates: [c.c1[1], c.c1[0]] } });
  }
  src.setData({ type: "FeatureCollection", features: f });
}
function styleShift() {
  if (!map.getLayer("shift-case")) return;
  const cs = getComputedStyle(document.documentElement), ink = cs.getPropertyValue("--ink").trim(), pan = cs.getPropertyValue("--panel").trim();
  map.setPaintProperty("shift-case", "line-color", pan); map.setPaintProperty("shift-line", "line-color", ink);
  map.setPaintProperty("shift-a", "circle-stroke-color", ink); map.setPaintProperty("shift-a", "circle-color", pan); map.setPaintProperty("shift-b", "circle-color", ink); map.setPaintProperty("shift-b", "circle-stroke-color", pan);
}
const padFor = () => phone() ? { top: 56, left: 16, right: 16, bottom: Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sheet-h")) || 300) + 24 } : { top: 56, left: 24, right: 24, bottom: 40 };
function update(reload, refit) {
  if (!S.sp || !INFO[S.sp]) return;
  if (!I().ssps.includes(S.ssp)) S.ssp = I().ssps[0];
  renderControls(); head(); summary(); placeCard(); legend(); placeMarker();
  const wh = isWithheld(); $("o-novel").disabled = wh; if (wh) $("o-novel").checked = true;
  if (map && map.loaded !== undefined) {
    if (reload) {
      if (refit) { const b = rec(S.sp).bbox; map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: padFor(), duration: reduced ? 0 : 500, maxZoom: 5 }); }
      loadScene(S.sp, S.ssp);
    }
    shiftLayer(); map.triggerRepaint();
  }
  try { history.replaceState(null, "", "#" + S.sp); } catch (e) { }
}
async function loadInfo(id) {
  if (INFO[id]) return INFO[id];
  const t0 = performance.now(), r = await fetch(DATA + rec(id).info[0]);
  if (!r.ok) throw new Error("info " + r.status);
  INFO[id] = await r.json(); T.info = Math.round(performance.now() - t0); return INFO[id];
}
async function pick(id) {
  if (!ST.byId[id]) return;
  S.sp = id; renderResults(); $("sp-head").setAttribute("aria-busy", "true");
  try { await loadInfo(id); } catch (e) { $("sp-head").innerHTML = '<p role="alert">This species could not be loaded. Check your connection and try again.</p>'; return; }
  $("sp-head").removeAttribute("aria-busy");
  if (!INFO[id].ssps.includes(S.ssp)) S.ssp = INFO[id].ssps[0];
  update(true, true);
}

/* ------------------------------------------------------------ bottom sheet (phone), as on the main page */
const sheet = (() => {
  const mq = matchMedia("(max-width:820px) and (orientation:portrait)"), as = $("panel"), head = $("sheethead"), root = document.documentElement;
  const H = () => ({ peek: 64, half: Math.round(innerHeight * .46), full: Math.round(innerHeight * .88) });
  let st = "half", drag = null;
  function set(s) { if (!mq.matches) { root.style.removeProperty("--sheet-h"); as.classList.remove("collapsed"); return; } st = s; root.style.setProperty("--sheet-h", H()[s] + "px"); as.classList.toggle("collapsed", s === "peek"); $("sh-tog").setAttribute("aria-expanded", String(s !== "peek")); }
  $("sh-tog").addEventListener("click", () => set(st === "peek" ? "half" : "peek"));
  $("grab").addEventListener("click", () => { if (drag && drag.moved) return; set(st === "peek" ? "half" : st === "half" ? "full" : "half"); });
  $("grab").addEventListener("keydown", e => { if (e.key === "ArrowUp") { set(st === "peek" ? "half" : "full"); e.preventDefault(); } if (e.key === "ArrowDown") { set(st === "full" ? "half" : "peek"); e.preventDefault(); } });
  head.addEventListener("pointerdown", e => { if (!mq.matches || e.target.closest("#sh-tog")) return; drag = { y: e.clientY, h: as.getBoundingClientRect().height, moved: false }; head.setPointerCapture(e.pointerId); as.classList.add("dragging"); });
  head.addEventListener("pointermove", e => { if (!drag) return; const dy = drag.y - e.clientY; if (Math.abs(dy) > 4) drag.moved = true; if (drag.moved) root.style.setProperty("--sheet-h", Math.max(64, Math.min(H().full, drag.h + dy)) + "px"); });
  const end = () => { if (!drag) return; as.classList.remove("dragging"); if (drag.moved) { const h = parseFloat(root.style.getPropertyValue("--sheet-h")), o = H(); set(Object.keys(o).sort((a, b) => Math.abs(o[a] - h) - Math.abs(o[b] - h))[0]); } setTimeout(() => drag = null, 0); };
  head.addEventListener("pointerup", end); head.addEventListener("pointercancel", end);
  mq.addEventListener("change", () => { set(st); map && map.resize(); }); addEventListener("resize", () => { if (mq.matches) set(st); });
  set("half");
})();

/* ------------------------------------------------------------ boot */
const SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/></svg>';
const MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>';
const sysDark = matchMedia("(prefers-color-scheme: dark)");
const isDark = () => { const t = document.documentElement.getAttribute("data-theme"); return t ? t === "dark" : sysDark.matches; };
function baseStyle() { return useLand ? BLANK : STYLES[isDark() ? "dark" : "light"]; }
function applyTheme(restyle) {
  $("themebtn").innerHTML = isDark() ? SUN : MOON; $("themebtn").setAttribute("aria-pressed", String(isDark())); COL = colours();
  if (map) { if (restyle) map.setStyle(baseStyle()); else { styleShift(); map.triggerRepaint(); } }
  if (S.sp && INFO[S.sp]) legend();
}
$("themebtn").addEventListener("click", () => { const t = isDark() ? "light" : "dark"; document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("ct-theme", t); } catch (e) { } applyTheme(true); });
sysDark.addEventListener("change", () => { if (!document.documentElement.getAttribute("data-theme")) applyTheme(true); });
$("o-agree").addEventListener("change", e => { S.agree = e.target.checked; update(); });
$("o-novel").addEventListener("change", e => { S.novel = e.target.checked; legend(); map && map.triggerRepaint(); });
$("place-det").addEventListener("toggle", () => { placeCard(); placeMarker(); });
$("search").addEventListener("input", e => { S.q = e.target.value; renderResults(); });
$("retry").addEventListener("click", () => location.reload());
$("search").addEventListener("keydown", e => {
  const opts = [...$("results").querySelectorAll("[data-id]")]; if (!opts.length) return; let i = opts.findIndex(o => o.getAttribute("aria-selected") === "true");
  if (e.key === "ArrowDown" || e.key === "ArrowUp") { i = (i + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length; opts.forEach(o => o.setAttribute("aria-selected", "false")); opts[i].setAttribute("aria-selected", "true"); opts[i].scrollIntoView({ block: "nearest" }); $("search").setAttribute("aria-activedescendant", opts[i].id); e.preventDefault(); }
  if (e.key === "Enter" && i >= 0) { pick(opts[i].dataset.id); e.preventDefault(); }
});
function addLayers() {
  if (!map.getSource("shift")) {
    map.addSource("shift", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  }
  const first = (map.getStyle().layers.find(l => l.type === "symbol") || {}).id;                    // species colours sit under the labels
  if (!map.getLayer("species")) map.addLayer({ id: "species", type: "custom", renderingMode: "2d", onAdd: (m, g) => initGL(g), render }, first);
  const add = (l) => { if (!map.getLayer(l.id)) map.addLayer(l); };
  add({ id: "shift-case", type: "line", source: "shift", filter: ["==", "k", "l"], paint: { "line-width": 7, "line-color": "#fff" }, layout: { "line-cap": "round" } });
  add({ id: "shift-line", type: "line", source: "shift", filter: ["==", "k", "l"], paint: { "line-width": 3, "line-color": "#000" }, layout: { "line-cap": "round" } });
  add({ id: "shift-a", type: "circle", source: "shift", filter: ["==", "k", "a"], paint: { "circle-radius": 7, "circle-stroke-width": 3, "circle-color": "#fff", "circle-stroke-color": "#000" } });
  add({ id: "shift-b", type: "circle", source: "shift", filter: ["==", "k", "b"], paint: { "circle-radius": 7, "circle-stroke-width": 2, "circle-color": "#000", "circle-stroke-color": "#fff" } });
  styleShift(); shiftLayer();
}
let styleOk = false, started = false;
function tryStart() { if (started || !styleOk || !S.sp || !INFO[S.sp]) return; started = true; if (!INFO[S.sp].ssps.includes(S.ssp)) S.ssp = INFO[S.sp].ssps[0]; update(true, false); }
function startMap() {
  map = new maplibregl.Map({ container: "map", style: baseStyle(), center: [-30, 30], zoom: 1.2, renderWorldCopies: false, attributionControl: false, maxZoom: 9, minZoom: 0.3, dragRotate: false, pitchWithRotate: false, touchPitch: false });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  window.__map = map;
  let styled = false;
  map.on("error", e => { const u = String((e && e.error && (e.error.message || e.error)) || ""); if (!styled && !useLand && /style|openfreemap|Failed to fetch|NetworkError|tiles/i.test(u)) { useLand = true; map.setStyle(BLANK); } });
  map.on("style.load", () => {
    styled = true; if (useLand) map.setPaintProperty("bg", "background-color", getComputedStyle(document.documentElement).getPropertyValue("--ocean").trim());
    addLayers(); window.__styleReady = (window.__styleReady || 0) + 1;
    styleOk = true;
    if (!started) tryStart(); else if (S.sp && INFO[S.sp]) loadScene(S.sp, S.ssp);
  });
  map.on("moveend", () => { if (!S.sp || !SHOWN.sp) return; const sc = sceneFiles(SHOWN.sp, SHOWN.ssp), f = levelFor(); for (const x of [useLand ? sc.land : null, sc.base, sc.scen]) if (x) visible(f).forEach(([bx, by]) => entry(x, f, bx, by)); });
}
async function boot() {
  const t0 = performance.now();
  const r = await fetch(DATA + "index.json"); if (!r.ok) throw new Error("index " + r.status);
  ST = await r.json(); ST.byId = Object.fromEntries(ST.species.map(s => [s.id, s])); T.index = Math.round(performance.now() - t0);
  $("count").textContent = ST.species.length;
  applyTheme(false); renderResults(); renderControls();
  startMap();
  const h = decodeURIComponent(location.hash.slice(1)), id = ST.byId[h] ? h : (ST.byId.acer_saccharum ? "acer_saccharum" : ST.species[0].id);
  const b = rec(id).bbox; map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: padFor(), duration: 0, maxZoom: 5 });
  S.sp = id; renderResults();
  await loadInfo(id);
  window.__S = S; window.__T = T;
  tryStart();
}
boot().catch(e => { $("fatal").hidden = false; $("fatal-msg").textContent = e.message; console.error(e); });
