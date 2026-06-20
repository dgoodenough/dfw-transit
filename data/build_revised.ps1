$ErrorActionPreference="Stop"
$dir=(Split-Path $PSScriptRoot -Parent)
$ddir="$dir\data"
$kmlPath="C:\Users\justd\Downloads\FW_Subway_extracted\doc.kml"

# ---------- load KML line geometries ----------
[xml]$kml=Get-Content $kmlPath
$ns=New-Object System.Xml.XmlNamespaceManager($kml.NameTable);$ns.AddNamespace('k','http://www.opengis.net/kml/2.2')
function GetLine($name){
  foreach($pm in $kml.SelectNodes('//k:Placemark',$ns)){
    if($pm.SelectSingleNode('k:name',$ns).InnerText -eq $name){
      $ls=$pm.SelectSingleNode('k:LineString/k:coordinates',$ns)
      if($ls){ $pts=@(); foreach($c in ($ls.InnerText.Trim() -split '\s+')){$a=$c -split ',';$pts+=,@([double]$a[0],[double]$a[1])}; return ,$pts }
    }
  }
}
function NearestIdx($line,$lon,$lat){
  $best=0;$bd=1e9
  for($i=0;$i -lt $line.Count;$i++){ $d=[math]::Pow($line[$i][0]-$lon,2)+[math]::Pow($line[$i][1]-$lat,2); if($d -lt $bd){$bd=$d;$best=$i} }
  return $best
}
function Slice($line,$a,$b){ $o=@(); for($i=$a;$i -le $b;$i++){ $o+=,$line[$i] }; return ,$o }

$main = GetLine 'Main St Line'          # Purple, Meacham->La Gran Plaza
$green= GetLine 'Green Line'            # Teal (has bad east tail)
$blue = GetLine 'Blue Line'            # Blue, Handley->past downtown
$orangeS = GetLine 'Orange Line'        # Orange south, downtown->Waterside (18 pt one)
if($orangeS.Count -gt 30){ $orangeS = GetLine 'Orange Line' } # guard (name collision handled below)

# name 'Orange Line' collides with Dallas existing line (78pts). pick the short FW one:
$orangeCandidates=@()
foreach($pm in $kml.SelectNodes('//k:Placemark',$ns)){
  if($pm.SelectSingleNode('k:name',$ns).InnerText -eq 'Orange Line'){
    $ls=$pm.SelectSingleNode('k:LineString/k:coordinates',$ns)
    $pts=@(); foreach($c in ($ls.InnerText.Trim() -split '\s+')){$a=$c -split ',';$pts+=,@([double]$a[0],[double]$a[1])}
    $orangeCandidates+=,$pts
  }
}
$orangeS = ($orangeCandidates | Sort-Object {$_.Count})[0]   # the 18-pt FW one
# same guard for Green/Blue (Dallas dupes are 52/65 pts; FW are 29/54). pick by FW bbox (lon<-97.2)
function PickFW($name){
  $cands=@()
  foreach($pm in $kml.SelectNodes('//k:Placemark',$ns)){
    if($pm.SelectSingleNode('k:name',$ns).InnerText -eq $name){
      $ls=$pm.SelectSingleNode('k:LineString/k:coordinates',$ns)
      $pts=@(); foreach($c in ($ls.InnerText.Trim() -split '\s+')){$a=$c -split ',';$pts+=,@([double]$a[0],[double]$a[1])}
      $cands+=,$pts
    }
  }
  foreach($c in $cands){ if($c[0][0] -lt -97.2){ return ,$c } }
  return ,$cands[0]
}
$green=PickFW 'Green Line'; $blue=PickFW 'Blue Line'

# ---------- FIX 1: Orange shares Purple N spine, branches SW ----------
$iSMain = NearestIdx $main -97.3259 32.7418      # S Main on Purple spine
$orangeNorth = Slice $main 0 $iSMain             # Meacham -> S Main (shared w/ Purple)
$orange = @(); foreach($p in $orangeNorth){$orange+=,$p}; foreach($p in $orangeS){$orange+=,$p}

# ---------- FIX 2: Teal east re-aligned, drop Woodhaven/old Riverbend/My Lan ----------
$iDt = NearestIdx $green -97.333 32.7571         # downtown anchor on Green
$tealWest = Slice $green $iDt ($green.Count-1)    # downtown -> Ridgmar Mall (good)
$tealEastNew = @(@(-97.2645,32.8029),@(-97.2700,32.7740),@(-97.3060,32.7731),@(-97.3285,32.7618)) # Haltom->Riverside->SixPts->TrinityBluff
$teal=@(); foreach($p in $tealEastNew){$teal+=,$p}; foreach($p in $tealWest){$teal+=,$p}

