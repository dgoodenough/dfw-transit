param([Parameter(Mandatory=$true)][string]$In)   # edited .kml / .kmz / .geojson
$ErrorActionPreference="Stop"
# Convert a hand-edited lines file back into the DB:
#   geometry -> db/manual_geom.geojson (build_db + build_stations apply as final override)
#   year     -> line_years.csv  (from KML Year folder, or GeoJSON "year" property)
#   mode     -> line_modes.csv  (extra lines only; from KML Mode subfolder or GeoJSON "mode")
$dir=(Split-Path $PSScriptRoot -Parent); $ddir="$dir\data"; $dbdir="$dir\db"
$STEPS=@(2025,2035,2040,2045,2050,2055,2060,2065,2070)
$feats=@()   # @{name;coords;year(or $null);mode(or $null)}
$ext=[System.IO.Path]::GetExtension($In).ToLower()
if($ext -eq '.kmz'){ Add-Type -AssemblyName System.IO.Compression.FileSystem
  $tmp=Join-Path $env:TEMP ('kmz_'+[guid]::NewGuid()); [System.IO.Compression.ZipFile]::ExtractToDirectory($In,$tmp)
  $In=(Get-ChildItem $tmp -Filter *.kml -Recurse | Select-Object -First 1).FullName; $ext='.kml' }
function ToMode($s){ switch -regex ($s){ '^metro'{'metro'} '^commuter'{'commuter'} '^brt'{'brt'} default{$null} } }
function ToYear($s){ if($s -match 'Existing'){return 2025}; if($s -match '^\s*(\d{4})'){ $y=[int]$Matches[1]; if($STEPS -contains $y){return $y} }; return $null }
if($ext -eq '.kml'){
  [xml]$k=Get-Content $In -Raw
  $ns=New-Object System.Xml.XmlNamespaceManager($k.NameTable); $ns.AddNamespace('k','http://www.opengis.net/kml/2.2')
  foreach($pm in $k.SelectNodes('//k:Placemark',$ns)){
    $ls=$pm.SelectSingleNode('.//k:LineString/k:coordinates',$ns); if(-not $ls){continue}
    $nm=$pm.SelectSingleNode('k:name',$ns).InnerText
    $coords=@(); foreach($t in ($ls.InnerText.Trim() -split '\s+')){ if(-not $t){continue}; $a=$t -split ','; $coords+=,@([double]$a[0],[double]$a[1]) }
    if($coords.Count -lt 2){continue}
    # ancestry: Placemark -> Mode folder -> Year folder
    $mode=$null;$year=$null
    $mf=$pm.ParentNode; if($mf -and $mf.LocalName -eq 'Folder'){ $mn=$mf.SelectSingleNode('k:name',$ns); if($mn){$mode=ToMode $mn.InnerText}
      $yf=$mf.ParentNode; if($yf -and $yf.LocalName -eq 'Folder'){ $yn=$yf.SelectSingleNode('k:name',$ns); if($yn){$year=ToYear $yn.InnerText} } }
    $feats+=@{name=$nm;coords=$coords;year=$year;mode=$mode}
  }
} else {
  foreach($f in ((Get-Content $In -Raw|ConvertFrom-Json).features)){
    if($f.geometry.type -ne 'LineString'){continue}
    $nm=$f.properties.name; $coords=@(); foreach($c in $f.geometry.coordinates){ $coords+=,@([double]$c[0],[double]$c[1]) }
    if(-not $nm -or $coords.Count -lt 2){continue}
    $year=$null; if($f.properties.PSObject.Properties.Name -contains 'year'){ $y=[int]$f.properties.year; if($STEPS -contains $y){$year=$y} }
    $mode=$null; if($f.properties.mode){ $mode=ToMode $f.properties.mode }
    $feats+=@{name=$nm;coords=$coords;year=$year;mode=$mode}
  }
}
"parsed $($feats.Count) lines from $([System.IO.Path]::GetFileName($In))"

# 1) geometry -> manual_geom.geojson
$gj=@()
foreach($f in $feats){ $c=($f.coords | ForEach-Object {'['+[math]::Round($_[0],6)+','+[math]::Round($_[1],6)+']'}) -join ','
  $gj+='{"type":"Feature","properties":{"name":"'+($f.name -replace '"','\"')+'"},"geometry":{"type":"LineString","coordinates":['+$c+']}}' }
Set-Content "$dbdir\manual_geom.geojson" ('{"type":"FeatureCollection","features":['+($gj -join ',')+']}') -Encoding utf8

# 2) year -> line_years.csv  (scope fw for "<Line> (core)", else extra; preserve other rows)
function BaseName($n){ return ($n -replace ' \(core\)( \d+)?$','') }
function IsCore($n){ return ($n -match ' \(core\)( \d+)?$') }
$ly=@{}  # "scope|line" -> year
foreach($r in (Import-Csv "$ddir\line_years.csv")){ if($r.line){ $ly["$($r.scope)|$($r.line)"]=$r.year } }
$yc=0
foreach($f in $feats){ if($null -eq $f.year -or $f.year -le 2025){continue}   # Existing-folder lines are forced 2025 by the builder; don't clutter line_years
  $scope= if(IsCore $f.name){'fw'}else{'extra'}; $base=BaseName $f.name
  $key="$scope|$base"; if($ly[$key] -ne "$($f.year)"){ $yc++ }; $ly[$key]="$($f.year)" }
$rows=@(); foreach($kk in $ly.Keys){ $p=$kk -split '\|',2; $rows+=[pscustomobject]@{scope=$p[0];line=$p[1];year=$ly[$kk]} }
$rows | Sort-Object scope,line | Export-Csv "$ddir\line_years.csv" -NoTypeInformation
"updated line_years.csv ($yc year changes)"

# 3) mode -> line_modes.csv  (EXTRA lines only; FW core stays metro)
$lm=@{}
if(Test-Path "$ddir\line_modes.csv"){ foreach($r in (Import-Csv "$ddir\line_modes.csv")){ if($r.line){ $lm[$r.line]=$r.mode } } }
$mc=0; $fwModeWarn=@()
foreach($f in $feats){ if($null -eq $f.mode){continue}
  if(IsCore $f.name){ if($f.mode -ne 'metro'){ $fwModeWarn+=$f.name }; continue }
  if($lm[$f.name] -ne $f.mode){ $mc++ }; $lm[$f.name]=$f.mode }
if($lm.Count){ $mrows=@(); foreach($kk in $lm.Keys){ $mrows+=[pscustomobject]@{line=$kk;mode=$lm[$kk]} }; $mrows | Sort-Object line | Export-Csv "$ddir\line_modes.csv" -NoTypeInformation }
"updated line_modes.csv ($mc mode changes)"
if($fwModeWarn.Count){ "  NOTE: FW core stays metro - ignored non-metro folder for: $($fwModeWarn -join ', ')" }
"REBUILD: build_db -> build_extra -> corridor_share -> build_stations -> build_db_full -> build_feasibility -> build_app"