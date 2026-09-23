# Assembles a self-contained delivery archive (app + installer + packaging + tools + verification + SHA256SUMS).
# Usage: powershell -File packaging\assemble-archive.ps1   (paths below are for the 1.0.4 demo archive; bump for future versions)
# Notes for maintainers: the script itself contains Chinese and therefore needs a UTF-8 BOM under Windows PowerShell 5.1.
$ErrorActionPreference='Stop'
$root='D:\AppProject'
$a=Join-Path $root '最终封装交付_1.0.4_演示版'
if(Test-Path -LiteralPath $a){Remove-Item -LiteralPath $a -Recurse -Force}
New-Item -ItemType Directory -Force -Path (Join-Path $a 'installer'),(Join-Path $a 'packaging\libs\webview2'),(Join-Path $a 'verification') | Out-Null
robocopy (Join-Path $root 'dist\FinAgent') (Join-Path $a 'app') /MIR /NFL /NDL /NJH /NJS /NP
if($LASTEXITCODE -ge 8){throw "app mirror failed $LASTEXITCODE"}
Copy-Item -LiteralPath (Join-Path $root 'dist\releases\1.0.4\Experimental\FinAgent-Setup-x64.exe') -Destination (Join-Path $a 'installer')
foreach($f in 'Launcher.cs','finagent.iss','assert-production.mjs'){Copy-Item -LiteralPath (Join-Path $root "packaging\$f") -Destination (Join-Path $a 'packaging')}
Copy-Item -LiteralPath (Join-Path $root 'packaging\rebuild-archive.ps1') -Destination (Join-Path $a 'packaging\rebuild.ps1')
Copy-Item -Path (Join-Path $root 'packaging\libs\webview2\*') -Destination (Join-Path $a 'packaging\libs\webview2')
robocopy (Join-Path $root 'tools\InnoSetup') (Join-Path $a 'tools\InnoSetup') /MIR /NFL /NDL /NJH /NJS /NP
if($LASTEXITCODE -ge 8){throw "tools mirror failed $LASTEXITCODE"}
Copy-Item -LiteralPath (Join-Path $root '最终封装交付_1.0.3_实验版\重新封装.cmd') -Destination $a
# Delivery-facing docs live in the repo so the archive stays reproducible.
$docs=Join-Path $root 'docs\交付说明'
Copy-Item -LiteralPath (Join-Path $docs '目录说明.md') -Destination $a
Copy-Item -LiteralPath (Join-Path $docs '使用说明-演示版.md') -Destination $a
Copy-Item -LiteralPath (Join-Path $docs '安装与卸载说明.txt') -Destination (Join-Path $a 'installer')
Copy-Item -LiteralPath (Join-Path $root 'desktop\ACCEPTANCE.md') -Destination (Join-Path $a 'verification')
$qa=Join-Path $root 'desktop\qa'
function Latest-Dir($pat){Get-ChildItem $qa -Directory -Filter $pat | Sort-Object Name | Select-Object -Last 1}
Copy-Item -LiteralPath (Join-Path (Latest-Dir 'installer-*').FullName 'result.json') -Destination (Join-Path $a 'verification\安装验收.json')
Copy-Item -LiteralPath (Join-Path (Latest-Dir 'experimental-*').FullName 'result.json') -Destination (Join-Path $a 'verification\演示端到端.json')
Copy-Item -LiteralPath (Join-Path (Latest-Dir 'production-*').FullName 'result.json') -Destination (Join-Path $a 'verification\正式隔离.json')
Copy-Item -LiteralPath (Join-Path (Latest-Dir 'export-*').FullName 'result.json') -Destination (Join-Path $a 'verification\导出流程.json')
$mismatch=0;$count=0
Get-ChildItem (Join-Path $root 'dist\FinAgent') -Recurse -File | ForEach-Object {
  $rel=$_.FullName.Substring((Join-Path $root 'dist\FinAgent').Length+1)
  $dst=Join-Path (Join-Path $a 'app') $rel
  $count++
  if(-not (Test-Path -LiteralPath $dst) -or (Get-FileHash -LiteralPath $_.FullName).Hash -ne (Get-FileHash -LiteralPath $dst).Hash){$mismatch++}
}
[ordered]@{sourceFiles=$count;mismatch=$mismatch;status=$(if($mismatch -eq 0){'PASS'}else{'FAIL'})} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $a 'verification\归档核对.json') -Encoding utf8
if($mismatch -ne 0){throw "archive hash mismatch $mismatch"}
$lines=Get-ChildItem $a -Recurse -File | Where-Object {$_.Name -ne 'SHA256SUMS.txt' -and $_.FullName -notmatch '\\rebuilt\\'} | Sort-Object FullName | ForEach-Object {
  $rel=$_.FullName.Substring($a.Length+1)
  (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash+"  "+$rel
}
[System.IO.File]::WriteAllLines((Join-Path $a 'SHA256SUMS.txt'),$lines,(New-Object Text.UTF8Encoding $true))
Write-Output ("archive assembled: "+(Get-ChildItem $a -Recurse -File).Count+" files")
# After assembling: packaging\rebuild.ps1 -ValidateOnly (self-containment) and a full rebuild are run by hand.