# ---------- FIX 3: Blue terminates at Central Station ----------
$iCentral = NearestIdx $blue -97.3267 32.7525
$blueFixed = Slice $blue 0 $iCentral

$purple=$main

# ---------- stops (apply relocations / drops) ----------
$allStops = Import-Csv "C:\Users\justd\Downloads\FW_stations.csv" | Where-Object {$_.Folder -like 'Stops and Potential*Fort worth'}
# phase-one line colors
$phaseColors=@{'880E4F'='Purple';'C2185B'='Purple';'097138'='Teal';'01579B'='Blue';'F57C00'='Orange'}
$drop=@('Woodhaven','Riverbend','A Stop','NRH2YIMBY','Fair Oaks','Lake Worth','TCU','TCU E','Bluebonnet Circle','Berry/Stalcup','Berry/Riverside','Renaissance Square','BRT','BRT/ Subway','NAS JRB')
$reloc=@{
  'Meacham Airport'=@(-97.3490,32.8130,'Meacham / Mercado N');
  'My Lan (My Favorites)'=@(-97.2700,32.7740,'Riverside / Race St')
}
$stops=@()
foreach($s in $allStops){
  $hex=($s.Style -split '-')[2]
  if(-not $phaseColors.ContainsKey($hex)){continue}
  if($drop -contains $s.Name){continue}
  $lon=[double]$s.Lon;$lat=[double]$s.Lat;$nm=$s.Name
  if($reloc.ContainsKey($s.Name)){ $lon=$reloc[$s.Name][0];$lat=$reloc[$s.Name][1];$nm=$reloc[$s.Name][2] }
  $stops+=[pscustomobject]@{Name=$nm;Line=$phaseColors[$hex];Lon=$lon;Lat=$lat;Note=''}
}
# special markers
$stops+=[pscustomobject]@{Name='Lockheed Martin (F-35)';Line='GAP';Lon=-97.4490;Lat=32.7760;Note='20k jobs - not served until Ph2'}

# ---------- colors ----------
$col=@{Teal='#00b251';Blue='#0896d7';Orange='#df8600';Purple='#662c90';GAP='#e03131'}

# ---------- emit GeoJSON ----------
function LineFeat($name,$line,$c){
  $coords=($line | ForEach-Object { "[{0},{1}]" -f $_[0],$_[1] }) -join ','
  return '{"type":"Feature","properties":{"name":"'+$name+'","mode":"metro","stroke":"'+$c+'","stroke-width":4},"geometry":{"type":"LineString","coordinates":['+$coords+']}}'
}
$feats=@()
$feats+=LineFeat 'Teal Line' $teal $col.Teal
$feats+=LineFeat 'Blue Line' $blueFixed $col.Blue
$feats+=LineFeat 'Orange Line' $orange $col.Orange
$feats+=LineFeat 'Purple Line' $purple $col.Purple
foreach($s in $stops){
  $c= if($col.ContainsKey($s.Line)){$col[$s.Line]}else{'#333'}
  $feats+=('{"type":"Feature","properties":{"name":"'+($s.Name -replace '"','')+'","line":"'+$s.Line+'","marker-color":"'+$c+'","note":"'+$s.Note+'"},"geometry":{"type":"Point","coordinates":['+$s.Lon+','+$s.Lat+']}}')
}
$geojson='{"type":"FeatureCollection","features":['+($feats -join ',')+']}'
Set-Content "$dir\maps\FW_PhaseOne_revised.geojson" $geojson -Encoding utf8
"GeoJSON written: $($stops.Count) stops, 4 lines"

# ---------- emit geographic SVG (with rivers) ----------
$lonMin=-97.462;$lonMax=-97.205;$latMin=32.678;$latMax=32.832
$lat0=([math]::PI/180)*(($latMin+$latMax)/2); $kx=[math]::Cos($lat0)
$W=1180.0; $H=$W*(($latMax-$latMin)/(($lonMax-$lonMin)*$kx))
function PX($lon){ ($lon-$lonMin)/($lonMax-$lonMin)*$W }
function PY($lat){ ($latMax-$lat)/($latMax-$latMin)*$H }
# invariant number format (NO thousands separator - {0:N1} inserts commas that corrupt SVG point lists)
function F($v){ ([math]::Round([double]$v,1)).ToString([System.Globalization.CultureInfo]::InvariantCulture) }
function Path($line){ ($line | ForEach-Object { (F (PX $_[0]))+','+(F (PY $_[1])) }) -join ' ' }

