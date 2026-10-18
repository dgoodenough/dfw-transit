$ErrorActionPreference="Stop"
# Export every line's full as-built path as ONE editable feature (KML + GeoJSON) for manual geometry fixing.
# Edit paths in Google Earth Pro / My Maps (KML) or geojson.io (GeoJSON), then send back -> import_lines.ps1.
# Stops are NOT exported (they auto-regenerate along the edited path). Reference stops included in a separate, ignore-on-import folder.
$dir=(Split-Path $PSScriptRoot -Parent); $dbdir="$dir\db"; $ddir="$dir\data"; $outdir="$dir\edit"
if(-not (Test-Path $outdir)){ New-Item -ItemType Directory $outdir | Out-Null }
# source = exact per-line input geometry the builders consume (idempotent round-trip):
#   fw_lines_source.geojson (FW core, from build_db) + lines_source.geojson (extra, from build_stations)
$linePaths=@()
foreach($srcF in @("$dbdir\fw_lines_source.geojson","$dbdir\lines_source.geojson")){
  if(-not (Test-Path $srcF)){ continue }
  foreach($f in ((Get-Content $srcF -Raw|ConvertFrom-Json).features)){
    $path=@(); foreach($c in $f.geometry.coordinates){ $path+=,@([double]$c[0],[double]$c[1]) }
    if($path.Count -ge 2){ $col=$f.properties.color; if(-not $col){$col='#888888'}
      $linePaths+=[pscustomobject]@{name=$f.properties.name;mode=$f.properties.mode;color=$col;path=$path} }
  }
}
if($linePaths.Count -eq 0){ throw "no *_lines_source.geojson found - run build_db + build_stations first" }

# opening year per line = line_years.csv (each line's OWN year; NOT min station year, which is polluted by shared interchanges)
$STEPS=@(2025,2035,2040,2045,2050,2055,2060,2065,2070)
$ly=@{}
foreach($r in (Import-Csv "$ddir\line_years.csv")){ if($r.line){ $ly["$($r.scope)|$($r.line)"]=[int]$r.year } }
function BaseName($n){ return ($n -replace ' \(core\)( \d+)?$','') }   # "Teal (core) 2" -> "Teal"
function YearOf($lp){ $b=BaseName $lp.name; $scope= if($lp.name -match '\(core\)'){'fw'}else{'extra'}; $k="$scope|$b"
  $y= if($ly.ContainsKey($k)){$ly[$k]}else{2025}; if($STEPS -notcontains $y){ $y=2025 }; return $y }
foreach($lp in $linePaths){ $lp | Add-Member -NotePropertyName year -NotePropertyValue (YearOf $lp) -Force }
"loaded $($linePaths.Count) editable line paths (FW core + extra); foldered by year x mode"

# ---- GeoJSON (for geojson.io: flat, but year+mode are editable properties) ----
$gj=@()
foreach($lp in $linePaths){ $c=($lp.path | ForEach-Object {'['+[math]::Round($_[0],6)+','+[math]::Round($_[1],6)+']'}) -join ','
  $gj+='{"type":"Feature","properties":{"name":"'+($lp.name -replace '"','\"')+'","mode":"'+$lp.mode+'","year":'+$lp.year+',"stroke":"'+$lp.color+'","stroke-width":3},"geometry":{"type":"LineString","coordinates":['+$c+']}}' }
Set-Content "$outdir\dfw_lines.geojson" ('{"type":"FeatureCollection","features":['+($gj -join ',')+']}') -Encoding utf8

# ---- KML (Google Earth Pro: nested Year > Mode folders; drag a line between folders to re-phase / change mode) ----
function KmlColor($hex){ $h=$hex.TrimStart('#'); if($h.Length -ne 6){return 'ff8888ff'}; 'ff'+$h.Substring(4,2)+$h.Substring(2,2)+$h.Substring(0,2) }  # aabbggrr
$modeLabel=[ordered]@{metro='Metro';commuter='Commuter';brt='BRT'}
$kml=New-Object System.Text.StringBuilder
[void]$kml.AppendLine('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>DFW lines - drag between Year/Mode folders</name>')
foreach($lp in ($linePaths | Sort-Object {$_.color} -Unique)){ $sid='s'+([math]::Abs($lp.color.GetHashCode())); $styleIds=$styleIds; if(-not $styleIds){$styleIds=@{}}
  if(-not $styleIds.ContainsKey($lp.color)){ $styleIds[$lp.color]=$sid; [void]$kml.AppendLine('<Style id="'+$sid+'"><LineStyle><color>'+(KmlColor $lp.color)+'</color><width>4</width></LineStyle></Style>') } }
foreach($yr in $STEPS){
  $ylabel= if($yr -eq 2025){'Existing'}else{"$yr"}
  [void]$kml.AppendLine('<Folder><name>'+$ylabel+'</name>')
  foreach($mk in $modeLabel.Keys){
    [void]$kml.AppendLine('<Folder><name>'+$modeLabel[$mk]+'</name>')
    foreach($lp in ($linePaths | Where-Object {$_.year -eq $yr -and $_.mode -eq $mk})){
      $coords=($lp.path | ForEach-Object {"$([math]::Round($_[0],6)),$([math]::Round($_[1],6)),0"}) -join ' '
      [void]$kml.AppendLine('<Placemark><name>'+($lp.name -replace '&','&amp;' -replace '<','&lt;')+'</name><styleUrl>#'+$styleIds[$lp.color]+'</styleUrl><LineString><tessellate>1</tessellate><coordinates>'+$coords+'</coordinates></LineString></Placemark>')
    }
    [void]$kml.AppendLine('</Folder>')
  }
  [void]$kml.AppendLine('</Folder>')
}
[void]$kml.AppendLine('</Document></kml>')
Set-Content "$outdir\dfw_lines.kml" $kml.ToString() -Encoding utf8
"wrote edit/dfw_lines.kml (Year>Mode folders) + edit/dfw_lines.geojson (year+mode props) - $($linePaths.Count) lines"