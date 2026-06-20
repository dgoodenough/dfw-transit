$ErrorActionPreference="Stop"
$dir=(Split-Path $PSScriptRoot -Parent); $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.9*[math]::PI/180)
function RDist($alon,$alat,$blon,$blat){ [math]::Sqrt([math]::Pow(($alon-$blon)*$mlon,2)+[math]::Pow(($alat-$blat)*$mlat,2)) }

# ---- build rail graph ----
$rail=Get-Content "$ddir\dfw_rail.json" -Raw | ConvertFrom-Json
$adj=@{}; $coord=@{}
function NK($lon,$lat){ "{0:F6}|{1:F6}" -f $lon,$lat }
foreach($w in $rail.elements){ if(-not $w.geometry){continue}
  $g=$w.geometry
  for($i=0;$i -lt $g.Count-1;$i++){
    $alon=[double]$g[$i].lon;$alat=[double]$g[$i].lat;$blon=[double]$g[$i+1].lon;$blat=[double]$g[$i+1].lat
    $a=NK $alon $alat; $b=NK $blon $blat; if($a -eq $b){continue}
    if(-not $coord.ContainsKey($a)){$coord[$a]=@($alon,$alat)}
    if(-not $coord.ContainsKey($b)){$coord[$b]=@($blon,$blat)}
    $d=RDist $alon $alat $blon $blat
    if(-not $adj.ContainsKey($a)){$adj[$a]=@{}}
    if(-not $adj.ContainsKey($b)){$adj[$b]=@{}}
    if(-not $adj[$a].ContainsKey($b) -or $adj[$a][$b] -gt $d){$adj[$a][$b]=$d}
    if(-not $adj[$b].ContainsKey($a) -or $adj[$b][$a] -gt $d){$adj[$b][$a]=$d}
  }
}
"rail nodes: $($adj.Count)"
$allKeys=@($coord.Keys); $allLon=@();$allLat=@(); foreach($k in $allKeys){ $allLon+=$coord[$k][0];$allLat+=$coord[$k][1] }
function NearestNode($lon,$lat){ $best=1e18;$bk=$null; for($i=0;$i -lt $allKeys.Count;$i++){ $dx=($allLon[$i]-$lon)*$mlon; if([math]::Abs($dx) -gt 16000){continue}; $dy=($allLat[$i]-$lat)*$mlat; $d=$dx*$dx+$dy*$dy; if($d -lt $best){$best=$d;$bk=$allKeys[$i]} }; return @($bk,[math]::Sqrt($best)) }

# ---- commuter endpoints + towns; force their nearest rail nodes to be junctions ----
$ex=Get-Content "$dbdir\network_extra.geojson" -Raw | ConvertFrom-Json
$ends=@()
foreach($f in $ex.features){ if($f.properties.kind -eq 'line' -and $f.properties.mode -eq 'commuter'){
  $cs=$f.geometry.coordinates
  foreach($p in @($cs[0],$cs[-1])){ $ends+=[pscustomobject]@{name=$f.properties.name;color=$f.properties.color;lon=[double]$p[0];lat=[double]$p[1]} }
}}
$towns=@(
 @{n='Cleburne';lat=32.3476;lon=-97.3867},@{n='Alvarado';lat=32.4068;lon=-97.2114},
 @{n='Bowie';lat=33.5590;lon=-97.8483},@{n='Chico';lat=33.2940;lon=-97.7920},
 @{n='Gainesville';lat=33.6259;lon=-97.1334},@{n='Sherman';lat=33.6357;lon=-96.6089},
 @{n='Terrell';lat=32.7357;lon=-96.2752},@{n='Kaufman';lat=32.5885;lon=-96.3089},
 @{n='Ennis';lat=32.3293;lon=-96.6253},@{n='Waxahachie';lat=32.3865;lon=-96.8483}
)
$isJ=@{}; foreach($n in $adj.Keys){ if($adj[$n].Count -ne 2){$isJ[$n]=$true} }
foreach($e in $ends){ $nn=NearestNode $e.lon $e.lat; $e | Add-Member node $nn[0]; $e | Add-Member snap ([math]::Round($nn[1])); if($nn[0]){$isJ[$nn[0]]=$true} }
foreach($t in $towns){ $nn=NearestNode $t.lon $t.lat; $t.node=$nn[0]; $t.snap=[math]::Round($nn[1]); if($nn[0]){$isJ[$nn[0]]=$true} }
"junctions (incl forced): $($isJ.Count)"

# ---- contract to junction super-edges ----
$superAdj=@{}
foreach($j in $isJ.Keys){
  foreach($nb in @($adj[$j].Keys)){
    $prev=$j;$cur=$nb;$len=$adj[$j][$nb];$geom=@($coord[$j],$coord[$cur]);$guard=0
    while(-not $isJ.ContainsKey($cur) -and $guard -lt 100000){ $guard++
      $nxt=$null; foreach($k in $adj[$cur].Keys){ if($k -ne $prev){$nxt=$k;break} }
      if($nxt -eq $null){break}
      $len+=$adj[$cur][$nxt]; $geom+=,$coord[$nxt]; $prev=$cur; $cur=$nxt }
    if($cur -ne $j){ if(-not $superAdj.ContainsKey($j)){$superAdj[$j]=@()}; $superAdj[$j]+=[pscustomobject]@{to=$cur;len=$len;geom=$geom} }
  }
}
$jcoord=@{}; foreach($j in $isJ.Keys){ $jcoord[$j]=$coord[$j] }
"super-edges from $($superAdj.Count) junctions"

