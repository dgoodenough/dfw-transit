$ErrorActionPreference="Stop"
# Merges the FW core tables (fw_*.csv) + extra-network tables (_extra_*.csv) into the
# unified, editable source of truth: db/stations.csv, db/lines.csv, db/station_lines.csv, db/segments.csv.
# Opening YEARS are materialized as data here (edit a cell -> rebuild app -> done).
$dir=(Split-Path $PSScriptRoot -Parent); $ddir="$dir\data"; $dbdir="$dir\db"

function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2); return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }
$cores=@(@(32.7767,-96.7970),@(32.7555,-97.3308)); $STEPS=@(2025,2035,2040,2045,2050,2055,2060,2065,2070)
function CoreKm($lat,$lon){ $m=1e9; foreach($c in $cores){ $d=Hav $lat $lon $c[0] $c[1]; if($d -lt $m){$m=$d} }; return $m }
function YearBand($phase,$lat,$lon){ if($phase -le 0){return 2025}; $d=CoreKm $lat $lon
  if($phase -eq 1){ if($d -lt 8){2035}elseif($d -lt 15){2040}else{2045} } elseif($phase -eq 2){ if($d -lt 18){2050}else{2055} } else { if($d -lt 30){2060}elseif($d -lt 50){2065}else{2070} } }
function StationYear($phase,$lat,$lon,$act,$isTerm){ $y=YearBand $phase $lat $lon
  if(-not $isTerm -and $act -lt 5000 -and $y -lt 2070){ $i=[array]::IndexOf($STEPS,$y); $y=$STEPS[[math]::Min($i+1,8)] }; return $y }
# Session B paced phasing for FW lines (data/line_years.csv, scope=fw)
$fwYearOv=@{}; foreach($r in (Import-Csv "$ddir\line_years.csv" | Where-Object {$_.scope -eq 'fw'})){ $fwYearOv[$r.line]=[int]$r.year }

# density for FW act
$dens=@(); foreach($r in (Import-Csv "$ddir\metroplex_density.csv")){ $dens+=[pscustomobject]@{lat=[double]$r.lat;lon=[double]$r.lon;act=[int]$r.pop+[int]$r.jobs} }
function Act1k($lat,$lon){ $s=0; foreach($b in $dens){ if([math]::Abs($b.lat-$lat) -lt 0.013 -and [math]::Abs($b.lon-$lon) -lt 0.016){ if((Hav $lat $lon $b.lat $b.lon) -le 1.0){ $s+=$b.act } } }; return $s }

$fwCol=@{Teal='#00b251';Blue='#0896d7';Orange='#df8600';Pink='#d63384';Silver='#9aa0a6';Red='#bd1038';Purple='#7b2d8e'}
$fwSt=Import-Csv "$dbdir\fw_stations.csv"
$fwSL=Import-Csv "$dbdir\fw_station_lines.csv"
$fwSeg=Import-Csv "$dbdir\fw_segments.csv"

# FW terminus flags + per-station phase (min across its lines)
$term=@{}; foreach($g in ($fwSL | Group-Object line)){ $sq=$g.Group | Sort-Object {[int]$_.seq}; $term[$sq[0].station_id]=$true; $term[$sq[-1].station_id]=$true }
$phByStation=@{}; foreach($r in $fwSL){ $p=[int]$r.phase; if(-not $phByStation.ContainsKey($r.station_id) -or $p -lt $phByStation[$r.station_id]){ $phByStation[$r.station_id]=$p } }
$slPhase=@{}; foreach($r in $fwSL){ $slPhase["$($r.line)|$($r.station_id)"]=[int]$r.phase }

# ---- unified stations ----
$uniSt=@()
$fwYear=@{}
foreach($s in $fwSt){
  $lat=[double]$s.lat;$lon=[double]$s.lon
  $act=Act1k $lat $lon
  $ph= if($phByStation.ContainsKey($s.station_id)){$phByStation[$s.station_id]}else{[int]$s.phase_opened}
  # base year = earliest override among the station's lines; infill bump (+5) for low-act non-termini
  $base=9999; foreach($l in ($s.lines -split ';')){ if($fwYearOv.ContainsKey($l) -and $fwYearOv[$l] -lt $base){ $base=$fwYearOv[$l] } }
  if($base -lt 9999){
    $yr=$base
    if(-not [bool]$term[$s.station_id] -and $act -lt 5000 -and $yr -lt 2070){ $i=[array]::IndexOf($STEPS,$yr); $yr=$STEPS[[math]::Min($i+1,8)] }
  } else { $yr=StationYear $ph $lat $lon $act ([bool]$term[$s.station_id]) }
  $fwYear[$s.station_id]=$yr
  $c= if($s.lines){ $fwCol[ (($s.lines -split ';')[0]) ] } else { '#666' }
  $uniSt+=[pscustomobject]@{station_id=$s.station_id;name=$s.name;mode='metro';lat=$s.lat;lon=$s.lon;year_opens=$yr;act=$act;lines=$s.lines;n_lines=$s.num_lines;color=$c;src='fw'}
}
foreach($s in (Import-Csv "$dbdir\_extra_stations.csv")){
  $nl=($s.lines -split ';').Count
  $uniSt+=[pscustomobject]@{station_id=$s.station_id;name=$s.name;mode=$s.mode;lat=$s.lat;lon=$s.lon;year_opens=$s.year_opens;act=$s.act;lines=$s.lines;n_lines=$nl;color=$s.color;src='extra'}
}
$uniSt | Export-Csv "$dbdir\stations.csv" -NoTypeInformation

