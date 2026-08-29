@echo off
setlocal
for %%I in ("%~dp0..\..") do set "KFPS_ROOT=%%~fI"

if not exist "%KFPS_ROOT%\KFPS.exe" (
    echo KFPS.exe was not found at "%KFPS_ROOT%".
    exit /b 1
)

set "KFPS_FORCE_LOCAL_RTTI_RECOVERY=1"
start "" "%KFPS_ROOT%\KFPS.exe"
