$ErrorActionPreference="Stop"
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"
$dbdir="$dir\db"
$kmlPath="C:\Users\justd\Downloads\FW_Subway_extracted\doc.kml"
[xml]$kml=Get-Content $kmlPath
$ns=New-Object System.Xml.XmlNamespaceManager($kml.NameTable);$ns.AddNamespace('k','http://www.opengis.net/kml/2.2')

# cores
$coreD=@(32.7767,-96.7970); $coreF=@(32.7555,-97.3308)
function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2)
  return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }
function CoreDist($lat,$lon){ [math]::Min((Hav $lat $lon $coreD[0] $coreD[1]),(Hav $lat $lon $coreF[0] $coreF[1])) }
function PhaseFor($med){ if($med -le 9){1}elseif($med -le 20){2}else{3} }
# naming pass
$renames=@(); foreach($r in (Import-Csv "$dir\data\renames.csv")){ $renames+=[pscustomobject]@{old=$r.old_name;lat=[double]$r.lat;lon=[double]$r.lon;new=$r.new_name} }
function Rename($nm,$lat,$lon){ foreach($r in $renames){ if($r.old -eq $nm -and [math]::Abs($r.lat-$lat) -lt 0.003 -and [math]::Abs($r.lon-$lon) -lt 0.003){ return $r.new } }; return $nm }

# mode colors
$cMetroDefault='#888'; $cCommuter='#5b6770'; $cBRT='#00838f'
# per-name metro color overrides for legibility (else use KMZ color)
$nameColor=@{}

$existCommuter=@('TRE','Texrail','A Train')
$skip=@('M Trolley Pt 1','M Line Part 2','M Line Pt 3','Dallas Streetcar','Also Red Line','Line 7','Line 9','Line 5','Line 8','Line 6')  # Line 6 cut per Session B (0.24 commutes/$M)

