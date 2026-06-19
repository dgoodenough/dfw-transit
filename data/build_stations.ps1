$ErrorActionPreference="Stop"
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.85*[math]::PI/180)
function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2); return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }
$cores=@(@(32.7767,-96.7970),@(32.7555,-97.3308)); $STEPS=@(2025,2035,2040,2045,2050,2055,2060,2065,2070)
function CoreKm($lat,$lon){ $m=1e9; foreach($c in $cores){ $d=Hav $lat $lon $c[0] $c[1]; if($d -lt $m){$m=$d} }; return $m }
function YearBand($phase,$lat,$lon){ if($phase -eq 0){return 2025}; $d=CoreKm $lat $lon
  if($phase -eq 1){ if($d -lt 8){2035}elseif($d -lt 15){2040}else{2045} } elseif($phase -eq 2){ if($d -lt 18){2050}else{2055} } else { if($d -lt 30){2060}elseif($d -lt 50){2065}else{2070} } }
function StationYear($phase,$lat,$lon,$act,$isTerm){ $y=YearBand $phase $lat $lon
  if(-not $isTerm -and $act -lt 5000 -and $y -lt 2070){ $i=[array]::IndexOf($STEPS,$y); $y=$STEPS[[math]::Min($i+1,8)] }; return $y }
# Session B paced phasing: explicit per-line opening years (data/line_years.csv, scope=extra) override the distance bands
$lineYear=@{}; foreach($r in (Import-Csv "$ddir\line_years.csv" | Where-Object {$_.scope -eq 'extra'})){ $lineYear[$r.line]=[int]$r.year }
function StationYearOv($lineName,$phase,$lat,$lon,$act,$isTerm){
  if($lineYear.ContainsKey($lineName)){ $y=$lineYear[$lineName]
    if(-not $isTerm -and $act -lt 5000 -and $y -lt 2070){ $i=[array]::IndexOf($STEPS,$y); $y=$STEPS[[math]::Min($i+1,8)] }; return $y }
  return (StationYear $phase $lat $lon $act $isTerm) }

# density + county (geoid chars 2..4 = county FIPS)
$dens=@(); foreach($r in (Import-Csv "$ddir\metroplex_density.csv")){ $dens+=[pscustomobject]@{lat=[double]$r.lat;lon=[double]$r.lon;act=[int]$r.pop+[int]$r.jobs;cty=$r.geoid.Substring(2,3)} }
function Act1k($lat,$lon){ $s=0; foreach($b in $dens){ if([math]::Abs($b.lat-$lat) -lt 0.013 -and [math]::Abs($b.lon-$lon) -lt 0.016){ if((Hav $lat $lon $b.lat $b.lon) -le 1.0){ $s+=$b.act } } }; return $s }
function InCore($lat,$lon){ $best=1e9;$cty=''; foreach($b in $dens){ if([math]::Abs($b.lat-$lat) -gt 0.05 -or [math]::Abs($b.lon-$lon) -gt 0.06){continue}; $d=[math]::Pow($b.lat-$lat,2)+[math]::Pow($b.lon-$lon,2); if($d -lt $best){$best=$d;$cty=$b.cty} }; return ($cty -eq '439' -or $cty -eq '113') }

# OSM stations + town centers
$poi=Get-Content "$ddir\dfw_poi.json" -Raw | ConvertFrom-Json
$osm=@(); foreach($e in $poi.elements){ if($e.tags.railway -or $e.tags.public_transport){ if($e.lat){ $osm+=[pscustomobject]@{name=$(if($e.tags.name){$e.tags.name}else{'Station'});lat=[double]$e.lat;lon=[double]$e.lon} } } }
$places=@(); foreach($e in $poi.elements){ if($e.tags.place -and $e.lat){ $places+=[pscustomobject]@{name=$e.tags.name;lat=[double]$e.lat;lon=[double]$e.lon} } }
"OSM stations: $($osm.Count) | town centers: $($places.Count)"
function NearestPlace($lat,$lon){ $best=1e9;$bn=$null; foreach($p in $places){ if([math]::Abs($p.lat-$lat) -gt 0.05 -or [math]::Abs($p.lon-$lon) -gt 0.06){continue}; $d=Hav $lat $lon $p.lat $p.lon; if($d -lt $best){$best=$d;$bn=$p.name} }; if($best -le 4){return $bn}; return $null }
$hoods=@(); if(Test-Path "$ddir\dfw_hoods.json"){ foreach($e in (Get-Content "$ddir\dfw_hoods.json" -Raw|ConvertFrom-Json).elements){ if($e.tags.name -and $e.lat){ $hoods+=[pscustomobject]@{name=$e.tags.name;lat=[double]$e.lat;lon=[double]$e.lon} } } }
function NearestHood($lat,$lon){ $best=1e9;$bn=$null; foreach($h in $hoods){ if([math]::Abs($h.lat-$lat) -gt 0.02 -or [math]::Abs($h.lon-$lon) -gt 0.024){continue}; $d=Hav $lat $lon $h.lat $h.lon; if($d -lt $best){$best=$d;$bn=$h.name} }; if($best -le 1.5){return $bn}; return $null }

