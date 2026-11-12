// The methods page: citation, version details and the organism records table. RELEASE and DATA_VERSION come from
// <html data-release data-version>, which the build fills in.
"use strict";
// ---- release details: edit these when publishing a new version
const AUTHOR={name:"Climate Twins"};
const TITLE="Climate Twins: present-day climate analogs for projected 2050 and 2100 climates";
const RELEASE=document.documentElement.dataset.release, DATA_VERSION=document.documentElement.dataset.version, YEAR="2026";
const MODELS=[["ACCESS-CM2","r1i1p1f1",2.10],["AWI-CM-1-1-MR","r1i1p1f1",2.06],["BCC-CSM2-MR","r1i1p1f1",1.72],["CNRM-CM6-1-HR","r1i1p1f2",2.48],
  ["CNRM-CM6-1","r1i1p1f2",2.14],["CNRM-ESM2-1","r1i1p1f2",1.86],["CanESM5-CanOE","r1i1p2f1",2.74],["CanESM5","r1i1p2f1",2.74],
  ["EC-Earth3-Veg-LR","r1i1p1f1",null],["EC-Earth3-Veg","r4i1p1f1",2.62],["EC-Earth3","r4i1p1f1",2.30],["FGOALS-g3","r1i1p1f1",1.54],
  ["GFDL-ESM4","r1i1p1f1",1.63],["GISS-E2-1-G","r1i1p3f1",1.80],["INM-CM4-8","r1i1p1f1",1.33],["INM-CM5-0","r1i1p1f1",1.41],
  ["IPSL-CM6A-LR","r1i1p1f1",2.32],["KACE-1-0-G","r1i1p1f1",2.04],["MIROC-ES2L","r4i1p1f2",1.55],["MIROC6","r1i1p1f1",1.55],
  ["MPI-ESM1-2-HR","r1i1p1f1",1.66],["MPI-ESM1-2-LR","r1i1p1f1",1.84],["MRI-ESM2-0","r1i1p1f1",1.64],["UKESM1-0-LL","r1i1p1f2",2.79]];

document.getElementById("m-author").textContent=AUTHOR.name;
document.querySelectorAll(".v-rel").forEach(e=>e.textContent=RELEASE);
document.querySelectorAll(".v-data").forEach(e=>e.textContent=DATA_VERSION);
document.getElementById("modeltable").innerHTML=MODELS.map(([m,r,t])=>{
  const inE=t!=null&&t>=1.4&&t<=2.2,why=t==null?"No TCR in table":t>2.2?"Above range":"Below range";
  return `<tr><td>${m}</td><td>${r}</td><td class="n">${t==null?"–":t.toFixed(2)}</td><td>${inE?'<span class="tag in">Yes</span>':`<span class="tag out">${why}</span>`}</td></tr>`;}).join("");

// ---- suggested citation, with this site's own address and today's date
const mapURL=new URL("./",location.href).href.replace(/\/methods(\.html)?\/?$/,"/");
const today=new Date(),months=["January","February","March","April","May","June","July","August","September","October","November","December"];
const acc=`${months[today.getMonth()]} ${today.getDate()}, ${today.getFullYear()}`,iso=today.toISOString().slice(0,10);
const apa=`${AUTHOR.name} (${YEAR}). ${TITLE} (Version ${RELEASE}, data version ${DATA_VERSION}) [Interactive web map]. Retrieved ${acc}, from ${mapURL}`;
document.getElementById("c-apa").innerHTML=`${AUTHOR.name} (${YEAR}). <em>${TITLE}</em> (Version ${RELEASE}, data version ${DATA_VERSION}) [Interactive web map]. Retrieved ${acc}, from <a href="${mapURL}">${mapURL}</a>`;
document.getElementById("c-bib").textContent=`@misc{climatetwins${YEAR},
  author       = {{${AUTHOR.name}}},
  title        = {{${TITLE}}},
  year         = {${YEAR}},
  version      = {${RELEASE}},
  note         = {Interactive web map; data version ${DATA_VERSION}},
  howpublished = {\\url{${mapURL}}},
  urldate      = {${iso}}
}`;
document.querySelectorAll("[data-copy]").forEach(b=>b.addEventListener("click",async()=>{
  const id=b.dataset.copy,txt=id==="c-apa"?apa:document.getElementById(id).textContent,st=document.querySelector(".copied");
  try{await navigator.clipboard.writeText(txt);st.textContent="Copied.";}catch(e){st.textContent="Copying isn't available here; select the text instead.";}
  setTimeout(()=>st.textContent="",2500);}));

