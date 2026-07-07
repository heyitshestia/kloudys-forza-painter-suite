@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not defined REPO_URL set "REPO_URL=https://github.com/heyitshestia/kloudys-forza-painter-suite.git"
if not defined BRANCH set "BRANCH=main"

if not defined KFPS_UPDATER_REMOTE_BOOTSTRAP (
    set "KFPS_UPDATER_REMOTE_BOOTSTRAP=1"
    if not defined KFPS_UPDATER_ROOT set "KFPS_UPDATER_ROOT=%CD%"
    set "KFPS_UPDATER_TEMP=%TEMP%\kfps-latest-updater-%RANDOM%-%RANDOM%.bat"
    set "KFPS_REMOTE_UPDATER_URL="
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$repo=$env:REPO_URL; $branch=$env:BRANCH; if($repo -match 'github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)(\.git)?$'){ $url='https://raw.githubusercontent.com/' + $Matches.owner + '/' + $Matches.repo + '/' + $branch + '/03_update_from_github.bat'; $content=(Invoke-WebRequest -UseBasicParsing -Uri $url -Headers @{'User-Agent'='KFPS-Updater'}).Content; $content=$content -replace '\r?\n', [Environment]::NewLine; [IO.File]::WriteAllText($env:KFPS_UPDATER_TEMP, $content, [Text.Encoding]::ASCII); exit 0 }; exit 1" >nul 2>nul
    if exist "!KFPS_UPDATER_TEMP!" (
        call "!KFPS_UPDATER_TEMP!"
        set "KFPS_UPDATER_EXIT=!ERRORLEVEL!"
        del /f /q "!KFPS_UPDATER_TEMP!" >nul 2>nul
        exit /b !KFPS_UPDATER_EXIT!
    )
)

if not defined KFPS_UPDATER_HANDOFF (
    set "KFPS_UPDATER_HANDOFF=1"
    if not defined KFPS_UPDATER_ROOT set "KFPS_UPDATER_ROOT=%CD%"
    set "KFPS_UPDATER_TEMP=%TEMP%\kfps-updater-handoff-%RANDOM%-%RANDOM%.bat"
    copy /y "%~f0" "!KFPS_UPDATER_TEMP!" >nul
    if errorlevel 1 (
        echo Failed to create updater handoff copy.
        exit /b 1
    )
    call "!KFPS_UPDATER_TEMP!"
    set "KFPS_UPDATER_EXIT=!ERRORLEVEL!"
    del /f /q "!KFPS_UPDATER_TEMP!" >nul 2>nul
    exit /b !KFPS_UPDATER_EXIT!
)

if defined KFPS_UPDATER_ROOT cd /d "%KFPS_UPDATER_ROOT%"

call :resolve_update_root
if errorlevel 1 exit /b 1

call :init_update_log
call :capture_current_version OLD_VERSION

call :log "KFPS Launcher updater"
call :log ""
call :log "Use this batch file exclusively for updates."
call :log "Close the app before continuing."
call :log "This updates program files from GitHub and preserves generated/runtime data."
call :log "Current version: !OLD_VERSION!"
call :log "Log file: !UPDATE_LOG!"
call :log ""

call :ensure_git
if errorlevel 1 goto :fail
call :check_update_locks
if errorlevel 1 goto :fail_quiet

if exist ".git\" (
    call :log "Git checkout detected. Syncing tracked app files to latest %BRANCH%..."
    git fetch origin %BRANCH%
    if errorlevel 1 goto :fail
    call :backup_existing_files
    if errorlevel 1 goto :fail
    git reset --hard origin/%BRANCH%
    if errorlevel 1 (
        call :log ""
        call :log "Update failed because Git could not reset this folder to the latest version."
        call :log "Generated outputs are stored separately and are not intentionally removed."
        goto :fail
    )
    git clean -fdx -e runtime/ -e imgs/ -e webui-data/ -e python/ -e "*.kfpskey"
    if errorlevel 1 (
        call :log "Warning: Git cleanup of untracked program files reported an error."
    )
    call :write_build_commit "%CD%"
    call :verify_program_file_sync "%CD%"
    if errorlevel 1 goto :fail
    call :cleanup_retired_files
    call :verify_retired_files_removed
    if errorlevel 1 goto :fail
    goto :done
)

call :log "This folder is not a Git checkout."
call :log "A fresh copy will be downloaded and copied over this folder, like dragging new files over old ones."
call :log "Existing generated/runtime data will be preserved."
call :log ""

set "TMP_PARENT=%TEMP%\kloudys-forza-painter-suite-update"
set "TMP_REPO=%TMP_PARENT%\repo"
if exist "%TMP_PARENT%" rmdir /s /q "%TMP_PARENT%"
mkdir "%TMP_PARENT%" >nul 2>nul

git clone --depth 1 --branch %BRANCH% "%REPO_URL%" "%TMP_REPO%"
if errorlevel 1 goto :fail

call :backup_existing_files
if errorlevel 1 goto :fail
call :check_update_locks
if errorlevel 1 goto :fail_quiet

call :sync_program_files_from_repo "%TMP_REPO%"
if errorlevel 1 goto :fail
call :verify_program_file_sync "%TMP_REPO%"
if errorlevel 1 goto :fail
call :ensure_qml_root_binary
if errorlevel 1 goto :fail
call :verify_native_root_binary
if errorlevel 1 goto :fail
call :cleanup_retired_files
call :verify_retired_files_removed
if errorlevel 1 goto :fail
call :write_build_commit "%TMP_REPO%"