# ---- unified lines ----
$uniLn=@(); $fid=0
foreach($ln in @('Teal','Blue','Orange','Pink','Silver','Red','Purple')){
  $fid++; $nst=($fwSL | Where-Object {$_.line -eq $ln}).Count
  $uniLn+=[pscustomobject]@{line_id=('F{0:D2}' -f $fid);name=$ln;mode='metro';phase='';color=$fwCol[$ln];src='fw';n_stations=$nst}
}
foreach($l in (Import-Csv "$dbdir\_extra_lines.csv")){ $uniLn+=$l }
$uniLn | Export-Csv "$dbdir\lines.csv" -NoTypeInformation

# ---- unified station_lines ----
$uniSL=@()
$fwLineId=@{}; $fid=0; foreach($ln in @('Teal','Blue','Orange','Pink','Silver','Red','Purple')){ $fid++; $fwLineId[$ln]=('F{0:D2}' -f $fid) }
$fwName=@{}; foreach($s in $fwSt){ $fwName[$s.station_id]=$s.name }
foreach($r in ($fwSL | Sort-Object line,{[int]$_.seq})){
  $uniSL+=[pscustomobject]@{line_id=$fwLineId[$r.line];line=$r.line;seq=$r.seq;station_id=$r.station_id;station_name=$fwName[$r.station_id];year=$fwYear[$r.station_id]}
}
foreach($r in (Import-Csv "$dbdir\_extra_station_lines.csv")){ $uniSL+=$r }
$uniSL | Export-Csv "$dbdir\station_lines.csv" -NoTypeInformation

# ---- unified segments ----
# FW: keep multi-line segments; add per-line years (YearBand at segment midpoint w/ that line's phase)
$uniSeg=@()
foreach($s in $fwSeg){
  $inner=$s.geometry_wkt -replace '^LINESTRING \(','' -replace '\)$',''
  $pts=@(); foreach($p in ($inner -split ',')){ $xy=$p.Trim() -split '\s+'; $pts+=,@([double]$xy[0],[double]$xy[1]) }
  $mid=$pts[[int]($pts.Count/2)]
  $lns=$s.lines -split ';'; $yrs=@()
  foreach($l in $lns){
    if($fwYearOv.ContainsKey($l)){ $yrs+=$fwYearOv[$l]; continue }
    $pf=$slPhase["$l|$($s.from_id)"]; $pt=$slPhase["$l|$($s.to_id)"]
    $p= if($pf -ne $null -and $pt -ne $null){[math]::Max($pf,$pt)} elseif($pf -ne $null){$pf} elseif($pt -ne $null){$pt} else {[int]$s.phase}
    $yrs+=YearBand $p $mid[1] $mid[0]
  }
  $uniSeg+=[pscustomobject]@{segment_id=$s.segment_id;line_id='';line=$s.lines;mode='metro';color='';from_id=$s.from_id;from_name=$s.from_name;to_id=$s.to_id;to_name=$s.to_name;year_opens=($yrs -join ';');src='fw';geometry_wkt=$s.geometry_wkt}
}
foreach($s in (Import-Csv "$dbdir\_extra_segments.csv")){
  $uniSeg+=[pscustomobject]@{segment_id=$s.segment_id;line_id=$s.line_id;line=$s.line;mode=$s.mode;color=$s.color;from_id=$s.from_id;from_name=$s.from_name;to_id=$s.to_id;to_name=$s.to_name;year_opens=$s.year_opens;src='extra';geometry_wkt=$s.geometry_wkt}
}
$uniSeg | Export-Csv "$dbdir\segments.csv" -NoTypeInformation

"== UNIFIED DB =="
"stations.csv      : $($uniSt.Count)  (fw $(($uniSt|Where-Object{$_.src -eq 'fw'}).Count) / extra $(($uniSt|Where-Object{$_.src -eq 'extra'}).Count))"
"lines.csv         : $($uniLn.Count)"
"station_lines.csv : $($uniSL.Count)"
"segments.csv      : $($uniSeg.Count)  (fw $(($uniSeg|Where-Object{$_.src -eq 'fw'}).Count) / extra $(($uniSeg|Where-Object{$_.src -eq 'extra'}).Count))"