$ErrorActionPreference="Stop"
# Cedar-Hill-style ROW audit for the Legacy Line: sample its geometry and measure
# distance to nearest RAIL / FREEWAY / ARTERIAL separately, to see what (if anything) it follows.
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
$mlat=110540.0;$mlon=111320.0*[math]::Cos(33.08*[math]::PI/180)
function Rdm($alon,$alat,$blon,$blat){ [math]::Sqrt([math]::Pow(($alon-$blon)*$mlon,2)+[math]::Pow(($alat-$blat)*$mlat,2)) }
function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2); return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }
$rx=[regex]'"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*"lon"\s*:\s*(-?\d+\.\d+)'
$cell=0.02
function LoadGrid($file){ $g=@{}; if(-not(Test-Path $file)){return $g}; $raw=[System.IO.File]::ReadAllText($file); $m=$rx.Matches($raw)
  for($i=0;$i -lt $m.Count;$i+=2){ $lo=[double]$m[$i].Groups[2].Value;$la=[double]$m[$i].Groups[1].Value
    if($la -lt 32.9 -or $la -gt 33.3 -or $lo -lt -96.95 -or $lo -gt -96.6){continue}  # Collin window
    $k="{0}|{1}" -f [math]::Floor($lo/$cell),[math]::Floor($la/$cell); if(-not $g.ContainsKey($k)){$g[$k]=New-Object System.Collections.Generic.List[object]}; [void]$g[$k].Add(@($lo,$la)) }
  return $g }
function Near($g,$lon,$lat){ $best=1e9; $cx=[math]::Floor($lon/$cell);$cy=[math]::Floor($lat/$cell)
  for($dx=-1;$dx -le 1;$dx++){for($dy=-1;$dy -le 1;$dy++){ $k="{0}|{1}" -f ($cx+$dx),($cy+$dy); if($g.ContainsKey($k)){ foreach($p in $g[$k]){ $d=Rdm $lon $lat $p[0] $p[1]; if($d -lt $best){$best=$d} } } }}
  return $best }
$gRail=LoadGrid "$ddir\dfw_rail.json"; $gFwy=LoadGrid "$ddir\dfw_freeways.json"; $gArt=LoadGrid "$ddir\dfw_arterials.json"
"ref pts in Collin window: rail=$(($gRail.Values|ForEach-Object{$_.Count}|Measure-Object -Sum).Sum) fwy=$(($gFwy.Values|ForEach-Object{$_.Count}|Measure-Object -Sum).Sum) art=$(($gArt.Values|ForEach-Object{$_.Count}|Measure-Object -Sum).Sum)"

$segs=Import-Csv "$dbdir\segments.csv" | Where-Object {($_.line -split ';') -contains 'Legacy Line'}
$railH=0;$fwyH=0;$artH=0;$green=0;$tot=0;$worst=@()
foreach($s in $segs){
  $inner=$s.geometry_wkt -replace '^LINESTRING \(','' -replace '\)$',''
  $pc=@(); foreach($p in ($inner -split ',')){ $xy=$p.Trim() -split '\s+'; $pc+=,@([double]$xy[0],[double]$xy[1]) }
  for($i=0;$i -lt $pc.Count-1;$i++){ $a=$pc[$i];$b=$pc[$i+1]; $seg=Rdm $a[0] $a[1] $b[0] $b[1]; $n=[math]::Max(1,[math]::Floor($seg/250))
    for($k=0;$k -lt $n;$k++){ $t=$k/$n; $lo=$a[0]+$t*($b[0]-$a[0]); $la=$a[1]+$t*($b[1]-$a[1]); $tot++
      $dr=Near $gRail $lo $la; $df=Near $gFwy $lo $la; $da=Near $gArt $lo $la; $mn=[math]::Min($dr,[math]::Min($df,$da))
      if($mn -gt 350){ $green++; $worst+=[pscustomobject]@{lat=[math]::Round($la,4);lon=[math]::Round($lo,4);rail=[int]$dr;fwy=[int]$df;art=[int]$da} }
      elseif($dr -le 150){ $railH++ } elseif($df -le 200){ $fwyH++ } elseif($da -le 200){ $artH++ }
      else { } } }
}
"`n== LEGACY LINE corridor characterization ($tot sample pts @250m) =="
"  on RAIL (<=150m):     {0,4}  ({1}%)" -f $railH,[math]::Round(100*$railH/$tot)
"  on FREEWAY (<=200m):  {0,4}  ({1}%)" -f $fwyH,[math]::Round(100*$fwyH/$tot)
"  on ARTERIAL (<=200m): {0,4}  ({1}%)" -f $artH,[math]::Round(100*$artH/$tot)
$near=$tot-$green-$railH-$fwyH-$artH
"  near-but-mid (150-350m): {0,4}  ({1}%)" -f $near,[math]::Round(100*$near/$tot)
"  GREENFIELD (>350m any): {0,4}  ({1}%)" -f $green,[math]::Round(100*$green/$tot)
if($green){ "`n  greenfield points (nothing within 350m):"; $worst | Format-Table -AutoSize | Out-String -Width 100 }