# density pins (renamed) for metro anchoring
$renames=@(); foreach($r in (Import-Csv "$ddir\renames.csv")){ $renames+=[pscustomobject]@{old=$r.old_name;lat=[double]$r.lat;lon=[double]$r.lon;new=$r.new_name} }
function Rn($nm,$lat,$lon){ foreach($r in $renames){ if($r.old -eq $nm -and [math]::Abs($r.lat-$lat) -lt 0.003 -and [math]::Abs($r.lon-$lon) -lt 0.003){ return $r.new } }; return $nm }
$pins=@(); foreach($p in (Import-Csv "C:\Users\justd\Downloads\FW_stations.csv" | Where-Object {$_.Folder -like 'Stops and potential*'})){ $pins+=[pscustomobject]@{name=(Rn $p.Name ([double]$p.Lat) ([double]$p.Lon));lat=[double]$p.Lat;lon=[double]$p.Lon} }
# real existing-line stations (from OSM route relations)
$exStops=@{}; if(Test-Path "$ddir\existing_stops.json"){ $es=Get-Content "$ddir\existing_stops.json" -Raw | ConvertFrom-Json; foreach($pp in $es.PSObject.Properties){ $exStops[$pp.Name]=$pp.Value } }

# ---- geometry helpers ----
function CumLen($coords){ $cum=@(0.0); for($i=1;$i -lt $coords.Count;$i++){ $cum+=$cum[$i-1]+(Hav $coords[$i-1][1] $coords[$i-1][0] $coords[$i][1] $coords[$i][0])*1000 }; return ,$cum }
function ProjOnLine($coords,$cum,$plon,$plat){
  $px=$plon*$mlon;$py=$plat*$mlat;$best=1e18;$bl=$plon;$ba=$plat;$balong=0.0
  for($i=0;$i -lt $coords.Count-1;$i++){ $ax=$coords[$i][0]*$mlon;$ay=$coords[$i][1]*$mlat;$bx=$coords[$i+1][0]*$mlon;$by=$coords[$i+1][1]*$mlat
    $dx=$bx-$ax;$dy=$by-$ay;$L2=$dx*$dx+$dy*$dy; $t= if($L2 -gt 0){(($px-$ax)*$dx+($py-$ay)*$dy)/$L2}else{0}; if($t -lt 0){$t=0}elseif($t -gt 1){$t=1}
    $cx=$ax+$t*$dx;$cy=$ay+$t*$dy;$d=[math]::Pow($px-$cx,2)+[math]::Pow($py-$cy,2)
    if($d -lt $best){$best=$d;$bl=$cx/$mlon;$ba=$cy/$mlat;$seg=[math]::Sqrt($L2);$balong=$cum[$i]+$t*$seg} }
  return [pscustomobject]@{lon=$bl;lat=$ba;dist=[math]::Sqrt($best);along=$balong}
}
function InterpAt($coords,$cum,$d){ $seg=1; while($seg -lt $cum.Count-1 -and [double]$cum[$seg] -lt [double]$d){$seg++}
  $a=$coords[$seg-1];$b=$coords[$seg]; $c0=[double]$cum[$seg-1];$c1=[double]$cum[$seg]; $sl=$c1-$c0; $t=0.0; if($sl -gt 0){ $t=([double]$d-$c0)/$sl }
  $alon=[double]$a[0];$alat=[double]$a[1];$blon=[double]$b[0];$blat=[double]$b[1]
  return @(($alon+$t*($blon-$alon)),($alat+$t*($blat-$alat))) }
