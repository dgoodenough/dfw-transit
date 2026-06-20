$ErrorActionPreference="Stop"
$dir=(Split-Path $PSScriptRoot -Parent)
$dbdir="$dir\db"

# SINGLE SOURCE OF TRUTH: the unified db tables (years are data; edit a cell -> rebuild)
$stations=Import-Csv "$dbdir\stations.csv"
$segs=Import-Csv "$dbdir\segments.csv"
# color fix: extra Silver (#BDBDBD) is too light to see on the CARTO light basemap -> darker slate
foreach($x in $segs){ if($x.color -eq '#BDBDBD'){$x.color='#6b7785'} }
foreach($x in $stations){ if($x.color -eq '#BDBDBD'){$x.color='#6b7785'} }
function ParseWkt($wkt){ $inner=$wkt -replace '^LINESTRING \(','' -replace '\)$',''
  $pc=@(); foreach($p in ($inner -split ',')){ $xy=$p.Trim() -split '\s+'; $pc+=,@([double]$xy[0],[double]$xy[1]) }; return ,$pc }

# FW stations JSON
$stJs=@(); foreach($s in ($stations | Where-Object {$_.src -eq 'fw'})){
  $stJs+='"'+$s.station_id+'":{"n":"'+($s.name -replace '"','\"')+'","lat":'+$s.lat+',"lon":'+$s.lon+',"yr":'+$s.year_opens+',"act":'+$s.act+',"lines":"'+$s.lines+'"}' }
$ST='{'+($stJs -join ',')+'}'

# FW segments JSON (per-line years from DB) + canonical orientation for stable offsets
$segJs=@()
foreach($s in ($segs | Where-Object {$_.src -eq 'fw'})){
  $pc=ParseWkt $s.geometry_wkt
  $dx=$pc[-1][0]-$pc[0][0]; $dy=$pc[-1][1]-$pc[0][1]
  $fwd= if([math]::Abs($dx) -ge [math]::Abs($dy)){ $dx -ge 0 } else { $dy -ge 0 }
  if(-not $fwd){ [array]::Reverse($pc) }
  $g='['+(($pc | ForEach-Object { '['+$_[0]+','+$_[1]+']' }) -join ',')+']'
  $lns=$s.line -split ';'; $yrs=$s.year_opens -split ';'; $lp=@()
  for($i=0;$i -lt $lns.Count;$i++){ $y= if($i -lt $yrs.Count){$yrs[$i]}else{$yrs[-1]}; $lp+='{"l":"'+$lns[$i]+'","y":'+$y+'}' }
  $segJs+='{"g":'+$g+',"lp":['+($lp -join ',')+']}'
}
$SEG='['+($segJs -join ',')+']'

# EXTRA network from DB: segments (year-tagged, contiguous-by-construction) + stations
# group extra segments by endpoint-pair so paired tracks (two metro lines on one corridor) bundle for offset rendering
$exSegJs=@()
$exGrp=[ordered]@{}
foreach($s in ($segs | Where-Object {$_.src -eq 'extra'})){
  $pair=(@($s.from_id,$s.to_id) | Sort-Object) -join '|'
  $pc=ParseWkt $s.geometry_wkt
  $g='['+(($pc | ForEach-Object { '['+$_[0]+','+$_[1]+']' }) -join ',')+']'
  if(-not $exGrp.Contains($pair)){ $exGrp[$pair]=[ordered]@{g=$g;m=$s.mode;lines=[ordered]@{}} }
  foreach($ln in ($s.line -split ';')){ $exGrp[$pair].lines[$ln]=@{c=$s.color;y=$s.year_opens} }
}
foreach($k in $exGrp.Keys){ $b=$exGrp[$k]
  $lj=@(); foreach($ln in $b.lines.Keys){ $lj+='{"n":"'+($ln -replace '"','\"')+'","c":"'+$b.lines[$ln].c+'","y":'+$b.lines[$ln].y+'}' }
  $exSegJs+='{"m":"'+$b.m+'","lines":['+($lj -join ',')+'],"g":'+$b.g+'}'
}
$exStJs=@()
foreach($s in ($stations | Where-Object {$_.src -eq 'extra'})){
  $exStJs+='{"id":"'+$s.station_id+'","n":"'+($s.name -replace '"','\"')+'","m":"'+$s.mode+'","c":"'+$s.color+'","y":'+$s.year_opens+',"a":'+$s.act+',"lat":'+$s.lat+',"lon":'+$s.lon+',"lines":"'+($s.lines -replace '"','\"')+'"}'
}
$EXTRA='{"segs":['+($exSegJs -join ',')+'],"stops":['+($exStJs -join ',')+']}'