# real OSM geometry for existing services (overrides schematic KMZ geometry)
$eg=@{}; if(Test-Path "$dir\data\existing_geom.json"){ $ej=Get-Content "$dir\data\existing_geom.json" -Raw | ConvertFrom-Json; foreach($pp in $ej.PSObject.Properties){ $pts2=@(); foreach($c in $pp.Value){ $pts2+=,@([double]$c[0],[double]$c[1]) }; $eg[$pp.Name]=$pts2 } }
# metro ROW-snapped geometry fixes (Session B metro audit), then BRT road-graph routes (B2 - take precedence)
$rowFix=@{}
foreach($fxf in @("$dir\db\metro_row_fixes.geojson","$dir\db\brt_row_routes.geojson")){
  if(Test-Path $fxf){ foreach($ff in ((Get-Content $fxf -Raw | ConvertFrom-Json).features)){ $pts3=@(); foreach($c in $ff.geometry.coordinates){ $pts3+=,@([double]$c[0],[double]$c[1]) }; $rowFix[$ff.properties.name]=$pts3 } }
}
# per-line mode override (line_modes.csv, from the edit round-trip's Year/Mode folders) - extra lines only
$modeOv=@{}; if(Test-Path "$dir\data\line_modes.csv"){ foreach($r in (Import-Csv "$dir\data\line_modes.csv")){ if($r.line){ $modeOv[$r.line]=$r.mode } } }
# FW downtown convergence tails (inner terminus -> Fort Worth Central), appended to each FW commuter line
$fwConv=@{}; if(Test-Path "$dir\db\fw_convergence.geojson"){ foreach($ff in ((Get-Content "$dir\db\fw_convergence.geojson" -Raw | ConvertFrom-Json).features)){ $tp=@(); foreach($c in $ff.geometry.coordinates){ $tp+=,@([double]$c[0],[double]$c[1]) }; $fwConv[$ff.properties.name]=$tp } }
$lineFeat=@(); $reg=@(); $allLinePts=@()
$lid=0
foreach($folder in $kml.SelectNodes('//k:Folder',$ns)){
  $fname=$folder.SelectSingleNode('k:name',$ns).InnerText
  if($fname -eq 'Subway Lines'){ continue }  # FW metro: handled by clean DB
  foreach($pm in $folder.SelectNodes('k:Placemark',$ns)){
    $nm=$pm.SelectSingleNode('k:name',$ns).InnerText
    $ls=$pm.SelectSingleNode('k:LineString/k:coordinates',$ns)
    if(-not $ls){continue}
    if($skip -contains $nm){continue}
    $pts=@(); foreach($c in ($ls.InnerText.Trim() -split '\s+')){$a=$c -split ',';$pts+=,@([double]$a[0],[double]$a[1])}
    if($eg.ContainsKey($nm)){ $pts=$eg[$nm] }   # use real OSM track for existing services
    elseif($rowFix.ContainsKey($nm)){ $pts=$rowFix[$nm] }   # metro audit: corridor-snapped geometry
    if($pts.Count -lt 2){continue}
    # (FW downtown convergence tails applied centrally in build_stations, which sees all line sources)
    # degenerate loop check
    if(($pts[0][0] -eq $pts[-1][0]) -and ($pts[0][1] -eq $pts[-1][1]) -and $pts.Count -lt 6){continue}

    # classify mode
    $mode='metro'
    if($fname -eq 'Existing Transit'){ if($existCommuter -contains $nm){$mode='commuter'} else {$mode='metro'} }
    elseif($fname -eq 'Commuter Rail'){ $mode='commuter' }
    elseif($fname -like 'Proposed BRT*' -or $fname -like 'BRT from*'){ $mode='brt' }
    elseif($nm -eq 'Cotton Belt'){ $mode='metro' }   # DART Silver Line = solid DART line, not dashed commuter
    else { $mode='metro' }
    if($nm -eq 'Beltline Line'){ $mode='brt' }       # Session B: Beltline as BRT ($22B metro -> ~$3B BRT, ~2.1 commutes/$M)
    if($modeOv.ContainsKey($nm)){ $mode=$modeOv[$nm] }   # manual mode override (edit round-trip Year/Mode folders)

    # phase: existing rail -> 1; else distance band (median vertex dist to nearest core)
    $dists=@(); foreach($p in $pts){ $dists+=CoreDist $p[1] $p[0] }
    $sorted=$dists | Sort-Object; $med=$sorted[[int]([math]::Floor($sorted.Count/2))]
    $isExisting = ($fname -eq 'Existing Transit')
    $phase = if($isExisting){0} else { PhaseFor $med }   # 0 = already-existing systems (own scrubber step)
    if($nm -eq 'Cotton Belt'){ $phase=0 }   # DART Silver Line opened 2025 -> Existing (uses real OSM geom + stops)

    # color
    if($mode -eq 'commuter'){ $color=$cCommuter }
    elseif($mode -eq 'brt'){ $color=$cBRT }
    else {
      $su=$pm.SelectSingleNode('k:styleUrl',$ns).InnerText  # like #line-9C27B0-5069-nodesc
      if($su -match 'line-([0-9A-Fa-f]{6})'){ $hex='#'+$matches[1] } else { $hex=$cMetroDefault }
      if($hex -eq '#000000'){ $hex=$cMetroDefault }
      $color=$hex
    }
    if($nm -eq 'Cotton Belt'){ $color='#8c969e' }   # DART Silver Line silver/gray

    if($nm -eq 'No Idea'){ $nm='Arboretum Line' }   # placeholder name visible in map popups
    $lid++
    $lineId=('L{0:D2}' -f $lid)
    $coords=($pts | ForEach-Object { '['+$_[0]+','+$_[1]+']' }) -join ','
    $lineFeat+='{"type":"Feature","properties":{"id":"'+$lineId+'","name":"'+($nm -replace '"','\"')+'","kind":"line","mode":"'+$mode+'","phase":'+$phase+',"color":"'+$color+'","folder":"'+($fname -replace '"','\"')+'"},"geometry":{"type":"LineString","coordinates":['+$coords+']}}'
    $reg+=[pscustomobject]@{line_id=$lineId;name=$nm;mode=$mode;phase=$phase;color=$color;folder=$fname;npts=$pts.Count;median_km=[math]::Round($med,1)}
    foreach($p in $pts){ $allLinePts+=[pscustomobject]@{id=$lineId;mode=$mode;phase=$phase;color=$color;lon=$p[0];lat=$p[1]} }
  }
}

