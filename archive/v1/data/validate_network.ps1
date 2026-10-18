$ErrorActionPreference="Stop"
# NETWORK VALIDATION ("testing phase") - operational sanity, run after any rebuild:
#  V1 terminus connectivity: every proposed line end must reach a transfer station, P&R (freeway), or yard - else DANGLING
#  V2 mid-route U-turns / hairpins (retraced segments; <25deg turns between long segs)
#  V3 rail yard access: each rail line needs a yard within 3km of a terminus (yards = OSM service=yard) + failsafe (2nd yard <=10km)
$dir=(Split-Path $PSScriptRoot -Parent); $ddir="$dir\data"; $dbdir="$dir\db"
function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2); return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }

$stations=Import-Csv "$dbdir\stations.csv"
$slines=Import-Csv "$dbdir\station_lines.csv"
$segs=Import-Csv "$dbdir\segments.csv"

# yards: dedicated Overpass pull (railway=yard / landuse=railway / service=yard), way centers
$yards=@()
foreach($e in ((Get-Content "$ddir\dfw_yards.json" -Raw | ConvertFrom-Json).elements)){ if($e.center){ $yards+=,@([double]$e.center.lon,[double]$e.center.lat) } }
"yards (OSM): $($yards.Count)"
# town centers: a commuter terminus AT a town center is valid by design (network rule)
$towns=@(); foreach($e in ((Get-Content "$ddir\dfw_poi.json" -Raw | ConvertFrom-Json).elements)){ if($e.tags.place -and $e.lat){ $towns+=,@([double]$e.lon,[double]$e.lat) } }
# freeway points for P&R terminus acceptance
$rxPt2=[regex]'"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*"lon"\s*:\s*(-?\d+\.\d+)'
$fwPts=@(); $rawF=[System.IO.File]::ReadAllText("$ddir\dfw_freeways.json"); $mF=$rxPt2.Matches($rawF)
for($i=0;$i -lt $mF.Count;$i+=8){ $fwPts+=,@([double]$mF[$i].Groups[2].Value,[double]$mF[$i].Groups[1].Value) }
$rawF=$null

# line geometries per line (extra: ordered segments; fw: per line via segments)
$report=@()
$lineGeo=@{}   # line label -> list of segment polylines (unordered ok for checks)
foreach($s in $segs){
  $inner=$s.geometry_wkt -replace '^LINESTRING \(','' -replace '\)$',''
  $pc=@(); foreach($p in ($inner -split ',')){ $xy=$p.Trim() -split '\s+'; $pc+=,@([double]$xy[0],[double]$xy[1]) }
  foreach($ln in ($s.line -split ';')){
    $key="$($s.mode)|$ln|$($s.src)"
    if(-not $lineGeo.ContainsKey($key)){ $lineGeo[$key]=New-Object System.Collections.Generic.List[object] }
    [void]$lineGeo[$key].Add(@{from=$s.from_id;to=$s.to_id;pc=$pc})
  }
}
# termini per line from station_lines (seq min/max)
$termsByLine=@{}
foreach($g in ($slines | Group-Object line_id)){
  $sq=$g.Group | Sort-Object {[int]$_.seq}
  $termsByLine[$g.Group[0].line]=@($sq[0].station_id,$sq[-1].station_id)
}
$stById=@{}; foreach($s in $stations){ $stById[$s.station_id]=$s }

"`n== V1 TERMINUS CONNECTIVITY (proposed lines) =="
foreach($lnName in ($termsByLine.Keys | Sort-Object)){
  $t=$termsByLine[$lnName]
  $bad=@()
  foreach($tid in $t){
    $ts=$stById[$tid]; if(-not $ts){continue}
    if([int]$ts.year_opens -le 2025){continue}
    $lat=[double]$ts.lat;$lon=[double]$ts.lon
    # transfer: another station of a DIFFERENT line within 500m
    $ok=$false
    if(([int]$ts.n_lines) -ge 2){ $ok=$true }
    if(-not $ok){ foreach($o in $stations){ if($o.station_id -eq $tid){continue}
      if([math]::Abs([double]$o.lat-$lat) -gt 0.006 -or [math]::Abs([double]$o.lon-$lon) -gt 0.007){continue}
      if($o.lines -eq $ts.lines){continue}
      if((Hav $lat $lon ([double]$o.lat) ([double]$o.lon))*1000 -le 500){ $ok=$true; break } } }
    if(-not $ok){ foreach($y in $yards){ if((Hav $lat $lon $y[1] $y[0])*1000 -le 1500){ $ok=$true; break } } }
    # P&R: freeway within 1km qualifies a terminus (park-and-ride end)
    if(-not $ok){ foreach($p in $fwPts){ if([math]::Abs($p[1]-$lat) -gt 0.012 -or [math]::Abs($p[0]-$lon) -gt 0.014){continue}
      if((Hav $lat $lon $p[1] $p[0])*1000 -le 1000){ $ok=$true; break } } }
    # town-center terminus = valid by design (commuter rule: town centers outside core)
    if(-not $ok){ foreach($p in $towns){ if([math]::Abs($p[1]-$lat) -gt 0.025 -or [math]::Abs($p[0]-$lon) -gt 0.03){continue}
      if((Hav $lat $lon $p[1] $p[0])*1000 -le 2000){ $ok=$true; break } } }
    if(-not $ok){ $bad+=$ts.name }
  }
  if($bad.Count -gt 0){ $report+="V1 DANGLING terminus: $lnName -> $($bad -join ' & ') (no transfer/P&R/yard within reach)" }
}
$v1=$report | Where-Object {$_ -like 'V1*'}
if($v1){ $v1 } else { "  all proposed termini connect (transfer/yard)" }

