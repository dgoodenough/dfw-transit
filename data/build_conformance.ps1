$ErrorActionPreference="Stop"
# Stop-spacing conformance pass against cited standards (see DESIGN_STANDARDS.md):
#  BRT      : ITDP 2024 band 300-800m optimal / TCRP 118 US practice up to ~1.2mi arterial -> too-close <300m, ok 300-1900m, wide >1900m
#  Metro    : industry band (TCRP 155 pending) -> too-close <600m, ok 600-2500m, wide >2500m
#  Commuter : Nelson/TREC empirical 3.5-10mi  -> too-close <2400m (1.5mi), ok 2.4-16km, wide >16km
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2); return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }

$stations=Import-Csv "$dbdir\stations.csv"
$stById=@{}; foreach($s in $stations){ $stById[$s.station_id]=$s }
$slines=Import-Csv "$dbdir\station_lines.csv"
$term=@{}; foreach($g in ($slines | Group-Object line_id)){ $sq=$g.Group | Sort-Object {[int]$_.seq}; $term[$sq[0].station_id]=$true; $term[$sq[-1].station_id]=$true }
$segs=Import-Csv "$dbdir\segments.csv"

$bands=@{ brt=@(300,1900); metro=@(600,2500); commuter=@(2400,16000) }
$rows=@()
foreach($s in $segs){
  # proposed only: skip pure-existing segments
  $yrs=@(); foreach($y in ($s.year_opens -split ';')){ $yrs+=[int]$y }
  if(($yrs | Measure-Object -Maximum).Maximum -le 2025){ continue }
  $inner=$s.geometry_wkt -replace '^LINESTRING \(','' -replace '\)$',''
  $pc=@(); foreach($p in ($inner -split ',')){ $xy=$p.Trim() -split '\s+'; $pc+=,@([double]$xy[0],[double]$xy[1]) }
  $len=0.0; for($i=1;$i -lt $pc.Count;$i++){ $len+=(Hav $pc[$i-1][1] $pc[$i-1][0] $pc[$i][1] $pc[$i][0])*1000 }
  $b=$bands[$s.mode]; if(-not $b){ $b=$bands['metro'] }
  $cls= if($len -lt $b[0]){'too-close'} elseif($len -gt $b[1]){'wide'} else {'ok'}
  $fa= if($stById.ContainsKey($s.from_id)){[int]$stById[$s.from_id].act}else{0}
  $ta= if($stById.ContainsKey($s.to_id)){[int]$stById[$s.to_id].act}else{0}
  # recommendation for too-close: drop the lower-act, non-terminus station
  $rec=''
  if($cls -eq 'too-close'){
    $fT=[bool]$term[$s.from_id]; $tT=[bool]$term[$s.to_id]
    if($fT -and $tT){ $rec='both termini - keep' }
    elseif($fT){ $rec="drop '$($s.to_name)' (act $ta)" }
    elseif($tT){ $rec="drop '$($s.from_name)' (act $fa)" }
    else { $rec= if($fa -le $ta){"drop '$($s.from_name)' (act $fa)"}else{"drop '$($s.to_name)' (act $ta)"} }
  } elseif($cls -eq 'wide' -and $s.mode -ne 'commuter'){ $rec='infill candidate if demand' }
  $rows+=[pscustomobject]@{segment_id=$s.segment_id;line=$s.line;mode=$s.mode;src=$s.src;from=$s.from_name;to=$s.to_name;len_m=[math]::Round($len);verdict=$cls;from_act=$fa;to_act=$ta;recommendation=$rec}
}
$rows | Export-Csv "$ddir\stop_conformance.csv" -NoTypeInformation
"== STOP-SPACING CONFORMANCE (proposed network only) =="
"segments evaluated: $($rows.Count)"
$rows | Group-Object mode | ForEach-Object { $m=$_.Name
  $ok=($_.Group|Where-Object{$_.verdict -eq 'ok'}).Count; $tc=($_.Group|Where-Object{$_.verdict -eq 'too-close'}).Count; $w=($_.Group|Where-Object{$_.verdict -eq 'wide'}).Count
  "  {0,-9} ok={1,-4} too-close={2,-3} wide={3}" -f $m,$ok,$tc,$w }
"`n-- TOO-CLOSE pairs (worst first) --"
$rows | Where-Object {$_.verdict -eq 'too-close'} | Sort-Object len_m | Select-Object -First 20 | ForEach-Object { "  [$($_.mode)] $($_.line): $($_.from) <-> $($_.to) = $($_.len_m)m -> $($_.recommendation)" }
"`n-- WIDE metro/BRT gaps (worst first) --"
$rows | Where-Object {$_.verdict -eq 'wide' -and $_.mode -ne 'commuter'} | Sort-Object -Descending len_m | Select-Object -First 12 | ForEach-Object { "  [$($_.mode)] $($_.line): $($_.from) <-> $($_.to) = $([math]::Round($_.len_m/1000,1))km" }
"`n-- COMMUTER out of band --"
$rows | Where-Object {$_.verdict -ne 'ok' -and $_.mode -eq 'commuter'} | Sort-Object len_m | ForEach-Object { "  $($_.line): $($_.from) <-> $($_.to) = $([math]::Round($_.len_m/1000,1))km ($($_.verdict))" }