rmdir /s /q "%TMP_PARENT%" >nul 2>nul

:done
call :capture_current_version FINAL_VERSION
call :log ""
call :log "Update complete."
call :log "Version: !OLD_VERSION! to !FINAL_VERSION!"
call :log "Backup folder: !BACKUP_DIR!"
call :relaunch_kfps_after_update
if defined KFPS_RELAUNCH_AFTER_UPDATE (
    call :log "KFPS should reopen automatically."
) else (
    call :log "Run KFPS.exe from the main KFPS folder when you are ready."
)
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 0

:fail_quiet
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 1

:fail
call :log ""
call :log "Update failed. No generated images or runtime output were intentionally removed."
call :log "If program files were partially changed, check backup folder: !BACKUP_DIR!"
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 1

:relaunch_kfps_after_update
if not defined KFPS_RELAUNCH_AFTER_UPDATE exit /b 0
set "KFPS_RELAUNCH_EXE="
if defined KFPS_RELAUNCH_TARGET (
    if exist "%KFPS_RELAUNCH_TARGET%" set "KFPS_RELAUNCH_EXE=%KFPS_RELAUNCH_TARGET%"
)
if not defined KFPS_RELAUNCH_EXE (
    if exist "%CD%\..\KFPS.exe" set "KFPS_RELAUNCH_EXE=%CD%\..\KFPS.exe"
)
if not defined KFPS_RELAUNCH_EXE (
    if exist "%CD%\KFPS.exe" set "KFPS_RELAUNCH_EXE=%CD%\KFPS.exe"
)
if not defined KFPS_RELAUNCH_EXE (
    call :log "Update finished, but KFPS.exe could not be found for automatic relaunch."
    exit /b 0
)
call :log "Relaunching KFPS..."
start "" "!KFPS_RELAUNCH_EXE!"
exit /b 0

:init_update_log
set "UPDATE_STAMP=manual"
for /f "delims=" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss" 2^>nul') do set "UPDATE_STAMP=%%T"
set "UPDATE_LOG_DIR=%CD%\runtime\update-logs"
if not exist "%UPDATE_LOG_DIR%" mkdir "%UPDATE_LOG_DIR%" >nul 2>nul
set "UPDATE_LOG=%UPDATE_LOG_DIR%\update-%UPDATE_STAMP%.log"
> "%UPDATE_LOG%" echo KFPS Launcher update log
set "BACKUP_ROOT=%LOCALAPPDATA%\KloudysFH6Painter\update-backups"
if "%LOCALAPPDATA%"=="" set "BACKUP_ROOT=%TEMP%\KloudysFH6Painter\update-backups"
set "BACKUP_DIR=%BACKUP_ROOT%\%UPDATE_STAMP%"
exit /b 0

:log
if "%~1"=="" (
    echo.
    if defined UPDATE_LOG (
        >> "%UPDATE_LOG%" echo.
    )
) else (
    echo %~1
    if defined UPDATE_LOG (
        >> "%UPDATE_LOG%" echo [%DATE% %TIME%] %~1
    )
)
exit /b 0

:capture_current_version
set "%~1=unknown"
if exist "VERSION" (
    for /f "usebackq delims=" %%V in ("VERSION") do (
        set "%~1=%%V"
        goto :capture_current_version_done
    )
)
if exist ".git\" (
    for /f "delims=" %%V in ('git rev-parse --short^=8 HEAD 2^>nul') do set "%~1=git:%%V"
)
:capture_current_version_done
exit /b 0

:resolve_update_root
set "KFPS_START_DIR=%CD%"
call :is_kfps_app_root
if not errorlevel 1 exit /b 0

set "KFPS_CANDIDATE_ROOT=%KFPS_START_DIR%\KloudysFH6Painter"
if exist "%KFPS_CANDIDATE_ROOT%\" (
    cd /d "%KFPS_CANDIDATE_ROOT%" >nul 2>nul
    call :is_kfps_app_root
    if not errorlevel 1 exit /b 0
    cd /d "%KFPS_START_DIR%" >nul 2>nul
)

echo Refusing to update from this folder:
echo %KFPS_START_DIR%
echo.
echo This updater must be run from inside KloudysFH6Painter, or from the folder that contains KloudysFH6Painter.
echo No files were changed.
if not "%FORZA_PAINTER_NO_PAUSE%"=="1" pause
exit /b 1

:is_kfps_app_root
if not exist "VERSION" exit /b 1
if not exist "KFPS.UI\" exit /b 1
if not exist "assets\" exit /b 1
if not exist "settings\" exit /b 1
if not exist "fh6_probe.py" exit /b 1
if not exist "generator_backend.py" exit /b 1
if not exist "KloudysGalateaGenesis.exe" exit /b 1
exit /b 0

:backup_existing_files
call :log "Backing up current app files before overwrite..."
if not exist "!BACKUP_DIR!" mkdir "!BACKUP_DIR!" >nul 2>nul
robocopy "%CD%" "!BACKUP_DIR!" /E /R:1 /W:1 /XD ".git" "runtime" "imgs" "webui-data" "dist" "build" "__pycache__" "python" /XF "*.pyc" >nul
if errorlevel 8 (
    call :log "Backup warning. Robocopy exit code: %ERRORLEVEL%"
    call :log "Continuing update without blocking because generated/runtime data is preserved separately."
)
call :log "Backup folder: !BACKUP_DIR!"
exit /b 0

