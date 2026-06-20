$ErrorActionPreference="Stop"
$dir=(Split-Path $PSScriptRoot -Parent)
$ddir="$dir\data"
$dbdir="$dir\db"; New-Item -ItemType Directory -Force $dbdir | Out-Null
# hand-edits round-trip: FW core lines exported as "<Line> (core)"; load any overrides
$fwManual=@{}
if(Test-Path "$dbdir\manual_geom.geojson"){ foreach($ff in ((Get-Content "$dbdir\manual_geom.geojson" -Raw|ConvertFrom-Json).features)){ if(-not $ff.geometry){continue}; $cc=@(); foreach($c in $ff.geometry.coordinates){ $cc+=,@([double]$c[0],[double]$c[1]) }; $fwManual[$ff.properties.name]=$cc } }
$kmlPath="C:\Users\justd\Downloads\FW_Subway_extracted\doc.kml"
[xml]$kml=Get-Content $kmlPath
$ns=New-Object System.Xml.XmlNamespaceManager($kml.NameTable);$ns.AddNamespace('k','http://www.opengis.net/kml/2.2')

# ---- geometry helpers (same as builder) ----
function AllLines($name){ $out=@(); foreach($pm in $kml.SelectNodes('//k:Placemark',$ns)){ if($pm.SelectSingleNode('k:name',$ns).InnerText -eq $name){ $ls=$pm.SelectSingleNode('k:LineString/k:coordinates',$ns); if($ls){ $pts=@(); foreach($c in ($ls.InnerText.Trim() -split '\s+')){$a=$c -split ',';$pts+=,@([double]$a[0],[double]$a[1])}; $out+=,$pts } } }; return ,$out }
function PickFW($name){ foreach($c in (AllLines $name)){ if($c[0][0] -lt -97.2){return ,$c} }; return ,((AllLines $name)[0]) }
function PickShort($name){ ,((AllLines $name) | Sort-Object {$_.Count})[0] }
function NearestIdx($line,$lon,$lat){ $b=0;$bd=1e9; for($i=0;$i -lt $line.Count;$i++){ $d=[math]::Pow($line[$i][0]-$lon,2)+[math]::Pow($line[$i][1]-$lat,2); if($d -lt $bd){$bd=$d;$b=$i} }; return $b }
function Slice($line,$a,$b){ $o=@(); for($i=$a;$i -le $b;$i++){ $o+=,$line[$i] }; return ,$o }
function Concat(){ $o=@(); foreach($seg in $args){ foreach($p in $seg){ $o+=,$p } }; return ,$o }
function Tag($seg,$ph){ $o=@(); foreach($p in $seg){ $o+=,@($p[0],$p[1],$ph) }; return ,$o }

# ---- rebuild cleaned geometry pieces ----
$main=PickFW 'Main St Line'; $green=PickFW 'Green Line'; $blue=PickFW 'Blue Line'
$main[0]=@(-97.3490,32.8130)  # snap north terminus to relocated Meacham/Mercado N stop
# Orange south leg - cleaned to pass through the Magnolia stops (raw KMZ ran ~350m north of them)
$orangeS=@(@(-97.3267,32.7380),@(-97.3283,32.7352),@(-97.3316,32.7307),@(-97.3394,32.7307),@(-97.3457,32.7298),@(-97.3613,32.7292),@(-97.3776,32.7220),@(-97.3866,32.7111),@(-97.3960,32.7088),@(-97.4154,32.6990))
$iSMain=NearestIdx $main -97.3259 32.7418; $orange1=Concat (Slice $main 0 $iSMain) $orangeS
$iDt=NearestIdx $green -97.333 32.7571; $tealWest=Slice $green $iDt ($green.Count-1)
$tealEastNew=@(@(-97.2645,32.8029),@(-97.2700,32.7740),@(-97.3060,32.7731),@(-97.3285,32.7618))
$teal1=Concat $tealEastNew $tealWest
$iCentral=NearestIdx $blue -97.3267 32.7525; $blue1=Slice $blue 0 $iCentral
$blueWestExt=Concat (Slice $blue $iCentral ($blue.Count-1)) (PickFW 'blue line ctd') (PickFW 'Western Hills Ext')
$silver=@(@(-97.4298,32.8122),@(-97.4080,32.7985),@(-97.3857,32.7836),@(-97.3640,32.7670),@(-97.3370,32.7550),@(-97.3345,32.7350),@(-97.3325,32.7150),@(-97.3317,32.7059),@(-97.3043,32.7059),@(-97.2852,32.7124),@(-97.2600,32.7095),@(-97.2380,32.7085))
$red=@(@(-97.4678,32.6753),@(-97.4400,32.6885),@(-97.4154,32.6990),@(-97.3960,32.7088),@(-97.3866,32.7111),@(-97.3720,32.7210),@(-97.3613,32.7292),@(-97.3628,32.7390),@(-97.3646,32.7472))
$purpleTCU=@(@(-97.3267,32.7525),@(-97.3316,32.7307),@(-97.3457,32.7298),@(-97.3604,32.7096),@(-97.3604,32.6991))
$orangeHulen=Concat (PickFW 'Hulen Ext') (,@(-97.4130,32.6380))  # extend to Altamesa terminus
$magentaEverman=@(@(-97.3245,32.6863),@(-97.3100,32.6600),@(-97.2950,32.6330))
$tealWood=@(@(-97.2700,32.7740),@(-97.2450,32.7700),@(-97.2261,32.7638))

