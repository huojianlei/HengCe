param([string]$Package='D:\AppProject\dist\FinAgent-Production', [string]$Compiler='', [string]$OutputDirectory='', [switch]$ZipOnly)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$env:TEMP=Join-Path $projectRoot '临时'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
$outputRoot=Join-Path $projectRoot 'dist'
$distRoot=$outputRoot
if($OutputDirectory){$outputRoot=[IO.Path]::GetFullPath($OutputDirectory);if(-not $outputRoot.StartsWith($distRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw '安装包输出必须位于 dist 子目录'}}
$packageRoot=[IO.Path]::GetFullPath($Package)
if(-not $packageRoot.StartsWith([IO.Path]::GetFullPath($distRoot)+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw '打包源必须位于项目 dist 子目录'}
$flavor=(Get-Content -LiteralPath (Join-Path $packageRoot 'build-flavor.txt') -Raw).Trim()
if($flavor -notin @('Production','Experimental')){throw '缺少有效构建版本标识'}
if($flavor -eq 'Production'){
 & (Join-Path $packageRoot 'runtime\node.exe') (Join-Path $PSScriptRoot 'assert-production.mjs') $packageRoot
 if($LASTEXITCODE -ne 0){throw '正式包隔离检查失败，拒绝封装'}
}
if(-not $Compiler){$Compiler=Join-Path (Split-Path $projectRoot -Parent) 'tools\InnoSetup\ISCC.exe'}
if(-not (Test-Path -LiteralPath $Compiler)){throw '缺少 Inno Setup 编译器；请参考 packaging/README.md 安装便携编译器'}
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
if(-not $ZipOnly){
 & $Compiler "/DPackageRoot=$packageRoot" "/DOutputRoot=$outputRoot" "/DAppFlavor=$flavor" (Join-Path $PSScriptRoot 'finagent.iss')
 if($LASTEXITCODE -ne 0){throw '标准 Windows 安装器编译失败'}
}elseif(-not (Test-Path -LiteralPath (Join-Path $outputRoot '衡策-1.0.5-安装包.exe'))){throw 'ZipOnly 需要已有的本轮安装器'}
$zipPath=Join-Path $outputRoot '衡策-1.0.5-便携包.zip'
$setupPath=Join-Path $outputRoot '衡策-1.0.5-安装包.exe'
Add-Type -AssemblyName System.IO.Compression.FileSystem
if(Test-Path -LiteralPath $zipPath){Remove-Item -LiteralPath $zipPath}
$zipStream=[IO.File]::Open($zipPath,[IO.FileMode]::CreateNew)
try {
 $zipArchive=[IO.Compression.ZipArchive]::new($zipStream,[IO.Compression.ZipArchiveMode]::Create,$false)
 try {
  Get-ChildItem -LiteralPath $packageRoot -File -Recurse | Where-Object { $_.FullName -notmatch '[\\/](qa-模板包内验证|__pycache__)[\\/]|\.pyc$' } | ForEach-Object {
   $relative=$_.FullName.Substring($packageRoot.Length+1).Replace('\','/')
   [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zipArchive,$_.FullName,$relative,[IO.Compression.CompressionLevel]::Optimal) | Out-Null
  }
 } finally { $zipArchive.Dispose() }
} finally { $zipStream.Dispose() }
Get-FileHash -Algorithm SHA256 -LiteralPath $setupPath,$zipPath | ForEach-Object {"$($_.Hash)  $([IO.Path]::GetFileName($_.Path))"} | Set-Content -LiteralPath (Join-Path $outputRoot '文件校验清单.txt') -Encoding utf8
Get-Item -LiteralPath $setupPath,$zipPath | Select-Object Name,Length
