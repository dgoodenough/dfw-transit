$ErrorActionPreference="Stop"
# Metro ROW audit: proposed metro lines vs rail + freeway + arterial reference network.
# Existing DART lines (phase 0) skipped per user. PASS = p90 deviation <= 350 m.
$dir=(Split-Path $PSScriptRoot -Parent); $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.85*[math]::PI/180)
function RDist($alon,$alat,$blon,$blat){ [math]::Sqrt([math]::Pow(($alon-$blon)*$mlon,2)+[math]::Pow(($alat-$blat)*$mlat,2)) }

$grid=@{}; $cell=0.02; $nPts=0
function AddPt([double]$lon,[double]$lat){
  $k="{0}|{1}" -f [math]::Floor($lon/$cell),[math]::Floor($lat/$cell)
  if(-not $grid.ContainsKey($k)){$grid[$k]=New-Object System.Collections.Generic.List[object]}
  [void]$grid[$k].Add(@($lon,$lat)); $script:nPts++
}
# regex-stream coordinate pairs (lat/lon) from overpass geom JSON - avoids 60MB ConvertFrom-Json
$rx=[regex]'"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*"lon"\s*:\s*(-?\d+\.\d+)'
$skip=0
foreach($src in @("$ddir\dfw_arterials.json","$ddir\dfw_freeways.json","$ddir\dfw_rail.json")){
  $raw=[System.IO.File]::ReadAllText($src)
  $m=$rx.Matches($raw)
  for($i=0;$i -lt $m.Count;$i+=3){  # every 3rd point is plenty for a deviation grid
    AddPt ([double]$m[$i].Groups[2].Value) ([double]$m[$i].Groups[1].Value)
  }
  "$([System.IO.Path]::GetFileName($src)): cumulative grid pts $nPts"
  $raw=$null
}
function NearRef($lon,$lat){
  $best=1e18
  $cx=[math]::Floor($lon/$cell);$cy=[math]::Floor($lat/$cell)
  for($dx=-1;$dx -le 1;$dx++){ for($dy=-1;$dy -le 1;$dy++){
    $k="{0}|{1}" -f ($cx+$dx),($cy+$dy)
    if($grid.ContainsKey($k)){ foreach($p in $grid[$k]){ $d=RDist $lon $lat $p[0] $p[1]; if($d -lt $best){$best=$d} } } } }
  return $best
}

# ---- proposed metro lines: extra (network_extra incl N2) + FW core (from fw segments) ----
$targets=@()
foreach($f in ((Get-Content "$dbdir\network_extra.geojson" -Raw | ConvertFrom-Json).features)){
  if($f.properties.kind -ne 'line' -or $f.properties.mode -ne 'metro' -or [int]$f.properties.phase -eq 0){continue}
  $coords=@(); foreach($c in $f.geometry.coordinates){ $coords+=,@([double]$c[0],[double]$c[1]) }
  if($coords.Count -ge 2){ $targets+=[pscustomobject]@{name=$f.properties.name;coords=$coords} }
}
# FW lines from unified segments (multi-line segments attribute to each line)
$fwSamples=@{}
foreach($s in (Import-Csv "$dbdir\segments.csv" | Where-Object {$_.src -eq 'fw'})){
  $inner=$s.geometry_wkt -replace '^LINESTRING \(','' -replace '\)$',''
  $pc=@(); foreach($p in ($inner -split ',')){ $xy=$p.Trim() -split '\s+'; $pc+=,@([double]$xy[0],[double]$xy[1]) }
  $devs=New-Object System.Collections.Generic.List[double]
  for($i=0;$i -lt $pc.Count-1;$i++){ $a=$pc[$i];$b=$pc[$i+1]; $seg=RDist $a[0] $a[1] $b[0] $b[1]
    $n=[math]::Max(1,[math]::Floor($seg/400))
    for($t=0;$t -lt $n;$t++){ $f2=$t/$n; [void]$devs.Add((NearRef ($a[0]+$f2*($b[0]-$a[0])) ($a[1]+$f2*($b[1]-$a[1])))) } }
  foreach($ln in ($s.line -split ';')){ if(-not $fwSamples.ContainsKey($ln)){$fwSamples[$ln]=New-Object System.Collections.Generic.List[double]}
    foreach($d in $devs){ [void]$fwSamples[$ln].Add($d) } }
}

"== METRO ROW AUDIT (vs rail+freeway+arterial; PASS p90<=350m) =="
"`n-- extra/Dallas/Mid-Cities lines --"
foreach($L in $targets){
  $devs=New-Object System.Collections.Generic.List[double]
  for($i=0;$i -lt $L.coords.Count-1;$i++){ $a=$L.coords[$i];$b=$L.coords[$i+1]; $seg=RDist $a[0] $a[1] $b[0] $b[1]
    $n=[math]::Max(1,[math]::Floor($seg/400))
    for($t=0;$t -lt $n;$t++){ $f2=$t/$n; [void]$devs.Add((NearRef ($a[0]+$f2*($b[0]-$a[0])) ($a[1]+$f2*($b[1]-$a[1])))) } }
  $sorted=$devs | Sort-Object
  $p90=$sorted[[int][math]::Floor($sorted.Count*0.9)]; $mx=$sorted[-1]
  $p90s= if($p90 -gt 5000){'>2200'}else{[string][math]::Round($p90)}
  $mxs= if($mx -gt 5000){'>2200'}else{[string][math]::Round($mx)}
  $v= if($p90 -le 350){'PASS'}else{'FAIL'}
  "{0,-22} p90={1,6}m max={2,6}m  {3}" -f $L.name,$p90s,$mxs,$v
}
"`n-- FW core lines --"
foreach($ln in ($fwSamples.Keys | Sort-Object)){
  $sorted=$fwSamples[$ln] | Sort-Object
  $p90=$sorted[[int][math]::Floor($sorted.Count*0.9)]; $mx=$sorted[-1]
  $p90s= if($p90 -gt 5000){'>2200'}else{[string][math]::Round($p90)}
  $mxs= if($mx -gt 5000){'>2200'}else{[string][math]::Round($mx)}
  $v= if($p90 -le 350){'PASS'}else{'FAIL'}
  "{0,-22} p90={1,6}m max={2,6}m  {3}" -f $ln,$p90s,$mxs,$v
}