param([switch]$ValidateOnly)
$ErrorActionPreference='Stop'
$archiveRoot=Split-Path $PSScriptRoot -Parent
$appRoot=Join-Path $archiveRoot 'app'
$flavor=(Get-Content -LiteralPath (Join-Path $appRoot 'build-flavor.txt') -Raw).Trim()
if($flavor -notin @('Production','Experimental')){throw 'Invalid build flavor'}
if($flavor -eq 'Production'){
 & (Join-Path $appRoot 'runtime\node.exe') (Join-Path $PSScriptRoot 'assert-production.mjs') $appRoot
 if($LASTEXITCODE -ne 0){throw 'Production isolation check failed'}
}
Push-Location -LiteralPath $appRoot
try{
 & (Join-Path $appRoot 'runtime\python\python.exe') -B -X utf8 -c "import numpy,onnxruntime,tokenizers,pdfminer,pymupdf; print('Bundled Python OK')"
 if($LASTEXITCODE -ne 0){throw 'Python dependencies failed'}
 & (Join-Path $appRoot 'runtime\node.exe') --input-type=module -e "await import('./desktop/engine.mjs'); console.log('Bundled engine OK');"
 if($LASTEXITCODE -ne 0){throw 'Engine dependencies failed'}
}finally{Pop-Location}
if($ValidateOnly){Write-Output 'Archive validation passed';exit 0}
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$webview2=Join-Path $PSScriptRoot 'libs\webview2'
if(-not (Test-Path -LiteralPath (Join-Path $webview2 'Microsoft.Web.WebView2.Core.dll'))){throw 'Missing WebView2 SDK assemblies under packaging/libs/webview2'}
& $compiler /nologo /target:winexe /platform:x64 /optimize+ /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:"$webview2\Microsoft.Web.WebView2.Core.dll" /reference:"$webview2\Microsoft.Web.WebView2.WinForms.dll" "/out:$appRoot\FinAgent.exe" (Join-Path $PSScriptRoot 'Launcher.cs')
if($LASTEXITCODE -ne 0){throw 'Launcher build failed'}
foreach($name in 'Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll'){Copy-Item -LiteralPath (Join-Path $webview2 $name) -Destination $appRoot -Force}
Copy-Item -LiteralPath (Join-Path $webview2 'WebView2Loader-x64.dll') -Destination (Join-Path $appRoot 'WebView2Loader.dll') -Force
$out=Join-Path $archiveRoot 'rebuilt'
New-Item -ItemType Directory -Force -Path $out | Out-Null
& (Join-Path $archiveRoot 'tools\InnoSetup\ISCC.exe') "/DPackageRoot=$appRoot" "/DOutputRoot=$out" "/DAppFlavor=$flavor" (Join-Path $PSScriptRoot 'finagent.iss')
if($LASTEXITCODE -ne 0){throw 'Installer build failed'}
$hash=Get-FileHash -LiteralPath (Join-Path $out 'FinAgent-Setup-x64.exe') -Algorithm SHA256
($hash.Hash+'  FinAgent-Setup-x64.exe') | Set-Content -LiteralPath (Join-Path $out 'SHA256SUMS.txt') -Encoding utf8
Write-Output "Built: $out"
