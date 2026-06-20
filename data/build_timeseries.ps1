$ErrorActionPreference="Stop"
$dir=(Split-Path $PSScriptRoot -Parent)
$ddir="$dir\data"
$kmlPath="C:\Users\justd\Downloads\FW_Subway_extracted\doc.kml"
[xml]$kml=Get-Content $kmlPath
$ns=New-Object System.Xml.XmlNamespaceManager($kml.NameTable);$ns.AddNamespace('k','http://www.opengis.net/kml/2.2')

function AllLines($name){
  $out=@()
  foreach($pm in $kml.SelectNodes('//k:Placemark',$ns)){
    if($pm.SelectSingleNode('k:name',$ns).InnerText -eq $name){
      $ls=$pm.SelectSingleNode('k:LineString/k:coordinates',$ns)
      if($ls){ $pts=@(); foreach($c in ($ls.InnerText.Trim() -split '\s+')){$a=$c -split ',';$pts+=,@([double]$a[0],[double]$a[1])}; $out+=,$pts }
    }
  }
  return ,$out
}
function PickFW($name){ foreach($c in (AllLines $name)){ if($c[0][0] -lt -97.2){return ,$c} }; return ,((AllLines $name)[0]) }
function PickShort($name){ ,((AllLines $name) | Sort-Object {$_.Count})[0] }
function NearestIdx($line,$lon,$lat){ $b=0;$bd=1e9; for($i=0;$i -lt $line.Count;$i++){ $d=[math]::Pow($line[$i][0]-$lon,2)+[math]::Pow($line[$i][1]-$lat,2); if($d -lt $bd){$bd=$d;$b=$i} }; return $b }
function Slice($line,$a,$b){ $o=@(); for($i=$a;$i -le $b;$i++){ $o+=,$line[$i] }; return ,$o }
function Concat(){ $o=@(); foreach($seg in $args){ foreach($p in $seg){ $o+=,$p } }; return ,$o }

# ===== PHASE 1 (revised geometry) =====
$main = PickFW 'Main St Line'
$main[0]=@(-97.3490,32.8130)   # relocated Meacham terminus (consistent with db/)
$green= PickFW 'Green Line'
$blue = PickFW 'Blue Line'
# Orange south leg cleaned to pass through Magnolia stops (consistent with db/)
$orangeS = @(@(-97.3267,32.7380),@(-97.3283,32.7352),@(-97.3316,32.7307),@(-97.3394,32.7307),@(-97.3457,32.7298),@(-97.3613,32.7292),@(-97.3776,32.7220),@(-97.3866,32.7111),@(-97.3960,32.7088),@(-97.4154,32.6990))
$iSMain = NearestIdx $main -97.3259 32.7418
$orange1 = Concat (Slice $main 0 $iSMain) $orangeS
$iDt = NearestIdx $green -97.333 32.7571
$tealWest = Slice $green $iDt ($green.Count-1)
$tealEastNew = @(@(-97.2645,32.8029),@(-97.2700,32.7740),@(-97.3060,32.7731),@(-97.3285,32.7618))
$teal1 = Concat $tealEastNew $tealWest
$iCentral = NearestIdx $blue -97.3267 32.7525
$blue1 = Slice $blue 0 $iCentral

# ===== PHASE 2 additions =====
$blueWestExt = Concat (Slice $blue $iCentral ($blue.Count-1)) (PickFW 'blue line ctd') (PickFW 'Western Hills Ext')
# Silver - cleaned: Lake Worth -> Jacksboro Hwy -> Fair Oaks -> downtown -> Hemphill -> E Berry St -> Berry/Stalcup
$silver = @(@(-97.4298,32.8122),@(-97.4080,32.7985),@(-97.3857,32.7836),@(-97.3640,32.7670),@(-97.3370,32.7550),@(-97.3345,32.7350),@(-97.3325,32.7150),@(-97.3317,32.7059),@(-97.3043,32.7059),@(-97.2852,32.7124),@(-97.2600,32.7095),@(-97.2380,32.7085))
# Red - cleaned: Benbrook -> Waterside -> Clearfork -> Stonegate -> University Park -> cut north -> Museum Way
$red = @(@(-97.4678,32.6753),@(-97.4400,32.6885),@(-97.4154,32.6990),@(-97.3960,32.7088),@(-97.3866,32.7111),@(-97.3720,32.7210),@(-97.3613,32.7292),@(-97.3628,32.7390),@(-97.3646,32.7472))