function SliceLine($coords,$cum,$aA,$aB){ $pA=InterpAt $coords $cum $aA; $pB=InterpAt $coords $cum $aB
  $g=@(); $g+=,$pA
  for($i=0;$i -lt $coords.Count;$i++){ $ci=[double]$cum[$i]; if($ci -gt ($aA+1) -and $ci -lt ($aB-1)){ $g+=,@([double]$coords[$i][0],[double]$coords[$i][1]) } }
  $g+=,$pB; return ,$g }

# FW downtown convergence tails (inner terminus -> Fort Worth Central), appended to each FW commuter line
$fwConv=@{}; if(Test-Path "$dbdir\fw_convergence.geojson"){ foreach($ff in ((Get-Content "$dbdir\fw_convergence.geojson" -Raw | ConvertFrom-Json).features)){ $tp=@(); foreach($c in $ff.geometry.coordinates){ $tp+=,@([double]$c[0],[double]$c[1]) }; $fwConv[$ff.properties.name]=$tp } }

# corridor-share overrides (Jun 15 fixes): replace whole-line geometry by name; remove merged-away lines
$corrFix=@{}; $corrRemove=@()
if(Test-Path "$dbdir\corridor_fixes.geojson"){ $cf=Get-Content "$dbdir\corridor_fixes.geojson" -Raw | ConvertFrom-Json; if($cf.remove){$corrRemove=@($cf.remove)}; foreach($ff in $cf.features){ $cc=@(); foreach($c in $ff.geometry.coordinates){ $cc+=,@([double]$c[0],[double]$c[1]) }; $corrFix[$ff.properties.name]=$cc } }
# manual hand-edits (from edit/ round-trip via import_lines.ps1) = FINAL geometry, applied last (after tails) so re-import is idempotent
$manualFix=@{}
if(Test-Path "$dbdir\manual_geom.geojson"){ foreach($ff in ((Get-Content "$dbdir\manual_geom.geojson" -Raw | ConvertFrom-Json).features)){ if(-not $ff.geometry){continue}; $cc=@(); foreach($c in $ff.geometry.coordinates){ $cc+=,@([double]$c[0],[double]$c[1]) }; $manualFix[$ff.properties.name]=$cc } }

# ---- collect lines (network_extra + commuter_ext only; orphan spurs dropped) ----
$lines=@(); $lineFeats=@()
foreach($gf in @("$dbdir\network_extra.geojson","$dbdir\commuter_ext.geojson","$dbdir\midlothian_ext.geojson")){
  if(-not (Test-Path $gf)){continue}
  foreach($f in ((Get-Content $gf -Raw | ConvertFrom-Json).features)){ if($f.properties.kind -ne 'line'){continue}
    if(@('Cleburne Line (ROW)','Chico Line (ROW)','Line 80','NAS JRB BRT') -contains $f.properties.name){continue}  # cuts: Cleburne(TexPress dup), Chico 0.47/$M, Line 80 & NAS JRB BRT (overlap FW Crosstown Loop)
    if($corrRemove -contains $f.properties.name){continue}   # merged away (Arboretum -> Line 76)
    $coords=@(); foreach($c in $f.geometry.coordinates){ $coords+=,@([double]$c[0],[double]$c[1]) }
    if($corrFix.ContainsKey($f.properties.name)){ $coords=$corrFix[$f.properties.name] }   # corridor-share geometry override
    if($coords.Count -lt 2){continue}
    # FW convergence: append rail-routed tail to downtown FW Central at the inner (downtown) end
    if($fwConv.ContainsKey($f.properties.name)){
      $tail=$fwConv[$f.properties.name]; $ti=$tail[0]
      $d0=[math]::Pow($coords[0][0]-$ti[0],2)+[math]::Pow($coords[0][1]-$ti[1],2)
      $dN=[math]::Pow($coords[-1][0]-$ti[0],2)+[math]::Pow($coords[-1][1]-$ti[1],2)
      if($d0 -lt $dN){ $rev=@(); for($z=$coords.Count-1;$z -ge 0;$z--){$rev+=,$coords[$z]}; $coords=$rev }  # inner end last
      for($z=1;$z -lt $tail.Count;$z++){ $coords+=,$tail[$z] }
    }
    if($manualFix.ContainsKey($f.properties.name)){ $coords=$manualFix[$f.properties.name] }   # hand-edit = final geometry (overrides tails/corridor fixes)
    $lineFeats+=$f
    $lines+=[pscustomobject]@{name=$f.properties.name;mode=$f.properties.mode;phase=[int]$f.properties.phase;color=$f.properties.color;coords=$coords}
  }
}
"lines: $($lines.Count)"
# dump effective per-line input geometry = the editable source for the hand-edit round-trip (idempotent)
$srcGj=@()
foreach($L in $lines){ $c=($L.coords | ForEach-Object {'['+[math]::Round([double]$_[0],6)+','+[math]::Round([double]$_[1],6)+']'}) -join ','
  $srcGj+='{"type":"Feature","properties":{"name":"'+($L.name -replace '"','\"')+'","mode":"'+$L.mode+'","color":"'+$L.color+'"},"geometry":{"type":"LineString","coordinates":['+$c+']}}' }
