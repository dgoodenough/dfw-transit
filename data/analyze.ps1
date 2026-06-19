$ErrorActionPreference = "Stop"
$dir = "C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit\data"
$kmlPath = "C:\Users\justd\Downloads\FW_Subway_extracted\doc.kml"

function Haversine($lat1,$lon1,$lat2,$lon2){
  $R=6371.0; $dLat=([math]::PI/180)*($lat2-$lat1); $dLon=([math]::PI/180)*($lon2-$lon1)
  $a=[math]::Sin($dLat/2)*[math]::Sin($dLat/2)+[math]::Cos([math]::PI/180*$lat1)*[math]::Cos([math]::PI/180*$lat2)*[math]::Sin($dLon/2)*[math]::Sin($dLon/2)
  return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a))
}

# ---- 1. Load BG centroids+population, restrict to FW-area bbox ----
$bgs=@()
$latMin=32.60;$latMax=32.86;$lonMin=-97.56;$lonMax=-97.14
Get-Content "$dir\CenPop2020_BG_TX.txt" | Select-Object -Skip 1 | ForEach-Object {
  $p=$_ -split ','
  if($p.Count -ge 7){
    $lat=[double]$p[5]; $lon=[double]$p[6]
    if($lat -ge $latMin -and $lat -le $latMax -and $lon -ge $lonMin -and $lon -le $lonMax){
      $geoid=$p[0]+$p[1]+$p[2]+$p[3]
      $bgs+=[pscustomobject]@{GEOID=$geoid;Pop=[int]$p[4];Lat=$lat;Lon=$lon;Jobs=0}
    }
  }
}
"BG centroids in FW bbox: $($bgs.Count)"
$bgIdx=@{}; foreach($b in $bgs){$bgIdx[$b.GEOID]=$b}

# ---- 2. Load LODES jobs (gz), filter Tarrant blocks, aggregate to BG ----
$fs=[System.IO.File]::OpenRead("$dir\tx_wac.csv.gz")
$gz=New-Object System.IO.Compression.GzipStream($fs,[System.IO.Compression.CompressionMode]::Decompress)
$sr=New-Object System.IO.StreamReader($gz)
$header=$sr.ReadLine() -split ','
$iGeo=[array]::IndexOf($header,'w_geocode'); $iC000=[array]::IndexOf($header,'C000')
$jobAgg=@{}
while(($line=$sr.ReadLine()) -ne $null){
  if($line.StartsWith('48439')){
    $p=$line -split ','
    $bg=$p[$iGeo].Substring(0,12)
    $jobAgg[$bg]=[int]($jobAgg[$bg]) + [int]$p[$iC000]
  }
}
$sr.Close();$gz.Close();$fs.Close()
$totJobs=0; foreach($k in $jobAgg.Keys){ if($bgIdx.ContainsKey($k)){$bgIdx[$k].Jobs=$jobAgg[$k]}; $totJobs+=$jobAgg[$k] }
"Tarrant BGs with jobs: $($jobAgg.Count)  | total jobs (Tarrant): $totJobs"

# ---- 3. Load FW stops ----
$stops = Import-Csv "C:\Users\justd\Downloads\FW_stations.csv" | Where-Object {$_.Folder -like 'Stops and Potential*Fort worth'}
$colorMap=@{'880E4F'='Purple';'C2185B'='Purple-N';'097138'='Teal';'01579B'='Blue';'F57C00'='Orange';'FFEA00'='Yellow(P3)';'FFD600'='Yellow/mix';'AFB42B'='Silver-E(P2)';'FBC02D'='Teal-E';'BDBDBD'='Silver(P2)';'795548'='BRT'}
$stopObjs=@()
foreach($s in $stops){
  $hex=($s.Style -split '-')[2]
  $line= if($colorMap.ContainsKey($hex)){$colorMap[$hex]}else{$hex}
  $stopObjs+=[pscustomobject]@{Name=$s.Name;Line=$line;Lat=[double]$s.Lat;Lon=[double]$s.Lon}
}

# ---- 4. Score each stop: pop & jobs within radius ----
$R=1.0
$rows=@()
foreach($s in $stopObjs){
  $p=0;$j=0
  foreach($b in $bgs){
    if([math]::Abs($b.Lat-$s.Lat) -lt 0.02 -and [math]::Abs($b.Lon-$s.Lon) -lt 0.02){
      if((Haversine $s.Lat $s.Lon $b.Lat $b.Lon) -le $R){ $p+=$b.Pop; $j+=$b.Jobs }
    }
  }
  $rows+=[pscustomobject]@{Name=$s.Name;Line=$s.Line;Pop1k=$p;Jobs1k=$j;Act1k=($p+$j)}
}
"`n===== STOP ACTIVITY (pop+jobs within ${R} km, BG-centroid based) ====="
$rows | Sort-Object Act1k -Descending | Format-Table Name,Line,Pop1k,Jobs1k,Act1k -AutoSize | Out-String -Width 200
$rows | Sort-Object Act1k -Descending | Export-Csv "$dir\stop_scores.csv" -NoTypeInformation