# ===== PHASE 3 additions =====
$purpleTCU = @(@(-97.3267,32.7525),@(-97.3316,32.7307),@(-97.3457,32.7298),@(-97.3604,32.7096),@(-97.3604,32.6991))
$orangeHulen = PickFW 'Hulen Ext'
$magentaEverman = @(@(-97.3245,32.6863),@(-97.3100,32.6600),@(-97.2950,32.6330))
$tealWood = @(@(-97.2700,32.7740),@(-97.2450,32.7700),@(-97.2261,32.7638))

# ===== line registry: Name, ColorKey, Phase, Verts =====
$LINES=@(
 @{N='Magenta Line';C='Magenta';P=1;V=$main},
 @{N='Orange Line';C='Orange';P=1;V=$orange1},
 @{N='Teal Line';C='Teal';P=1;V=$teal1},
 @{N='Blue Line';C='Blue';P=1;V=$blue1},
 @{N='Blue West Ext';C='Blue';P=2;V=$blueWestExt},
 @{N='Silver Line';C='Silver';P=2;V=$silver},
 @{N='Red Line';C='Red';P=2;V=$red},
 @{N='Purple Line (TCU)';C='Purple';P=3;V=$purpleTCU},
 @{N='Orange South Ext';C='Orange';P=3;V=$orangeHulen},
 @{N='Magenta South Ext';C='Magenta';P=3;V=$magentaEverman},
 @{N='Teal East Ext';C='Teal';P=3;V=$tealWood}
)

# ===== stops: Name, ColorKey, Phase, lon, lat =====
$colByHex=@{'880E4F'='Magenta';'C2185B'='Magenta';'097138'='Teal';'01579B'='Blue';'F57C00'='Orange'}
$drop=@('A Stop','Riverbend','NRH2YIMBY','TCU E','BRT','BRT/ Subway','NAS JRB','The L Word','Berry/Stalcup','Berry/Riverside','Renaissance Square','Fair Oaks','Lake Worth','TCU','Bluebonnet Circle','Woodhaven')
$reloc=@{'Meacham Airport'=@(-97.3490,32.8130,'Meacham / Mercado N');'My Lan (My Favorites)'=@(-97.2700,32.7740,'Riverside / Race St')}
$STOPS=@()
foreach($s in (Import-Csv "C:\Users\justd\Downloads\FW_stations.csv" | Where-Object {$_.Folder -like 'Stops and Potential*Fort worth'})){
  $hex=($s.Style -split '-')[2]; if(-not $colByHex.ContainsKey($hex)){continue}; if($drop -contains $s.Name){continue}
  $lon=[double]$s.Lon;$lat=[double]$s.Lat;$nm=$s.Name
  if($reloc.ContainsKey($s.Name)){$lon=$reloc[$s.Name][0];$lat=$reloc[$s.Name][1];$nm=$reloc[$s.Name][2]}
  $STOPS+=@{N=$nm;C=$colByHex[$hex];P=1;Lon=$lon;Lat=$lat}
}
# phase-2 stops
$STOPS+=@{N='Lake Worth';C='Silver';P=2;Lon=-97.4298;Lat=32.8122}
$STOPS+=@{N='Fair Oaks';C='Silver';P=2;Lon=-97.3857;Lat=32.7836}
$STOPS+=@{N='Berry / Riverside';C='Silver';P=2;Lon=-97.3043;Lat=32.7059}
$STOPS+=@{N='Renaissance Sq';C='Silver';P=2;Lon=-97.2852;Lat=32.7124}
$STOPS+=@{N='Berry / Stalcup';C='Silver';P=2;Lon=-97.2380;Lat=32.7085}
$STOPS+=@{N='Benbrook';C='Red';P=2;Lon=-97.4678;Lat=32.6753}
# phase-3 stops
$STOPS+=@{N='TCU';C='Purple';P=3;Lon=-97.3604;Lat=32.7096}
$STOPS+=@{N='Bluebonnet Circle';C='Purple';P=3;Lon=-97.3604;Lat=32.6991}
$STOPS+=@{N='Hulen Mall';C='Orange';P=3;Lon=-97.4161;Lat=32.6455}
$STOPS+=@{N='Altamesa';C='Orange';P=3;Lon=-97.4130;Lat=32.6380}
$STOPS+=@{N='Woodhaven';C='Teal';P=3;Lon=-97.2261;Lat=32.7638}
$STOPS+=@{N='Everman';C='Magenta';P=3;Lon=-97.2950;Lat=32.6330}