Set-Content "$dbdir\lines_source.geojson" ('{"type":"FeatureCollection","features":['+($srcGj -join ',')+']}') -Encoding utf8

$stopFeats=@(); $lf=@(); $genCount=0
# DB accumulators (consolidated-DB rows for the extra network)
$dbStations=@(); $dbSL=@(); $dbSegs=@(); $dbLines=@(); $sid=0; $lid=0; $segid=0
function EmitStop($nm,$lon,$lat,$mode,$phase,$color,$act,$yr){ "{`"type`":`"Feature`",`"properties`":{`"name`":`"$($nm -replace '"','\"')`",`"kind`":`"stop`",`"mode`":`"$mode`",`"phase`":$phase,`"color`":`"$color`",`"act`":$act,`"yr`":$yr},`"geometry`":{`"type`":`"Point`",`"coordinates`":[$([math]::Round($lon,6)),$([math]::Round($lat,6))]}}" }

foreach($L in $lines){
  $cum=@(0.0); for($i=1;$i -lt $L.coords.Count;$i++){ $cum+=$cum[$i-1]+(Hav $L.coords[$i-1][1] $L.coords[$i-1][0] $L.coords[$i][1] $L.coords[$i][0])*1000 }
  $total=$cum[-1]; if($total -lt 50){continue}
  $cand=@()  # {lon,lat,along,name,act,isTerm}
  $short=(($L.name -replace ' Line.*','') -replace ' \(ROW\)','').Trim()
  if($short -match '(?i)^(No Idea|Line \d+|\d+|BRT|Beltline.*|3|46)$'){ $mid=$L.coords[[int]($L.coords.Count/2)]; $sp2=NearestPlace $mid[1] $mid[0]; $short= if($sp2){$sp2}else{'Stop'} }

  if($L.phase -eq 0){
    # EXISTING line: real stations from the OSM route relation, snapped onto the track
    if($exStops.ContainsKey($L.name)){ foreach($s in $exStops[$L.name]){ $pr=ProjOnLine $L.coords $cum ([double]$s.lon) ([double]$s.lat)
      $cand+=[pscustomobject]@{lon=$pr.lon;lat=$pr.lat;along=$pr.along;name=$s.name;act=0;isTerm=$false} } }
  }
  elseif($L.mode -eq 'commuter'){
    # termini ALWAYS (named by nearest town center)
    foreach($end in @(@($L.coords[0],0.0),@($L.coords[-1],$total))){ $c=$end[0]; $cand+=[pscustomobject]@{lon=$c[0];lat=$c[1];along=$end[1];name=(NearestPlace $c[1] $c[0]);act=0;isTerm=$true} }
    # walk the line: in core counties -> ~3.5km spacing; outside -> town centers only
    $sp=3500.0; $d=$sp
    while($d -lt $total-800){ $pt=InterpAt $L.coords $cum $d
      if(InCore $pt[1] $pt[0]){ $cand+=[pscustomobject]@{lon=$pt[0];lat=$pt[1];along=$d;name=$null;act=0;isTerm=$false} }
      $d+=$sp }
    foreach($pl in $places){ $pr=ProjOnLine $L.coords $cum $pl.lon $pl.lat
      if($pr.dist -le 3500 -and -not (InCore $pr.lat $pr.lon)){ $cand+=[pscustomobject]@{lon=$pr.lon;lat=$pr.lat;along=$pr.along;name=$pl.name;act=0;isTerm=$false} } }
  }
  else {
    # METRO / BRT: density-anchored. termini + nearby density pins, gap-fill at density peaks
    foreach($end in @(@($L.coords[0],0.0),@($L.coords[-1],$total))){ $c=$end[0]; $cand+=[pscustomobject]@{lon=$c[0];lat=$c[1];along=$end[1];name=$null;act=0;isTerm=$true} }
    foreach($p in $pins){ if([math]::Abs($p.lat-$L.coords[0][1]) -gt 0.5 -and [math]::Abs($p.lat-$L.coords[-1][1]) -gt 0.5){continue}
      $pr=ProjOnLine $L.coords $cum $p.lon $p.lat
      if($pr.dist -le 700){ $cand+=[pscustomobject]@{lon=$pr.lon;lat=$pr.lat;along=$pr.along;name=$p.name;act=0;isTerm=$false} } }
  }

  # sort + cluster-merge. prefer a real name + carry terminus flag. (tight for existing - real DART stops are ~400m apart;
  # commuter wide so a terminus and its town-center pin merge instead of producing "Gainesville"+"Gainesville 2")
  $ddist= if($L.phase -eq 0){150}elseif($L.mode -eq 'commuter'){2500}else{700}
  $cand=$cand | Sort-Object along
  $kept=@()
  foreach($c in $cand){
    if($kept.Count -gt 0 -and ($c.along-$kept[-1].along) -lt $ddist){
      $last=$kept[-1]
      if($c.name -and -not $last.name){ $last.name=$c.name }
      if($c.isTerm){ $last.isTerm=$true; if($c.name){$last.name=$c.name} }
      continue
    }
    $kept+=$c
  }

  # METRO/BRT gap fill at density peak where gap > 3500m
  if($L.phase -ne 0 -and $L.mode -ne 'commuter'){
    $filled=@(); for($k=0;$k -lt $kept.Count;$k++){ $filled+=$kept[$k]
      if($k -lt $kept.Count-1){ $gap=$kept[$k+1].along-$kept[$k].along
        if($gap -gt 3500){ $nfill=[math]::Floor($gap/2500); for($m=1;$m -le $nfill;$m++){ $dd=$kept[$k].along+$gap*$m/($nfill+1); $pt=InterpAt $L.coords $cum $dd; $filled+=[pscustomobject]@{lon=$pt[0];lat=$pt[1];along=$dd;name=$null;act=0;isTerm=$false} } } } }
    $kept=$filled | Sort-Object along
  }

  # emit stops, then line SEGMENTS between consecutive opened stations (so a line never overhangs past its terminus)
  $idx=0; $usedNames=@{}; $emitted=@(); $lastAlong=$null
  for($ki=0;$ki -lt $kept.Count;$ki++){ $c=$kept[$ki]; $idx++
    $act= if($L.phase -eq 0){0}else{Act1k $c.lat $c.lon}
    # prune empty filler stations (planned, non-terminus, unnamed, zero activity) -
    # BUT never if pruning would open a >3.5km hole on a metro/brt line (gap guard vs. orphan mega-gaps)
    if($L.phase -ge 1 -and -not $c.isTerm -and -not $c.name -and $act -eq 0){
      $next= if($ki -lt $kept.Count-1){$kept[$ki+1].along}else{$c.along}
      $prev= if($lastAlong -ne $null){$lastAlong}else{0}
      $gapIfPruned=$next-$prev
      if($L.mode -eq 'commuter' -or $gapIfPruned -le 3500){ continue }
    }
    $lastAlong=$c.along
    $nm=$c.name
    $junk = (-not $nm) -or ($nm -match '(?i)^(Point \d+|design ?\d*|industry|jobs|somewhere|hmm|ugh|aopd|lots( of apts)?|a place|also a place|i wish|o stuff|apt|apts|med|connect|people|stuff|porolly not|N legacy e)$')
    if($junk -and $L.phase -ne 0){ $hn=NearestHood $c.lat $c.lon; if(-not $hn){$hn=NearestPlace $c.lat $c.lon}; $nm= if($hn){$hn}else{"$short $idx"} }
    # termini deserve real names: try place/hood before falling back to "<line> N"
    if(-not $nm -and $c.isTerm){ $tn=NearestPlace $c.lat $c.lon; if(-not $tn){$tn=NearestHood $c.lat $c.lon}; if($tn){$nm=$tn} }
    if(-not $nm){ $nm="$short $idx" }
    if($usedNames.ContainsKey($nm)){ $usedNames[$nm]++; $nm="$nm $($usedNames[$nm])" } else { $usedNames[$nm]=1 }
    $yr= if($L.phase -eq 0){2025}else{ StationYearOv $L.name $L.phase $c.lat $c.lon $act $c.isTerm }
    $stopFeats+=EmitStop $nm $c.lon $c.lat $L.mode $L.phase $L.color $act $yr; $genCount++
    $sid++
    $emitted+=[pscustomobject]@{id=('X{0:D3}' -f $sid);name=$nm;lon=$c.lon;lat=$c.lat;along=$c.along;yr=$yr;act=$act}
  }
  # one full line + its stations' opening fractions; the app clips the line to its opened stations
  if($emitted.Count -ge 2 -and $total -gt 0){
    $stj=($emitted | ForEach-Object { '{"f":'+([math]::Round($_.along/$total,4))+',"y":'+[int]$_.yr+'}' }) -join ','
    $coords=($L.coords | ForEach-Object { '['+[math]::Round([double]$_[0],6)+','+[math]::Round([double]$_[1],6)+']' }) -join ','
    $lf+='{"type":"Feature","properties":{"name":"'+($L.name -replace '"','\"')+'","kind":"line","mode":"'+$L.mode+'","phase":'+$L.phase+',"color":"'+$L.color+'","stops":['+$stj+']},"geometry":{"type":"LineString","coordinates":['+$coords+']}}'
  }
  # ---- consolidated-DB rows for this line ----
  if($emitted.Count -ge 2){
    $lid++; $lineId=('E{0:D2}' -f $lid)
    $dbLines+=[pscustomobject]@{line_id=$lineId;name=$L.name;mode=$L.mode;phase=$L.phase;color=$L.color;src='extra';n_stations=$emitted.Count}
    $seq=0
    foreach($e in $emitted){ $seq++
      $dbStations+=[pscustomobject]@{station_id=$e.id;name=$e.name;mode=$L.mode;lat=[math]::Round($e.lat,6);lon=[math]::Round($e.lon,6);year_opens=$e.yr;act=$e.act;lines=$L.name;color=$L.color;src='extra'}
      # (consolidation pass below merges cross-line duplicates within 250m into shared stations)
      $dbSL+=[pscustomobject]@{line_id=$lineId;line=$L.name;seq=$seq;station_id=$e.id;station_name=$e.name;year=$e.yr}
    }
    # clip-rule segment years: seg k opens at max(min(yr[0..k]), min(yr[k+1..n-1])) -> contiguous growth, no orphans
    $n=$emitted.Count
    $pre=New-Object 'int[]' $n; $suf=New-Object 'int[]' $n
    $pre[0]=$emitted[0].yr; for($k=1;$k -lt $n;$k++){ $pre[$k]=[math]::Min($pre[$k-1],[int]$emitted[$k].yr) }
    $suf[$n-1]=$emitted[$n-1].yr; for($k=$n-2;$k -ge 0;$k--){ $suf[$k]=[math]::Min($suf[$k+1],[int]$emitted[$k].yr) }
    for($k=0;$k -lt $n-1;$k++){
      $segid++
      $sg=SliceLine $L.coords $cum $emitted[$k].along $emitted[$k+1].along
      $wkt='LINESTRING (' + (($sg | ForEach-Object { "$([math]::Round($_[0],6)) $([math]::Round($_[1],6))" }) -join ', ') + ')'
      $dbSegs+=[pscustomobject]@{segment_id=('XSEG{0:D3}' -f $segid);line_id=$lineId;line=$L.name;mode=$L.mode;color=$L.color;from_id=$emitted[$k].id;from_name=$emitted[$k].name;to_id=$emitted[$k+1].id;to_name=$emitted[$k+1].name;year_opens=[math]::Max($pre[$k],$suf[$k+1]);src='extra';geometry_wkt=$wkt}
    }
  }
}
"generated stations: $genCount"