# ---- stations: snap the candidate "in between" pins to nearest extra line ----
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.8*[math]::PI/180)
$cands=Import-Csv "C:\Users\justd\Downloads\FW_stations.csv" -ErrorAction SilentlyContinue
if(-not $cands){ $cands=Import-Csv "C:\Users\justd\Downloads\FW_stations.csv" }
$cands = Import-Csv "C:\Users\justd\Downloads\FW_stations.csv" | Where-Object {$_.Folder -like 'Stops and potential stops in between*'}
$stFeat=@()
$THRESH=1000.0   # widened to pull in more of the marked destination pins
foreach($cp in $cands){
  $clon=[double]$cp.Lon;$clat=[double]$cp.Lat;$cpx=$clon*$mlon;$cpy=$clat*$mlat
  $best=1e9;$bl=$null
  foreach($lp in $allLinePts){
    $d=[math]::Sqrt([math]::Pow($cpx-$lp.lon*$mlon,2)+[math]::Pow($cpy-$lp.lat*$mlat,2))
    if($d -lt $best){$best=$d;$bl=$lp}
  }
  if($best -lt $THRESH -and $bl){
    $nm=Rename $cp.Name $clat $clon
    $stFeat+='{"type":"Feature","properties":{"name":"'+($nm -replace '"','\"')+'","kind":"stop","mode":"'+$bl.mode+'","phase":'+$bl.phase+',"color":"'+$bl.color+'"},"geometry":{"type":"Point","coordinates":['+$clon+','+$clat+']}}'
  }
}

# ---- FW crosstown BRT loop (planning sheet: Parts 1-4, along 183 N / east side / Berry St S / west side) ----
$loop=@(@(-97.4386,32.7421),@(-97.3850,32.7660),@(-97.2645,32.8029),@(-97.2212,32.7945),@(-97.2261,32.7638),@(-97.2181,32.7325),@(-97.2380,32.7085),@(-97.3043,32.7059),@(-97.3317,32.7059),@(-97.3866,32.7111),@(-97.4154,32.6990),@(-97.4163,32.7283),@(-97.4386,32.7421))
if($rowFix.ContainsKey('FW Crosstown Loop')){ $loop=$rowFix['FW Crosstown Loop'] }   # B2 road-routed
$loopCoords=($loop | ForEach-Object { '['+$_[0]+','+$_[1]+']' }) -join ','
$lineFeat+='{"type":"Feature","properties":{"id":"BRTLOOP","name":"FW Crosstown Loop","kind":"line","mode":"brt","phase":2,"color":"#00838f","folder":"FW BRT Loop"},"geometry":{"type":"LineString","coordinates":['+$loopCoords+']}}'
foreach($s in @(@('NW Loop 820/183',-97.3850,32.7660),@('Riverbend',-97.2212,32.7945))){ $stFeat+='{"type":"Feature","properties":{"name":"'+$s[0]+'","kind":"stop","mode":"brt","phase":2,"color":"#00838f"},"geometry":{"type":"Point","coordinates":['+$s[1]+','+$s[2]+']}}' }
$reg+=[pscustomobject]@{line_id='BRTLOOP';name='FW Crosstown Loop';mode='brt';phase=2;color='#00838f';folder='FW BRT Loop';npts=$loop.Count;median_km=0}