:check_update_locks
set "LOCK_REPORT=%TEMP%\kloudys-update-locks-%RANDOM%.txt"
if exist "!LOCK_REPORT!" del /f /q "!LOCK_REPORT!" >nul 2>nul
set "KFPS_LOCK_REPORT=!LOCK_REPORT!"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $root=(Resolve-Path '.').Path; $parent=(Resolve-Path '..').Path; $lockReport=$env:KFPS_LOCK_REPORT; function InTree($path,$base){ if(-not $path){ return $false }; try{ $full=[IO.Path]::GetFullPath($path); return $full.StartsWith($base,[StringComparison]::OrdinalIgnoreCase) } catch { return $false } }; $names=@('KFPS.exe','Kloudys Painter Launcher.exe','Kloudys Painter.exe','KloudysGalateaGenesis.exe','KloudysGeneratorV7.exe','KloudysGeneratorV6.exe','KloudysGeneratorV6-Go.exe','KloudysGeneratorV5.exe','KloudysGeneratorV5DetailLock.exe','KloudysGeneratorV4.exe','KloudysGeneratorV2.exe','KloudysGeneratorV2Fast.exe','KloudysGeneratorV2Speed.exe','ForzaVinylStudio.exe'); $procs=Get-CimInstance Win32_Process; $locks=$procs | Where-Object { $cmd=$_.CommandLine; $path=$_.ExecutablePath; ((($names -contains $_.Name) -and ((InTree $path $root) -or (InTree $path $parent) -or ($cmd -like ('*' + $root + '*')) -or ($cmd -like ('*' + $parent + '*')))) -or (($_.Name -match '^pythonw?\.exe$') -and ($cmd -like ('*' + $root + '*')) -and ($cmd -match 'app_qt.py|start_fabric_editor.py|forza_generator_v2.py|benchmark_generator_settings.py|KFPS\.UI'))) }; if($locks){ $locks | ForEach-Object { ('PID ' + $_.ProcessId + ' - ' + $_.Name) } | Set-Content -LiteralPath $lockReport -Encoding ASCII; $locks | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 1500; $remaining=Get-CimInstance Win32_Process | Where-Object { $cmd=$_.CommandLine; $path=$_.ExecutablePath; ((($names -contains $_.Name) -and ((InTree $path $root) -or (InTree $path $parent) -or ($cmd -like ('*' + $root + '*')) -or ($cmd -like ('*' + $parent + '*')))) -or (($_.Name -match '^pythonw?\.exe$') -and ($cmd -like ('*' + $root + '*')) -and ($cmd -match 'app_qt.py|start_fabric_editor.py|forza_generator_v2.py|benchmark_generator_settings.py|KFPS\.UI'))) }; if($remaining){ 'Still running after termination attempt:' | Add-Content -LiteralPath $lockReport -Encoding ASCII; $remaining | ForEach-Object { ('PID ' + $_.ProcessId + ' - ' + $_.Name) } | Add-Content -LiteralPath $lockReport -Encoding ASCII; exit 2 } }; exit 0"
if errorlevel 1 (
    call :log ""
    call :log "Update tried to stop KFPS processes, but Windows reports that one is still running."
    call :log "Close the listed process manually or restart Windows, then run this updater again."
    if exist "!LOCK_REPORT!" (
        call :log "Running process details:"
        for /f "usebackq delims=" %%L in ("!LOCK_REPORT!") do call :log "%%L"
        del /f /q "!LOCK_REPORT!" >nul 2>nul
    )
    exit /b 1
)
if exist "!LOCK_REPORT!" (
    call :log ""
    call :log "Stopped running KFPS processes before updating:"
    for /f "usebackq delims=" %%L in ("!LOCK_REPORT!") do call :log "%%L"
    del /f /q "!LOCK_REPORT!" >nul 2>nul
)
exit /b 0

:write_build_commit
set "COMMIT_SHA="
for /f "delims=" %%V in ('git -C "%~1" rev-parse HEAD 2^>nul') do set "COMMIT_SHA=%%V"
if defined COMMIT_SHA (
    > "%CD%\BUILD_COMMIT" echo !COMMIT_SHA!
)
exit /b 0

:sync_program_files_from_repo
set "SYNC_REPO=%~1"
if not exist "%SYNC_REPO%\VERSION" (
    call :log "Update sync failed: cloned repository is missing VERSION."
    exit /b 1
)
call :log "Mirroring program files from GitHub while preserving generated/runtime data..."
robocopy "%SYNC_REPO%" "%CD%" /MIR /R:2 /W:1 /XD ".git" "runtime" "imgs" "webui-data" "dist" "build" "__pycache__" "python" /XF "*.pyc" "*.kfpskey" >nul
if errorlevel 8 (
    call :log "File mirror failed during update copy. Robocopy exit code: %ERRORLEVEL%"
    exit /b 1
)
exit /b 0

