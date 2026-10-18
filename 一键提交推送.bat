@echo off
rem ============================================================
rem 衡策插件仓（HengCe）· 一键提交推送（双击即可）
rem ============================================================
cd /d %~dp0
set HTTPS_PROXY=http://127.0.0.1:19828
set HTTP_PROXY=http://127.0.0.1:19828

echo [1/2] 提交并推送…
git add -A
git commit -m "插件线修复：字节协议/期间缺省/背景置脏/挂载三法与包名可移植"
git push

echo [2/2] 完成！仓库：https://github.com/huojianlei/HengCe
pause
