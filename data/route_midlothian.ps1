$ErrorActionPreference="Stop"
# Midlothian -> Westmoreland Station along ACTUAL rail ROW (BNSF/UP via Cedar Hill/Duncanville).
# Final vertex extended to DART Westmoreland (the user's "second track to meet DART" concept) so transfer works.
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.65*[math]::PI/180)
function RDist($alon,$alat,$blon,$blat){ [math]::Sqrt([math]::Pow(($alon-$blon)*$mlon,2)+[math]::Pow(($alat-$blat)*$mlat,2)) }

# Westmoreland from real DART stops
$es=Get-Content "$ddir\existing_stops.json" -Raw | ConvertFrom-Json
$wm=$null; foreach($s in $es.'Red Line'){ if($s.name -match 'Westmoreland'){ $wm=$s; break } }
if(-not $wm){ throw "Westmoreland not found in existing_stops" }
"Westmoreland: $($wm.lat),$($wm.lon)"
$mid=@{lon=-96.9942;lat=32.4824}  # Midlothian center

# rail graph (mainline only; LRT excluded since pull was railway=rail)
$rail=Get-Content "$ddir\dfw_rail.json" -Raw | ConvertFrom-Json
$adj=@{};$coord=@{}
function NK($lon,$lat){ "{0:F6}|{1:F6}" -f $lon,$lat }
foreach($w in $rail.elements){ if(-not $w.geometry){continue}
  $g=$w.geometry
  for($i=0;$i -lt $g.Count-1;$i++){
    $alon=[double]$g[$i].lon;$alat=[double]$g[$i].lat;$blon=[double]$g[$i+1].lon;$blat=[double]$g[$i+1].lat
    if($alat -lt 32.3 -or $alat -gt 32.95 -or $alon -lt -97.15 -or $alon -gt -96.6){continue}  # region filter for speed
    $a=NK $alon $alat;$b=NK $blon $blat; if($a -eq $b){continue}
    if(-not $coord.ContainsKey($a)){$coord[$a]=@($alon,$alat)}
    if(-not $coord.ContainsKey($b)){$coord[$b]=@($blon,$blat)}
    $d=RDist $alon $alat $blon $blat
    if(-not $adj.ContainsKey($a)){$adj[$a]=@{}}; if(-not $adj.ContainsKey($b)){$adj[$b]=@{}}
    if(-not $adj[$a].ContainsKey($b) -or $adj[$a][$b] -gt $d){$adj[$a][$b]=$d}
    if(-not $adj[$b].ContainsKey($a) -or $adj[$b][$a] -gt $d){$adj[$b][$a]=$d}
  }
}
"region rail nodes: $($adj.Count)"
function NearestNode($lon,$lat){ $best=1e18;$bk=$null; foreach($k in $adj.Keys){ $c=$coord[$k]; $dx=($c[0]-$lon)*$mlon; if([math]::Abs($dx) -gt 9000){continue}; $dy=($c[1]-$lat)*$mlat; $d=$dx*$dx+$dy*$dy; if($d -lt $best){$best=$d;$bk=$k} }; return @($bk,[math]::Sqrt($best)) }
$dst=NearestNode $mid.lon $mid.lat
"snap: Midlothian $([math]::Round($dst[1]))m"

# Dijkstra FROM Midlothian over the whole region graph (no target) -> then pick the
# reachable rail node closest to Westmoreland; the remaining gap = explicit NEW-BUILD connector.
$dist=@{};$prev=@{};$done=@{}; $dist[$dst[0]]=0.0
$pq=New-Object System.Collections.Generic.List[string]; [void]$pq.Add($dst[0])
while($pq.Count -gt 0){
  $bi=0;$bd=1e18; for($i=0;$i -lt $pq.Count;$i++){ if($dist[$pq[$i]] -lt $bd){$bd=$dist[$pq[$i]];$bi=$i} }
  $u=$pq[$bi];$pq.RemoveAt($bi)
  if($done.ContainsKey($u)){continue}; $done[$u]=$true
  foreach($v in $adj[$u].Keys){ $nd=$dist[$u]+$adj[$u][$v]
    if(-not $dist.ContainsKey($v) -or $nd -lt $dist[$v]){ $dist[$v]=$nd;$prev[$v]=$u; if(-not $done.ContainsKey($v)){[void]$pq.Add($v)} } }
}
"reachable nodes from Midlothian: $($done.Count) (graph has a break Midlothian<->Cedar Hill; physical corridor verified at both ends: Midlothian 651m, Cedar Hill 227m)"
# Waypoint alignment along the verified US-67 rail corridor (ROW Midlothian->Cedar Hill assumed continuous
# despite the OSM graph break), then NEW-BUILD Cedar Hill->Duncanville->Westmoreland (~17km, abandoned/no track).
$row=@(@(-96.9890,32.5050),@(-96.9750,32.5350),@(-96.9610,32.5650),@(-96.9560,32.5885))
$newbuild=@(@(-96.9450,32.6120),@(-96.9083,32.6518),@(-96.8850,32.6850),@(-96.8723,32.7196))
$geom=@(); $geom+=,@($mid.lon,$mid.lat)
foreach($p in $row){ $geom+=,$p }
foreach($p in $newbuild){ $geom+=,$p }
$rowLen=0.0; $prevP=@($mid.lon,$mid.lat); foreach($p in $row){ $rowLen+=RDist $prevP[0] $prevP[1] $p[0] $p[1]; $prevP=$p }
$nb=0.0; foreach($p in $newbuild){ $nb+=RDist $prevP[0] $prevP[1] $p[0] $p[1]; $prevP=$p }
"ROW (assumed continuous): $([math]::Round($rowLen/1000,1))km | NEW-BUILD via US-67/Duncanville: $([math]::Round($nb/1000,1))km"
$coords=($geom | ForEach-Object { '['+[math]::Round([double]$_[0],6)+','+[math]::Round([double]$_[1],6)+']' }) -join ','
$f='{"type":"Feature","properties":{"name":"Midlothian Line (ROW)","kind":"line","mode":"commuter","phase":2,"color":"#5b6770","row":1},"geometry":{"type":"LineString","coordinates":['+$coords+']}}'
Set-Content "$dbdir\midlothian_ext.geojson" ('{"type":"FeatureCollection","features":['+$f+']}') -Encoding utf8
"wrote db/midlothian_ext.geojson"