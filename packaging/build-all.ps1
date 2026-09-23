param([string]$Destination='', [switch]$SkipRuntime, [ValidateSet('Production','Experimental')][string]$Flavor='Production')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$sharedRoot=Split-Path $projectRoot -Parent
$env:TEMP=Join-Path $projectRoot '临时'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
if(-not $Destination){$Destination=Join-Path $projectRoot $(if($Flavor -eq 'Experimental'){'dist\FinAgent'}else{'dist\FinAgent-Production'})}
$packageRoot=[IO.Path]::GetFullPath($Destination)
if(-not $packageRoot.StartsWith([IO.Path]::GetFullPath((Join-Path $projectRoot 'dist'))+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw '构建目标必须位于项目 dist 子目录'}
New-Item -ItemType Directory -Force $packageRoot,(Join-Path $packageRoot 'runtime'),(Join-Path $packageRoot 'desktop'),(Join-Path $packageRoot 'kb2'),(Join-Path $packageRoot 'fenxi'),(Join-Path $packageRoot 'algo'),(Join-Path $packageRoot 'release plugin(1)\release plugin') | Out-Null
# Copy only audited core files needed by the desktop adapter; no mutable database generation.
Copy-Item -LiteralPath (Join-Path $projectRoot 'release plugin(1)\release plugin\src') -Destination (Join-Path $packageRoot 'release plugin(1)\release plugin') -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'release plugin(1)\release plugin\package.json') -Destination (Join-Path $packageRoot 'release plugin(1)\release plugin') -Force
foreach($name in 'server.mjs','engine.mjs','bridge.py','ai-boundary.mjs','ai_worker.py','package.json'){Copy-Item -LiteralPath (Join-Path $projectRoot "desktop\$name") -Destination (Join-Path $packageRoot 'desktop') -Force}
& node (Join-Path $PSScriptRoot 'prepare-desktop.mjs') $packageRoot $Flavor
if($LASTEXITCODE -ne 0){throw '桌面资源隔离构建失败'}
if($Flavor -eq 'Experimental'){
 foreach($name in '演示底稿-预算基础.xlsx','演示底稿-实时经营.xlsx'){
  Copy-Item -LiteralPath (Join-Path $projectRoot "desktop\experimental\$name") -Destination (Join-Path $packageRoot 'desktop\experimental') -Force
 }
}
foreach($name in 'query_kb2.py','build_kb2.py','guanli_ku.sqlite'){Copy-Item -LiteralPath (Join-Path $sharedRoot "kb2\$name") -Destination (Join-Path $packageRoot 'kb2') -Force}
Copy-Item -LiteralPath (Join-Path $sharedRoot 'kb2\models') -Destination (Join-Path $packageRoot 'kb2') -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'fenxi\analysis_generator.py') -Destination (Join-Path $packageRoot 'fenxi') -Force
foreach($name in 'model_api.py','data_ingest.py','excel_contract.py','xlsx_reader.py','excel_ingest.py','excel_generate.py','external_templates.py','external_generate.py'){Copy-Item -LiteralPath (Join-Path $projectRoot "algo\$name") -Destination (Join-Path $packageRoot 'algo') -Force}
foreach($name in '模板结构规范-预算基础.json','模板结构规范-实时经营.json','数值黑名单哈希.json'){Copy-Item -LiteralPath (Join-Path $projectRoot "desktop\templates\$name") -Destination (Join-Path $packageRoot 'desktop\templates') -Force}
Copy-Item -LiteralPath (Join-Path $projectRoot 'desktop\README.md') -Destination (Join-Path $packageRoot '使用说明.md') -Force
$nodePath=(Get-Command node.exe).Source
Copy-Item -LiteralPath $nodePath -Destination (Join-Path $packageRoot 'runtime\node.exe') -Force
if(-not $SkipRuntime){
 & (Join-Path $sharedRoot 'kb\env\Scripts\python.exe') -X utf8 (Join-Path $PSScriptRoot 'bundle-runtime.py') (Join-Path $packageRoot 'runtime\python')
 if($LASTEXITCODE -ne 0){throw 'Python runtime 打包失败'}
}
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$webview2=Join-Path $PSScriptRoot 'libs\webview2'
$appIcon=Join-Path $PSScriptRoot 'assets\衡策图标.ico'
if(-not (Test-Path -LiteralPath $appIcon)){throw '缺少用户指定的衡策图标，请先运行 packaging/prepare-icon.ps1'}
Copy-Item -LiteralPath $appIcon -Destination (Join-Path $packageRoot '衡策图标.ico') -Force
foreach($name in 'Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll','WebView2Loader-x64.dll'){if(-not (Test-Path -LiteralPath (Join-Path $webview2 $name))){throw "缺少 WebView2 SDK 程序集 $name；请参照 packaging/libs/webview2/VERSION.txt 下载并解包"}}
& $compiler /nologo /target:winexe /platform:x64 /optimize+ "/win32icon:$appIcon" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:"$webview2\Microsoft.Web.WebView2.Core.dll" /reference:"$webview2\Microsoft.Web.WebView2.WinForms.dll" "/out:$packageRoot\FinAgent.exe" (Join-Path $PSScriptRoot 'Launcher.cs')
if($LASTEXITCODE -ne 0){throw '启动器编译失败'}
# Managed assemblies and the x64 native loader must sit next to FinAgent.exe at runtime.
foreach($name in 'Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll'){Copy-Item -LiteralPath (Join-Path $webview2 $name) -Destination $packageRoot -Force}
Copy-Item -LiteralPath (Join-Path $webview2 'WebView2Loader-x64.dll') -Destination (Join-Path $packageRoot 'WebView2Loader.dll') -Force
# The installed package validates its own copied runtime, not PATH or a developer virtualenv.
& (Join-Path $packageRoot 'runtime\python\python.exe') -X utf8 -c "import numpy,onnxruntime,tokenizers,pdfminer,pymupdf; print('Packaged Python imports OK')"
if($LASTEXITCODE -ne 0){throw '便携 Python 验证失败'}
Push-Location -LiteralPath $packageRoot
try { & (Join-Path $packageRoot 'runtime\node.exe') --input-type=module -e "await import('./desktop/engine.mjs'); console.log('Packaged engine imports OK');" 2>&1 | Write-Output }
finally { Pop-Location }
if($LASTEXITCODE -ne 0){throw '打包后计算验证失败；请从包目录执行构建验证'}
if($Flavor -eq 'Production'){
 & (Join-Path $packageRoot 'runtime\node.exe') (Join-Path $PSScriptRoot 'assert-production.mjs') $packageRoot
 if($LASTEXITCODE -ne 0){throw '正式包隔离验证失败；本地生成模型组件禁止交付'}
}
Write-Output "完成：$packageRoot\FinAgent.exe"
