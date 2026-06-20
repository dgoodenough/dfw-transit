$ErrorActionPreference="Stop"
$ddir=$PSScriptRoot
# metroplex counties: Dallas 113, Tarrant 439, Collin 085, Denton 121, Rockwall 397, Johnson 251, Ellis 139, Parker 367, Kaufman 257
$counties='113','439','085','121','397','251','139','367','257'
$cset=@{}; foreach($c in $counties){ $cset[$c]=$true }

# BG centroids + population
$bg=@{}
Get-Content "$ddir\CenPop2020_BG_TX.txt" | Select-Object -Skip 1 | ForEach-Object {
  $p=$_ -split ','
  if($p.Count -ge 7 -and $cset.ContainsKey($p[1])){
    $geoid=$p[0]+$p[1]+$p[2]+$p[3]
    $bg[$geoid]=[pscustomobject]@{Pop=[int]$p[4];Lat=[double]$p[5];Lon=[double]$p[6];Jobs=0}
  }
}
"BG centroids (metroplex): $($bg.Count)"

# jobs from LODES, aggregate to BG
$fs=[System.IO.File]::OpenRead("$ddir\tx_wac.csv.gz")
$gz=New-Object System.IO.Compression.GzipStream($fs,[System.IO.Compression.CompressionMode]::Decompress)
$sr=New-Object System.IO.StreamReader($gz)
$header=$sr.ReadLine() -split ','
$iGeo=[array]::IndexOf($header,'w_geocode'); $iC000=[array]::IndexOf($header,'C000')
$tot=0
while(($line=$sr.ReadLine()) -ne $null){
  if($line.StartsWith('48')){
    $cty=$line.Substring(2,3)
    if($cset.ContainsKey($cty)){
      $p=$line -split ','
      $g=$p[$iGeo].Substring(0,12)
      if($bg.ContainsKey($g)){ $bg[$g].Jobs += [int]$p[$iC000]; $tot+=[int]$p[$iC000] }
    }
  }
}
$sr.Close();$gz.Close();$fs.Close()
"jobs total (metroplex): $tot"

$out=@()
foreach($k in $bg.Keys){ $b=$bg[$k]; $out+=[pscustomobject]@{geoid=$k;pop=$b.Pop;jobs=$b.Jobs;lat=$b.Lat;lon=$b.Lon} }
$out | Export-Csv "$ddir\metroplex_density.csv" -NoTypeInformation
"wrote metroplex_density.csv ($($out.Count) BGs)"