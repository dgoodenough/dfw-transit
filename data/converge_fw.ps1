$ErrorActionPreference="Stop"
# Converge all FW-side commuter lines into downtown Fort Worth (Central Station) so
# every one has a stop there and can transfer to TexRail/TRE. Routes each line's
# inner terminus -> FW Central along real rail ROW (these corridors meet at Tower 55).
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.75*[math]::PI/180)
function RDist($alon,$alat,$blon,$blat){ [math]::Sqrt([math]::Pow(($alon-$blon)*$mlon,2)+[math]::Pow(($alat-$blat)*$mlat,2)) }
$FWC=@(-97.325572,32.751994)   # Fort Worth Central (X113)

# rail graph (region around FW)
$rail=Get-Content "$ddir\dfw_rail.json" -Raw | ConvertFrom-Json
$adj=@{};$coord=@{}
function NK($lon,$lat){ "{0:F6}|{1:F6}" -f $lon,$lat }
foreach($w in $rail.elements){ if(-not $w.geometry){continue}
  $g=$w.geometry
  for($i=0;$i -lt $g.Count-1;$i++){
    $alon=[double]$g[$i].lon;$alat=[double]$g[$i].lat;$blon=[double]$g[$i+1].lon;$blat=[double]$g[$i+1].lat
    if($alat -lt 32.55 -or $alat -gt 33.05 -or $alon -lt -97.55 -or $alon -gt -97.0){continue}
    $a=NK $alon $alat;$b=NK $blon $blat; if($a -eq $b){continue}
    if(-not $coord.ContainsKey($a)){$coord[$a]=@($alon,$alat)}
    if(-not $coord.ContainsKey($b)){$coord[$b]=@($blon,$blat)}
    $d=RDist $alon $alat $blon $blat
    if(-not $adj.ContainsKey($a)){$adj[$a]=@{}}; if(-not $adj.ContainsKey($b)){$adj[$b]=@{}}
    if(-not $adj[$a].ContainsKey($b) -or $adj[$a][$b] -gt $d){$adj[$a][$b]=$d}
    if(-not $adj[$b].ContainsKey($a) -or $adj[$b][$a] -gt $d){$adj[$b][$a]=$d}
  } }
$allK=@($coord.Keys)
"FW-region rail nodes: $($adj.Count)"
function NearestNode($lon,$lat){ $best=1e18;$bk=$null; foreach($k in $allK){ $c=$coord[$k]; $dx=($c[0]-$lon)*$mlon; if([math]::Abs($dx) -gt 7000){continue}; $dy=($c[1]-$lat)*$mlat; $d=$dx*$dx+$dy*$dy; if($d -lt $best){$best=$d;$bk=$k} }; return @($bk,[math]::Sqrt($best)) }

# precompute Dijkstra FROM FW Central over the rail graph (single source -> all)
$cn=NearestNode $FWC[0] $FWC[1]
"FW Central snaps to rail at $([math]::Round($cn[1]))m"
$dist=@{};$prev=@{};$done=@{}; $dist[$cn[0]]=0.0
$pq=New-Object System.Collections.Generic.List[string]; [void]$pq.Add($cn[0])
while($pq.Count -gt 0){
  $bi=0;$bd=1e18; for($i=0;$i -lt $pq.Count;$i++){ if($dist[$pq[$i]] -lt $bd){$bd=$dist[$pq[$i]];$bi=$i} }
  $u=$pq[$bi];$pq.RemoveAt($bi)
  if($done.ContainsKey($u)){continue}; $done[$u]=$true
  foreach($v in $adj[$u].Keys){ $nd=$dist[$u]+$adj[$u][$v]
    if(-not $dist.ContainsKey($v) -or $nd -lt $dist[$v]){ $dist[$v]=$nd;$prev[$v]=$u; if(-not $done.ContainsKey($v)){[void]$pq.Add($v)} } } }
"rail reachable from FW Central: $($done.Count) nodes"

# inner terminus (downtown-facing end) of each line to converge, from current DB
$st=Import-Csv "$dbdir\stations.csv"
$targets=@(
 @{line='Bowie Line (ROW)';      inner=@(-97.330252,32.823451)},  # Gainesville 3
 @{line='Gainesville Line (ROW)';inner=@(-97.330252,32.823451)},
 @{line='FTW/Denton';            inner=@(-97.282179,32.824252)},  # Haltom City
 @{line='TexRail 3rd exp';       inner=$null},
 @{line='SE TexRail';            inner=$null}
)
function InnerOf($lineName){ $ss=$st | Where-Object {($_.lines -split ';') -contains $lineName -and $_.mode -eq 'commuter'}
  $best=1e18;$bp=$null; foreach($s in $ss){ $d=RDist $FWC[0] $FWC[1] ([double]$s.lon) ([double]$s.lat); if($d -lt $best){$best=$d;$bp=@([double]$s.lon,[double]$s.lat)} }; return $bp }

$feat=@()
foreach($T in $targets){
  $inner= if($T.inner){$T.inner}else{InnerOf $T.line}
  if(-not $inner){ "  $($T.line): no inner terminus found, skip"; continue }
  $sn=NearestNode $inner[0] $inner[1]
  if(-not $done.ContainsKey($sn[0])){ "  $($T.line): inner terminus not rail-connected to FW Central (snap $([math]::Round($sn[1]))m) - FLAG"; continue }
  # path FW Central -> inner (reverse for line orientation: ends at FW Central)
  $path=@(); $cur=$sn[0]
  while($cur -ne $cn[0]){ $path=,$coord[$cur]+$path; $cur=$prev[$cur] }
  $path=,$coord[$cn[0]]+$path   # path now: FWCentral ... inner
  # tail geometry should run inner -> FW Central exactly (so it appends to the line's inner end)
  $geom=@(); $geom+=,$inner
  for($i=$path.Count-1;$i -ge 0;$i--){ $geom+=,$path[$i] }
  $geom+=,$FWC   # land exactly on FW Central for consolidation merge
  $km=[math]::Round($dist[$sn[0]]/1000,1)
  "  {0,-24} routed inner->FW Central {1}km ({2} pts)" -f $T.line,$km,$geom.Count
  $cj=($geom | ForEach-Object { '['+[math]::Round([double]$_[0],6)+','+[math]::Round([double]$_[1],6)+']' }) -join ','
  $feat+='{"type":"Feature","properties":{"name":"'+$T.line+'"},"geometry":{"type":"LineString","coordinates":['+$cj+']}}'
}
Set-Content "$dbdir\fw_convergence.geojson" ('{"type":"FeatureCollection","features":['+($feat -join ',')+']}') -Encoding utf8
"wrote db/fw_convergence.geojson ($($feat.Count) convergence tails)"