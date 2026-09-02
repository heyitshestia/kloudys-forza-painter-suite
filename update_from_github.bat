@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "APP_DIR_NAME=%%~nxI"
if exist "%SCRIPT_DIR%..\KFPS-Updater.exe" (
    "%SCRIPT_DIR%..\KFPS-Updater.exe" --root "%SCRIPT_DIR%.." --relaunch %*
    if not errorlevel 1 exit /b 0
    set "OUTER_ERROR=!ERRORLEVEL!"
    if !OUTER_ERROR! EQU 5 goto outer_launch_failed
    if !OUTER_ERROR! EQU 193 goto outer_launch_failed
    if !OUTER_ERROR! EQU 216 goto outer_launch_failed
    if !OUTER_ERROR! EQU 9009 goto outer_launch_failed
    exit /b !OUTER_ERROR!
)
:try_inner
if /I "%APP_DIR_NAME%"=="KloudysFH6Painter" if exist "%SCRIPT_DIR%KFPS-Updater.exe" (
    "%SCRIPT_DIR%KFPS-Updater.exe" --root "%SCRIPT_DIR%.." --relaunch %*
    exit /b !ERRORLEVEL!
)
call "%SCRIPT_DIR%03_update_from_github.bat" %*
exit /b %ERRORLEVEL%

:outer_launch_failed
if /I "%APP_DIR_NAME%"=="KloudysFH6Painter" if exist "%SCRIPT_DIR%KFPS-Updater.exe" goto try_inner_after_outer
exit /b !OUTER_ERROR!

:try_inner_after_outer
echo Outer bootstrap updater failed; retrying the independently repairable inner copy.
"%SCRIPT_DIR%KFPS-Updater.exe" --root "%SCRIPT_DIR%.." --relaunch %*
exit /b %ERRORLEVEL%
