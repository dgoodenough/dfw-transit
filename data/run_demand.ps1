$ErrorActionPreference="Stop"
$dir="C:\Users\justd\OneDrive\Documents\Ultiworld\dfw-transit"; $ddir="$dir\data"; $dbdir="$dir\db"
Add-Type -TypeDefinition (Get-Content "$ddir\DemandEngine.cs" -Raw) -Language CSharp

$costPerKm=@{metro=150.0;brt=20.0;commuter=10.0}  # $M/km

"=== FULL 2070 NETWORK ==="
$sw=[System.Diagnostics.Stopwatch]::StartNew()
$e=New-Object DemandEngine
$e.Load("$dbdir\stations.csv","$dbdir\segments.csv","$dbdir\station_lines.csv",$false)
$e.AllPairs(); "all-pairs done $([math]::Round($sw.Elapsed.TotalSeconds))s"
$e.LoadTracts("$ddir\tract_centroids.csv")
$res=$e.RunOD("$ddir\od_tracts.csv",$true)
"full: $res  ($([math]::Round($sw.Elapsed.TotalSeconds))s)"

# line ranking (existing systems = baseline, no build cost)
$existingLines=@('TRE','Texrail','A Train','Orange Line','Green Line','Red Line','Blue Line','Cotton Belt')
$rows=@()
foreach($ln in $e.lineFlow.Keys){
  $fl=[math]::Round($e.lineFlow[$ln])
  $len=[math]::Round($e.lineLenKm[$ln],1); $md=$e.lineMode[$ln]
  $isEx=($existingLines -contains ($ln -replace '^E\d+:',''))
  $cost= if($isEx){0}else{[math]::Round($len*$costPerKm[$md])}
  $bc= if($cost -gt 0){[math]::Round($fl/$cost,2)}else{''}
  $rows+=[pscustomobject]@{line=$ln;mode=$md;status=$(if($isEx){'existing'}else{'proposed'});len_km=$len;cost_M=$cost;competitive_commutes=$fl;commutes_per_Mdollar=$bc}
}
$rows | Sort-Object -Descending competitive_commutes | Export-Csv "$ddir\line_ranking.csv" -NoTypeInformation

# missing corridors
$mc=@()
foreach($k in $e.missing.Keys){ $mc+=[pscustomobject]@{corridor=$k;flows=[math]::Round($e.missing[$k])} }
$mc | Sort-Object -Descending flows | Select-Object -First 30 | Export-Csv "$ddir\missing_corridors.csv" -NoTypeInformation

"=== EXISTING-ONLY (calibration) ==="
$c=New-Object DemandEngine
$c.Load("$dbdir\stations.csv","$dbdir\segments.csv","$dbdir\station_lines.csv",$true)
$c.AllPairs(); $c.LoadTracts("$ddir\tract_centroids.csv")
$calres=$c.RunOD("$ddir\od_tracts.csv",$true)
"existing: $calres"
"existing per-line flows:"
foreach($ln in ($c.lineFlow.Keys | Sort-Object {-$c.lineFlow[$_]})){ "  {0,-14} {1}" -f $ln,[math]::Round($c.lineFlow[$ln]) }

"`nTOP 15 LINES (full network):"
$rows | Sort-Object -Descending competitive_commutes | Select-Object -First 15 | Format-Table line,mode,len_km,cost_M,competitive_commutes,commutes_per_Mdollar -AutoSize | Out-String -Width 120
"TOP 10 MISSING CORRIDORS:"
$mc | Sort-Object -Descending flows | Select-Object -First 10 | ForEach-Object { "  $($_.corridor)  flows=$($_.flows)" }