# ---- Session B new lines (from demand-engine missing-corridor scan) ----
# N1 Collin Commuter: Plano Parker Rd (DART Red) -> Allen -> McKinney, ex-H&TC ROW (DART-owned)
$n1=@(@(-96.7090,33.0518),@(-96.6936,33.0772),@(-96.6706,33.1031),@(-96.6398,33.1532),@(-96.6155,33.1976))
# N2 Legacy Line: Frisco (DNT-East) -> Legacy West -> Plano Parker Rd (Red Line)
$n2=@(@(-96.8236,33.1507),@(-96.8228,33.0986),@(-96.8222,33.0777),@(-96.7905,33.0660),@(-96.7521,33.0560),@(-96.7090,33.0518))
# (N3 Cedar Hill replaced by ROW-routed Midlothian->Westmoreland line: data/route_midlothian.ps1 -> db/midlothian_ext.geojson)
# N4 Ross Avenue BRT: Medical District -> Maple -> Uptown -> Ross Ave -> Lakewood (intra-Dallas E-W gap, ~5.8k unserved)
$n4=@(@(-96.8390,32.8095),@(-96.8260,32.8030),@(-96.8160,32.7980),@(-96.8030,32.7950),@(-96.7975,32.7895),@(-96.7860,32.7950),@(-96.7780,32.8000),@(-96.7700,32.8055),@(-96.7600,32.8090),@(-96.7490,32.8125))
# N5 Forest Lane BRT: Marsh Ln -> Preston -> Forest Ln Stn (Red) -> Lake Highlands -> LBJ/Skillman (Blue)
$n5=@(@(-96.8568,32.9092),@(-96.8350,32.9090),@(-96.8120,32.9090),@(-96.7950,32.9089),@(-96.7780,32.9091),@(-96.7616,32.9095),@(-96.7480,32.9090),@(-96.7350,32.9080),@(-96.7200,32.9065),@(-96.7062,32.9056))
# N6 Jefferson Blvd BRT: Union Station -> Jefferson Viaduct -> Bishop Arts -> Jefferson Blvd -> Cockrell Hill
$n6=@(@(-96.8077,32.7768),@(-96.8120,32.7660),@(-96.8266,32.7448),@(-96.8420,32.7437),@(-96.8530,32.7436),@(-96.8660,32.7437),@(-96.8800,32.7438),@(-96.8910,32.7437))
$newLines=@(
 @{id='N1';n='Collin Commuter';m='commuter';c='#5b6770';v=$n1},
 @{id='N2';n='Legacy Line';m='metro';c='#0d8a4f';v=$n2},
 @{id='N4';n='Ross Avenue BRT';m='brt';c='#00838f';v=$n4},
 @{id='N5';n='Forest Lane BRT';m='brt';c='#00838f';v=$n5},
 @{id='N6';n='Jefferson Blvd BRT';m='brt';c='#00838f';v=$n6})
foreach($NL in $newLines){
  if($rowFix.ContainsKey($NL.n)){ $NL.v=$rowFix[$NL.n] }   # Legacy Line snapped
  $nmode= if($modeOv.ContainsKey($NL.n)){$modeOv[$NL.n]}else{$NL.m}   # manual mode override
  $cj=($NL.v | ForEach-Object { '['+$_[0]+','+$_[1]+']' }) -join ','
  $lineFeat+='{"type":"Feature","properties":{"id":"'+$NL.id+'","name":"'+$NL.n+'","kind":"line","mode":"'+$nmode+'","phase":2,"color":"'+$NL.c+'","folder":"Session B new"},"geometry":{"type":"LineString","coordinates":['+$cj+']}}'
  $reg+=[pscustomobject]@{line_id=$NL.id;name=$NL.n;mode=$nmode;phase=2;color=$NL.c;folder='Session B new';npts=$NL.v.Count;median_km=0}
}

$gj='{"type":"FeatureCollection","features":['+(($lineFeat+$stFeat) -join ',')+']}'
Set-Content "$dbdir\network_extra.geojson" $gj -Encoding utf8
$reg | Sort-Object mode,phase,name | Export-Csv "$dbdir\lines_extra.csv" -NoTypeInformation

"== EXTRA NETWORK BUILT =="
"lines: $($reg.Count)  (metro=$(($reg|? mode -eq metro).Count) commuter=$(($reg|? mode -eq commuter).Count) brt=$(($reg|? mode -eq brt).Count))"
"snapped stations: $($stFeat.Count)"
"by phase: P1=$(($reg|? phase -eq 1).Count) P2=$(($reg|? phase -eq 2).Count) P3=$(($reg|? phase -eq 3).Count)"