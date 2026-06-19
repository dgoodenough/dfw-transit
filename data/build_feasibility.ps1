$ErrorActionPreference="Stop"
# Scores every non-existing station in the UNIFIED DB (db/stations.csv) on activity
# (act column, already computed) + park-and-ride potential (distance to nearest freeway).
# Output: data/feasibility_stations.csv (classification lives here, not in the DB).
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.85*[math]::PI/180)

$stations=Import-Csv "$dbdir\stations.csv"
$slines=Import-Csv "$dbdir\station_lines.csv"

# terminus = first/last seq on any line
$term=@{}
foreach($g in ($slines | Group-Object line_id)){ $sq=$g.Group | Sort-Object {[int]$_.seq}; $term[$sq[0].station_id]=$true; $term[$sq[-1].station_id]=$true }

# freeways (downsampled)
$fw=Get-Content "$ddir\dfw_freeways.json" -Raw | ConvertFrom-Json
$fwx=New-Object System.Collections.ArrayList; $fwy=New-Object System.Collections.ArrayList
foreach($el in $fw.elements){ if($el.geometry){ $i=0; foreach($g in $el.geometry){ if($i % 4 -eq 0){ [void]$fwx.Add([double]$g.lon*$mlon); [void]$fwy.Add([double]$g.lat*$mlat) }; $i++ } } }
$fwx=$fwx.ToArray(); $fwy=$fwy.ToArray()
function FwyDist($lat,$lon){ $px=$lon*$mlon;$py=$lat*$mlat;$best=1e12
  for($i=0;$i -lt $fwx.Count;$i++){ $dx=$px-$fwx[$i]; if([math]::Abs($dx) -gt 1500){continue}; $dy=$py-$fwy[$i]; $d=$dx*$dx+$dy*$dy; if($d -lt $best){$best=$d} }
  return [math]::Sqrt($best) }

$rows=@()
foreach($s in ($stations | Where-Object {[int]$_.year_opens -gt 2025})){
  $lat=[double]$s.lat;$lon=[double]$s.lon;$a=[int]$s.act
  $fd=[math]::Round((FwyDist $lat $lon))
  $isT=[bool]$term[$s.station_id]
  $cls= if($a -ge 12000){'strong'} elseif($a -ge 5000){'moderate'} elseif($isT -and $fd -le 800){'park-ride'} elseif($fd -le 600){'park-ride?'} else {'weak'}
  $rows+=[pscustomobject]@{station_id=$s.station_id;name=$s.name;mode=$s.mode;src=$s.src;year_opens=$s.year_opens;term=[int]$isT;act1k=$a;fwy_m=$fd;feasibility=$cls;lat=$s.lat;lon=$s.lon}
}
$rows | Sort-Object feasibility,act1k | Export-Csv "$ddir\feasibility_stations.csv" -NoTypeInformation
"== FEASIBILITY (unified DB) =="
"scored: $($rows.Count) non-existing stations"
foreach($c in 'strong','moderate','park-ride','park-ride?','weak'){ "  $c : $(($rows|Where-Object{$_.feasibility -eq $c}).Count)" }