function RouteJ($src,$dst,$slon,$slat,$tlon,$tlat){
  if(-not $src -or -not $dst){return $null}
  $loMin=[math]::Min($slon,$tlon)-0.3;$loMax=[math]::Max($slon,$tlon)+0.3;$laMin=[math]::Min($slat,$tlat)-0.3;$laMax=[math]::Max($slat,$tlat)+0.3
  $dist=@{};$prev=@{};$prevEdge=@{};$done=@{}; $dist[$src]=0.0
  $pq=New-Object System.Collections.Generic.List[string]; [void]$pq.Add($src)
  while($pq.Count -gt 0){
    $bi=0;$bd=1e18; for($i=0;$i -lt $pq.Count;$i++){ if($dist[$pq[$i]] -lt $bd){$bd=$dist[$pq[$i]];$bi=$i} }
    $u=$pq[$bi]; $pq.RemoveAt($bi)
    if($done.ContainsKey($u)){continue}; $done[$u]=$true
    if($u -eq $dst){break}
    if(-not $superAdj.ContainsKey($u)){continue}
    foreach($e in $superAdj[$u]){ $v=$e.to; $c=$jcoord[$v]; if($c[0] -lt $loMin -or $c[0] -gt $loMax -or $c[1] -lt $laMin -or $c[1] -gt $laMax){continue}
      $nd=$dist[$u]+$e.len
      if(-not $dist.ContainsKey($v) -or $nd -lt $dist[$v]){ $dist[$v]=$nd;$prev[$v]=$u;$prevEdge[$v]=$e; if(-not $done.ContainsKey($v)){[void]$pq.Add($v)} } }
  }
  if(-not $dist.ContainsKey($dst)){return $null}
  $path=@(); $cur=$dst
  while($cur -ne $src -and $prevEdge.ContainsKey($cur)){ $path=,$prevEdge[$cur]+$path; $cur=$prev[$cur] }
  if($cur -ne $src){return $null}
  $g=@(); foreach($e in $path){ foreach($p in $e.geom){ if($g.Count -eq 0 -or $g[-1][0] -ne $p[0] -or $g[-1][1] -ne $p[1]){ $g+=,$p } } }
  return [pscustomobject]@{geom=$g;len=$dist[$dst]}
}

$feat=@(); $log=@()
foreach($tn in $towns){
  if(-not $tn.node -or $tn.snap -gt 8000){ $log+=[pscustomobject]@{town=$tn.n;via='-';straight_km='-';rail_km='-';status="no rail near town (snap $($tn.snap)m)"}; continue }
  $cand=$ends | Sort-Object { RDist $_.lon $_.lat $tn.lon $tn.lat }
  $bestR=$null;$bestVia=$null;$bestStraight=$null
  foreach($e in $cand){ if($e.snap -gt 4000){continue}
    $straight=RDist $e.lon $e.lat $tn.lon $tn.lat
    $r=RouteJ $e.node $tn.node $e.lon $e.lat $tn.lon $tn.lat
    if($r -and $r.geom.Count -ge 2 -and $r.len -lt ($straight*2.4 + 6000)){
      if(-not $bestR -or $r.len -lt $bestR.len){ $bestR=$r;$bestVia=$e;$bestStraight=$straight }
      if($r.len -lt $straight*1.3){break}
    }
  }
  if($bestR){
    $coords=($bestR.geom | ForEach-Object { '['+[math]::Round($_[0],6)+','+[math]::Round($_[1],6)+']' }) -join ','
    $feat+='{"type":"Feature","properties":{"name":"'+$tn.n+' Line (ROW)","kind":"line","mode":"commuter","phase":3,"color":"'+$bestVia.color+'","row":1},"geometry":{"type":"LineString","coordinates":['+$coords+']}}'
    $feat+='{"type":"Feature","properties":{"name":"'+$tn.n+'","kind":"stop","mode":"commuter","phase":3,"color":"'+$bestVia.color+'","row":1},"geometry":{"type":"Point","coordinates":['+$tn.lon+','+$tn.lat+']}}'
    $log+=[pscustomobject]@{town=$tn.n;via=$bestVia.name;straight_km=[math]::Round($bestStraight/1000,1);rail_km=[math]::Round($bestR.len/1000,1);status='routed'}
  } else { $log+=[pscustomobject]@{town=$tn.n;via='-';straight_km='-';rail_km='-';status='no connected ROW from any commuter line'} }
}
Set-Content "$dbdir\commuter_ext.geojson" ('{"type":"FeatureCollection","features":['+($feat -join ',')+']}') -Encoding utf8
$log | Export-Csv "$ddir\commuter_ext_log.csv" -NoTypeInformation
"== COMMUTER EXTENSIONS =="
$log | Format-Table town,via,straight_km,rail_km,status -AutoSize | Out-String -Width 150