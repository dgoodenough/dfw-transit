param(
  [string]$Origin = "Bowie",
  [string]$Dest   = "Mesquite",
  [int]$Year      = 2070
)
$ErrorActionPreference="Stop"
# TRIP PLANNER / SANITY-CHECK LAYER
# Reuses the unified DB as a line-aware time graph and reconstructs a readable itinerary
# (walk -> board -> ride -> transfer -> ... -> walk) with a total door-to-door estimate.
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2); return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }

# ---- model constants ----
# spacing-dependent: segment time = len/cruise*60 + per-stop penalty. Effective avg speed rises with stop spacing.
$cruise=@{metro=63.0;brt=38.0;commuter=72.0}    # km/h between-stop cruise
$tstop =@{metro=1.2; brt=0.9; commuter=1.4}     # min lost per stop (dwell + accel/decel)
$wait =@{metro=5.0; brt=5.0; commuter=12.0}      # min: avg wait = headway/2 (commuter rail less frequent)
$WALK=4.8; $WALKMAX=1.6; $DRIVEMAX=10.0; $DRIVEKMH=40.0; $XFER_FRICTION=2.0

$stations=Import-Csv "$dbdir\stations.csv" | Where-Object {[int]$_.year_opens -le $Year}
$stById=@{}; foreach($s in $stations){ $stById[$s.station_id]=$s }
$segs=Import-Csv "$dbdir\segments.csv"

# ---- build graph: platform nodes (P:id) + per-line nodes (L:id|line) ----
$adj=@{}
function AddEdge($a,$b,$w,$kind){ if(-not $adj.ContainsKey($a)){$adj[$a]=New-Object System.Collections.Generic.List[object]}; [void]$adj[$a].Add(@{to=$b;w=$w;kind=$kind}) }
$plat=@{}  # station_id -> $true (platform exists)
foreach($s in $segs){
  $lns=$s.line -split ';'; $yrs=$s.year_opens -split ';'; $mode=$s.mode
  if(-not $stById.ContainsKey($s.from_id) -or -not $stById.ContainsKey($s.to_id)){continue}
  # segment length
  $inner=$s.geometry_wkt -replace '^LINESTRING \(','' -replace '\)$',''
  $pc=@(); foreach($p in ($inner -split ',')){ $xy=$p.Trim() -split '\s+'; $pc+=,@([double]$xy[0],[double]$xy[1]) }
  $len=0.0; for($i=1;$i -lt $pc.Count;$i++){ $len+=(Hav $pc[$i-1][1] $pc[$i-1][0] $pc[$i][1] $pc[$i][0]) }
  $vc=$cruise[$mode]; if(-not $vc){$vc=45.0}; $ts=$tstop[$mode]; if(-not $ts){$ts=1.0}
  for($k=0;$k -lt $lns.Count;$k++){
    $y=[int]$yrs[[math]::Min($k,$yrs.Count-1)]; if($y -gt $Year){continue}
    $ln=$lns[$k]
    $fa="L:$($s.from_id)|$ln"; $fb="L:$($s.to_id)|$ln"
    $t=$len/$vc*60.0+$ts
    AddEdge $fa $fb $t 'ride'; AddEdge $fb $fa $t 'ride'
    # board/alight to platform
    $w=$wait[$mode]; if(-not $w){$w=6.0}
    foreach($e in @(@($s.from_id,$fa),@($s.to_id,$fb))){
      AddEdge "P:$($e[0])" $e[1] $w 'board'
      AddEdge $e[1] "P:$($e[0])" 0.0 'alight'
      $plat[$e[0]]=$true
    }
  }
}
# transfer walks between distinct nearby platforms (<=400m) not already merged
$ppids=@($plat.Keys)
for($i=0;$i -lt $ppids.Count;$i++){ for($j=$i+1;$j -lt $ppids.Count;$j++){
  $a=$stById[$ppids[$i]];$b=$stById[$ppids[$j]]
  if([math]::Abs([double]$a.lat-[double]$b.lat) -gt 0.005 -or [math]::Abs([double]$a.lon-[double]$b.lon) -gt 0.006){continue}
  $d=(Hav ([double]$a.lat) ([double]$a.lon) ([double]$b.lat) ([double]$b.lon))
  if($d*1000 -le 400){ $tw=$d/$WALK*60+$XFER_FRICTION; AddEdge "P:$($ppids[$i])" "P:$($ppids[$j])" $tw 'xferwalk'; AddEdge "P:$($ppids[$j])" "P:$($ppids[$i])" $tw 'xferwalk' } } }

