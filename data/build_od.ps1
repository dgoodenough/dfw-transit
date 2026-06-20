$ErrorActionPreference="Stop"
# Stream tx_od.csv.gz -> aggregate home-tract -> work-tract flows, metroplex counties only.
$ddir=$PSScriptRoot
$counties=@('113','439','085','121','397','251','139','367','257')
$cset=New-Object 'System.Collections.Generic.HashSet[string]'
foreach($c in $counties){ [void]$cset.Add($c) }

$fs=[System.IO.File]::OpenRead("$ddir\tx_od.csv.gz")
$gz=New-Object System.IO.Compression.GzipStream($fs,[System.IO.Compression.CompressionMode]::Decompress)
$sr=New-Object System.IO.StreamReader($gz)
[void]$sr.ReadLine()  # header: w_geocode,h_geocode,S000,...
$agg=New-Object 'System.Collections.Generic.Dictionary[string,int]'
$nRows=0; $nKept=0
$sw=[System.Diagnostics.Stopwatch]::StartNew()
while(($line=$sr.ReadLine()) -ne $null){
  $nRows++
  # fast county check on both geocodes before any split
  $wc=$line.Substring(2,3)
  if(-not $cset.Contains($wc)){ continue }
  $ci=$line.IndexOf(',')
  $hc=$line.Substring($ci+3,3)
  if(-not $cset.Contains($hc)){ continue }
  $c2=$line.IndexOf(',',$ci+1)
  $c3=$line.IndexOf(',',$c2+1)
  $wTr=$line.Substring(0,11)
  $hTr=$line.Substring($ci+1,11)
  $s=[int]$line.Substring($c2+1,$c3-$c2-1)
  $key=$hTr+'|'+$wTr
  $cur=0
  if($agg.TryGetValue($key,[ref]$cur)){ $agg[$key]=$cur+$s } else { $agg[$key]=$s }
  $nKept++
}
$sr.Close();$gz.Close();$fs.Close()
"rows: $nRows | metroplex rows: $nKept | tract-pairs: $($agg.Count) | $([math]::Round($sw.Elapsed.TotalSeconds))s"
$out=New-Object System.Text.StringBuilder
[void]$out.AppendLine("h_tract,w_tract,jobs")
foreach($kv in $agg.GetEnumerator()){ $p=$kv.Key.Split('|'); [void]$out.AppendLine("$($p[0]),$($p[1]),$($kv.Value)") }
[System.IO.File]::WriteAllText("$ddir\od_tracts.csv",$out.ToString())
$tot=0; foreach($v in $agg.Values){$tot+=$v}
"total metroplex commute flows: $tot | wrote od_tracts.csv"