Set-Content "$dbdir\extra_final.geojson" ('{"type":"FeatureCollection","features":['+(($lf+$stopFeats) -join ',')+']}') -Encoding utf8
"wrote extra_final.geojson: $($lf.Count) lines + $genCount stops"

# ---- NAMING PASS: replace generic "<line> N" names on proposed stops with real local names ----
# pool: neighbourhoods/suburbs/towns/villages/hamlets + malls/universities/hospitals/stadiums (dfw_gazetteer) + dfw_hoods
$gaz=New-Object System.Collections.Generic.List[object]
$wByPlace=@{neighbourhood=1.3;suburb=1.3;quarter=1.2;city=1.0;town=1.0;village=0.8;hamlet=0.5}
if(Test-Path "$ddir\dfw_gazetteer.json"){ foreach($e in (Get-Content "$ddir\dfw_gazetteer.json" -Raw|ConvertFrom-Json).elements){
  $la= if($e.lat){$e.lat}elseif($e.center){$e.center.lat}else{$null}; if($null -eq $la){continue}
  $lo= if($e.lon){$e.lon}else{$e.center.lon}; $nm=$e.tags.name; if(-not $nm){continue}
  $w=0.0
  if($e.tags.place){ $w= if($wByPlace.ContainsKey($e.tags.place)){$wByPlace[$e.tags.place]}else{0.6} }
  elseif($e.tags.shop -eq 'mall'){ $w=1.1 } elseif($e.tags.amenity -eq 'university' -or $e.tags.amenity -eq 'hospital'){ $w=1.0 } elseif($e.tags.leisure -eq 'stadium'){ $w=1.0 }
  if($w -gt 0){ [void]$gaz.Add([pscustomobject]@{name=$nm;lat=[double]$la;lon=[double]$lo;w=$w}) } } }
