$ErrorActionPreference="Stop"
# Network overlap audit: for every pair of lines, what % of the SHORTER line lies within 250m of the other.
# High coverage => near-duplicate (like Line 80 inside the FW Crosstown Loop). Partial = shared trunk (fine).
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $dbdir="$dir\db"
function Hav($la1,$lo1,$la2,$lo2){ $R=6371.0;$dla=([math]::PI/180)*($la2-$la1);$dlo=([math]::PI/180)*($lo2-$lo1)
  $a=[math]::Sin($dla/2)*[math]::Sin($dla/2)+[math]::Cos([math]::PI/180*$la1)*[math]::Cos([math]::PI/180*$la2)*[math]::Sin($dlo/2)*[math]::Sin($dlo/2); return $R*2*[math]::Atan2([math]::Sqrt($a),[math]::Sqrt(1-$a)) }
$segs=Import-Csv "$dbdir\segments.csv"

# per-line: collect geometry, sample every ~300m
$rawPts=@{}; $mode=@{}
foreach($s in $segs){
  $inner=$s.geometry_wkt -replace '^LINESTRING \(','' -replace '\)$',''
  $pc=@(); foreach($p in ($inner -split ',')){ $xy=$p.Trim() -split '\s+'; $pc+=,@([double]$xy[0],[double]$xy[1]) }
  foreach($ln in ($s.line -split ';')){
    if(-not $rawPts.ContainsKey($ln)){ $rawPts[$ln]=New-Object System.Collections.Generic.List[object]; $mode[$ln]=$s.mode }
    for($i=1;$i -lt $pc.Count;$i++){ [void]$rawPts[$ln].Add($pc[$i-1]); }
    [void]$rawPts[$ln].Add($pc[-1])
  }
}
$pts=@{}; $len=@{}
foreach($ln in $rawPts.Keys){
  $arr=$rawPts[$ln]; $samp=New-Object System.Collections.Generic.List[object]; $acc=999.0; $prev=$null; $tot=0.0
  foreach($p in $arr){ if($prev){ $d=(Hav $prev[1] $prev[0] $p[1] $p[0]); $acc+=$d; $tot+=$d }; if($acc -ge 0.3){ [void]$samp.Add($p); $acc=0.0 }; $prev=$p }
  if($samp.Count -eq 0){ [void]$samp.Add($arr[0]) }
  $pts[$ln]=$samp; $len[$ln]=$tot
}

# global grid of all sampled points (cell ~250m) labeled by line
$cell=0.003; $grid=@{}
foreach($ln in $pts.Keys){ foreach($p in $pts[$ln]){
  $k="{0}|{1}" -f [math]::Floor($p[0]/$cell),[math]::Floor($p[1]/$cell)
  if(-not $grid.ContainsKey($k)){$grid[$k]=New-Object System.Collections.Generic.List[object]}
  [void]$grid[$k].Add(@($ln,$p[0],$p[1])) } }

# coverage[A][B] = fraction of A's points within 250m of some B point
$cov=@{}
foreach($A in $pts.Keys){ $cov[$A]=@{}
  foreach($p in $pts[$A]){
    $cx=[math]::Floor($p[0]/$cell);$cy=[math]::Floor($p[1]/$cell)
    $hit=@{}
    for($dx=-1;$dx -le 1;$dx++){ for($dy=-1;$dy -le 1;$dy++){
      $k="{0}|{1}" -f ($cx+$dx),($cy+$dy)
      if($grid.ContainsKey($k)){ foreach($q in $grid[$k]){ if($q[0] -eq $A){continue}
        if((Hav $p[1] $p[0] $q[2] $q[1])*1000 -le 250){ $hit[$q[0]]=$true } } } } }
    foreach($B in $hit.Keys){ $cov[$A][$B]=[int]$cov[$A][$B]+1 }
  }
}

"== LINE OVERLAP AUDIT (>=60% of shorter line within 250m of another) =="
$seen=@{}; $flags=@()
foreach($A in ($pts.Keys | Sort-Object)){
  foreach($B in $cov[$A].Keys){
    $covAB=$cov[$A][$B]/$pts[$A].Count
    # only report from the SHORTER line's perspective to avoid dup rows
    if($len[$A] -gt $len[$B]){continue}
    if($covAB -ge 0.60){
      $covBA= if($cov[$B].ContainsKey($A)){[math]::Round(100*$cov[$B][$A]/$pts[$B].Count)}else{0}
      $flags+=[pscustomobject]@{shorter=$A;sh_km=[math]::Round($len[$A],1);sh_mode=$mode[$A];longer=$B;lo_km=[math]::Round($len[$B],1);lo_mode=$mode[$B];pct_short_in_long=[math]::Round(100*$covAB);pct_long_in_short=$covBA}
    }
  }
}
if($flags.Count -eq 0){ "  none." }
else{ $flags | Sort-Object -Descending pct_short_in_long | Format-Table shorter,sh_km,sh_mode,longer,lo_km,lo_mode,pct_short_in_long,pct_long_in_short -AutoSize | Out-String -Width 140 }
"`n(pct_short_in_long = how much of the shorter line is buried in the longer one; >=85% ~ true duplicate, 60-85% = heavy shared trunk to review)"