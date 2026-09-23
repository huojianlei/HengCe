# Regenerates SHA256SUMS.txt for a delivery archive (excludes SHA256SUMS.txt itself and any rebuilt\ output).
# Run after editing archive documents. Contains Chinese -> keep the UTF-8 BOM.
param([string]$Archive='D:\AppProject\最终封装交付_1.0.4_演示版')
$ErrorActionPreference='Stop'
if(-not (Test-Path -LiteralPath $Archive)){throw "archive not found: $Archive"}
$lines=Get-ChildItem $Archive -Recurse -File | Where-Object {$_.Name -ne 'SHA256SUMS.txt' -and $_.FullName -notmatch '\\rebuilt\\'} | Sort-Object FullName | ForEach-Object {
  $rel=$_.FullName.Substring($Archive.Length+1)
  (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash+"  "+$rel
}
[System.IO.File]::WriteAllLines((Join-Path $Archive 'SHA256SUMS.txt'),$lines,(New-Object Text.UTF8Encoding $true))
Write-Output ("sha entries: "+$lines.Count)