// ---- theme: shared with the map through localStorage "ct-theme"
const KEY="ct-theme",sys=matchMedia("(prefers-color-scheme: dark)"),RM=matchMedia("(prefers-reduced-motion: reduce)").matches;
const SUN='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4.2" fill="currentColor" stroke="none"/><path d="M12 2.5v2.3M12 19.2v2.3M2.5 12h2.3M19.2 12h2.3M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></svg>';
const MOON='<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M20.3 14.6A8.6 8.6 0 0 1 9.4 3.7a8.6 8.6 0 1 0 10.9 10.9z"/></svg>';
function saved(){try{const t=localStorage.getItem(KEY);return t==="dark"||t==="light"?t:null;}catch(e){return null;}}
let dark=saved()?saved()==="dark":sys.matches;
const btn=document.getElementById("themebtn");
function paint(anim){document.documentElement.setAttribute("data-theme",dark?"dark":"light");const lbl=dark?"Light mode":"Dark mode";
  const set=()=>{btn.innerHTML=dark?SUN:MOON;btn.setAttribute("aria-label",lbl);btn.title=lbl;btn.setAttribute("aria-pressed",String(dark));};
  if(!anim||RM){set();return;}btn.classList.add("spin");setTimeout(()=>{set();btn.classList.remove("spin");},180);}
paint(false);
btn.addEventListener("click",()=>{dark=!dark;try{localStorage.setItem(KEY,dark?"dark":"light");}catch(e){}paint(true);});
sys.addEventListener("change",e=>{if(!saved()){dark=e.matches;paint(true);}});
window.addEventListener("storage",e=>{if(e.key===KEY&&e.newValue){dark=e.newValue==="dark";paint(false);}});

// ---- contents: collapsed on narrow screens, opens on tap, closes after choosing a section
(()=>{const n=document.querySelector("nav.toc"),h=n&&n.querySelector("h2");if(!h)return;h.tabIndex=0;h.setAttribute("role","button");
  const narrow=matchMedia("(max-width:900px)"),set=o=>{n.classList.toggle("open",o);h.setAttribute("aria-expanded",String(o));};
  set(false);h.addEventListener("click",()=>{if(narrow.matches)set(!n.classList.contains("open"));});
  h.addEventListener("keydown",e=>{if((e.key==="Enter"||e.key===" ")&&narrow.matches){e.preventDefault();set(!n.classList.contains("open"));}});
  n.addEventListener("click",e=>{if(narrow.matches&&e.target.closest("a"))set(false);});})();
// ---- contents: mark the section being read
const links=[...document.querySelectorAll("nav.toc a")],secs=links.map(a=>document.querySelector(a.getAttribute("href")));
if("IntersectionObserver" in window){const vis=new Map();
  const io=new IntersectionObserver(es=>{es.forEach(e=>vis.set(e.target,e.isIntersecting));
    const first=secs.find(s=>vis.get(s));if(first)links.forEach((a,i)=>a.classList.toggle("on",secs[i]===first));},{rootMargin:"-10% 0px -70% 0px"});
  secs.forEach(s=>s&&io.observe(s));}

(async()=>{const m=document.querySelector('meta[name="species-data-base"]');const base=new URL(m.content,location.href).href.replace(/\/?$/,"/");const tb=document.getElementById("doirows");
const G={tree:"Trees",bird:"Birds",mammal:"Mammals",insect_arachnid:"Insects and ticks",wild_plant:"Wild plants",crop:"Crops",reptile:"Reptiles and amphibians",amphibian:"Reptiles and amphibians",fish:"Fish"},esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
try{const ix=await (await fetch(base+"index.json")).json();tb.innerHTML=ix.species.map(s=>`<tr><td>${esc(s.name)} <i>(${esc(s.sci)})</i></td><td>${esc(G[s.group]||(s.group[0].toUpperCase()+s.group.slice(1).replace(/_/g," ")))}</td><td>${s.tier}</td><td>${s.season?"breeding season":"all year"}</td><td>${(s.dois||[]).map(d=>`<a href="${esc(d)}">${esc(d.replace("https://doi.org/","doi:"))}</a>`).join(", ")||"n/a"}</td></tr>`).join("");}
catch(e){tb.innerHTML='<tr><td colspan="5">The organism list could not be loaded.</td></tr>';}})();
