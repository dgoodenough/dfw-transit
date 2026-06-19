$ErrorActionPreference="Stop"
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"
function Dm($alon,$alat,$blon,$blat){ [math]::Sqrt([math]::Pow(($alon-$blon)*93680,2)+[math]::Pow(($alat-$blat)*110540,2)) }
$map=@{ 'Red Line'='Red Line';'Blue Line'='Blue Line';'Green Line'='Green Line';'Orange Line'='Orange Line';
        'DCTA A-Train'='A Train';'TEXRail'='Texrail';'Trinity Railway Express'='TRE';'TRE'='TRE';'Silver Line'='Cotton Belt' }

# node id -> {name,lat,lon} (real station nodes on the routes)
$nodeById=@{}
foreach($e in (Get-Content "$ddir\dfw_route_stops.json" -Raw | ConvertFrom-Json).elements){ if($e.id -and $e.lat){ $nodeById[[string]$e.id]=[pscustomobject]@{name=$e.tags.name;lat=[double]$e.lat;lon=[double]$e.lon} } }

$o=Get-Content "$ddir\dfw_routes.json" -Raw | ConvertFrom-Json
$best=@{}
foreach($rel in $o.elements){
  $nm=$rel.tags.name; if(-not $nm){continue}
  $key=($nm -split ':')[0].Trim(); if(-not $map.ContainsKey($key)){continue}
  $my=$map[$key]
  # collect track ways + stop refs
  $ways=@(); $stopRefs=@()
  foreach($m in $rel.members){
    if($m.type -eq 'node' -and $m.role -match 'stop'){ $stopRefs+=[string]$m.ref; continue }
    if($m.type -ne 'way' -or ($m.role -match 'stop|platform') -or -not $m.geometry){continue}
    $pts=@(); foreach($g in $m.geometry){ $pts+=,@([double]$g.lon,[double]$g.lat) }; if($pts.Count -ge 2){ $ways+=,$pts }
  }
  if($ways.Count -eq 0){continue}
  # greedy chaining from the longest way (ignores disconnected sidings/yards; avoids member-order backtracks)
  $n=$ways.Count; $used=New-Object 'bool[]' $n
  $si=0;$bl=0; for($i=0;$i -lt $n;$i++){ $L=0.0; for($j=1;$j -lt $ways[$i].Count;$j++){ $L+=Dm $ways[$i][$j-1][0] $ways[$i][$j-1][1] $ways[$i][$j][0] $ways[$i][$j][1] }; if($L -gt $bl){$bl=$L;$si=$i} }
  $chain=@(); foreach($p in $ways[$si]){ $chain+=,$p }; $used[$si]=$true
  $tol=150.0; $go=$true
  while($go){ $go=$false; $head=$chain[0]; $tail=$chain[-1]
    for($i=0;$i -lt $n;$i++){ if($used[$i]){continue}; $w=$ways[$i]; $ws=$w[0]; $we=$w[-1]
      if((Dm $tail[0] $tail[1] $ws[0] $ws[1]) -lt $tol){ for($j=1;$j -lt $w.Count;$j++){$chain+=,$w[$j]}; $used[$i]=$true;$go=$true;break }
      elseif((Dm $tail[0] $tail[1] $we[0] $we[1]) -lt $tol){ for($j=$w.Count-2;$j -ge 0;$j--){$chain+=,$w[$j]}; $used[$i]=$true;$go=$true;break }
      elseif((Dm $head[0] $head[1] $we[0] $we[1]) -lt $tol){ $nw=@(); for($j=0;$j -lt $w.Count-1;$j++){$nw+=,$w[$j]}; $chain=$nw+$chain; $used[$i]=$true;$go=$true;break }
      elseif((Dm $head[0] $head[1] $ws[0] $ws[1]) -lt $tol){ $nw=@(); for($j=$w.Count-1;$j -ge 1;$j--){$nw+=,$w[$j]}; $chain=$nw+$chain; $used[$i]=$true;$go=$true;break }
    }
  }
  $result=@(); foreach($p in $chain){ if($result.Count -eq 0 -or (Dm $result[-1][0] $result[-1][1] $p[0] $p[1]) -gt 2){ $result+=,$p } }
  if($result.Count -lt 2){continue}
  $len=0.0; for($i=1;$i -lt $result.Count;$i++){ $len+=Dm $result[$i-1][0] $result[$i-1][1] $result[$i][0] $result[$i][1] }
  if(-not $best.ContainsKey($my) -or $len -gt $best[$my].len){ $best[$my]=@{len=$len;geom=$result;stops=$stopRefs} }
}

$gj=@(); $sj=@()
foreach($k in ($best.Keys | Sort-Object)){
  $coords=($best[$k].geom | ForEach-Object { '['+[math]::Round($_[0],6)+','+[math]::Round($_[1],6)+']' }) -join ','
  $gj+='"'+$k+'":['+$coords+']'
  # resolve stops
  $sts=@(); $seen=@{}
  foreach($ref in $best[$k].stops){ if($seen.ContainsKey($ref)){continue}; $seen[$ref]=$true; $n=$nodeById[$ref]; if(-not $n){continue}
    $nm2= if($n.name){$n.name}else{"$k stop"}
    $sts+='{"name":"'+($nm2 -replace '"','\"')+'","lat":'+$n.lat+',"lon":'+$n.lon+'}' }
  $sj+='"'+$k+'":['+($sts -join ',')+']'
}
Set-Content "$ddir\existing_geom.json" ('{'+($gj -join ',')+'}') -Encoding utf8
Set-Content "$ddir\existing_stops.json" ('{'+($sj -join ',')+'}') -Encoding utf8
"matched existing routes (geom km / stops):"
foreach($k in ($best.Keys | Sort-Object)){ $ns=($best[$k].stops | Select-Object -Unique).Count; "  {0,-12} {1:N1} km, {2} stops" -f $k,($best[$k].len/1000),$ns }