# ---- resolve origin/dest to a point ----
function Resolve($q){
  if($q -match '^\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*$'){ return @{name=$q;lat=[double]$Matches[1];lon=[double]$Matches[2]} }
  $m=$stations | Where-Object {$_.name -eq $q} | Select-Object -First 1
  if(-not $m){ $m=$stations | Where-Object {$_.name -like "*$q*"} | Select-Object -First 1 }
  if($m){ return @{name=$m.name;lat=[double]$m.lat;lon=[double]$m.lon} }
  if(Test-Path "$ddir\dfw_poi.json"){ foreach($e in ((Get-Content "$ddir\dfw_poi.json" -Raw|ConvertFrom-Json).elements)){ if($e.tags.place -and $e.tags.name -eq $q -and $e.lat){ return @{name=$e.tags.name;lat=[double]$e.lat;lon=[double]$e.lon} } } }
  throw "Could not resolve '$q' to a station or town."
}
$O=Resolve $Origin; $D=Resolve $Dest
# access edges: walk <=1.6km else drive (P&R) <=10km, to all reachable platforms
function Access($point,$nodeName,$toward){
  $any=$false; $best=1e9
  foreach($ppid in $ppids){ $s=$stById[$ppid]
    $d=(Hav $point.lat $point.lon ([double]$s.lat) ([double]$s.lon)); if($d -lt $best){$best=$d}
    if($d -le $WALKMAX){ $t=$d/$WALK*60; if($toward){AddEdge $nodeName "P:$ppid" $t 'walk'}else{AddEdge "P:$ppid" $nodeName $t 'walk'}; $any=$true } }
  if(-not $any){ foreach($ppid in $ppids){ $s=$stById[$ppid]
    $d=(Hav $point.lat $point.lon ([double]$s.lat) ([double]$s.lon))
    if($d -le $DRIVEMAX){ $t=$d*1.3/$DRIVEKMH*60+3; if($toward){AddEdge $nodeName "P:$ppid" $t 'drive'}else{AddEdge "P:$ppid" $nodeName $t 'drive'}; $any=$true } } }
  return @($any,$best)
}
$ao=Access $O 'ORIG' $true; $ad=Access $D 'DEST' $false
if(-not $ao[0]){ throw "No station within $DRIVEMAX km of origin '$($O.name)' (nearest $([math]::Round($ao[1],1)) km)." }
if(-not $ad[0]){ throw "No station within $DRIVEMAX km of dest '$($D.name)' (nearest $([math]::Round($ad[1],1)) km)." }

# ---- Dijkstra ORIG -> DEST ----
$dist=@{}; $prev=@{}; $prevKind=@{}; $done=@{}
$dist['ORIG']=0.0
$pq=New-Object System.Collections.Generic.List[string]; [void]$pq.Add('ORIG')
while($pq.Count -gt 0){
  $bi=0;$bd=1e18; for($i=0;$i -lt $pq.Count;$i++){ if($dist[$pq[$i]] -lt $bd){$bd=$dist[$pq[$i]];$bi=$i} }
  $u=$pq[$bi]; $pq.RemoveAt($bi)
  if($done.ContainsKey($u)){continue}; $done[$u]=$true
  if($u -eq 'DEST'){break}
  if(-not $adj.ContainsKey($u)){continue}
  foreach($e in $adj[$u]){ $v=$e.to; $nd=$dist[$u]+$e.w
    if(-not $dist.ContainsKey($v) -or $nd -lt $dist[$v]){ $dist[$v]=$nd;$prev[$v]=$u;$prevKind[$v]=$e.kind; if(-not $done.ContainsKey($v)){[void]$pq.Add($v)} } } }