:verify_program_file_sync
set "VERIFY_REPO=%~1"
if not exist "%VERIFY_REPO%\.git\" (
    call :log "Verification failed: repository metadata is missing for hash verification."
    exit /b 1
)
call :log "Verifying updated program files against Git..."
set "KFPS_VERIFY_REPO=%VERIFY_REPO%"
set "KFPS_VERIFY_APP=%CD%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $repo=(Resolve-Path -LiteralPath $env:KFPS_VERIFY_REPO).Path; $app=(Resolve-Path -LiteralPath $env:KFPS_VERIFY_APP).Path; $tracked=& git -C $repo ls-files; if($LASTEXITCODE -ne 0){ throw 'git ls-files failed' }; $skip='^(runtime/|imgs/|webui-data/|python/|dist/|build/)|(^|/)__pycache__/|\.pyc$|\.kfpskey$'; $checked=0; $repaired=0; $failed=@(); foreach($rel in $tracked){ if($rel -match $skip){ continue }; $src=Join-Path $repo ($rel -replace '/', [IO.Path]::DirectorySeparatorChar); $dst=Join-Path $app ($rel -replace '/', [IO.Path]::DirectorySeparatorChar); if(-not (Test-Path -LiteralPath $src -PathType Leaf)){ $failed += $rel; continue }; $needCopy=$false; if(-not (Test-Path -LiteralPath $dst -PathType Leaf)){ $needCopy=$true } else { $srcHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash; $dstHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $dst).Hash; if($srcHash -ne $dstHash){ $needCopy=$true } }; if($needCopy){ $parent=Split-Path -Parent $dst; if($parent -and -not (Test-Path -LiteralPath $parent)){ New-Item -ItemType Directory -Force -Path $parent | Out-Null }; Copy-Item -LiteralPath $src -Destination $dst -Force; $repaired++ }; $srcHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash; if(-not (Test-Path -LiteralPath $dst -PathType Leaf)){ $failed += $rel; continue }; $dstHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $dst).Hash; if($srcHash -ne $dstHash){ $failed += $rel } else { $checked++ } }; if($failed.Count -gt 0){ Write-Host ('Verification failed for ' + $failed.Count + ' file(s):'); $failed | Select-Object -First 25 | ForEach-Object { Write-Host ('  ' + $_) }; exit 1 }; Write-Host ('Verified ' + $checked + ' tracked program file(s); repaired ' + $repaired + ' mismatched/missing file(s).'); exit 0"
if errorlevel 1 (
    call :log "Program file verification failed. Git copy and local install still differ."
    exit /b 1
)
call :log "Program file verification passed."
exit /b 0

:verify_same_file
if not exist "%~1" (
    call :log "Verification failed: source file is missing: %~1"
    exit /b 1
)
if not exist "%~2" (
    call :log "Verification failed: destination file is missing: %~2"
    exit /b 1
)
fc /b "%~1" "%~2" >nul
if errorlevel 1 (
    call :log "Verification failed: updated file does not match repository copy: %~2"
    exit /b 1
)
exit /b 0

:ensure_git
where git >nul 2>nul
if not errorlevel 1 exit /b 0

if exist "%ProgramFiles%\Git\cmd\git.exe" (
    set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
    exit /b 0
)
if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" (
    set "PATH=%ProgramFiles(x86)%\Git\cmd;%PATH%"
    exit /b 0
)

set "PORTABLE_GIT_ROOT=%LOCALAPPDATA%\KloudysFH6Painter\PortableGit"
if exist "%PORTABLE_GIT_ROOT%\cmd\git.exe" (
    set "PATH=%PORTABLE_GIT_ROOT%\cmd;%PATH%"
    exit /b 0
)

echo Git was not found. Installing PortableGit silently for this user...
set "GIT_INSTALLER=%TEMP%\PortableGit-64-bit.7z.exe"
if exist "%GIT_INSTALLER%" del /f /q "%GIT_INSTALLER%" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Continue'; $out=Join-Path $env:TEMP 'PortableGit-64-bit.7z.exe'; $urls=@('https://github.com/git-for-windows/git/releases/download/v2.54.0.windows.1/PortableGit-2.54.0-64-bit.7z.exe','https://sourceforge.net/projects/git-for-windows.mirror/files/v2.54.0.windows.1/PortableGit-2.54.0-64-bit.7z.exe/download'); foreach($url in $urls){ try { Write-Host ('Downloading PortableGit from ' + $url); Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out -Headers @{'User-Agent'='KloudysFH6Painter'}; if((Test-Path $out) -and ((Get-Item $out).Length -gt 1000000)){ exit 0 } } catch { Write-Host ('PortableGit download failed from ' + $url + ': ' + $_.Exception.Message) } }; exit 1"
if errorlevel 1 (
    echo Failed to download PortableGit.
    exit /b 1
)
if not exist "%GIT_INSTALLER%" (
    echo PortableGit archive was not downloaded.
    exit /b 1
)

"%GIT_INSTALLER%" -y -o"%PORTABLE_GIT_ROOT%" >nul
if errorlevel 1 (
    echo PortableGit extraction failed.
    exit /b 1
)

set "PATH=%PORTABLE_GIT_ROOT%\cmd;%PATH%"

where git >nul 2>nul
if errorlevel 1 (
    echo PortableGit was extracted but is not available in this session.
    echo Close this window and run 03_update_from_github.bat again.
    exit /b 1
)

echo PortableGit installed and ready.
exit /b 0

:try_local_qml_bundle_update
call :init_qml_payload_defaults
set "QML_BUNDLE_UPDATE_DONE="
set "QML_LOCAL_BUNDLE="
if defined KFPS_QML_BUNDLE_ZIP (
    if exist "%KFPS_QML_BUNDLE_ZIP%" set "QML_LOCAL_BUNDLE=%KFPS_QML_BUNDLE_ZIP%"
)
if not defined QML_LOCAL_BUNDLE (
    if exist "%CD%\..\%QML_BINARY_ASSET_NAME%" set "QML_LOCAL_BUNDLE=%CD%\..\%QML_BINARY_ASSET_NAME%"
)
if not defined QML_LOCAL_BUNDLE (
    if exist "%USERPROFILE%\Desktop\%QML_BINARY_ASSET_NAME%" set "QML_LOCAL_BUNDLE=%USERPROFILE%\Desktop\%QML_BINARY_ASSET_NAME%"
)
if not defined QML_LOCAL_BUNDLE exit /b 0

