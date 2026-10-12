/* The places map's basemap, shared so both halves of the site look the same: Positron, recoloured layer by layer for dark mode,
   with state and province lines from the continent view down. Copied from web/index.html (keep the two in step). */
const CTBASE = (() => {
const LBL_HALO="rgba(17,24,30,.9)";
const DARK_BASE={
  background:{"background-color":"#1d262e"},park:{"fill-color":"#1f2a2a"},water:{"fill-color":"#0d151b"},
  landcover_ice_shelf:{"fill-color":"#2a333b"},landcover_glacier:{"fill-color":"#2a333b"},
  landuse_residential:{"fill-color":"#222b33"},landcover_wood:{"fill-color":"#1f2a28"},
  waterway:{"line-color":"#15212a"},building:{"fill-color":"#27313a","fill-outline-color":"#303a44"},
  "aeroway-area":{"fill-color":"#2a333b"},"aeroway-runway":{"line-color":"#39434c"},"aeroway-taxiway":{"line-color":"#313b44"},"aeroway-runway-casing":{"line-color":"#2a333b"},
  road_area_pier:{"fill-color":"#1d262e"},road_pier:{"line-color":"#1d262e"},
  highway_path:{"line-color":"#2e3841"},highway_minor:{"line-color":"#333d47"},
  highway_major_casing:{"line-color":"#2a333c"},highway_major_inner:{"line-color":"#3e4852"},highway_major_subtle:{"line-color":"rgba(78,90,101,.55)"},
  highway_motorway_casing:{"line-color":"#2a333c"},highway_motorway_inner:{"line-color":"#4a5560"},highway_motorway_subtle:{"line-color":"rgba(78,90,101,.5)"},
  highway_motorway_bridge_casing:{"line-color":"#2a333c"},highway_motorway_bridge_inner:{"line-color":"#4a5560"},
  tunnel_motorway_casing:{"line-color":"#2a333c"},tunnel_motorway_inner:{"line-color":"#343e48"},
  railway:{"line-color":"#3a444d"},railway_dashline:{"line-color":"#1d262e"},railway_transit:{"line-color":"#3a444d"},railway_transit_dashline:{"line-color":"#1d262e"},
  railway_service:{"line-color":"#3a444d"},railway_service_dashline:{"line-color":"#1d262e"},
  boundary_2:{"line-color":"#8793a0"},boundary_3:{"line-color":"#5f6b77"},boundary_disputed:{"line-color":"#8793a0"},
  waterway_line_label:{"text-color":"#667a88","text-halo-color":"rgba(13,21,27,.75)"},
  water_name_point_label:{"text-color":"#86a0d2","text-halo-color":"rgba(13,21,27,.75)"},water_name_line_label:{"text-color":"#86a0d2","text-halo-color":"rgba(13,21,27,.75)"},
  "highway-name-path":{"text-color":"#8f9aa4","text-halo-color":"#172028"},"highway-name-minor":{"text-color":"#9aa5ae","text-halo-color":"#172028"},"highway-name-major":{"text-color":"#9aa5ae","text-halo-color":"#172028"},
  "highway-shield-non-us":{"icon-opacity":0.55},"highway-shield-us-interstate":{"icon-opacity":0.55},road_shield_us:{"icon-opacity":0.55},
  airport:{"text-color":"#9aa5ae","text-halo-color":"#172028"},
  label_other:{"text-color":"#aeb8c1","text-halo-color":LBL_HALO},label_state:{"text-color":"#aeb8c1","text-halo-color":LBL_HALO},
  label_village:{"text-color":"#dfe5ea","text-halo-color":LBL_HALO},label_town:{"text-color":"#e6ebef","text-halo-color":LBL_HALO},
  label_city:{"text-color":"#eef2f5","text-halo-color":LBL_HALO},label_city_capital:{"text-color":"#eef2f5","text-halo-color":LBL_HALO},
  label_country_1:{"text-color":"#eef2f5","text-halo-color":LBL_HALO},label_country_2:{"text-color":"#e6ebef","text-halo-color":LBL_HALO},label_country_3:{"text-color":"#dfe5ea","text-halo-color":LBL_HALO}};
const cnorm=(()=>{const c=document.createElement("canvas").getContext("2d");return v=>{c.fillStyle="#000";c.fillStyle=v;return c.fillStyle;};})();
// Fallback for layers not in DARK_BASE: fills/lines become dark slate, text becomes light, halos dark.
function darkColor(v,prop){
  if(Array.isArray(v))return v.map(x=>darkColor(x,prop));
  if(typeof v!=="string"||!/^(#|rgb|hsl)/i.test(v))return v;
  const n=cnorm(v);let r,g,b,a=1;
  if(n[0]==="#"){const x=parseInt(n.slice(1),16);r=x>>16&255;g=x>>8&255;b=x&255;}else{const m=n.match(/[\d.]+/g).map(Number);[r,g,b]=m;if(m.length>3)a=m[3];}
  const L=(0.2126*r+0.7152*g+0.0722*b)/255,mix=(t,base)=>base.map(c=>Math.round(c+t*(255-c)));
  let o;if(prop==="text-color")o=mix(0.55+0.35*(1-L),[40,50,60]);else if(prop==="text-halo-color")o=[17,24,30];else o=mix(0.03+0.14*(1-L),[24,32,40]);
  return a<1?`rgba(${o[0]},${o[1]},${o[2]},${a})`:`rgb(${o[0]},${o[1]},${o[2]})`;}

let baseOrig = null;
function reset() { baseOrig = null; }
function stateLines(map, dark) {
  if (!map || !map.getLayer("boundary_3")) return;
  try {
    map.setLayerZoomRange("boundary_3", 2, 24);
    map.setFilter("boundary_3", ["all", ["==", ["get", "admin_level"], 4], ["!=", ["get", "maritime"], 1]]);
    map.setPaintProperty("boundary_3", "line-color", dark ? "#6f7c89" : "#98a1ab");
    map.setPaintProperty("boundary_3", "line-width", ["interpolate", ["linear"], ["zoom"], 2, 0.6, 5, 1, 8, 1.4, 12, 2]);
    map.setPaintProperty("boundary_3", "line-opacity", ["interpolate", ["linear"], ["zoom"], 2, 0.65, 4, 1]);
    map.setPaintProperty("boundary_3", "line-dasharray", [3, 2]);
  } catch (e) { }
}
const SKIP = id => id === "species" || id.startsWith("shift-");
function paint(map, dark) {
  const st = map.getStyle(); if (!st || !st.layers) return;
  if (!baseOrig) { baseOrig = {}; for (const l of st.layers) { if (SKIP(l.id)) continue; const o = {}, p = l.paint || {}; for (const k in p) if (/color|icon-opacity/.test(k)) o[k] = p[k]; baseOrig[l.id] = o; } }
  for (const l of st.layers) {
    const o = baseOrig[l.id]; if (!o) continue; const d = DARK_BASE[l.id] || {}, keys = new Set([...Object.keys(o), ...Object.keys(d)]);
    for (const k of keys) { let v; if (dark) v = k in d ? d[k] : /color/.test(k) ? darkColor(o[k], k) : o[k]; else v = o[k]; try { map.setPaintProperty(l.id, k, v); } catch (e) { } }
  }
}
return { paint, stateLines, reset };
})();