if(-not $dist.ContainsKey('DEST')){
  "`nNO ROUTE from $($O.name) to $($D.name) by $Year."
  $reached=@($dist.Keys | Where-Object {$_ -like 'P:*'})
  "  reachable platforms from origin: $($reached.Count) of $($plat.Count)"
  $best=1e9;$bn=$null
  foreach($k in $reached){ $sid=$k.Substring(2); $s=$stById[$sid]; if(-not $s){continue}
    $dd=(Hav $D.lat $D.lon ([double]$s.lat) ([double]$s.lon)); if($dd -lt $best){$best=$dd;$bn=$s.name} }
  "  closest the origin-reachable network gets to $($D.name): $bn ($([math]::Round($best,1)) km short)"
  "  reachable set: " + (($reached | ForEach-Object { $stById[$_.Substring(2)].name } | Sort-Object -Unique) -join ', ')
  return
}
# ---- reconstruct ----
$path=@(); $cur='DEST'; while($cur){ $path=,$cur+$path; if($cur -eq 'ORIG'){break}; $cur=$prev[$cur] }
function NodeStation($n){ if($n -like 'P:*'){return $n.Substring(2)}; if($n -like 'L:*'){return ($n.Substring(2) -split '\|')[0]}; return $null }
function NodeLine($n){ if($n -like 'L:*'){return ($n.Substring(2) -split '\|')[1]}; return $null }

"`n=== TRIP: $($O.name)  ->  $($D.name)   (network as of $Year) ==="
$legs=@()
$i=0
while($i -lt $path.Count-1){
  $a=$path[$i]; $b=$path[$i+1]; $kind=$prevKind[$b]
  if($kind -eq 'walk' -or $kind -eq 'drive'){
    $sid=if($a -eq 'ORIG'){NodeStation $b}else{NodeStation $a}
    $sn=if($sid){$stById[$sid].name}else{'?'}
    $verb=if($kind -eq 'drive'){'DRIVE (P&R)'}else{'WALK'}
    $to=if($a -eq 'ORIG'){"to $sn"}else{"to $($D.name)"}
    $legs+=[pscustomobject]@{leg=$verb;detail=$to;min=[math]::Round($dist[$b]-$dist[$a],1)}
    $i++; continue
  }
  if($kind -eq 'board'){
    # accumulate the ensuing ride(s) on this line
    $ln=NodeLine $b; $startSid=NodeStation $b; $boardMin=$dist[$b]-$dist[$a]
    $j=$i+1; $stops=0
    while($j -lt $path.Count-1 -and $prevKind[$path[$j+1]] -eq 'ride'){ $j++; $stops++ }
    $endSid=NodeStation $path[$j]
    $rideMin=$dist[$path[$j]]-$dist[$b]
    $mode=$stById[$startSid].mode
    $legs+=[pscustomobject]@{leg=("BOARD/"+$mode);detail=("${ln}: $($stById[$startSid].name) -> $($stById[$endSid].name), $stops stops");min=[math]::Round($boardMin+$rideMin,1)}
    $i=$j; continue
  }
  if($kind -eq 'xferwalk'){
    $legs+=[pscustomobject]@{leg='TRANSFER-WALK';detail=("$($stById[(NodeStation $a)].name) -> $($stById[(NodeStation $b)].name)");min=[math]::Round($dist[$b]-$dist[$a],1)}
    $i++; continue
  }
  $i++  # alight (0-cost, folded into next board's wait)
}
$legs | Format-Table @{l='Leg';e={$_.leg}},@{l='Detail';e={$_.detail}},@{l='Min';e={$_.min};a='right'} -AutoSize | Out-String -Width 100
$tot=$dist['DEST']
$nx=@($legs | Where-Object {$_.leg -like 'BOARD*'}).Count
$T=[math]::Round($tot); $hh=[math]::Floor($T/60); $mm=$T%60   # round total first so 60 rolls to next hour
"TOTAL: {0}{1} min   ({2} vehicle(s), {3} transfer(s))" -f $(if($hh){"$hh h "}else{""}),$mm,$nx,([math]::Max(0,$nx-1))
"Modeled door-to-door incl. walk + average waits. Straight-line distance {0} km." -f [math]::Round((Hav $O.lat $O.lon $D.lat $D.lon),1)