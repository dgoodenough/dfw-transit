$ErrorActionPreference="Stop"
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.85*[math]::PI/180)
$renames=@(); foreach($r in (Import-Csv "$ddir\renames.csv")){ $renames+=[pscustomobject]@{old=$r.old_name;lat=[double]$r.lat;lon=[double]$r.lon;new=$r.new_name} }
function Rename($nm,$lat,$lon){ foreach($r in $renames){ if($r.old -eq $nm -and [math]::Abs($r.lat-$lat) -lt 0.003 -and [math]::Abs($r.lon-$lon) -lt 0.003){ return $r.new } }; return $nm }

$ex=Get-Content "$dbdir\network_extra.geojson" -Raw | ConvertFrom-Json
# existing line vertices (phase 0)
$exist=@()
# planned lines (phase>=1): name,color,mode,phase, verts(meters)
$planned=@()
foreach($f in $ex.features){ if($f.properties.kind -ne 'line'){continue}
  $ph=[int]$f.properties.phase
  if($ph -eq 0){ foreach($c in $f.geometry.coordinates){ try{$exist+=,@([double]($c[0]),[double]($c[1]))}catch{} } }
  else {
    $v=@(); foreach($c in $f.geometry.coordinates){ try{$v+=,@([double]($c[0]),[double]($c[1]))}catch{} }
    $planned+=[pscustomobject]@{name=$f.properties.name;color=$f.properties.color;mode=$f.properties.mode;phase=$ph;verts=$v}
  }
}
"existing vertices: $($exist.Count) | planned lines: $($planned.Count)"

$orphans=Import-Csv "$ddir\feasibility_orphans.csv"
$feat=@(); $log=@()
foreach($o in $orphans){
  $olon=[double]$o.lon;$olat=[double]$o.lat;$act=[int]$o.act1k
  $onm=Rename $o.name $olat $olon
  $ox=$olon*$mlon;$oy=$olat*$mlat
  # nearest existing
  $dEx=1e12; foreach($e in $exist){ $ex2=$e[0]*$mlon; $dx=$ox-$ex2;if([math]::Abs($dx) -gt 1500){continue};$dy=$oy-$e[1]*$mlat;$d=$dx*$dx+$dy*$dy;if($d -lt $dEx){$dEx=$d} }
  $dEx=[math]::Sqrt($dEx)
  # nearest planned line + point
  $best=1e12;$bL=$null;$bP=$null
  foreach($pl in $planned){ foreach($v in $pl.verts){ $dx=$ox-$v[0]*$mlon;$dy=$oy-$v[1]*$mlat;$d=$dx*$dx+$dy*$dy; if($d -lt $best){$best=$d;$bL=$pl;$bP=$v} } }
  $dPl=[math]::Sqrt($best)
  $decision='skip'
  if($dEx -le 1200){ $decision='served-existing' }
  elseif($act -ge 8000 -and $dPl -le 6000 -and $bL){
    $decision="extend $($bL.name)"
    # connector + stop
    $conn='[['+$bP[0]+','+$bP[1]+'],['+$olon+','+$olat+']]'
    $feat+='{"type":"Feature","properties":{"name":"'+($onm -replace '"','\"')+' (ext)","kind":"line","mode":"'+$bL.mode+'","phase":'+$bL.phase+',"color":"'+$bL.color+'","ext":1},"geometry":{"type":"LineString","coordinates":'+$conn+'}}'
    $feat+='{"type":"Feature","properties":{"name":"'+($onm -replace '"','\"')+'","kind":"stop","mode":"'+$bL.mode+'","phase":'+$bL.phase+',"color":"'+$bL.color+'","ext":1},"geometry":{"type":"Point","coordinates":['+$olon+','+$olat+']}}'
  }
  $log+=[pscustomobject]@{orphan=$onm;act=$act;dExist_m=[math]::Round($dEx);dPlanned_m=[math]::Round($dPl);nearest_planned=$bL.name;decision=$decision}
}
Set-Content "$dbdir\extensions.geojson" ('{"type":"FeatureCollection","features":['+($feat -join ',')+']}') -Encoding utf8
$log | Sort-Object act -Descending | Export-Csv "$ddir\extensions_log.csv" -NoTypeInformation
"== EXTENSIONS =="
$log | Sort-Object act -Descending | Format-Table orphan,act,dExist_m,dPlanned_m,nearest_planned,decision -AutoSize | Out-String -Width 160