call :log "Local QML migration bundle found."
call :log "Bundle: !QML_LOCAL_BUNDLE!"
call :backup_existing_files
if errorlevel 1 exit /b 1

set "QML_STAGE=%TEMP%\kfps-qml-bundle-update-%RANDOM%-%RANDOM%"
if exist "!QML_STAGE!" rmdir /s /q "!QML_STAGE!" >nul 2>nul
mkdir "!QML_STAGE!" >nul 2>nul
set "KFPS_QML_STAGE=!QML_STAGE!"
set "KFPS_QML_BUNDLE=!QML_LOCAL_BUNDLE!"
set "KFPS_APP_ROOT=%CD%"
call :log "Extracting QML migration bundle..."
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; Expand-Archive -LiteralPath $env:KFPS_QML_BUNDLE -DestinationPath $env:KFPS_QML_STAGE -Force; $bundleRoot=Get-ChildItem -LiteralPath $env:KFPS_QML_STAGE -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'KloudysFH6Painter') } | Select-Object -First 1; if(-not $bundleRoot){ if(Test-Path (Join-Path $env:KFPS_QML_STAGE 'KloudysFH6Painter')){ $bundleRoot=Get-Item -LiteralPath $env:KFPS_QML_STAGE } }; if(-not $bundleRoot){ throw 'QML bundle does not contain KloudysFH6Painter' }; Set-Content -LiteralPath (Join-Path $env:KFPS_QML_STAGE 'bundle-root.txt') -Value $bundleRoot.FullName -Encoding ASCII"
if errorlevel 1 (
    call :log "Failed to extract QML migration bundle."
    exit /b 1
)
for /f "usebackq delims=" %%R in ("!QML_STAGE!\bundle-root.txt") do set "QML_BUNDLE_ROOT=%%R"
if not exist "!QML_BUNDLE_ROOT!\KloudysFH6Painter\" (
    call :log "Extracted QML bundle is missing KloudysFH6Painter."
    exit /b 1
)

call :log "Copying QML app files into this install..."
robocopy "!QML_BUNDLE_ROOT!\KloudysFH6Painter" "%CD%" /E /R:2 /W:1 /XD .git runtime imgs webui-data dist build __pycache__ python /XF "*.pyc" "*.kfpskey" >nul
if errorlevel 8 (
    call :log "QML bundle app copy failed. Robocopy exit code: %ERRORLEVEL%"
    exit /b 1
)

if exist "!QML_BUNDLE_ROOT!\KFPS.exe" (
    copy /y "!QML_BUNDLE_ROOT!\KFPS.exe" "%CD%\KFPS.exe" >nul 2>nul
) else (
    call :log "QML bundle is missing parent KFPS.exe."
    exit /b 1
)

call :cleanup_retired_files
if exist "!QML_STAGE!" rmdir /s /q "!QML_STAGE!" >nul 2>nul
set "QML_BUNDLE_UPDATE_DONE=1"
exit /b 0

