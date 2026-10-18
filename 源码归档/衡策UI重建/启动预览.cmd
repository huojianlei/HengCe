@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "D:\dev-env\node\22.22.2\node.exe" (
  "D:\dev-env\node\22.22.2\node.exe" "启动预览.mjs"
) else (
  node "启动预览.mjs"
)
pause