# ===== colors =====
$col=@{Teal='#00b251';Blue='#0896d7';Orange='#df8600';Magenta='#d63384';Silver='#9aa0a6';Red='#bd1038';Purple='#7b2d8e'}
$colLabel=@{Teal='Teal';Blue='Blue';Orange='Orange';Magenta='Pink';Silver='Silver';Red='Red';Purple='Purple (TCU)'}
$yearOf=@{1='2050';2='2060';3='2070'}
$addedOf=@{1='Teal, Blue, Orange, Pink (core build)';2='+ Silver (Lake Worth-Berry/Stalcup), Red (Benbrook), Blue west to 820';3='+ Purple (TCU), Orange to Hulen, Pink to Everman, Teal to Woodhaven'}

# ===== projection =====
$lonMin=-97.485;$lonMax=-97.205;$latMin=32.625;$latMax=32.835
$lat0=([math]::PI/180)*(($latMin+$latMax)/2);$kx=[math]::Cos($lat0)
$W=1180.0;$H=$W*(($latMax-$latMin)/(($lonMax-$lonMin)*$kx))
function PX($lon){ ($lon-$lonMin)/($lonMax-$lonMin)*$W }
function PY($lat){ ($latMax-$lat)/($latMax-$latMin)*$H }
function F($v){ ([math]::Round([double]$v,1)).ToString([System.Globalization.CultureInfo]::InvariantCulture) }
function Path($line){ ($line | ForEach-Object { (F (PX $_[0]))+','+(F (PY $_[1])) }) -join ' ' }

# rivers (clip to core)
$riv=Get-Content "$ddir\fw_rivers.json" -Raw | ConvertFrom-Json
$rivPaths=@();$rL0=-97.425;$rL1=-97.212;$rB0=32.695;$rB1=32.815
foreach($el in $riv.elements){ if($el.geometry -and $el.tags.name -like '*Trinity River*'){
  $run=@();$plo=$null;$pla=$null
  foreach($g in $el.geometry){ $lo=[double]$g.lon;$la=[double]$g.lat
    $ins=($lo -ge $rL0 -and $lo -le $rL1 -and $la -ge $rB0 -and $la -le $rB1)
    $jmp=if($plo -ne $null){[math]::Sqrt([math]::Pow($lo-$plo,2)+[math]::Pow($la-$pla,2))}else{0}
    if($ins -and $jmp -lt 0.012){ $run+=(F (PX $lo))+','+(F (PY $la)) } else { if($run.Count -gt 1){$rivPaths+=($run -join ' ')}; $run=if($ins){@((F (PX $lo))+','+(F (PY $la)))}else{@()} }
    $plo=$lo;$pla=$la }
  if($run.Count -gt 1){$rivPaths+=($run -join ' ')} } }