# ---- 7 full lines, each = list of phase-tagged polylines ----
function Polys{ $a=@(); foreach($p in $args){ $a+=,$p }; return ,$a }
$LINEDEF=[ordered]@{
 Teal   = Polys (Tag $teal1 1) (Tag $tealWood 3)
 Blue   = Polys (Concat (Tag $blue1 1) (Tag $blueWestExt 2))
 Orange = Polys (Concat (Tag $orange1 1) (Tag $orangeHulen 3))
 Pink   = Polys (Concat (Tag $main 1) (Tag $magentaEverman 3))
 Silver = Polys (Tag $silver 2)
 Red    = Polys (Tag $red 2)
 Purple = Polys (Tag $purpleTCU 3)
}

# FW core hand-edit round-trip: apply manual_geom overrides (keyed "<Line> (core)") + dump editable source.
# (years come from line_years.csv via build_db_full, so a single phase tag is fine for edited geometry.)
$fwCol=@{Teal='#00b251';Blue='#0896d7';Orange='#df8600';Pink='#d63384';Silver='#9aa0a6';Red='#bd1038';Purple='#7b2d8e'}
$fwSrc=@()
foreach($lname in @($LINEDEF.Keys)){
  # apply hand-edit overrides: branch j exports as "<Line> (core)" (j=1) / "<Line> (core) <j>" (j>=2)
  $mp=@()
  if($fwManual.ContainsKey("$lname (core)")){ $mp+=,$fwManual["$lname (core)"] }
  $j=2; while($fwManual.ContainsKey("$lname (core) $j")){ $mp+=,$fwManual["$lname (core) $j"]; $j++ }
  if($mp.Count -gt 0){ $pl=@(); foreach($poly in $mp){ $pl+=,(Tag $poly 1) }; $LINEDEF[$lname]=$pl }
  # dump one feature per polyline (preserves branches)
  $pj=0
  foreach($poly in $LINEDEF[$lname]){ $pj++
    $nm= if($pj -eq 1){"$lname (core)"}else{"$lname (core) $pj"}
    $c=($poly | ForEach-Object {'['+[math]::Round($_[0],6)+','+[math]::Round($_[1],6)+']'}) -join ','
    $fwSrc+='{"type":"Feature","properties":{"name":"'+$nm+'","mode":"metro","color":"'+$fwCol[$lname]+'"},"geometry":{"type":"LineString","coordinates":['+$c+']}}'
  }
}
Set-Content "$dbdir\fw_lines_source.geojson" ('{"type":"FeatureCollection","features":['+($fwSrc -join ',')+']}') -Encoding utf8

