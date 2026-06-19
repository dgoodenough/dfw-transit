$ErrorActionPreference="Stop"
# Phase 1: audit every proposed commuter line's deviation from real OSM rail.
# Phase 2: re-route failers along the rail graph between their endpoints (gaps -> explicit new-build connectors).
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.9*[math]::PI/180)
function RDist($alon,$alat,$blon,$blat){ [math]::Sqrt([math]::Pow(($alon-$blon)*$mlon,2)+[math]::Pow(($alat-$blat)*$mlat,2)) }

# ---- rail points -> spatial grid for fast nearest queries ----
$rail=Get-Content "$ddir\dfw_rail.json" -Raw | ConvertFrom-Json
$grid=@{}; $cell=0.02
function GK($lon,$lat){ "{0}|{1}" -f [math]::Floor($lon/$cell),[math]::Floor($lat/$cell) }
$railPts=New-Object System.Collections.Generic.List[object]
foreach($w in $rail.elements){ if(-not $w.geometry){continue}
  $i=0
  foreach($g in $w.geometry){ if($i%2 -eq 0){
    $p=@([double]$g.lon,[double]$g.lat); [void]$railPts.Add($p)
    $k=GK $p[0] $p[1]; if(-not $grid.ContainsKey($k)){$grid[$k]=New-Object System.Collections.Generic.List[object]}
    [void]$grid[$k].Add($p) }; $i++ } }
"rail grid: $($railPts.Count) pts"
function NearRail($lon,$lat){
  $best=1e18
  $cx=[math]::Floor($lon/$cell); $cy=[math]::Floor($lat/$cell)
  for($dx=-1;$dx -le 1;$dx++){ for($dy=-1;$dy -le 1;$dy++){
    $k="{0}|{1}" -f ($cx+$dx),($cy+$dy)
    if($grid.ContainsKey($k)){ foreach($p in $grid[$k]){ $d=RDist $lon $lat $p[0] $p[1]; if($d -lt $best){$best=$d} } } } }
  return [math]::Sqrt(1)*$best
}

# ---- collect commuter lines ----
$lines=@()
foreach($gf in @("$dbdir\network_extra.geojson","$dbdir\commuter_ext.geojson","$dbdir\midlothian_ext.geojson")){
  if(-not (Test-Path $gf)){continue}
  foreach($f in ((Get-Content $gf -Raw | ConvertFrom-Json).features)){
    if($f.properties.kind -ne 'line' -or $f.properties.mode -ne 'commuter'){continue}
    if([int]$f.properties.phase -eq 0){continue}
    if(@('Cleburne Line (ROW)','Chico Line (ROW)') -contains $f.properties.name){continue}
    $coords=@(); foreach($c in $f.geometry.coordinates){ $coords+=,@([double]$c[0],[double]$c[1]) }
    if($coords.Count -ge 2){ $lines+=[pscustomobject]@{name=$f.properties.name;color=$f.properties.color;coords=$coords} }
  }
}
"commuter lines to audit: $($lines.Count)"

# ---- audit: sample every ~400m ----
"`n== ROW AUDIT (deviation from nearest rail) =="
$audit=@{}
foreach($L in $lines){
  $devs=New-Object System.Collections.Generic.List[double]
  for($i=0;$i -lt $L.coords.Count-1;$i++){
    $a=$L.coords[$i];$b=$L.coords[$i+1]; $seg=RDist $a[0] $a[1] $b[0] $b[1]
    $n=[math]::Max(1,[math]::Floor($seg/400))
    for($s=0;$s -lt $n;$s++){ $t=$s/$n; $lo=$a[0]+$t*($b[0]-$a[0]); $la=$a[1]+$t*($b[1]-$a[1])
      [void]$devs.Add((NearRail $lo $la)) }
  }
  $sorted=$devs | Sort-Object
  $p90=$sorted[[int][math]::Floor($sorted.Count*0.9)]
  $mx=$sorted[-1]
  $verdict= if($p90 -le 300){'PASS'} else {'FAIL'}
  $audit[$L.name]=$verdict
  "{0,-26} p90={1,6}m max={2,6}m  {3}" -f $L.name,[math]::Round($p90),[math]::Round($mx),$verdict
}

# ---- routing graph (contracted) for re-routes ----
$adj=@{};$coord=@{}
function NK($lon,$lat){ "{0:F6}|{1:F6}" -f $lon,$lat }
foreach($w in $rail.elements){ if(-not $w.geometry){continue}
  $g=$w.geometry
  for($i=0;$i -lt $g.Count-1;$i++){
    $alon=[double]$g[$i].lon;$alat=[double]$g[$i].lat;$blon=[double]$g[$i+1].lon;$blat=[double]$g[$i+1].lat
    $a=NK $alon $alat;$b=NK $blon $blat; if($a -eq $b){continue}
    if(-not $coord.ContainsKey($a)){$coord[$a]=@($alon,$alat)}
    if(-not $coord.ContainsKey($b)){$coord[$b]=@($blon,$blat)}
    $d=RDist $alon $alat $blon $blat
    if(-not $adj.ContainsKey($a)){$adj[$a]=@{}}; if(-not $adj.ContainsKey($b)){$adj[$b]=@{}}
    if(-not $adj[$a].ContainsKey($b) -or $adj[$a][$b] -gt $d){$adj[$a][$b]=$d}
    if(-not $adj[$b].ContainsKey($a) -or $adj[$b][$a] -gt $d){$adj[$b][$a]=$d}
  } }