:install_qml_binary_payload
call :init_qml_payload_defaults
if exist "KFPS.exe" (
    call :log "Native launcher payload is present in the app root."
    exit /b 0
)
set "QML_PAYLOAD_ZIP="
if defined KFPS_QML_BUNDLE_ZIP (
    if exist "%KFPS_QML_BUNDLE_ZIP%" set "QML_PAYLOAD_ZIP=%KFPS_QML_BUNDLE_ZIP%"
)
if not defined QML_PAYLOAD_ZIP (
    if exist "%CD%\..\%QML_BINARY_ASSET_NAME%" set "QML_PAYLOAD_ZIP=%CD%\..\%QML_BINARY_ASSET_NAME%"
)
if not defined QML_PAYLOAD_ZIP (
    if exist "%USERPROFILE%\Desktop\%QML_BINARY_ASSET_NAME%" set "QML_PAYLOAD_ZIP=%USERPROFILE%\Desktop\%QML_BINARY_ASSET_NAME%"
)
set "KFPS_APP_ROOT=%CD%"
set "KFPS_QML_PAYLOAD_ZIP=%QML_PAYLOAD_ZIP%"
set "KFPS_QML_PAYLOAD_URL=%QML_BINARY_ASSET_URL%"
set "KFPS_QML_PAYLOAD_NAME=%QML_BINARY_ASSET_NAME%"
call :log "Installing native launcher payload..."
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $app=$env:KFPS_APP_ROOT; $zip=$env:KFPS_QML_PAYLOAD_ZIP; $url=$env:KFPS_QML_PAYLOAD_URL; if((-not $zip -or -not (Test-Path -LiteralPath $zip)) -and [string]::IsNullOrWhiteSpace($url)){ throw 'Native launcher payload is missing from the synced app files.' }; if(-not $zip -or -not (Test-Path -LiteralPath $zip)){ $zip=Join-Path $env:TEMP $env:KFPS_QML_PAYLOAD_NAME; $headers=@{'User-Agent'='KFPS-Updater'}; if($env:GH_TOKEN){ $headers['Authorization']='Bearer ' + $env:GH_TOKEN }; Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip -Headers $headers }; $stage=Join-Path $env:TEMP ('kfps-qml-payload-' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Force -Path $stage | Out-Null; Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force; $exe=Get-ChildItem -LiteralPath $stage -Recurse -File -Filter 'KFPS.exe' | Where-Object { $_.FullName -notmatch '\\KloudysFH6Painter\\KFPS\.exe$' } | Select-Object -First 1; if(-not $exe){ throw 'QML payload did not contain a parent KFPS.exe' }; Copy-Item -LiteralPath $exe.FullName -Destination (Join-Path $app 'KFPS.exe') -Force; Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue"
if errorlevel 1 (
    call :log "Failed to install QML native binary payload."
    call :log "If the binary asset cannot be downloaded, place %QML_BINARY_ASSET_NAME% next to the KFPS folder or set KFPS_QML_BUNDLE_ZIP."
    exit /b 1
)
call :log "Native launcher payload installed."
exit /b 0

:ensure_qml_root_binary
call :init_qml_payload_defaults
for %%I in ("%CD%") do set "CURRENT_FOLDER=%%~nxI"
if /I not "%CURRENT_FOLDER%"=="KloudysFH6Painter" exit /b 0
set "QML_ROOT_EXE=%CD%\..\KFPS.exe"
set "QML_MARKER=%CD%\runtime\native-root-exe-version.txt"
set "QML_ROOT_REASON="
if not exist "!QML_ROOT_EXE!" (
    set "QML_ROOT_REASON=missing"
) else (
    set "QML_ROOT_HASH="
    call :capture_file_sha256 "!QML_ROOT_EXE!" QML_ROOT_HASH
    if errorlevel 1 (
        set "QML_ROOT_REASON=updated"
    ) else if defined QML_BINARY_ASSET_SHA256 (
        if /I not "!QML_ROOT_HASH!"=="%QML_BINARY_ASSET_SHA256%" set "QML_ROOT_REASON=updated"
    )
)
if not defined QML_ROOT_REASON (
    set "QML_MARKER_VALUE="
    if exist "!QML_MARKER!" (
        for /f "usebackq delims=" %%V in ("!QML_MARKER!") do (
            if not defined QML_MARKER_VALUE set "QML_MARKER_VALUE=%%V"
        )
    )
    if not defined QML_MARKER_VALUE (
        if not exist "%CD%\runtime" mkdir "%CD%\runtime" >nul 2>nul
        > "!QML_MARKER!" echo %QML_BINARY_ASSET_NAME%
        exit /b 0
    )
    if /I "!QML_MARKER_VALUE!"=="%QML_BINARY_ASSET_NAME%" exit /b 0
    set "QML_ROOT_REASON=updated"
)
if /I "!QML_ROOT_REASON!"=="missing" call :log "Native KFPS launcher is missing; installing QML executable."
if /I "!QML_ROOT_REASON!"=="updated" call :log "Native launcher hash differs; replacing KFPS.exe."
call :install_qml_binary_payload
if errorlevel 1 exit /b 1
call :sync_native_root_exe
if exist "!QML_ROOT_EXE!" (
    set "QML_ROOT_HASH="
    call :capture_file_sha256 "!QML_ROOT_EXE!" QML_ROOT_HASH
    if not errorlevel 1 (
        if /I "!QML_ROOT_HASH!"=="%QML_BINARY_ASSET_SHA256%" (
            if not exist "%CD%\runtime" mkdir "%CD%\runtime" >nul 2>nul
            > "!QML_MARKER!" echo %QML_BINARY_ASSET_NAME%
            exit /b 0
        )
    )
)
call :log "Native launcher repair did not produce the expected QML launcher hash."
exit /b 1

:init_qml_payload_defaults
if not defined QML_BINARY_ASSET_NAME set "QML_BINARY_ASSET_NAME=KFPS-loose-launcher-v1"
if not defined QML_BINARY_ASSET_SHA256 set "QML_BINARY_ASSET_SHA256=C8427290547083752604215FEDB64CBF4D59481E9033DF1E201033070CB3FD43"
exit /b 0

:capture_file_sha256
set "HASH_VALUE="
if "%~1"=="" exit /b 1
if "%~2"=="" exit /b 1
if not exist "%~1" exit /b 1
for /f "tokens=1" %%H in ('certutil -hashfile "%~1" SHA256 2^>nul ^| findstr /R /V /C:"hash" /C:"CertUtil"') do (
    if not defined HASH_VALUE set "HASH_VALUE=%%H"
)
if not defined HASH_VALUE exit /b 1
set "%~2=%HASH_VALUE%"
exit /b 0

:verify_native_root_binary
call :init_qml_payload_defaults
for %%I in ("%CD%") do set "CURRENT_FOLDER=%%~nxI"
if /I not "%CURRENT_FOLDER%"=="KloudysFH6Painter" exit /b 0
set "QML_ROOT_EXE=%CD%\..\KFPS.exe"
if not exist "!QML_ROOT_EXE!" (
    call :log "Verification failed: native KFPS.exe is missing one folder above KloudysFH6Painter."
    exit /b 1
)
if not defined QML_BINARY_ASSET_SHA256 exit /b 0
set "QML_ROOT_HASH="
call :capture_file_sha256 "!QML_ROOT_EXE!" QML_ROOT_HASH
if errorlevel 1 (
    call :log "Verification failed: could not hash native KFPS.exe."
    exit /b 1
)
if /I not "!QML_ROOT_HASH!"=="%QML_BINARY_ASSET_SHA256%" (
    call :log "Verification failed: native KFPS.exe hash does not match the expected payload."
    exit /b 1
)
call :log "Native KFPS.exe verification passed."
exit /b 0

:cleanup_retired_files
call :ensure_qml_root_binary
if errorlevel 1 exit /b 1
call :verify_native_root_binary
if errorlevel 1 exit /b 1
call :cleanup_stale_release_git
if exist "settings\_archive_legacy_2026-05-22" rmdir /s /q "settings\_archive_legacy_2026-05-22" >nul 2>nul
if exist "settings\_default.ini" del /f /q "settings\_default.ini" >nul 2>nul
call :cleanup_3x_retired_files
for %%F in (
    "settings\a.3000-ultra-sharp.ini"
    "settings\a2.2000-ultra-sharp.ini"
    "settings\a2b.2000-ultra-sharp + Luma Bands.ini"
    "settings\ab.3000-ultra-sharp + Luma Bands.ini"
    "settings\b.1000-ultra-sharp.ini"
    "settings\bb.1000-ultra-sharp + Luma Bands.ini"
    "settings\c.3000-soft-detail.ini"
    "settings\c2.2000-soft-detail.ini"
    "settings\c2b.2000-soft-detail + Luma Bands.ini"
    "settings\cb.3000-soft-detail + Luma Bands.ini"
    "settings\d.1000-soft-detail.ini"
    "settings\db.1000-soft-detail + Luma Bands.ini"
    "settings\e.3000-smart-detail.ini"
    "settings\e2.2000-smart-detail.ini"
    "settings\e2b.2000-smart-detail + Luma Bands.ini"
    "settings\eb.3000-smart-detail + Luma Bands.ini"
    "settings\f.3000-anime-livery.ini"
    "settings\f2.2000-anime-livery.ini"
    "settings\f2b.2000-anime-livery + Luma Bands.ini"
    "settings\fb.3000-anime-livery + Luma Bands.ini"
    "settings\g.1000-smart-detail.ini"
    "settings\gb.1000-smart-detail + Luma Bands.ini"
    "settings\h.1000-anime-livery.ini"
    "settings\hb.1000-anime-livery + Luma Bands.ini"
    "settings\a.fast-ugly.ini"
    "settings\b.okay-draft.ini"
    "settings\c.pretty-good.ini"
    "settings\d.slow-beautiful.ini"
    "KloudysGeneratorV7.exe"
    "KloudysGeneratorV2.exe"
    "KloudysGeneratorV2Fast.exe"
    "KloudysGeneratorV2Speed.exe"
    "KloudysGeneratorV4.exe"
    "KloudysGeneratorV5DetailLock.exe"
    "KloudysGeneratorV5.exe"
    "KloudysGeneratorV6-Go.exe"
    "KloudysGeneratorV6.exe"
    "kloudys-fh6-generator.exe"
    "forza-painter-geometrize-go.exe"
    "docs\GENERATOR_BENCHMARK_PLAN.md"
    "tools\benchmark_generator_settings.py"
) do (
    if exist "%%~F" del /f /q "%%~F" >nul 2>nul
)
if exist "tools\__pycache__" rmdir /s /q "tools\__pycache__" >nul 2>nul
set "TOOLS_HAS_CONTENT="
if exist "tools\" (
    for /f "delims=" %%A in ('dir /a /b "tools" 2^>nul') do set "TOOLS_HAS_CONTENT=1"
    if not defined TOOLS_HAS_CONTENT rmdir /q "tools" >nul 2>nul
)
call :seed_bundle_logo_json
exit /b 0