# ---- master station list (from cleaned STOPS set) ----
$colByHex=@{'880E4F'='Pink';'C2185B'='Pink';'097138'='Teal';'01579B'='Blue';'F57C00'='Orange'}
$drop=@('A Stop','Riverbend','NRH2YIMBY','TCU E','BRT','BRT/ Subway','NAS JRB','The L Word','Berry/Stalcup','Berry/Riverside','Renaissance Square','Fair Oaks','Lake Worth','TCU','Bluebonnet Circle','Woodhaven')
$reloc=@{'Meacham Airport'=@(-97.3490,32.8130,'Meacham / Mercado N');'My Lan (My Favorites)'=@(-97.2700,32.7740,'Riverside / Race St')}
$raw=@()
foreach($s in (Import-Csv "C:\Users\justd\Downloads\FW_stations.csv" | Where-Object {$_.Folder -like 'Stops and Potential*Fort worth'})){
  $hex=($s.Style -split '-')[2]; if(-not $colByHex.ContainsKey($hex)){continue}; if($drop -contains $s.Name){continue}
  $lon=[double]$s.Lon;$lat=[double]$s.Lat;$nm=$s.Name
  if($reloc.ContainsKey($s.Name)){$lon=$reloc[$s.Name][0];$lat=$reloc[$s.Name][1];$nm=$reloc[$s.Name][2]}
  $raw+=@{N=$nm;Lon=$lon;Lat=$lat}
}
$extra=@(
 @{N='Lake Worth';Lon=-97.4298;Lat=32.8122},@{N='Fair Oaks';Lon=-97.3857;Lat=32.7836},
 @{N='Berry / Riverside';Lon=-97.3043;Lat=32.7059},@{N='Renaissance Sq';Lon=-97.2852;Lat=32.7124},
 @{N='Berry / Stalcup';Lon=-97.2380;Lat=32.7085},@{N='Benbrook';Lon=-97.4678;Lat=32.6753},
 @{N='TCU';Lon=-97.3604;Lat=32.7096},@{N='Bluebonnet Circle';Lon=-97.3604;Lat=32.6991},
 @{N='Hulen Mall';Lon=-97.4161;Lat=32.6455},@{N='Altamesa';Lon=-97.4130;Lat=32.6380},
 @{N='Woodhaven';Lon=-97.2261;Lat=32.7638},@{N='Everman';Lon=-97.2950;Lat=32.6330}
)
$raw+=$extra
# assign ids
$stations=@(); $i=0
foreach($r in $raw){ $i++; $stations+=[pscustomobject]@{id=('S{0:D3}' -f $i);name=$r.N;lat=[math]::Round($r.Lat,6);lon=[math]::Round($r.Lon,6)} }

# ---- planar projection (meters) for snapping ----
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.75*[math]::PI/180)
function MX($lon){ $lon*$mlon }; function MY($lat){ $lat*$mlat }
function SegDistAlong($px,$py,$ax,$ay,$bx,$by){
  $dx=$bx-$ax;$dy=$by-$ay;$L2=$dx*$dx+$dy*$dy
  $t= if($L2 -le 0){0}else{ (($px-$ax)*$dx+($py-$ay)*$dy)/$L2 }
  if($t -lt 0){$t=0}elseif($t -gt 1){$t=1}
  $cx=$ax+$t*$dx;$cy=$ay+$t*$dy
  $d=[math]::Sqrt([math]::Pow($px-$cx,2)+[math]::Pow($py-$cy,2))
  return @($d,$t)
}
$THRESH=230.0  # meters

# ---- snap stations to each line polyline; build station_lines + segments ----
$stationLines=@()   # station_id, line, seq, phase
$segMap=@{}         # key "idA|idB" (sorted) -> @{lines=set; phase; geom=[[lon,lat]...]; from;to}
function StById($id){ $stations | Where-Object {$_.id -eq $id} | Select-Object -First 1 }

