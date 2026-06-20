$ErrorActionPreference="Stop"
$dir=$PSScriptRoot
$kmlPath="C:\Users\justd\Downloads\FW_Subway_extracted\doc.kml"

function SegInt([double]$ax,[double]$ay,[double]$bx,[double]$by,[double]$cx,[double]$cy,[double]$dx,[double]$dy){
  $r1=$bx-$ax; $r2=$by-$ay; $s1=$dx-$cx; $s2=$dy-$cy
  $den=$r1*$s2 - $r2*$s1
  if([math]::Abs($den) -lt 1e-12){return $null}
  $t=(($cx-$ax)*$s2 - ($cy-$ay)*$s1)/$den
  $u=(($cx-$ax)*$r2 - ($cy-$ay)*$r1)/$den
  if($t -ge 0 -and $t -le 1 -and $u -ge 0 -and $u -le 1){
    return [pscustomobject]@{X=$ax+$t*$r1; Y=$ay+$t*$r2}
  }
  return $null
}

# rivers
$riv=Get-Content "$dir\fw_rivers.json" -Raw | ConvertFrom-Json
$rivers=@()
foreach($el in $riv.elements){
  if($el.geometry){
    $nm= if($el.tags.name){[string]$el.tags.name}else{'(unnamed)'}
    $xs=@();$ys=@()
    foreach($g in $el.geometry){$xs+=[double]$g.lon;$ys+=[double]$g.lat}
    $rivers+=[pscustomobject]@{Name=$nm;Xs=$xs;Ys=$ys;N=$xs.Count}
  }
}

[xml]$kml=Get-Content $kmlPath
$ns=New-Object System.Xml.XmlNamespaceManager($kml.NameTable);$ns.AddNamespace('k','http://www.opengis.net/kml/2.2')
$want=@('Main St Line','Green Line','Blue Line','blue line ctd','Orange Line','orange line continued')
$lab=@{'Main St Line'='Purple (Meacham->La Gran Plaza)';'Green Line'='Teal (E-W backbone)';'Blue Line'='Blue East (Handley->dt)';'blue line ctd'='Blue West (dt->Ridgmar)';'Orange Line'='Orange South (dt->Waterside)';'orange line continued'='Orange North (dt->Meacham)'}

"===== RIVER CROSSINGS (computed: line geometry x OSM waterways) ====="
foreach($pm in $kml.SelectNodes('//k:Placemark',$ns)){
  $nm=$pm.SelectSingleNode('k:name',$ns).InnerText
  if($want -contains $nm){
    $ls=$pm.SelectSingleNode('k:LineString/k:coordinates',$ns)
    $lx=@();$ly=@()
    foreach($c in ($ls.InnerText.Trim() -split '\s+')){$a=$c -split ',';$lx+=[double]$a[0];$ly+=[double]$a[1]}
    $cr=@()
    for($i=0;$i -lt $lx.Count-1;$i++){
      foreach($rv in $rivers){
        for($j=0;$j -lt $rv.N-1;$j++){
          $ip=SegInt $lx[$i] $ly[$i] $lx[$i+1] $ly[$i+1] $rv.Xs[$j] $rv.Ys[$j] $rv.Xs[$j+1] $rv.Ys[$j+1]
          if($ip -ne $null){ $cr+=[pscustomobject]@{River=$rv.Name;Lat=[math]::Round($ip.Y,4);Lon=[math]::Round($ip.X,4)} }
        }
      }
    }
    "`n{0}" -f $lab[$nm]
    if($cr.Count -eq 0){"      (no river crossings)"}
    else{ $cr | Group-Object River | ForEach-Object { "      {0} x{1}  [{2}]" -f $_.Name,$_.Count, (($_.Group | ForEach-Object {"$($_.Lat),$($_.Lon)"}) -join ' ; ') } }
  }
}