:cleanup_stale_release_git
for %%I in ("%CD%") do set "CURRENT_FOLDER=%%~nxI"
if /I not "%CURRENT_FOLDER%"=="KloudysFH6Painter" exit /b 0
if not exist "..\KFPS.exe" exit /b 0
if exist ".git\" (
    rmdir /s /q ".git" >nul 2>nul
    if not exist ".git\" call :log "Removed stale release Git metadata."
)
exit /b 0

:seed_bundle_logo_json
set "KFPS_LOGO_JSON=assets\app\KFPS Logo.json"
if not exist "%KFPS_LOGO_JSON%" exit /b 0
if not exist "imgs\generated\KFPS Logo\finals" mkdir "imgs\generated\KFPS Logo\finals" >nul 2>nul
if not exist "imgs\exported" mkdir "imgs\exported" >nul 2>nul
if not exist "imgs\editor\KFPS Logo" mkdir "imgs\editor\KFPS Logo" >nul 2>nul
copy /y "%KFPS_LOGO_JSON%" "imgs\generated\KFPS Logo\finals\KFPS Logo.3000v2.json" >nul 2>nul
copy /y "%KFPS_LOGO_JSON%" "imgs\exported\KFPS Logo.json" >nul 2>nul
copy /y "%KFPS_LOGO_JSON%" "imgs\editor\KFPS Logo\KFPS Logo.json" >nul 2>nul
exit /b 0