$allK=@($coord.Keys)
function NearestNode($lon,$lat){ $best=1e18;$bk=$null; foreach($k in $allK){ $c=$coord[$k]; $dx=($c[0]-$lon)*$mlon; if([math]::Abs($dx) -gt 8000){continue}; $dy=($c[1]-$lat)*$mlat; $d=$dx*$dx+$dy*$dy; if($d -lt $best){$best=$d;$bk=$k} }; return @($bk,[math]::Sqrt($best)) }

$failers=@($lines | Where-Object { $audit[$_.name] -eq 'FAIL' })
$isJ=@{}; foreach($n in $adj.Keys){ if($adj[$n].Count -ne 2){$isJ[$n]=$true} }
$ends=@{}
foreach($L in $failers){
  $e1=NearestNode $L.coords[0][0] $L.coords[0][1]; $e2=NearestNode $L.coords[-1][0] $L.coords[-1][1]
  $ends[$L.name]=@($e1,$e2)
  if($e1[0]){$isJ[$e1[0]]=$true}; if($e2[0]){$isJ[$e2[0]]=$true}
}
"junctions: $($isJ.Count)"
$superAdj=@{}
foreach($j in $isJ.Keys){
  foreach($nb in @($adj[$j].Keys)){
    $prev=$j;$cur=$nb;$len=$adj[$j][$nb];$geom=@($coord[$j],$coord[$cur]);$guard=0
    while(-not $isJ.ContainsKey($cur) -and $guard -lt 100000){ $guard++
      $nxt=$null; foreach($k in $adj[$cur].Keys){ if($k -ne $prev){$nxt=$k;break} }
      if($nxt -eq $null){break}
      $len+=$adj[$cur][$nxt]; $geom+=,$coord[$nxt]; $prev=$cur; $cur=$nxt }
    if($cur -ne $j){ if(-not $superAdj.ContainsKey($j)){$superAdj[$j]=@()}; $superAdj[$j]+=[pscustomobject]@{to=$cur;len=$len;geom=$geom} }
  } }
function RouteJ($src,$dst){
  $dist=@{};$prev=@{};$prevE=@{};$done=@{}; $dist[$src]=0.0
  $pq=New-Object System.Collections.Generic.List[string]; [void]$pq.Add($src)
  while($pq.Count -gt 0){
    $bi=0;$bd=1e18; for($i=0;$i -lt $pq.Count;$i++){ if($dist[$pq[$i]] -lt $bd){$bd=$dist[$pq[$i]];$bi=$i} }
    $u=$pq[$bi];$pq.RemoveAt($bi)
    if($done.ContainsKey($u)){continue}; $done[$u]=$true
    if($u -eq $dst){break}
    if(-not $superAdj.ContainsKey($u)){continue}
    foreach($e in $superAdj[$u]){ $v=$e.to; $nd=$dist[$u]+$e.len
      if(-not $dist.ContainsKey($v) -or $nd -lt $dist[$v]){ $dist[$v]=$nd;$prev[$v]=$u;$prevE[$v]=$e; if(-not $done.ContainsKey($v)){[void]$pq.Add($v)} } } }
  if(-not $dist.ContainsKey($dst)){return $null}
  $path=@(); $cur=$dst
  while($cur -ne $src -and $prevE.ContainsKey($cur)){ $path=,$prevE[$cur]+$path; $cur=$prev[$cur] }
  if($cur -ne $src){return $null}
  $g=@(); foreach($e in $path){ foreach($p in $e.geom){ if($g.Count -eq 0 -or $g[-1][0] -ne $p[0] -or $g[-1][1] -ne $p[1]){ $g+=,$p } } }
  return [pscustomobject]@{geom=$g;len=$dist[$dst]}
}

"`n== RE-ROUTES =="
$feat=@()
foreach($L in $failers){
  $e=$ends[$L.name]
  $origLen=0.0; for($i=1;$i -lt $L.coords.Count;$i++){ $origLen+=RDist $L.coords[$i-1][0] $L.coords[$i-1][1] $L.coords[$i][0] $L.coords[$i][1] }
  $r= if($e[0][0] -and $e[1][0]){ RouteJ $e[0][0] $e[1][0] } else { $null }
  $status=''
  if($r -and $r.len -lt ($origLen*1.8+8000)){
    # connectors from real endpoints to rail (new-build if long)
    $g=@(); $g+=,@($L.coords[0][0],$L.coords[0][1])
    foreach($p in $r.geom){ $g+=,$p }
    $g+=,@($L.coords[-1][0],$L.coords[-1][1])
    $nb=[math]::Round(($e[0][1]+$e[1][1]))
    $status="ROUTED $([math]::Round($r.len/1000,1))km rail + ${nb}m connectors"
    $coords=($g | ForEach-Object { '['+[math]::Round([double]$_[0],6)+','+[math]::Round([double]$_[1],6)+']' }) -join ','
    $feat+='{"type":"Feature","properties":{"name":"'+($L.name -replace '"','\"')+'","kind":"line","mode":"commuter","phase":2,"color":"'+$L.color+'","row":1},"geometry":{"type":"LineString","coordinates":['+$coords+']}}'
  } else {
    $why= if(-not $r){'no connected rail path'}else{"detour $([math]::Round($r.len/1000,1))km vs orig $([math]::Round($origLen/1000,1))km"}
    $status="NOT ROUTABLE ($why) - keeping drawn geometry, FLAGGED"
  }
  "{0,-26} snaps {1}m/{2}m  {3}" -f $L.name,[math]::Round($e[0][1]),[math]::Round($e[1][1]),$status
}
Set-Content "$dbdir\commuter_row.geojson" ('{"type":"FeatureCollection","features":['+($feat -join ',')+']}') -Encoding utf8
"wrote db/commuter_row.geojson ($($feat.Count) re-routed lines)"