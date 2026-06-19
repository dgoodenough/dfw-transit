$ErrorActionPreference="Stop"
# Topology fixes (user, Jun 15): make specified line pairs share a corridor + merge Line 76/Arboretum.
# Reads current network_extra.geojson geometry, splices, writes db/corridor_fixes.geojson (geometry
# overrides keyed by line name) + a removal list. build_stations applies these before stop generation.
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(32.8*[math]::PI/180)
function D($alon,$alat,$blon,$blat){ [math]::Sqrt([math]::Pow(($alon-$blon)*$mlon,2)+[math]::Pow(($alat-$blat)*$mlat,2)) }
$feats=(Get-Content "$dbdir\network_extra.geojson" -Raw|ConvertFrom-Json).features
function Coords($name){ $f=$feats|Where-Object{$_.properties.kind -eq 'line' -and $_.properties.name -eq $name}|Select-Object -First 1
  $c=@(); foreach($p in $f.geometry.coordinates){ $c+=,@([double]$p[0],[double]$p[1]) }; return ,$c }
function NIdx($coords,$lon,$lat){ $b=1e18;$bi=0; for($i=0;$i -lt $coords.Count;$i++){ $d=D $lon $lat $coords[$i][0] $coords[$i][1]; if($d -lt $b){$b=$d;$bi=$i} }; return $bi }
# orient so coords END nearest $endLon/$endLat
function Orient($coords,$endLon,$endLat){ if((D $coords[0][0] $coords[0][1] $endLon $endLat) -lt (D $coords[-1][0] $coords[-1][1] $endLon $endLat)){ $r=@(); for($i=$coords.Count-1;$i -ge 0;$i--){$r+=,$coords[$i]}; return ,$r }; return ,$coords }
function Slice($coords,$a,$b){ $lo=[math]::Min($a,$b);$hi=[math]::Max($a,$b); $s=@(); for($i=$lo;$i -le $hi;$i++){$s+=,$coords[$i]}; if($a -gt $b){ $r=@(); for($i=$s.Count-1;$i -ge 0;$i--){$r+=,$s[$i]}; return ,$r }; return ,$s }

# anchors
$OED=@(-96.776314,32.806144)   # Old East Dallas (just E of I-75)
$ZN =@(-96.674518,32.881345)   # Zacha Junction N (shared terminus)
$FPE9=@(-96.682746,32.777985)  # Fair Park E9
$PA =@(-96.79409,32.786763)    # Pearl/Arts District (uptown meet)
$VIC=@(-96.812028,32.793024)   # Victory (Arboretum uptown end)

# ===== FIX 3: Silver shares Blue Ctd east of Old East Dallas =====
$sv=Orient (Coords 'Silver') $ZN[0] $ZN[1]      # west -> Zacha
$bc=Orient (Coords 'Blue Ctd') $ZN[0] $ZN[1]
$svOED=NIdx $sv $OED[0] $OED[1]; $bcOED=NIdx $bc $OED[0] $OED[1]
$newSilver=@(); for($i=0;$i -le $svOED;$i++){$newSilver+=,$sv[$i]}; for($i=$bcOED+1;$i -lt $bc.Count;$i++){$newSilver+=,$bc[$i]}
"Silver: west[0..$svOED] + BlueCtd[$($bcOED+1)..$($bc.Count-1)] = $($newSilver.Count) pts (shares east of Old East Dallas)"

# ===== FIX 2: Line 76 shares DNT-East from Fair Park E9 to Pearl/Arts (uptown) =====
$l76=Orient (Coords 'Line 76') $PA[0] $PA[1]     # Mesquite -> Pearl(uptown) end
$dnt=(Coords 'DNT Line - East')
$l76_fpe9=NIdx $l76 $FPE9[0] $FPE9[1]
$dnt_fpe9=NIdx $dnt $FPE9[0] $FPE9[1]; $dnt_pa=NIdx $dnt $PA[0] $PA[1]
$dntShare=Slice $dnt $dnt_fpe9 $dnt_pa          # oriented FairParkE9 -> Pearl/Arts
# new Line 76 = Mesquite..FairParkE9 (from l76) + DNT FairParkE9..Pearl/Arts
$newL76=@(); for($i=0;$i -le $l76_fpe9;$i++){$newL76+=,$l76[$i]}; for($i=1;$i -lt $dntShare.Count;$i++){$newL76+=,$dntShare[$i]}
"Line 76: Mesquite..FairParkE9 ($($l76_fpe9+1)) + DNT FPE9..Pearl/Arts ($($dntShare.Count)) = $($newL76.Count) pts (pairs DNT-East to uptown)"

# ===== FIX 1: merge Arboretum into Line 76 (one line) =====
$arb=Orient (Coords 'Arboretum Line') $VIC[0] $VIC[1]   # LasColinas -> Victory(uptown)
# merged = Arboretum (LasColinas->Victory) + newL76 reversed (Pearl/Arts->...->Mesquite)
$merged=@(); foreach($p in $arb){$merged+=,$p}; for($i=$newL76.Count-1;$i -ge 0;$i--){$merged+=,$newL76[$i]}
"Merged Line 76 = Arboretum ($($arb.Count)) + reverse(newLine76) = $($merged.Count) pts (Victory->Pearl/Arts join $([math]::Round((D $VIC[0] $VIC[1] $PA[0] $PA[1])))m)"

# emit overrides
function Feat($name,$coords){ $cj=($coords|ForEach-Object{'['+[math]::Round([double]$_[0],6)+','+[math]::Round([double]$_[1],6)+']'}) -join ','
  return '{"type":"Feature","properties":{"name":"'+($name -replace '"','\"')+'"},"geometry":{"type":"LineString","coordinates":['+$cj+']}}' }
$out=@( (Feat 'Line 76' $merged), (Feat 'Silver' $newSilver) )
Set-Content "$dbdir\corridor_fixes.geojson" ('{"type":"FeatureCollection","remove":["Arboretum Line"],"features":['+($out -join ',')+']}') -Encoding utf8
"wrote db/corridor_fixes.geojson (override Line 76 + Silver; remove Arboretum Line)"