:cleanup_3x_retired_files
call :log "Cleaning retired 2.x UI and launcher files..."
if exist "app_qt.py" del /f /q "app_qt.py" >nul 2>nul
if exist "launcher_qt.py" del /f /q "launcher_qt.py" >nul 2>nul
if exist "00_launcher.bat" del /f /q "00_launcher.bat" >nul 2>nul
if exist "04_start_app.bat" del /f /q "04_start_app.bat" >nul 2>nul
if exist "Kloudys Painter Launcher.exe" del /f /q "Kloudys Painter Launcher.exe" >nul 2>nul
if exist "Kloudys Painter.exe" del /f /q "Kloudys Painter.exe" >nul 2>nul
if exist "..\Kloudys Painter Launcher.exe" del /f /q "..\Kloudys Painter Launcher.exe" >nul 2>nul
if exist "..\Kloudys Painter.exe" del /f /q "..\Kloudys Painter.exe" >nul 2>nul
if exist "KFPS.Wpf" rmdir /s /q "KFPS.Wpf" >nul 2>nul
exit /b 0

:verify_retired_files_removed
set "RETIRED_FOUND="
for %%F in (
    "app_qt.py"
    "launcher_qt.py"
    "00_launcher.bat"
    "04_start_app.bat"
    "Kloudys Painter Launcher.exe"
    "Kloudys Painter.exe"
    "..\Kloudys Painter Launcher.exe"
    "..\Kloudys Painter.exe"
    "KFPS.Wpf"
) do (
    if exist "%%~F" (
        call :log "Verification failed: retired file or folder still exists: %%~F"
        set "RETIRED_FOUND=1"
    )
)
if defined RETIRED_FOUND exit /b 1
call :log "Retired file cleanup verified."
exit /b 0

:sync_native_root_exe
if not exist "KFPS.exe" exit /b 0
for %%I in ("%CD%") do set "CURRENT_FOLDER=%%~nxI"
if /I not "%CURRENT_FOLDER%"=="KloudysFH6Painter" exit /b 0
set "KFPS_NATIVE_SOURCE=%CD%\KFPS.exe"
set "KFPS_NATIVE_TARGET=%CD%\..\KFPS.exe"
set "KFPS_NATIVE_LOG=%UPDATE_LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $src=$env:KFPS_NATIVE_SOURCE; $target=$env:KFPS_NATIVE_TARGET; $log=$env:KFPS_NATIVE_LOG; $root=(Resolve-Path '.').Path; $parent=(Resolve-Path '..').Path; function InTree($path,$base){ if(-not $path){ return $false }; try{ $full=[IO.Path]::GetFullPath($path); return $full.StartsWith($base,[StringComparison]::OrdinalIgnoreCase) } catch { return $false } }; function WriteLog($message){ if($log){ Add-Content -LiteralPath $log -Value ('[' + (Get-Date -Format 'dd.MM.yyyy HH:mm:ss,ff') + '] ' + $message) -Encoding ASCII } }; $names=@('KFPS.exe','Kloudys Painter Launcher.exe','Kloudys Painter.exe'); $locks=Get-CimInstance Win32_Process | Where-Object { $cmd=$_.CommandLine; $path=$_.ExecutablePath; ($names -contains $_.Name) -and ((InTree $path $root) -or (InTree $path $parent) -or ($cmd -like ('*' + $root + '*')) -or ($cmd -like ('*' + $parent + '*'))) }; if($locks){ WriteLog 'Stopped native launcher process(es) before replacing KFPS.exe.'; $locks | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 1200 }; $copied=$false; $last=$null; for($i=0; $i -lt 60; $i++){ try{ Copy-Item -LiteralPath $src -Destination $target -Force; $copied=$true; break } catch { $last=$_.Exception.Message; Start-Sleep -Milliseconds 500 } }; if(-not $copied){ WriteLog ('Native launcher replacement failed after retries: ' + $last); exit 2 }; exit 0"
if errorlevel 1 (
    call :schedule_native_handoff
    exit /b 1
)
call :log "Native KFPS launcher installed one folder above KloudysFH6Painter."
exit /b 0

:schedule_native_handoff
set "HANDOFF_SCRIPT=%CD%\tools\replace_parent_launcher.ps1"
if not exist "%HANDOFF_SCRIPT%" (
    call :log "Native launcher is currently running or locked; kept KFPS.exe inside KloudysFH6Painter."
    call :log "Manual fallback: close KFPS, then copy KloudysFH6Painter\KFPS.exe one folder above."
    exit /b 0
)
call :log "Native launcher target is currently running or locked."
call :log "Scheduled native launcher replacement after KFPS closes."
set "KFPS_HANDOFF_SCRIPT=%HANDOFF_SCRIPT%"
set "KFPS_HANDOFF_SOURCE=%CD%\KFPS.exe"
set "KFPS_HANDOFF_TARGET=%CD%\..\KFPS.exe"
set "KFPS_HANDOFF_OLD=%CD%\..\Kloudys Painter Launcher.exe"
set "KFPS_HANDOFF_LOG=%UPDATE_LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$script=$env:KFPS_HANDOFF_SCRIPT; $src=$env:KFPS_HANDOFF_SOURCE; $target=$env:KFPS_HANDOFF_TARGET; $old=$env:KFPS_HANDOFF_OLD; $log=$env:KFPS_HANDOFF_LOG; $args='-NoProfile -ExecutionPolicy Bypass -File \"' + $script + '\" -Source \"' + $src + '\" -Target \"' + $target + '\" -OldTarget \"' + $old + '\" -LogFile \"' + $log + '\" -DeleteSelf'; Start-Process -WindowStyle Hidden -FilePath powershell.exe -ArgumentList $args"
exit /b 0