if(Test-Path "$ddir\dfw_hoods.json"){ foreach($e in (Get-Content "$ddir\dfw_hoods.json" -Raw|ConvertFrom-Json).elements){ if($e.tags.name -and $e.lat){ [void]$gaz.Add([pscustomobject]@{name=$e.tags.name;lat=[double]$e.lat;lon=[double]$e.lon;w=1.3}) } } }
"naming gazetteer: $($gaz.Count) features"
function BestGaz($lat,$lon){ $best=1e9;$r=$null
  foreach($g in $gaz){ if([math]::Abs($g.lat-$lat) -gt 0.085 -or [math]::Abs($g.lon-$lon) -gt 0.095){continue}
    $d=Hav $lat $lon $g.lat $g.lon; if($d -gt 8){continue}; $sc=$d/$g.w
    if($sc -lt $best){$best=$sc;$r=@{name=$g.name;d=$d;flat=$g.lat;flon=$g.lon}} }
  return $r }
function Compass($flat,$flon,$lat,$lon){ $ang=[math]::Atan2($lat-$flat,$lon-$flon)*180/[math]::PI
  $dirs=@('E','NE','N','NW','W','SW','S','SE'); $i=[int][math]::Round($ang/45); if($i -lt 0){$i+=8}; return $dirs[$i%8] }