foreach($lname in $LINEDEF.Keys){
  $pIdx=0
  foreach($poly in $LINEDEF[$lname]){
    $pIdx++
    # precompute meter coords + cumulative length
    $mx=@();$my=@();$cum=@(0.0)
    for($k=0;$k -lt $poly.Count;$k++){ $mx+=MX $poly[$k][0]; $my+=MY $poly[$k][1] }
    for($k=1;$k -lt $poly.Count;$k++){ $cum+=$cum[$k-1]+[math]::Sqrt([math]::Pow($mx[$k]-$mx[$k-1],2)+[math]::Pow($my[$k]-$my[$k-1],2)) }
    # match stations
    $hits=@()
    foreach($st in $stations){
      $spx=MX $st.lon;$spy=MY $st.lat;$best=1e9;$bi=0;$bt=0
      for($k=0;$k -lt $poly.Count-1;$k++){ $r=SegDistAlong $spx $spy $mx[$k] $my[$k] $mx[$k+1] $my[$k+1]; if($r[0] -lt $best){$best=$r[0];$bi=$k;$bt=$r[1]} }
      if($best -lt $THRESH){
        $along=$cum[$bi]+$bt*([math]::Sqrt([math]::Pow($mx[$bi+1]-$mx[$bi],2)+[math]::Pow($my[$bi+1]-$my[$bi],2)))
        $ph=$poly[$bi][2]
        $hits+=[pscustomobject]@{id=$st.id;along=$along;segidx=$bi;t=$bt;phase=$ph}
      }
    }
    $hits=$hits | Sort-Object along
    # station_lines (seq within this polyline)
    $seq=0
    foreach($h in $hits){ $seq++; $stationLines+=[pscustomobject]@{station_id=$h.id;line=$lname;seq=$seq;phase=$h.phase;branch=$pIdx} }
    # segments between consecutive hits
    for($n=0;$n -lt $hits.Count-1;$n++){
      $A=$hits[$n];$B=$hits[$n+1]
      $sa=StById $A.id;$sb=StById $B.id
      # geometry: A coord + intermediate vertices (A.segidx+1 .. B.segidx) + B coord
      $g0=@(); $g0+=,@($sa.lon,$sa.lat)
      for($k=$A.segidx+1;$k -le $B.segidx;$k++){ $g0+=,@([math]::Round($poly[$k][0],6),[math]::Round($poly[$k][1],6)) }
      $g0+=,@($sb.lon,$sb.lat)
      $g=@(); foreach($pt in $g0){ if($g.Count -eq 0 -or $g[-1][0] -ne $pt[0] -or $g[-1][1] -ne $pt[1]){ $g+=,$pt } }
      $key= if($A.id -le $B.id){"$($A.id)|$($B.id)"}else{"$($B.id)|$($A.id)"}
      $segPhase=[math]::Max($A.phase,$B.phase)
      if($segMap.ContainsKey($key)){
        $segMap[$key].lines[$lname]=$true
        if($segPhase -lt $segMap[$key].phase){$segMap[$key].phase=$segPhase}
      } else {
        $segMap[$key]=@{from=$A.id;to=$B.id;lines=@{$lname=$true};phase=$segPhase;geom=$g}
      }
    }
  }
}

# ---- station summary: lines + phase_opened ----
$linesByStation=@{}; $phaseByStation=@{}
foreach($sl in $stationLines){
  if(-not $linesByStation.ContainsKey($sl.station_id)){$linesByStation[$sl.station_id]=@{}}
  $linesByStation[$sl.station_id][$sl.line]=$true
  if(-not $phaseByStation.ContainsKey($sl.station_id) -or $sl.phase -lt $phaseByStation[$sl.station_id]){$phaseByStation[$sl.station_id]=$sl.phase}
}
$lineOrder=@('Teal','Blue','Orange','Pink','Silver','Red','Purple')
$stationsOut=@()
foreach($st in $stations){
  $ls= if($linesByStation.ContainsKey($st.id)){ ($lineOrder | Where-Object {$linesByStation[$st.id].ContainsKey($_)}) -join ';' } else {''}
  $nl= if($linesByStation.ContainsKey($st.id)){$linesByStation[$st.id].Count}else{0}
  $po= if($phaseByStation.ContainsKey($st.id)){$phaseByStation[$st.id]}else{''}
  $stationsOut+=[pscustomobject]@{station_id=$st.id;name=$st.name;lat=$st.lat;lon=$st.lon;phase_opened=$po;num_lines=$nl;is_interchange=([int]($nl -ge 2));lines=$ls}
}

