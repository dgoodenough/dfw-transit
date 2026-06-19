$ErrorActionPreference="Stop"
# B2 v2: BRT through the road graph with operational sanity:
#  - sparse anchors (3km) so the router picks streets, not stale snap points
#  - leg-stitch backtrack trimming (no mid-route U-turns from anchor legs)
#  - logical termini: extend each end to nearest rail/metro station (<=1.5km) else freeway P&R point (<=1km)
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
Add-Type -TypeDefinition (Get-Content "$ddir\RoadRouter.cs" -Raw) -Language CSharp
$rr=New-Object RoadRouter
$rr.Load(@("$ddir\dfw_arterials.json","$ddir\dfw_freeways.json"))

function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2); return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }

# terminus targets: rail/metro/commuter stations (any year) from the unified DB
$railSt=@(); foreach($s in (Import-Csv "$dbdir\stations.csv")){ if($s.mode -in @('metro','commuter')){ $railSt+=,@([double]$s.lon,[double]$s.lat) } }
# freeway P&R points (sparse sample)
$rxPt=[regex]'"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*"lon"\s*:\s*(-?\d+\.\d+)'
$fw=@(); $raw=[System.IO.File]::ReadAllText("$ddir\dfw_freeways.json"); $m=$rxPt.Matches($raw)
for($i=0;$i -lt $m.Count;$i+=12){ $fw+=,@([double]$m[$i].Groups[2].Value,[double]$m[$i].Groups[1].Value) }
$raw=$null
function TermTarget($lon,$lat){
  $best=1e9;$bp=$null
  foreach($p in $railSt){ if([math]::Abs($p[1]-$lat) -gt 0.015 -or [math]::Abs($p[0]-$lon) -gt 0.018){continue}
    $d=(Hav $lat $lon $p[1] $p[0])*1000; if($d -lt $best){$best=$d;$bp=$p} }
  if($best -le 1500 -and $best -gt 120){ return @($bp,'station') }
  if($best -le 120){ return @($null,'already') }
  $best2=1e9;$bp2=$null
  foreach($p in $fw){ if([math]::Abs($p[1]-$lat) -gt 0.012 -or [math]::Abs($p[0]-$lon) -gt 0.014){continue}
    $d=(Hav $lat $lon $p[1] $p[0])*1000; if($d -lt $best2){$best2=$d;$bp2=$p} }
  if($best2 -le 1000 -and $best2 -gt 120){ return @($bp2,'P&R/freeway') }
  return @($null,'none')
}

$feat=@()
foreach($f in ((Get-Content "$dbdir\network_extra.geojson" -Raw | ConvertFrom-Json).features)){
  if($f.properties.kind -ne 'line' -or $f.properties.mode -ne 'brt'){continue}
  $nm=$f.properties.name
  $pc=@(); foreach($c in $f.geometry.coordinates){ $pc+=,@([double]$c[0],[double]$c[1]) }
  if($pc.Count -lt 2){continue}
  $isLoop = ((Hav $pc[0][1] $pc[0][0] $pc[-1][1] $pc[-1][0])*1000 -lt 800)
  # anchors every ~3km
  $anchors=New-Object System.Collections.Generic.List[object]
  $anchors.Add($pc[0]); $acc=0.0
  for($i=1;$i -lt $pc.Count;$i++){ $acc+=(Hav $pc[$i-1][1] $pc[$i-1][0] $pc[$i][1] $pc[$i][0])
    if($acc -ge 3.0 -or $i -eq $pc.Count-1){ $anchors.Add($pc[$i]); $acc=0.0 } }
  # logical termini (not for loops)
  $termNote=@('','')
  if(-not $isLoop){
    $t0=TermTarget $anchors[0][0] $anchors[0][1]
    if($t0[0]){ $anchors.Insert(0,$t0[0]); $termNote[0]=$t0[1] } elseif($t0[1] -eq 'none'){ $termNote[0]='DANGLING' } else { $termNote[0]='ok' }
    $t1=TermTarget $anchors[$anchors.Count-1][0] $anchors[$anchors.Count-1][1]
    if($t1[0]){ $anchors.Add($t1[0]); $termNote[1]=$t1[1] } elseif($t1[1] -eq 'none'){ $termNote[1]='DANGLING' } else { $termNote[1]='ok' }
  }
  # route leg by leg with backtrack trimming at stitches
  $flat=New-Object System.Collections.Generic.List[double]
  foreach($a in $anchors){ $flat.Add($a[0]); $flat.Add($a[1]) }
  $res=$rr.Route($flat.ToArray())
  $parts=$res -split ';'; $stats=$parts[0] -split '\|'
  $coords=New-Object System.Collections.Generic.List[object]
  for($i=1;$i -lt $parts.Count;$i++){ $xy=$parts[$i] -split ' '; $p=@([double]$xy[0],[double]$xy[1])
    # backtrack trim: if new point equals the point BEFORE the current tail, pop the tail (a U-turn retrace)
    if($coords.Count -ge 2){
      $prev2=$coords[$coords.Count-2]
      if([math]::Abs($prev2[0]-$p[0]) -lt 1e-6 -and [math]::Abs($prev2[1]-$p[1]) -lt 1e-6){ $coords.RemoveAt($coords.Count-1); continue }
    }
    $coords.Add($p)
  }
  # dedupe tight
  $out=@(); foreach($p in $coords){ if($out.Count -eq 0 -or (Hav $out[-1][1] $out[-1][0] $p[1] $p[0])*1000 -gt 25){ $out+=,$p } }
  "{0,-22} anchors={1,-3} routed={2,6}km failedLegs={3} pts={4,-5} ends: {5} / {6}" -f $nm,$anchors.Count,$stats[1],$stats[2],$out.Count,$termNote[0],$termNote[1]
  $cj=($out | ForEach-Object { '['+[math]::Round([double]$_[0],6)+','+[math]::Round([double]$_[1],6)+']' }) -join ','
  $feat+='{"type":"Feature","properties":{"name":"'+($nm -replace '"','\"')+'"},"geometry":{"type":"LineString","coordinates":['+$cj+']}}'
}
Set-Content "$dbdir\brt_row_routes.geojson" ('{"type":"FeatureCollection","features":['+($feat -join ',')+']}') -Encoding utf8
"wrote db/brt_row_routes.geojson ($($feat.Count) BRT lines)"