# rivers
$riv=Get-Content "$ddir\fw_rivers.json" -Raw | ConvertFrom-Json
$rivPaths=@()
# tighter river clip box (network core) so far upstream arms don't streak the corners
$exLon0=-97.425;$exLon1=-97.212;$exLat0=32.695;$exLat1=32.815
foreach($el in $riv.elements){
  if($el.geometry){
    $nm=if($el.tags.name){[string]$el.tags.name}else{''}
    $major = ($nm -like '*Trinity River*')
    $run=@();$plo=$null;$pla=$null
    foreach($g in $el.geometry){
      $lo=[double]$g.lon;$la=[double]$g.lat
      $inside = ($lo -ge $exLon0 -and $lo -le $exLon1 -and $la -ge $exLat0 -and $la -le $exLat1)
      $jump = if($plo -ne $null){ [math]::Sqrt([math]::Pow($lo-$plo,2)+[math]::Pow($la-$pla,2)) } else { 0 }
      if($inside -and $jump -lt 0.012){
        $run+=(F (PX $lo))+','+(F (PY $la))
      } else {
        if($run.Count -gt 1){ $rivPaths+=[pscustomobject]@{Pts=($run -join ' ');Major=$major} }
        $run= if($inside){ @((F (PX $lo))+','+(F (PY $la))) } else { @() }
      }
      $plo=$lo;$pla=$la
    }
    if($run.Count -gt 1){ $rivPaths+=[pscustomobject]@{Pts=($run -join ' ');Major=$major} }
  }
}

$sb=New-Object System.Text.StringBuilder
[void]$sb.AppendLine('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+[int]$W+' '+[int]([math]::Ceiling($H)+40)+'" font-family="Helvetica,Arial,sans-serif">')
[void]$sb.AppendLine('<rect width="100%" height="100%" fill="#f7f7f4"/>')
# rivers
foreach($r in $rivPaths){
  if($r.Major){ [void]$sb.AppendLine('<polyline points="'+$r.Pts+'" fill="none" stroke="#8fb8d8" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>') }
}
# lines
$lines=@(@('Purple',$purple),@('Orange',$orange),@('Blue',$blueFixed),@('Teal',$teal))
foreach($L in $lines){
  [void]$sb.AppendLine('<polyline points="'+(Path $L[1])+'" fill="none" stroke="'+$col[$L[0]]+'" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" opacity="0.92"/>')
}
# stops
foreach($s in $stops){
  $x=PX $s.Lon;$y=PY $s.Lat
  if($s.Line -eq 'GAP'){
    [void]$sb.AppendLine('<path d="M '+(F $x)+' '+(F ($y-9))+' l 2.6 5.4 l 5.9 .6 l -4.5 4 l 1.4 5.8 l -5.3 -3.1 l -5.3 3.1 l 1.4 -5.8 l -4.5 -4 l 5.9 -.6 z" fill="#e03131" stroke="#fff" stroke-width="1"/>')
    [void]$sb.AppendLine('<text x="'+(F ($x+10))+'" y="'+(F $y)+'" font-size="11" font-weight="700" fill="#c92a2a">'+$s.Name+'</text>')
  } else {
    $c=$col[$s.Line]
    [void]$sb.AppendLine('<circle cx="'+(F $x)+'" cy="'+(F $y)+'" r="4.2" fill="#fff" stroke="'+$c+'" stroke-width="2.2"/>')
    [void]$sb.AppendLine('<text x="'+(F ($x+6))+'" y="'+(F ($y+3))+'" font-size="9" fill="#222">'+($s.Name -replace '&','&amp;')+'</text>')
  }
}
# title + legend
[void]$sb.AppendLine('<text x="14" y="26" font-size="20" font-weight="700" fill="#111">Fort Worth Metro - Phase One (revised)</text>')
[void]$sb.AppendLine('<text x="14" y="44" font-size="11" fill="#555">To-scale. Trinity River forks in blue. Fixes: shared N river crossing, re-aligned Teal east, Blue terminates downtown, Lockheed gap flagged.</text>')
$lx=14;$ly=[int]$H+14
$leg=@(@('Teal',$col.Teal),@('Blue',$col.Blue),@('Orange',$col.Orange),@('Purple',$col.Purple))
$off=0
foreach($l in $leg){ [void]$sb.AppendLine('<line x1="'+($lx+$off)+'" y1="'+$ly+'" x2="'+($lx+$off+24)+'" y2="'+$ly+'" stroke="'+$l[1]+'" stroke-width="6" stroke-linecap="round"/><text x="'+($lx+$off+30)+'" y="'+($ly+4)+'" font-size="12" fill="#222">'+$l[0]+'</text>'); $off+=110 }
[void]$sb.AppendLine('</svg>')
Set-Content "$dir\maps\FW_PhaseOne_revised.svg" $sb.ToString() -Encoding utf8
"SVG written: ${W} x $([int]$H)"
"Lines (vertex counts): Purple=$($purple.Count) Orange=$($orange.Count) Blue=$($blueFixed.Count) Teal=$($teal.Count)"
