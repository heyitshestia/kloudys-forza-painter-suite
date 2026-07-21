@echo off
setlocal EnableExtensions EnableDelayedExpansion
title KFPS FH6 6-Step Locator Calibrator
cd /d "%~dp0"

echo KFPS FH6 6-Step Locator Calibrator
echo.
echo READ-ONLY. This scans FH6 memory and saves locator evidence.
echo It does not write to Forza.
echo.
echo Before continuing:
echo   1. Open Forza Horizon 6.
echo   2. Open a flat, ungrouped 3000-layer plain circle template.
echo   3. Keep the vinyl editor open.
echo.
echo Automatic shared-profile publication:
echo   Uses the KFPS Cloudflare relay. GitHub and GitHub CLI are not required.
echo   The first run enrolls this Windows account from rtti-enrollment.json.
echo   Publication only occurs after one profile passes all six scans.
echo.

if exist "%~dp0KFPS_FH6_Locator_Calibrator.exe" (
  "%~dp0KFPS_FH6_Locator_Calibrator.exe" %*
  set "RESULT=!ERRORLEVEL!"
  goto :finished
)

set "PY_EXE="
set "PY_ARGS="
if exist "%~dp0python\python.exe" set "PY_EXE=%~dp0python\python.exe"
if not defined PY_EXE (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PY_EXE=py"
    set "PY_ARGS=-3"
  )
)
if not defined PY_EXE (
  where python >nul 2>nul
  if not errorlevel 1 set "PY_EXE=python"
)
if not defined PY_EXE (
  echo Python was not found.
  echo Run this on a machine with KFPS standalone Python or install Python 3.12.
  pause
  exit /b 1
)

"%PY_EXE%" %PY_ARGS% "%~dp0kfps_fh6_six_step_locator_calibrator.py" %*
set "RESULT=%ERRORLEVEL%"

:finished
echo.
if "%RESULT%"=="0" (
  echo Calibrator completed successfully.
) else if "%RESULT%"=="2" (
  echo Calibration succeeded, but automatic publication needs attention.
  echo Ask the KFPS administrator to check or reset this helper enrollment.
) else (
  echo Calibrator stopped or did not produce one publishable six-scan profile.
)
pause
exit /b %RESULT%