# ---- write CSVs ----
$stationsOut | Sort-Object station_id | Export-Csv "$dbdir\fw_stations.csv" -NoTypeInformation
$slOut=@()
foreach($sl in ($stationLines | Sort-Object line,seq)){ $nm=(StById $sl.station_id).name; $slOut+=[pscustomobject]@{line=$sl.line;seq=$sl.seq;station_id=$sl.station_id;station_name=$nm;phase=$sl.phase;branch=$sl.branch} }
$slOut | Export-Csv "$dbdir\fw_station_lines.csv" -NoTypeInformation
$segOut=@(); $sid=0
foreach($key in ($segMap.Keys | Sort-Object)){ $sid++; $v=$segMap[$key]
  $wkt='LINESTRING (' + (($v.geom | ForEach-Object { "$($_[0]) $($_[1])" }) -join ', ') + ')'
  $lns=($lineOrder | Where-Object {$v.lines.ContainsKey($_)}) -join ';'
  $segOut+=[pscustomobject]@{segment_id=('SEG{0:D3}' -f $sid);from_id=$v.from;from_name=(StById $v.from).name;to_id=$v.to;to_name=(StById $v.to).name;lines=$lns;num_lines=$v.lines.Count;phase=$v.phase;geometry_wkt=$wkt}
}
$segOut | Export-Csv "$dbdir\fw_segments.csv" -NoTypeInformation

# ---- GeoJSON exports from the DB: stations / segments / combined network ----
$col=@{Teal='#00b251';Blue='#0896d7';Orange='#df8600';Pink='#d63384';Silver='#9aa0a6';Red='#bd1038';Purple='#7b2d8e'}
$segFeat=@()
foreach($key in ($segMap.Keys | Sort-Object)){ $v=$segMap[$key]
  $first=($lineOrder | Where-Object {$v.lines.ContainsKey($_)})[0]
  $coords=($v.geom | ForEach-Object { '['+$_[0]+','+$_[1]+']' }) -join ','
  $lns=($lineOrder | Where-Object {$v.lines.ContainsKey($_)}) -join ';'
  $segFeat+='{"type":"Feature","properties":{"from":"'+$v.from+'","to":"'+$v.to+'","lines":"'+$lns+'","num_lines":'+$v.lines.Count+',"phase":'+$v.phase+',"shared":'+([int]($v.lines.Count -ge 2))+',"stroke":"'+$col[$first]+'"},"geometry":{"type":"LineString","coordinates":['+$coords+']}}'
}
$stFeat=@()
foreach($st in $stationsOut){ $c= if($st.lines){$col[($st.lines -split ';')[0]]}else{'#666'}
  $stFeat+='{"type":"Feature","properties":{"station_id":"'+$st.station_id+'","name":"'+($st.name -replace '"','\"')+'","lines":"'+$st.lines+'","num_lines":'+$st.num_lines+',"is_interchange":'+$st.is_interchange+',"phase_opened":'+("$($st.phase_opened)")+',"marker-color":"'+$c+'"},"geometry":{"type":"Point","coordinates":['+$st.lon+','+$st.lat+']}}' }
function MakeGeo($features){ '{"type":"FeatureCollection","features":['+($features -join ',')+']}' }
Set-Content "$dbdir\stations.geojson" (MakeGeo $stFeat) -Encoding utf8
Set-Content "$dbdir\segments.geojson" (MakeGeo $segFeat) -Encoding utf8
Set-Content "$dbdir\network.geojson"  (MakeGeo ($segFeat+$stFeat)) -Encoding utf8
Set-Content "$dir\maps\FW_network.geojson" (MakeGeo ($segFeat+$stFeat)) -Encoding utf8  # convenient top-level copy

# ---- report ----
"== DB BUILT in db\ =="
"stations.csv      : $($stationsOut.Count) stations"
"station_lines.csv : $($slOut.Count) station-line memberships"
"segments.csv      : $($segOut.Count) segments ($(($segOut|Where-Object{$_.num_lines -ge 2}).Count) shared by 2+ lines)"
$un=$stationsOut | Where-Object {$_.num_lines -eq 0}
if($un){ "UNASSIGNED stations (no line within ${THRESH}m):"; $un | ForEach-Object { "  - $($_.name)" } } else { "all stations assigned to >=1 line" }
"interchanges (2+ lines): $(($stationsOut|Where-Object{$_.is_interchange -eq 1}).Count)"