# ---- ROUTING GRAPH (p2p db: nodes + per-line ride edges; in-browser Dijkstra gives any pair on demand) ----
function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2); return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }
# spacing-dependent speeds: segment time = len/cruise*60 + per-stop penalty (segment length = local stop spacing)
$cruise=@{metro=63.0;brt=38.0;commuter=72.0}; $tstop=@{metro=1.2;brt=0.9;commuter=1.4}
$ndJs=@()
foreach($s in $stations){ $ndJs+='"'+$s.station_id+'":{"n":"'+($s.name -replace '"','\"')+'","lat":'+$s.lat+',"lon":'+$s.lon+',"m":"'+$s.mode+'","yr":'+$s.year_opens+',"lines":"'+($s.lines -replace '"','\"')+'"}' }
$NODES='{'+($ndJs -join ',')+'}'
$edJs=@()
foreach($s in $segs){
  $pc=ParseWkt $s.geometry_wkt; $len=0.0; for($i=1;$i -lt $pc.Count;$i++){ $len+=(Hav $pc[$i-1][1] $pc[$i-1][0] $pc[$i][1] $pc[$i][0]) }
  $vc= if($cruise.ContainsKey($s.mode)){$cruise[$s.mode]}else{45.0}; $ts= if($tstop.ContainsKey($s.mode)){$tstop[$s.mode]}else{1.0}; $t=[math]::Round($len/$vc*60+$ts,2)
  $lns=$s.line -split ';'; $yrs=$s.year_opens -split ';'
  for($i=0;$i -lt $lns.Count;$i++){ $y= if($i -lt $yrs.Count){$yrs[$i]}else{$yrs[-1]}
    $edJs+='{"a":"'+$s.from_id+'","b":"'+$s.to_id+'","l":"'+($lns[$i] -replace '"','\"')+'","m":"'+$s.mode+'","y":'+$y+',"t":'+$t+'}' }
}
$EDGES='['+($edJs -join ',')+']'
Set-Content "$dbdir\route_graph.json" ('{"nodes":'+$NODES+',"edges":'+$EDGES+'}') -Encoding utf8

# ---- line catalogue for the selector (name, mode, color), de-duped, FW core first ----
$COLfw=@{Teal='#00b251';Blue='#0896d7';Orange='#df8600';Pink='#d63384';Silver='#9aa0a6';Red='#bd1038';Purple='#7b2d8e'}
$lineMeta=[ordered]@{}
foreach($s in ($segs | Where-Object {$_.src -eq 'fw'})){ foreach($ln in ($s.line -split ';')){ if(-not $lineMeta.Contains($ln)){ $c= if($COLfw.Contains($ln)){$COLfw[$ln]}else{'#888'}; $lineMeta[$ln]=@{m='metro';c=$c} } } }
foreach($s in ($segs | Where-Object {$_.src -eq 'extra'})){ if(-not $lineMeta.Contains($s.line)){ $lineMeta[$s.line]=@{m=$s.mode;c=$s.color} } }
$modeRank=@{metro=0;commuter=1;brt=2}
$lmJs=@()
foreach($k in ($lineMeta.Keys | Sort-Object @{e={$modeRank[$lineMeta[$_].m]}},@{e={$_}})){
  $lmJs+='{"n":"'+($k -replace '"','\"')+'","m":"'+$lineMeta[$k].m+'","c":"'+$lineMeta[$k].c+'"}'
}
$LINES='['+($lmJs -join ',')+']'

