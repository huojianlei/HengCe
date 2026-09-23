# Uses only a new project-local QA directory and this installer AppId; no real financial data or remote model calls.
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$qaRoot=Join-Path $projectRoot ('desktop\qa\installer-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
$installRoot=Join-Path $qaRoot '程序 安装'
$dataRoot=Join-Path $qaRoot '用户 数据'
$registryPath='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7097AF0-A718-476E-9629-0629608478EF}_is1'
if(Test-Path -LiteralPath $registryPath){throw '已有同 AppId 的安装，本脚本不会覆盖或卸载已有安装'}
if(-not ([IO.Path]::GetFullPath($installRoot).StartsWith([IO.Path]::GetFullPath((Join-Path $projectRoot 'desktop\qa'))+'\',[StringComparison]::OrdinalIgnoreCase))){throw 'QA 目录越界'}
New-Item -ItemType Directory -Path $qaRoot -Force | Out-Null
$setupPath=Join-Path $projectRoot 'dist\releases\1.0.4\Production\FinAgent-Setup-x64.exe'
$groupName='衡策'
$desktopShortcut=Join-Path ([Environment]::GetFolderPath('Desktop')) '衡策.lnk'
$testDesktop=-not (Test-Path -LiteralPath $desktopShortcut)
$taskOption=if($testDesktop){'/TASKS="desktopicon"'}else{'/TASKS="!desktopicon"'}
$arguments='/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="'+$installRoot+'" /GROUP="'+$groupName+'" '+$taskOption
$result=[ordered]@{setupSHA256=(Get-FileHash -LiteralPath $setupPath).Hash;installRoot=$installRoot;dataRoot=$dataRoot}
function Assert($condition,$message){if(-not $condition){throw $message}}
function Install-Package($phase){
 $p=Start-Process -FilePath $setupPath -ArgumentList ($arguments+' /LOG="'+$qaRoot+'\'+$phase+'.log"') -WindowStyle Hidden -Wait -PassThru
 Assert ($p.ExitCode -eq 0) ($phase+' exit '+$p.ExitCode)
}
$launcher=$null
try {
 Install-Package 'install'
 $uninstaller=Join-Path $installRoot 'unins000.exe'
 Assert (Test-Path -LiteralPath $uninstaller) '缺少卸载 EXE'
 $registered=Get-ItemProperty -LiteralPath $registryPath
 Assert ($registered.DisplayVersion -eq '1.0.4') '安装版本不符'
 Assert ($registered.UninstallString.Contains($installRoot)) '卸载登记路径错误'
 Assert ($registered.QuietUninstallString.Contains('/SILENT')) '缺少静默卸载登记'
 $groupPath=Join-Path ([Environment]::GetFolderPath('Programs')) $groupName
 Assert (Test-Path -LiteralPath (Join-Path $groupPath '衡策.lnk')) '缺少开始菜单入口'
 Assert (Test-Path -LiteralPath (Join-Path $groupPath '卸载衡策.lnk')) '缺少开始菜单卸载入口'
 if($testDesktop){Assert (Test-Path -LiteralPath $desktopShortcut) '缺少桌面入口'}
 $result.install='PASS';$result.desktopShortcut=if($testDesktop){'PASS'}else{'SKIPPED_EXISTING_SHORTCUT'}
 $outputRoot=Join-Path $installRoot '用户自定义报告'
 New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
 $sentinel=Join-Path $outputRoot '请保留.txt'
 'user-owned-report' | Set-Content -LiteralPath $sentinel -Encoding utf8
 Install-Package 'upgrade'
 Assert ((Get-Content -LiteralPath $sentinel -Raw).Trim() -eq 'user-owned-report') '覆盖安装修改用户文件'
 Assert ((Get-FileHash -LiteralPath (Join-Path $installRoot 'FinAgent.exe')).Hash -eq (Get-FileHash -LiteralPath (Join-Path $projectRoot 'dist\FinAgent\FinAgent.exe')).Hash) '安装内容与包不一致'
 $result.upgrade='PASS'
 # Reserve an unused loopback port, then launch only this test installation.
 $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
 $listener.Start();$port=$listener.LocalEndpoint.Port;$listener.Stop()
 $env:FINAGENT_DATA_DIR=$dataRoot;$env:FINAGENT_PORT=[string]$port
 $env:FINAGENT_PYTHON=Join-Path $installRoot 'runtime\python\python.exe'
 $launcher=Start-Process -FilePath (Join-Path $installRoot 'FinAgent.exe') -WorkingDirectory $installRoot -WindowStyle Hidden -PassThru
 $url='http://127.0.0.1:'+ $port
 $bootstrap=$null
 for($i=0;$i -lt 40;$i++){
  try{$bootstrap=Invoke-RestMethod -Uri ($url+'/api/bootstrap') -TimeoutSec 2;break}catch{Start-Sleep -Milliseconds 500}
 }
 Assert ($null -ne $bootstrap) '实际 EXE 启动未就绪'
 $headers=@{'X-Finagent-Token'=$bootstrap.token}
 Invoke-RestMethod -Uri ($url+'/api/settings') -Method Post -ContentType 'application/json; charset=utf-8' -Headers $headers -Body (@{outputDir=$outputRoot}|ConvertTo-Json) | Out-Null
 $demo=Get-Content -LiteralPath (Join-Path $installRoot 'desktop\web\demo.json') -Raw -Encoding utf8
 $calculation=Invoke-RestMethod -Uri ($url+'/api/analyze') -Method Post -ContentType 'application/json; charset=utf-8' -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes($demo)) -TimeoutSec 60
 Assert ($calculation.result.variance.xiang.Count -eq 5) '模拟计算结果不符'
 $search=Invoke-RestMethod -Uri ($url+'/api/search') -Method Post -ContentType 'application/json; charset=utf-8' -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes('{"query":"预算执行分析"}')) -TimeoutSec 240
 Assert ($search.references.Count -eq 4) '本地知识库检索结果不符'
 $result.launcher='PASS';$result.calculationRows=5;$result.knowledgeReferences=$search.references.Count
 # The live app mutex must reject silent uninstall without stopping or removing the app.
 $blocked=Start-Process -FilePath $uninstaller -ArgumentList ('/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="'+$qaRoot+'\uninstall-running.log"') -WindowStyle Hidden -Wait -PassThru
 Assert ($blocked.ExitCode -ne 0) '运行中卸载没有被阻止'
 Assert (Test-Path -LiteralPath (Join-Path $installRoot 'FinAgent.exe')) '运行中卸载删除了程序'
 $result.runningUninstallBlocked='PASS'
 & taskkill.exe /PID $launcher.Id /T /F | Out-Null
 $launcher=$null
 Start-Sleep -Milliseconds 700
 $uninstall=Start-Process -FilePath $uninstaller -ArgumentList ('/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="'+$qaRoot+'\uninstall.log"') -WindowStyle Hidden -Wait -PassThru
 Assert ($uninstall.ExitCode -eq 0) ('卸载失败 '+$uninstall.ExitCode)
 Assert (-not (Test-Path -LiteralPath (Join-Path $installRoot 'FinAgent.exe'))) '卸载未移除程序'
 Assert (-not (Test-Path -LiteralPath $registryPath)) '卸载登记残留'
 Assert (-not (Test-Path -LiteralPath (Join-Path $groupPath '衡策.lnk'))) '开始菜单残留'
 if($testDesktop){Assert (-not (Test-Path -LiteralPath $desktopShortcut)) '桌面入口残留'}
 Assert ((Get-Content -LiteralPath $sentinel -Raw).Trim() -eq 'user-owned-report') '卸载删除用户文件'
 Assert (Test-Path -LiteralPath (Join-Path $dataRoot 'last-session.json')) '卸载删除用户会话'
 Assert (Test-Path -LiteralPath (Join-Path $outputRoot ($calculation.result.id+'.json'))) '卸载删除分析报告'
 $result.uninstall='PASS';$result.userDataPreserved='PASS'
} finally {
 if($null -ne $launcher -and -not $launcher.HasExited){& taskkill.exe /PID $launcher.Id /T /F | Out-Null}
 $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $qaRoot 'result.json') -Encoding utf8
 Write-Output $qaRoot
}
