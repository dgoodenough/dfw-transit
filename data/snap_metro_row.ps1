$ErrorActionPreference="Stop"
# Snap failing metro lines onto the rail+freeway+arterial reference network.
# Method: densify to <=800m spacing, snap each pt to nearest ref pt within 900m, dedupe <60m.
$dir=(Split-Path $PSScriptRoot -Parent); $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.85*[math]::PI/180)
function RDist($alon,$alat,$blon,$blat){ [math]::Sqrt([math]::Pow(($alon-$blon)*$mlon,2)+[math]::Pow(($alat-$blat)*$mlat,2)) }
$grid=@{}; $cell=0.02
$rx=[regex]'"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*"lon"\s*:\s*(-?\d+\.\d+)'
foreach($src in @("$ddir\dfw_arterials.json","$ddir\dfw_freeways.json","$ddir\dfw_rail.json")){
  $raw=[System.IO.File]::ReadAllText($src); $m=$rx.Matches($raw)
  for($i=0;$i -lt $m.Count;$i+=3){
    $lon=[double]$m[$i].Groups[2].Value;$lat=[double]$m[$i].Groups[1].Value
    $k="{0}|{1}" -f [math]::Floor($lon/$cell),[math]::Floor($lat/$cell)
    if(-not $grid.ContainsKey($k)){$grid[$k]=New-Object System.Collections.Generic.List[object]}
    [void]$grid[$k].Add(@($lon,$lat)) }
  $raw=$null }
function NearRefPt($lon,$lat){
  $best=1e18;$bp=$null
  $cx=[math]::Floor($lon/$cell);$cy=[math]::Floor($lat/$cell)
  for($dx=-1;$dx -le 1;$dx++){ for($dy=-1;$dy -le 1;$dy++){
    $k="{0}|{1}" -f ($cx+$dx),($cy+$dy)
    if($grid.ContainsKey($k)){ foreach($p in $grid[$k]){ $d=RDist $lon $lat $p[0] $p[1]; if($d -lt $best){$best=$d;$bp=$p} } } } }
  return @($best,$bp)
}
$fix=@('DNT Line - West','Silver','Blue Ctd','Purple line','Legacy Line','Ross Avenue BRT','Forest Lane BRT','Jefferson Blvd BRT')
$feat=@()
foreach($f in ((Get-Content "$dbdir\network_extra.geojson" -Raw | ConvertFrom-Json).features)){
  if($f.properties.kind -ne 'line' -or ($f.properties.mode -ne 'metro' -and $f.properties.mode -ne 'brt')){continue}
  if($fix -notcontains $f.properties.name){continue}
  $pc=@(); foreach($c in $f.geometry.coordinates){ $pc+=,@([double]$c[0],[double]$c[1]) }
  # densify
  $dense=@()
  for($i=0;$i -lt $pc.Count-1;$i++){ $a=$pc[$i];$b=$pc[$i+1]; $dense+=,$a
    $seg=RDist $a[0] $a[1] $b[0] $b[1]; $n=[math]::Floor($seg/800)
    for($t=1;$t -le $n;$t++){ $fr=$t/($n+1); $dense+=,@(($a[0]+$fr*($b[0]-$a[0])),($a[1]+$fr*($b[1]-$a[1]))) } }
  $dense+=,$pc[-1]
  # snap
  $snapped=@()
  foreach($p in $dense){ $r=NearRefPt $p[0] $p[1]
    if($r[0] -le 900 -and $r[1]){ $snapped+=,$r[1] } else { $snapped+=,$p } }
  # dedupe
  $out=@(); foreach($p in $snapped){ if($out.Count -eq 0 -or (RDist $out[-1][0] $out[-1][1] $p[0] $p[1]) -gt 60){ $out+=,$p } }
  "{0,-18} {1} -> {2} pts" -f $f.properties.name,$pc.Count,$out.Count
  $coords=($out | ForEach-Object { '['+[math]::Round([double]$_[0],6)+','+[math]::Round([double]$_[1],6)+']' }) -join ','
  $feat+='{"type":"Feature","properties":{"name":"'+($f.properties.name -replace '"','\"')+'"},"geometry":{"type":"LineString","coordinates":['+$coords+']}}'
}
Set-Content "$dbdir\metro_row_fixes.geojson" ('{"type":"FeatureCollection","features":['+($feat -join ',')+']}') -Encoding utf8
"wrote db/metro_row_fixes.geojson ($($feat.Count) lines)"