"`n== V2 U-TURNS / HAIRPINS (mid-route) =="
$v2c=0
foreach($key in $lineGeo.Keys){
  $parts=$key -split '\|'
  foreach($seg in $lineGeo[$key]){
    $pc=$seg.pc
    for($i=1;$i -lt $pc.Count-1;$i++){
      $a=$pc[$i-1];$b=$pc[$i];$c=$pc[$i+1]
      $d1=(Hav $a[1] $a[0] $b[1] $b[0])*1000; $d2=(Hav $b[1] $b[0] $c[1] $c[0])*1000
      if($d1 -lt 150 -or $d2 -lt 150){continue}
      # angle at b
      $v1x=($a[0]-$b[0]);$v1y=($a[1]-$b[1]);$v2x=($c[0]-$b[0]);$v2y=($c[1]-$b[1])
      $dot=($v1x*$v2x+$v1y*$v2y)/([math]::Sqrt($v1x*$v1x+$v1y*$v1y)*[math]::Sqrt($v2x*$v2x+$v2y*$v2y))
      if($dot -gt 0.9){ $v2c++; $report+="V2 HAIRPIN: $($parts[1]) [$($parts[0])] near $([math]::Round($b[1],4)),$([math]::Round($b[0],4)) (segs $([math]::Round($d1))m/$([math]::Round($d2))m)" }
    }
  }
}
if($v2c -eq 0){ "  no mid-route U-turns/hairpins detected" } else { ($report | Where-Object {$_ -like 'V2*'}) | Select-Object -First 12; if($v2c -gt 12){"  ... +$($v2c-12) more"} }

"`n== V3 RAIL YARD ACCESS (metro+commuter, proposed) =="
$railLines=@{}
foreach($g in ($slines | Group-Object line)){
  $first=$g.Group[0]
  $anySt=$stById[$first.station_id]; if(-not $anySt){continue}
  if($anySt.mode -notin @('metro','commuter')){continue}
  $sq=$g.Group | Sort-Object {[int]$_.seq}
  $tids=@($sq[0].station_id,$sq[-1].station_id)
  $allNew=$true; foreach($r in $g.Group){ $st2=$stById[$r.station_id]; if($st2 -and [int]$st2.year_opens -le 2025){ $allNew=$false } }
  if(-not $allNew){continue}  # touches existing system -> can share its yards
  $minY=1e9
  foreach($tid in $tids){ $ts=$stById[$tid]; if(-not $ts){continue}
    foreach($y in $yards){ $d=(Hav ([double]$ts.lat) ([double]$ts.lon) $y[1] $y[0]); if($d -lt $minY){$minY=$d} } }
  $n10=0; foreach($tid in $tids){ $ts=$stById[$tid]; if(-not $ts){continue}
    foreach($y in $yards){ if((Hav ([double]$ts.lat) ([double]$ts.lon) $y[1] $y[0]) -le 10){ $n10++ } } }
  $verdict= if($minY -le 3){"OK (yard $([math]::Round($minY,1))km; failsafe count<=10km: $n10)"} elseif($minY -le 10){"NEW YARD SPUR NEEDED (~$([math]::Round($minY,1))km to nearest)"} else {"NEW YARD REQUIRED (nearest $([math]::Round($minY,1))km) - add fixed cost"}
  "  {0,-26} {1}" -f $g.Name,$verdict
  if($minY -gt 3){ $report+="V3 YARD: $($g.Name) - $verdict" }
}

$report | Out-File "$ddir\validation_flags.txt" -Encoding utf8
"`nflags written: $($report.Count) -> data/validation_flags.txt"