$pick=@{}; $feat=@{}
foreach($s in $dbStations){ if([int]$s.year_opens -le 2025 -or $s.name -notmatch ' \d+$'){continue}
  $b=BestGaz ([double]$s.lat) ([double]$s.lon); if($b){ $pick[$s.station_id]=$b.name; $feat[$s.station_id]=$b } }
# names already in use by NON-renamed stations (don't collide with them)
$taken=@{}; foreach($s in $dbStations){ if(-not $pick.ContainsKey($s.station_id)){ $taken[$s.name]=$true } }
$stByIdN=@{}; foreach($s in $dbStations){ $stByIdN[$s.station_id]=$s }
$byName=@{}; foreach($id in $pick.Keys){ $n=$pick[$id]; if(-not $byName.ContainsKey($n)){$byName[$n]=New-Object System.Collections.Generic.List[string]}; [void]$byName[$n].Add($id) }
$final=@{}
foreach($n in $byName.Keys){ $ids=@($byName[$n] | Sort-Object {$feat[$_].d})   # @() so single-id lists stay arrays (else $ids[0] indexes a char)
  for($i=0;$i -lt $ids.Count;$i++){ $id=$ids[$i]
    if($i -eq 0 -and -not $taken.ContainsKey($n)){ $final[$id]=$n; $taken[$n]=$true }
    else { $f=$feat[$id]; $stn=$stByIdN[$id]; $dir=Compass $f.flat $f.flon ([double]$stn.lat) ([double]$stn.lon); $c="$n $dir"; $k=2
      while($taken.ContainsKey($c)){ $c="$n $dir$k"; $k++ }; $final[$id]=$c; $taken[$c]=$true } } }
