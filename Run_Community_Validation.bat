@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo KFPS Community Validation
echo =========================
echo This checks a disposable local Community service and does not alter production.
echo.

set "KFPS_TEST_PYTHON=%~dp0python\python.exe"
if exist "%KFPS_TEST_PYTHON%" goto run_test

where py >nul 2>nul
if errorlevel 1 goto missing_python
set "KFPS_TEST_PYTHON=py"
set "KFPS_TEST_PYTHON_ARGS=-3.12"

:run_test
set "KFPS_TEST_NODE_ROOT=%~dp0tools\community_worker\.node"
if exist "%KFPS_TEST_NODE_ROOT%\node.exe" (
  set "PATH=%KFPS_TEST_NODE_ROOT%;%PATH%"
)

where node >nul 2>nul
if errorlevel 1 goto missing_node
where npm >nul 2>nul
if errorlevel 1 goto missing_node

if not defined KFPS_TEST_REPETITIONS set "KFPS_TEST_REPETITIONS=3"
"%KFPS_TEST_PYTHON%" %KFPS_TEST_PYTHON_ARGS% tools\community_worker\tools\run_community_test_bundle.py --repetitions %KFPS_TEST_REPETITIONS%
set "exit_code=%ERRORLEVEL%"
echo.
if "%exit_code%"=="0" (
  echo Validation passed. Send the ZIP shown above with your test report.
) else (
  echo Validation failed. Send the ZIP shown above so the failure can be diagnosed.
)
if not "%KFPS_TEST_NO_PAUSE%"=="1" pause
exit /b %exit_code%

:missing_python
echo Python 3.12 was not found. Use the bundled KFPS test package or install Python 3.12.
if not "%KFPS_TEST_NO_PAUSE%"=="1" pause
exit /b 2

:missing_node
echo The portable Node.js validation runtime was not found.
echo Use the complete bundled Community test package. Normal KFPS operation does not require Node.js.
if not "%KFPS_TEST_NO_PAUSE%"=="1" pause
exit /b 2
