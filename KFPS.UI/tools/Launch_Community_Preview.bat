@echo off
setlocal
pushd "%~dp0..\.."
"python\python.exe" "KFPS.UI\tools\community_preview.py"
if errorlevel 1 pause
popd