$rn=0; foreach($s in $dbStations){ if($final.ContainsKey($s.station_id)){ $s.name=$final[$s.station_id]; $rn++ } }
$nmByIdN=@{}; foreach($s in $dbStations){ $nmByIdN[$s.station_id]=$s.name }
foreach($r in $dbSL){ if($final.ContainsKey($r.station_id)){ $r.station_name=$nmByIdN[$r.station_id] } }
foreach($r in $dbSegs){ if($final.ContainsKey($r.from_id)){ $r.from_name=$nmByIdN[$r.from_id] }; if($final.ContainsKey($r.to_id)){ $r.to_name=$nmByIdN[$r.to_id] } }
"naming pass: renamed $rn generic proposed stops"

# ---- FW hub: snap each converging line's downtown-most stop exactly onto Fort Worth Central ----
# (the stop generator anchors termini to nearby POIs; force them to the shared hub so transfers are real)
$FWCh=@(32.751994,-97.325572)
foreach($ln in @('Bowie Line (ROW)','Gainesville Line (ROW)','FTW/Denton','TexRail 3rd exp','SE TexRail')){
  $cand=$dbStations | Where-Object {($_.lines -split ';') -contains $ln}
  $best=$null;$bd=1e9; foreach($c in $cand){ $d=Hav $FWCh[0] $FWCh[1] ([double]$c.lat) ([double]$c.lon); if($d -lt $bd){$bd=$d;$best=$c} }
  if($best -and $bd -le 3.5){ "  FW hub snap: $ln '$($best.name)' moved $([math]::Round($bd,2))km onto Fort Worth Central"; $best.lat=$FWCh[0]; $best.lon=$FWCh[1]; $best.name='Fort Worth Central' }
}

# ---- cross-line station consolidation: different lines' stops within 250m -> one shared station ----
# priority for the canonical station: existing(2025) > earlier year > higher act
$remap=@{}
$ordered=$dbStations | Sort-Object @{e={[int]$_.year_opens}},@{e={-[int]$_.act}}
$canon=@()
foreach($s in $ordered){
  if($remap.ContainsKey($s.station_id)){continue}
  $canon+=$s
  foreach($o in $dbStations){
    if($o.station_id -eq $s.station_id -or $remap.ContainsKey($o.station_id)){continue}
    if($o.lines -eq $s.lines){continue}   # never merge same-line neighbors
    if([math]::Abs([double]$o.lat-[double]$s.lat) -gt 0.0035 -or [math]::Abs([double]$o.lon-[double]$s.lon) -gt 0.004){continue}
    if((Hav ([double]$s.lat) ([double]$s.lon) ([double]$o.lat) ([double]$o.lon))*1000 -le 250){
      $remap[$o.station_id]=$s.station_id
      if(($s.lines -split ';') -notcontains $o.lines){ $s.lines=$s.lines+';'+$o.lines }
      if([int]$o.year_opens -lt [int]$s.year_opens){ $s.year_opens=$o.year_opens }
      if([int]$o.act -gt [int]$s.act){ $s.act=$o.act }
    }
  }
}
$nameById=@{}; foreach($s in $canon){ $nameById[$s.station_id]=$s.name }
foreach($r in $dbSL){ if($remap.ContainsKey($r.station_id)){ $r.station_id=$remap[$r.station_id]; $r.station_name=$nameById[$r.station_id] } }
foreach($r in $dbSegs){
  if($remap.ContainsKey($r.from_id)){ $r.from_id=$remap[$r.from_id]; $r.from_name=$nameById[$r.from_id] }
  if($remap.ContainsKey($r.to_id)){ $r.to_id=$remap[$r.to_id]; $r.to_name=$nameById[$r.to_id] }
}
"consolidated: $($remap.Count) duplicate stops merged -> $($canon.Count) stations"
$canon | Export-Csv "$dbdir\_extra_stations.csv" -NoTypeInformation
$dbSL | Export-Csv "$dbdir\_extra_station_lines.csv" -NoTypeInformation
$dbSegs | Export-Csv "$dbdir\_extra_segments.csv" -NoTypeInformation
$dbLines | Export-Csv "$dbdir\_extra_lines.csv" -NoTypeInformation
"wrote _extra DB tables: $($dbLines.Count) lines / $($dbStations.Count) stations / $($dbSegs.Count) segments"