$tpl=@'
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/>
<title>DFW Transit - Interactive Time-Series</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
 html,body{margin:0;height:100%} #map{position:absolute;inset:0}
 .panel{position:absolute;z-index:1000;top:12px;left:12px;background:rgba(255,255,255,.96);
  padding:14px 16px;border-radius:10px;box-shadow:0 1px 8px rgba(0,0,0,.25);font-family:Helvetica,Arial,sans-serif;width:300px}
 .panel h1{font-size:16px;margin:0 0 2px} .panel .sub{font-size:11px;color:#777;margin-bottom:10px}
 .row{display:flex;align-items:center;gap:10px;margin:8px 0}
 #year{font-size:22px;font-weight:700;min-width:64px} input[type=range]{flex:1}
 button{font-size:13px;padding:6px 12px;border:1px solid #bbb;background:#fff;border-radius:6px;cursor:pointer}
 button.primary{background:#0b7;color:#fff;border-color:#0b7}
 .modes label{font-size:13px;margin-right:12px;cursor:pointer}
 .legend{margin-top:8px;font-size:11px;color:#444;border-top:1px solid #eee;padding-top:6px}
 .legend i{display:inline-block;width:22px;height:0;border-top-width:4px;border-top-style:solid;margin-right:6px;vertical-align:middle}
 .added{font-size:11px;color:#555;margin-top:6px;min-height:26px}
 .lines{margin-top:8px;border-top:1px solid #eee;padding-top:6px}
 .lhdr{font-size:12px;font-weight:700;display:flex;justify-content:space-between;align-items:center;cursor:pointer}
 .lhdr .tog{font-size:11px;font-weight:400;color:#0a7}
 .lhdr .tog a{color:#0a7;text-decoration:underline;cursor:pointer;margin-left:6px}
 .llist{max-height:230px;overflow-y:auto;margin-top:4px;display:none}
 .llist.open{display:block}
 .lgrp{font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:#999;margin:6px 0 2px}
 .litem{display:flex;align-items:center;gap:6px;font-size:12px;padding:1px 0;cursor:pointer}
 .litem input{margin:0}
 .litem .sw{display:inline-block;width:16px;height:0;border-top:3px solid #888;flex:0 0 auto}
 .litem.off{opacity:.45}
 .pop b{font-size:13px}.pop .meta{font-size:11px;color:#555;margin-top:3px;line-height:1.45}
 .pop .ln{display:inline-block;margin:1px 4px 1px 0;padding:1px 6px;border-radius:8px;color:#fff;font-size:10px}
 button.trip.on{background:#7b2d8e;color:#fff;border-color:#7b2d8e}
 #trip{position:absolute;z-index:1000;top:12px;right:12px;width:280px;background:rgba(255,255,255,.97);
  padding:12px 14px;border-radius:10px;box-shadow:0 1px 8px rgba(0,0,0,.25);font-family:Helvetica,Arial,sans-serif;display:none}
 #trip.show{display:block}
 #trip h2{font-size:14px;margin:0 0 6px} #trip .ep{font-size:12px;margin:2px 0}
 #trip .ep b{display:inline-block;min-width:14px}
 #trip .tot{font-size:13px;font-weight:700;margin:8px 0 4px;border-top:1px solid #eee;padding-top:6px}
 #trip .leg{font-size:11px;color:#444;margin:3px 0;line-height:1.4;display:flex;gap:6px}
 #trip .leg .lc{width:10px;flex:0 0 auto;border-radius:2px}
 #trip .hint{font-size:11px;color:#888} #trip .close{float:right;cursor:pointer;color:#999}
</style></head><body>
<div id="map"></div>
<div id="trip">
 <span class="close" id="tripclose">&#10005;</span>
 <h2>Trip planner</h2>
 <div class="ep"><b>A</b> <span id="epA">click a station&hellip;</span></div>
 <div class="ep"><b>B</b> <span id="epB">click a station&hellip;</span></div>
 <div id="tripout"><div class="hint">Pick two stations on the map. Routes use the network shown at the current year.</div></div>
</div>
<div class="panel">
 <h1>DFW Transit &mdash; hypothetical</h1>
 <div class="sub">First pass. Opening year = phase band refined by distance to nearest core. 5-yr steps; edit phases in db/ to refine.</div>
 <div class="row"><span id="year">Existing</span><input type="range" id="phase" min="0" max="8" step="1" value="0"/></div>
 <div class="row"><button id="play" class="primary">&#9654; Play</button><button id="tripbtn" class="trip">&#128205; Plan a trip</button></div>
 <div class="row modes">
   <label><input type="checkbox" id="m_metro" checked> Metro</label>
   <label><input type="checkbox" id="m_commuter" checked> Commuter</label>
   <label><input type="checkbox" id="m_brt" checked> BRT</label>
 </div>
 <div class="added" id="added"></div>
 <div class="lines">
   <div class="lhdr" id="lhdr"><span>Lines &#9662;</span><span class="tog"><a id="lall">all</a><a id="lnone">none</a></span></div>
   <div class="llist" id="llist"></div>
 </div>
 <div class="legend">
   <div><i style="border-top-style:solid;border-color:#444"></i>Metro &middot; <i style="border-top-style:dashed;border-color:#5b6770"></i>Commuter &middot; <i style="border-top-style:dotted;border-color:#00838f"></i>BRT</div>
   <div style="margin-top:4px">stations: <b style="color:#16a34a">&#9679;</b> new this step &nbsp; <b style="color:#9aa0a6">&#9679;</b> existing today &nbsp; <span style="color:#999">&#9711;</span> already open</div>
 </div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const ST=__ST__, SEG=__SEG__, EXTRA=__EXTRA__, LINES=__LINES__, NODES=__NODES__, EDGES=__EDGES__;
// per-line visibility (default all on). Stations/segments hidden when their line(s) are off.
const LINEVIS={}; LINES.forEach(l=>LINEVIS[l.n]=true);
function lineOn(n){ return LINEVIS[n]!==false; }
function anyLineOn(arr){ return !arr.length || arr.some(lineOn); }
// station status colour relative to the scrubber year: existing today / new this step / already open
function statusColor(yr,cur){ return yr<=2025 ? '#9aa0a6' : (yr===cur ? '#16a34a' : '#ffffff'); }
function actTxt(a){ return (a&&a>0)?('<br>'+a.toLocaleString()+' pop+jobs/km'):''; }
function openTxt(yr){ return yr<=2025 ? 'existing today' : ('opens '+yr); }
function colFor(n){ const m=LINES.find(l=>l.n===n); return m?m.c:'#888'; }
function linePills(arr){ return arr.map(n=>'<span class="ln" style="background:'+colFor(n)+'">'+n+'</span>').join(''); }
function stationPopup(name,arr,mode,yr,act,lat,lon){
 const interchange = arr.length>=2 ? ' &middot; <b>interchange</b>' : '';
 return '<div class="pop"><b>'+name+'</b>'
  +'<div class="meta"><b>'+arr.length+' line'+(arr.length===1?'':'s')+'</b>'+interchange+'<br>'+linePills(arr)
  +'<br>mode: '+mode+'<br>'+openTxt(yr)+(act&&act>0?('<br>'+act.toLocaleString()+' pop+jobs / km'):'')
  +'<br><span style="color:#999">'+lat.toFixed(4)+', '+lon.toFixed(4)+'</span></div></div>';
}
const COL={Teal:'#00b251',Blue:'#0896d7',Orange:'#df8600',Pink:'#d63384',Silver:'#9aa0a6',Red:'#bd1038',Purple:'#7b2d8e'};
const ORDER=['Teal','Blue','Orange','Pink','Silver','Red','Purple'];
const SPACING=5, WEIGHT=4;
// 5-year scrubber. All opening years come from the DB (db/stations.csv + db/segments.csv) - no formulas here.
const STEPS=[2025,2035,2040,2045,2050,2055,2060,2065,2070];
function stepLabel(y){ return y===2025?'Existing':(''+y); }
const MODES={metro:true,commuter:true,brt:true};
const map=L.map('map').setView([32.78,-97.05],10);
const cartoAttr='&copy; OpenStreetMap &copy; CARTO';
const baseLayers={
 'Light':L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:20,attribution:cartoAttr}),
 'Dark':L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:20,attribution:cartoAttr}),
 'Streets':L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:20,attribution:cartoAttr}),
 'Satellite':L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles &copy; Esri'})
};
baseLayers['Light'].addTo(map);
L.control.layers(baseLayers,null,{position:'bottomright'}).addTo(map);

let cur=0, layers=[], fitted=false, timer=null;
function clr(){ layers.forEach(l=>map.removeLayer(l)); layers=[]; }
function offsetLL(geo, off){
 const pts=geo.map(g=>map.latLngToLayerPoint([g[1],g[0]])); const out=[];
 for(let i=0;i<pts.length;i++){ let nx=0,ny=0,c=0;
  if(i>0){const dx=pts[i].x-pts[i-1].x,dy=pts[i].y-pts[i-1].y,L1=Math.hypot(dx,dy)||1;nx+=-dy/L1;ny+=dx/L1;c++;}
  if(i<pts.length-1){const dx=pts[i+1].x-pts[i].x,dy=pts[i+1].y-pts[i].y,L1=Math.hypot(dx,dy)||1;nx+=-dy/L1;ny+=dx/L1;c++;}
  if(c){nx/=c;ny/=c;const L2=Math.hypot(nx,ny)||1;nx/=L2;ny/=L2;}
  out.push(map.layerPointToLatLng(L.point(pts[i].x+nx*off, pts[i].y+ny*off))); }
 return out;
}
function styleFor(mode,color){
 if(mode==='commuter') return {color:color,weight:3.5,opacity:.9,dashArray:'10 7'};
 if(mode==='brt') return {color:color,weight:3,opacity:.95,dashArray:'1 8',lineCap:'round'};
 return {color:color,weight:WEIGHT,opacity:.95,lineCap:'round',lineJoin:'round'};
}
function render(){
 clr(); const curYear=STEPS[cur];
 // FW metro via offset segment graph (per-line years from DB)
 if(MODES.metro){
  SEG.forEach(s=>{ const bundle=s.lp.map(x=>x.l).sort((a,b)=>ORDER.indexOf(a)-ORDER.indexOf(b)); const n=bundle.length;
   s.lp.forEach(x=>{ if(x.y>curYear) return; if(!lineOn(x.l)) return; const slot=bundle.indexOf(x.l)-(n-1)/2;
    layers.push(L.polyline(offsetLL(s.g,slot*SPACING),{color:COL[x.l],weight:WEIGHT,opacity:.95,lineCap:'round',lineJoin:'round'}).addTo(map)); }); });
 }
 // EXTRA network: between-station segments (clip-rule years from DB -> contiguous growth, no overhang)
 EXTRA.segs.forEach(s=>{ if(!MODES[s.m]) return;
  const vis=s.lines.filter(l=>lineOn(l.n) && l.y<=curYear); if(!vis.length) return;
  if(s.m==='metro' && s.lines.length>1){   // paired metro track -> offset side-by-side, both colors
   const order=s.lines.map(l=>l.n).slice().sort(); const n=order.length;
   vis.forEach(l=>{ const slot=order.indexOf(l.n)-(n-1)/2;
    const pl=L.polyline(offsetLL(s.g,slot*SPACING),{color:l.c,weight:WEIGHT,opacity:.95,lineCap:'round',lineJoin:'round'}).addTo(map);
    pl.bindPopup('<div class="pop"><b>'+l.n+'</b><div class="meta">mode: '+s.m+' &middot; '+openTxt(l.y)+'</div></div>'); layers.push(pl); }); }
  else { vis.forEach(l=>{ const pl=L.polyline(s.g.map(c=>[c[1],c[0]]),styleFor(s.m,l.c)).addTo(map);
    pl.bindPopup('<div class="pop"><b>'+l.n+'</b><div class="meta">mode: '+s.m+' &middot; '+openTxt(l.y)+'</div></div>'); layers.push(pl); }); }
 });
 EXTRA.stops.forEach(p=>{ if(!MODES[p.m]) return; const lns=p.lines?p.lines.split(';'):[]; if(!anyLineOn(lns)) return; if(p.y>curYear) return; const fc=statusColor(p.y,curYear); const multi=lns.length>=2;
  const mk=L.circleMarker([p.lat,p.lon],{radius:p.y===curYear?(multi?5:4.4):(multi?4.6:3.4),color:multi?'#222':p.c,weight:multi?2:1.3,fillColor:fc,fillOpacity:1}).bindPopup(stationPopup(p.n,lns,p.m,p.y,p.a,p.lat,p.lon)).addTo(map); tripify(mk,p.id); layers.push(mk); });
 // FW stations
 if(MODES.metro){ Object.entries(ST).forEach(([id,st])=>{ if(st.yr>curYear) return; const lines=st.lines?st.lines.split(';'):[]; if(!anyLineOn(lines)) return; const multi=lines.length>=2;
   const ring=multi?'#222':(lines.length?COL[lines[0]]:'#666'); const fc=statusColor(st.yr,curYear);
   const mk=L.circleMarker([st.lat,st.lon],{radius:(st.yr===curYear?5.4:(multi?5:3.8)),color:ring,weight:2,fillColor:fc,fillOpacity:1}).bindPopup(stationPopup(st.n,lines,'metro',st.yr,st.act,st.lat,st.lon)).addTo(map); tripify(mk,id); layers.push(mk); }); }
 if(!fitted){ const b=[]; SEG.forEach(s=>s.g.forEach(g=>b.push([g[1],g[0]]))); EXTRA.segs.forEach(s=>s.g.forEach(c=>b.push([c[1],c[0]])));
   if(b.length) map.fitBounds(L.latLngBounds(b).pad(.05)); fitted=true; }
 document.getElementById('year').textContent=stepLabel(curYear); document.getElementById('added').textContent=(curYear===2025?'Existing systems today (DART, TRE, TexRail, A-train) - real station locations.':'Network as of '+curYear+'.');
}
const sl=document.getElementById('phase'),pb=document.getElementById('play');
sl.addEventListener('input',()=>{stop();cur=+sl.value;render();if(epA&&epB)runTrip();});
['metro','commuter','brt'].forEach(m=>document.getElementById('m_'+m).addEventListener('change',e=>{MODES[m]=e.target.checked;render();}));
// ---- per-line selector ----
const llist=document.getElementById('llist');
const MLABEL={metro:'Metro',commuter:'Commuter Rail',brt:'BRT'};
['metro','commuter','brt'].forEach(mode=>{
 const grp=LINES.filter(l=>l.m===mode); if(!grp.length) return;
 const h=document.createElement('div'); h.className='lgrp'; h.textContent=MLABEL[mode]+' ('+grp.length+')'; llist.appendChild(h);
 grp.forEach(l=>{
  const lab=document.createElement('label'); lab.className='litem'; lab.title=l.n;
  const cb=document.createElement('input'); cb.type='checkbox'; cb.checked=true; cb.dataset.ln=l.n;
  const sw=document.createElement('i'); sw.className='sw'; sw.style.borderTopColor=l.c;
  if(l.m==='commuter'){sw.style.borderTopStyle='dashed';} else if(l.m==='brt'){sw.style.borderTopStyle='dotted';}
  const tx=document.createElement('span'); tx.textContent=l.n;
  cb.addEventListener('change',e=>{ LINEVIS[l.n]=e.target.checked; lab.classList.toggle('off',!e.target.checked); render(); });
  lab.appendChild(cb); lab.appendChild(sw); lab.appendChild(tx); llist.appendChild(lab);
 });
});
function setAll(v){ LINES.forEach(l=>LINEVIS[l.n]=v); llist.querySelectorAll('input').forEach(cb=>{cb.checked=v; cb.closest('.litem').classList.toggle('off',!v);}); render(); }
document.getElementById('lall').onclick=(e)=>{e.stopPropagation();setAll(true);};
document.getElementById('lnone').onclick=(e)=>{e.stopPropagation();setAll(false);};
document.getElementById('lhdr').onclick=()=>{llist.classList.toggle('open');};
function stop(){if(timer){clearInterval(timer);timer=null;pb.innerHTML='&#9654; Play';pb.classList.add('primary');}}
pb.onclick=()=>{if(timer){stop();return;}pb.innerHTML='&#10073;&#10073; Pause';pb.classList.remove('primary');timer=setInterval(()=>{cur=(cur+1)%9;sl.value=cur;render();if(epA&&epB)runTrip();},1400);};
map.on('zoomend',render);

// ===== TRIP PLANNER: click two stations -> Dijkstra on the open network -> time + path =====
const WAIT={metro:5,brt:5,commuter:12};
function hav(la1,lo1,la2,lo2){const R=6371,p=Math.PI/180,d1=(la2-la1)*p,d2=(lo2-lo1)*p;const a=Math.sin(d1/2)**2+Math.cos(la1*p)*Math.cos(la2*p)*Math.sin(d2/2)**2;return R*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));}
// walk transfers between distinct stations within 400m (precomputed once; coords static)
const NEARX=[]; (function(){ const ids=Object.keys(NODES); for(let i=0;i<ids.length;i++){ const a=NODES[ids[i]]; for(let j=i+1;j<ids.length;j++){ const b=NODES[ids[j]]; if(Math.abs(a.lat-b.lat)>0.004||Math.abs(a.lon-b.lon)>0.0048) continue; const d=hav(a.lat,a.lon,b.lat,b.lon); if(d<=0.4) NEARX.push([ids[i],ids[j],d/4.8*60+2]); } } })();
let tripMode=false, epA=null, epB=null, tripLayers=[], currentRoute=null;
function tripify(mk,id){ mk.on('click',function(e){ if(!tripMode) return; L.DomEvent.stopPropagation(e); map.closePopup(); pick(id); }); }
function nm(id){ return NODES[id]?NODES[id].n:id; }
function pick(id){ if(epA && !epB){ epB=id; } else { epA=id; epB=null; clearTrip(); } updEP(); if(epA&&epB) runTrip(); }
function updEP(){ document.getElementById('epA').textContent=epA?nm(epA):'click a station...'; document.getElementById('epB').textContent=epB?nm(epB):'click a station...'; }
function buildGraph(curYear){
 const adj={}; const add=(a,b,w,k)=>{(adj[a]=adj[a]||[]).push({b,w,k});};
 EDGES.forEach(e=>{ if(e.y>curYear) return; const na=NODES[e.a],nb=NODES[e.b]; if(!na||!nb||na.yr>curYear||nb.yr>curYear) return;
  const la='L:'+e.a+'|'+e.l, lb='L:'+e.b+'|'+e.l; add(la,lb,e.t,'ride'); add(lb,la,e.t,'ride');
  const w=WAIT[e.m]||6; add('P:'+e.a,la,w,'board'); add(la,'P:'+e.a,0,'alight'); add('P:'+e.b,lb,w,'board'); add(lb,'P:'+e.b,0,'alight'); });
 NEARX.forEach(x=>{ const a=NODES[x[0]],b=NODES[x[1]]; if(a.yr>curYear||b.yr>curYear) return; add('P:'+x[0],'P:'+x[1],x[2],'xferwalk'); add('P:'+x[1],'P:'+x[0],x[2],'xferwalk'); });
 return adj;
}
function dijkstra(adj,src,dst){
 const dist={},prev={},pk={},done={}; dist[src]=0; const fr=new Set([src]);
 while(fr.size){ let u=null,bd=Infinity; fr.forEach(n=>{ if(dist[n]<bd){bd=dist[n];u=n;} }); fr.delete(u); if(done[u])continue; done[u]=1; if(u===dst)break;
  (adj[u]||[]).forEach(e=>{ const nd=dist[u]+e.w; if(dist[e.b]===undefined||nd<dist[e.b]){ dist[e.b]=nd;prev[e.b]=u;pk[e.b]=e.k; if(!done[e.b])fr.add(e.b); } }); }
 if(dist[dst]===undefined) return null;
 const path=[]; let c=dst; while(c!==undefined){ path.unshift(c); if(c===src)break; c=prev[c]; }
 return {dist:dist[dst],path,pk};
}
function stOf(n){ return n.startsWith('P:')?n.slice(2):(n.startsWith('L:')?n.slice(2).split('|')[0]:null); }
function lnOf(n){ return n.startsWith('L:')?n.slice(2).split('|')[1]:null; }
function runTrip(){
 clearTrip(); const curYear=STEPS[cur];
 if(NODES[epA].yr>curYear||NODES[epB].yr>curYear){ currentRoute={err:'One station isn\'t open yet in '+stepLabel(curYear)+'.'}; drawPanel(); return; }
 const r=dijkstra(buildGraph(curYear),'P:'+epA,'P:'+epB);
 if(!r){ currentRoute={err:'No route on the '+stepLabel(curYear)+' network.'}; drawPanel(); return; }
 const legs=[]; let i=0; const p=r.path;
 while(i<p.length-1){ const k=r.pk[p[i+1]];
  if(k==='board'){ const ln=lnOf(p[i+1]); const start=stOf(p[i+1]); let j=i+1; let stops=0;
    while(j<p.length-1 && r.pk[p[j+1]]==='ride'){ j++; stops++; } const end=stOf(p[j]);
    const stations=[]; for(let z=i+1;z<=j;z++){ const s=stOf(p[z]); if(!stations.length||stations[stations.length-1]!==s) stations.push(s); }
    const mode=NODES[start].m;
    legs.push({type:'ride',line:ln,mode,stations,stops,from:nm(start),to:nm(end)}); i=j; }
  else i++; }
 currentRoute={tot:r.dist,legs,xfers:Math.max(0,legs.length-1)}; drawTrip(); drawPanel();
}
function clearTrip(){ tripLayers.forEach(l=>map.removeLayer(l)); tripLayers=[]; currentRoute=null; }
function drawTrip(){ tripLayers.forEach(l=>map.removeLayer(l)); tripLayers=[]; if(!currentRoute||currentRoute.err) return;
 currentRoute.legs.forEach(lg=>{ const pts=lg.stations.map(id=>[NODES[id].lat,NODES[id].lon]);
  tripLayers.push(L.polyline(pts,{color:'#fff',weight:9,opacity:.9}).addTo(map));
  tripLayers.push(L.polyline(pts,{color:colFor(lg.line),weight:5,opacity:1}).addTo(map)); });
 [epA,epB].forEach(id=>{ if(id) tripLayers.push(L.circleMarker([NODES[id].lat,NODES[id].lon],{radius:7,color:'#7b2d8e',weight:3,fillColor:'#fff',fillOpacity:1}).addTo(map)); });
}
function drawPanel(){ const out=document.getElementById('tripout');
 if(!currentRoute){ out.innerHTML='<div class="hint">Pick two stations on the map. Routes use the network shown at the current year.</div>'; return; }
 if(currentRoute.err){ out.innerHTML='<div class="hint" style="color:#b00">'+currentRoute.err+'</div>'; return; }
 const T=Math.round(currentRoute.tot), h=Math.floor(T/60), m=T%60; // round total first so 60 rolls to next hour
 let html='<div class="tot">'+(h?h+' h ':'')+m+' min &middot; '+currentRoute.legs.length+' vehicle'+(currentRoute.legs.length===1?'':'s')+', '+currentRoute.xfers+' transfer'+(currentRoute.xfers===1?'':'s')+'</div>';
 currentRoute.legs.forEach(lg=>{ html+='<div class="leg"><span class="lc" style="background:'+colFor(lg.line)+'"></span><span>'+lg.line+': '+lg.from+' &rarr; '+lg.to+' <span style="color:#999">('+lg.stops+' stop'+(lg.stops===1?'':'s')+')</span></span></div>'; });
 out.innerHTML=html;
}
const tb=document.getElementById('tripbtn'),tp=document.getElementById('trip');
tb.onclick=()=>{ tripMode=!tripMode; tb.classList.toggle('on',tripMode); tp.classList.toggle('show',tripMode); if(!tripMode){epA=epB=null;clearTrip();updEP();drawPanel();} };
document.getElementById('tripclose').onclick=()=>{ tripMode=false; tb.classList.remove('on'); tp.classList.remove('show'); epA=epB=null; clearTrip(); updEP(); drawPanel(); };
render();
</script></body></html>
'@
$html=$tpl.Replace('__ST__',$ST).Replace('__SEG__',$SEG).Replace('__EXTRA__',$EXTRA).Replace('__LINES__',$LINES).Replace('__NODES__',$NODES).Replace('__EDGES__',$EDGES)
$outHtml= if(Test-Path "$dir\maps"){"$dir\maps\FW_map_interactive.html"}else{"$dir\FW_map_interactive.html"}
Set-Content $outHtml $html -Encoding utf8
"app written from unified DB: $($stations.Count) stations / $($segs.Count) segments"