function RenderPhase($P){
  $sb=New-Object System.Text.StringBuilder
  $TH=[int]([math]::Ceiling($H)+70)
  [void]$sb.AppendLine('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+[int]$W+' '+$TH+'" font-family="Helvetica,Arial,sans-serif">')
  [void]$sb.AppendLine('<rect width="100%" height="100%" fill="#f7f7f4"/>')
  foreach($r in $rivPaths){ [void]$sb.AppendLine('<polyline points="'+$r+'" fill="none" stroke="#9ec7e0" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>') }
  # older lines first (thin/muted), then new-this-phase (bold)
  foreach($L in ($LINES | Where-Object {$_.P -le $P} | Sort-Object {if($_.P -eq $P){1}else{0}})){
    $isNew = ($L.P -eq $P)
    $sw = if($isNew){7}else{4.5}; $op = if($isNew){1.0}elseif($P -gt 1){0.85}else{1.0}
    if($isNew){ [void]$sb.AppendLine('<polyline points="'+(Path $L.V)+'" fill="none" stroke="#fff" stroke-width="'+($sw+3)+'" stroke-linecap="round" stroke-linejoin="round" opacity="0.7"/>') }
    [void]$sb.AppendLine('<polyline points="'+(Path $L.V)+'" fill="none" stroke="'+$col[$L.C]+'" stroke-width="'+$sw+'" stroke-linecap="round" stroke-linejoin="round" opacity="'+$op+'"/>')
  }
  foreach($s in ($STOPS | Where-Object {$_.P -le $P})){
    $x=PX $s.Lon;$y=PY $s.Lat;$isNew=($s.P -eq $P)
    $r= if($isNew){5.2}else{3.6}
    [void]$sb.AppendLine('<circle cx="'+(F $x)+'" cy="'+(F $y)+'" r="'+$r+'" fill="#fff" stroke="'+$col[$s.C]+'" stroke-width="2.2"/>')
    if($isNew -or $P -eq 1){ [void]$sb.AppendLine('<text x="'+(F ($x+6))+'" y="'+(F ($y+3))+'" font-size="8.5" fill="#333">'+($s.N -replace '&','&amp;')+'</text>') }
  }
  [void]$sb.AppendLine('<text x="14" y="28" font-size="22" font-weight="700" fill="#111">Fort Worth Metro - Phase '+$P+'  ('+$yearOf[$P]+')</text>')
  [void]$sb.AppendLine('<text x="14" y="48" font-size="12" fill="#666">'+$addedOf[$P]+'</text>')
  # legend
  $ly=[int]$H+30;$lx=14;$off=0
  $leg=@(@('Teal',$col.Teal),@('Blue',$col.Blue),@('Orange',$col.Orange),@('Pink',$col.Magenta),@('Silver',$col.Silver),@('Red',$col.Red),@('Purple (TCU)',$col.Purple))
  foreach($l in $leg){ [void]$sb.AppendLine('<line x1="'+($lx+$off)+'" y1="'+$ly+'" x2="'+($lx+$off+22)+'" y2="'+$ly+'" stroke="'+$l[1]+'" stroke-width="6" stroke-linecap="round"/><text x="'+($lx+$off+27)+'" y="'+($ly+4)+'" font-size="11" fill="#222">'+$l[0]+'</text>'); $off+=([int]$W/7) }
  [void]$sb.AppendLine('</svg>')
  $f="$dir\maps\FW_timeseries_P$P.svg"; Set-Content $f $sb.ToString() -Encoding utf8; return $f
}

foreach($P in 1,2,3){ $f=RenderPhase $P; "wrote $f" }
"lines: $($LINES.Count) | stops: $($STOPS.Count)"

# (web map + geojson now generated from the DB by build_app.ps1 / build_db.ps1)