# ---- 5. Coverage gaps: high-activity BGs far from any stop ----
"`n===== COVERAGE GAPS (BG act>1500, nearest FW stop > ${R} km) ====="
$gaps=@()
foreach($b in $bgs){
  $act=$b.Pop+$b.Jobs
  if($act -gt 1500){
    $min=999.0;$near=''
    foreach($s in $stopObjs){
      $d=Haversine $b.Lat $b.Lon $s.Lat $s.Lon
      if($d -lt $min){$min=$d;$near=$s.Name}
    }
    if($min -gt $R){ $gaps+=[pscustomobject]@{Lat=[math]::Round($b.Lat,4);Lon=[math]::Round($b.Lon,4);Pop=$b.Pop;Jobs=$b.Jobs;Act=$act;NearestStop=$near;DistKm=[math]::Round($min,2)} }
  }
}
$gaps | Sort-Object Act -Descending | Select-Object -First 18 | Format-Table -AutoSize | Out-String -Width 200

# ---- 6. River crossings ----
function SegInt($p1,$p2,$p3,$p4){
  # returns intersection point if segment p1p2 intersects p3p4 (x=lon,y=lat)
  $d1x=$p2[0]-$p1[0];$d1y=$p2[1]-$p1[1];$d2x=$p4[0]-$p3[0];$d2y=$p4[1]-$p3[1]
  $den=$d1x*$d2y-$d1y*$d2x
  if([math]::Abs($den) -lt 1e-12){return $null}
  $t=(($p3[0]-$p1[0])*$d2y-($p3[1]-$p1[1])*$d2x)/$den
  $u=(($p3[0]-$p1[0])*$d1y-($p3[1]-$p1[1])*$d1x)/$den
  if($t -ge 0 -and $t -le 1 -and $u -ge 0 -and $u -le 1){
    return @($p1[0]+$t*$d1x, $p1[1]+$t*$d1y)
  }
  return $null
}
$riv=Get-Content "$dir\fw_rivers.json" -Raw | ConvertFrom-Json
$rivers=@()
foreach($el in $riv.elements){
  if($el.geometry){
    $nm= if($el.tags.name){$el.tags.name}else{'(unnamed river)'}
    $pts=@(); foreach($g in $el.geometry){$pts+=,@([double]$g.lon,[double]$g.lat)}
    $rivers+=[pscustomobject]@{Name=$nm;Pts=$pts}
  }
}
"`nRiver ways loaded: $($rivers.Count)  | names: " + (($rivers.Name | Sort-Object -Unique) -join '; ')

[xml]$kml=Get-Content $kmlPath
$ns=New-Object System.Xml.XmlNamespaceManager($kml.NameTable);$ns.AddNamespace('k','http://www.opengis.net/kml/2.2')
$want=@('Main St Line','Green Line','Blue Line','blue line ctd','Orange Line','orange line continued')
$lineLabel=@{'Main St Line'='Purple';'Green Line'='Teal';'Blue Line'='Blue(E)';'blue line ctd'='Blue(W)';'Orange Line'='Orange(S)';'orange line continued'='Orange(N)'}
"`n===== RIVER CROSSINGS ====="
foreach($pm in $kml.SelectNodes('//k:Placemark',$ns)){
  $nm=$pm.SelectSingleNode('k:name',$ns).InnerText
  if($want -contains $nm){
    $ls=$pm.SelectSingleNode('k:LineString/k:coordinates',$ns)
    $lpts=@(); foreach($c in ($ls.InnerText.Trim() -split '\s+')){$a=$c -split ',';$lpts+=,@([double]$a[0],[double]$a[1])}
    $crossings=@()
    for($i=0;$i -lt $lpts.Count-1;$i++){
      foreach($rv in $rivers){
        for($j=0;$j -lt $rv.Pts.Count-1;$j++){
          $ip=SegInt $lpts[$i] $lpts[$i+1] $rv.Pts[$j] $rv.Pts[$j+1]
          if($ip){ $crossings+=[pscustomobject]@{River=$rv.Name;Lon=[math]::Round($ip[0],4);Lat=[math]::Round($ip[1],4)} }
        }
      }
    }
    "{0,-22} ({1}): {2} crossing(s)" -f $nm,$lineLabel[$nm],$crossings.Count
    $crossings | ForEach-Object { "      - {0}  @ {1},{2}" -f $_.River,$_.Lat,$_.Lon }
  }
}
