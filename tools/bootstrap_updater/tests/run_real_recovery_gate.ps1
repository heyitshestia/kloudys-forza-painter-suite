param(
    [Parameter(Mandatory = $true)]
    [string]$Archive,
    [Parameter(Mandatory = $true)]
    [string]$Updater
)

$ErrorActionPreference = "Stop"
$ToolRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $ToolRoot "build"
$RunRoot = Join-Path $BuildRoot ("real-recovery-" + [guid]::NewGuid().ToString("N"))
$ExtractRoot = Join-Path $RunRoot "extract"
$StateRoot = Join-Path $RunRoot "state"
$ExpectedArchiveHash = "551f4052ee8f6707d7c7e24fb7b42ed74be9bfac45e3cfdd7281ca773e1ad0ec"
$Started = [DateTime]::UtcNow

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

function Invoke-Recovery {
    param([switch]$CheckOnly)
    $arguments = @(
        "--root", $script:Target,
        "--state-dir", $StateRoot,
        "--recover",
        "--recovery-archive", $Archive,
        "--no-pause"
    )
    if ($CheckOnly) {
        $arguments += "--check"
    }
    & $Updater @arguments | Out-Host
    return $LASTEXITCODE
}

function Test-ReleaseInventory {
    $manifest = Get-Content -LiteralPath (Join-Path $script:Target "RELEASE-MANIFEST.json") -Raw | ConvertFrom-Json
    $failed = 0
    $managed = 0
    foreach ($record in $manifest.files) {
        $key = $record.path.ToLowerInvariant()
        if ($key.EndsWith(".pyc") -or $key.Contains("/__pycache__/")) {
            continue
        }
        if ($key -eq "kloudysfh6painter/03_update_from_github.bat" -or
            $key -eq "kloudysfh6painter/update_from_github.bat") {
            continue
        }
        $managed++
        $path = Join-Path $script:Target ($record.path -replace "/", "\")
        $info = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        if ($null -eq $info -or $info.PSIsContainer) {
            $failed++
            continue
        }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($info.Length -ne [int64]$record.size -or $hash -ne $record.sha256.ToLowerInvariant()) {
            $failed++
        }
    }
    return [pscustomobject]@{ Declared = @($manifest.files).Count; Managed = $managed; Failed = $failed }
}

if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
    throw "Recovery archive is missing: $Archive"
}
if (-not (Test-Path -LiteralPath $Updater -PathType Leaf)) {
    throw "Test updater is missing: $Updater"
}
$archiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
if ($archiveHash -ne $ExpectedArchiveHash) {
    throw "Recovery archive hash $archiveHash does not match the pinned release"
}

[IO.Directory]::CreateDirectory($ExtractRoot) | Out-Null
Write-Host "REAL_RECOVERY_RUN=$RunRoot"
Write-Host "Extracting the verified v3.1.54 recovery bundle..."
Expand-Archive -LiteralPath $Archive -DestinationPath $ExtractRoot
$script:Target = (Get-ChildItem -LiteralPath $ExtractRoot -Directory | Select-Object -First 1).FullName
$resolvedRun = [IO.Path]::GetFullPath($RunRoot) + [IO.Path]::DirectorySeparatorChar
$resolvedTarget = [IO.Path]::GetFullPath($script:Target)
if (-not $resolvedTarget.StartsWith($resolvedRun, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Extracted package escaped the recovery run: $resolvedTarget"
}

$testModeBefore = $env:KFPS_UPDATER_TEST_MODE
$pauseBefore = $env:KFPS_UPDATER_NO_PAUSE
$env:KFPS_UPDATER_TEST_MODE = "1"
$env:KFPS_UPDATER_NO_PAUSE = "1"
try {
    Write-Host "Scenario 1: stock package bootstrap migration"
    $migrationCheckCode = Invoke-Recovery -CheckOnly
    if ($migrationCheckCode -ne 3) {
        throw "Stock package migration check exited $migrationCheckCode instead of 3"
    }
    $migrationCode = Invoke-Recovery
    if ($migrationCode -ne 0) {
        throw "Stock package migration exited $migrationCode"
    }
    $appRoot = Join-Path $script:Target "KloudysFH6Painter"
    $primaryShim = Join-Path $appRoot "03_update_from_github.bat"
    $legacyWrapper = Join-Path $appRoot "update_from_github.bat"
    foreach ($updaterCopy in @((Join-Path $script:Target "KFPS-Updater.exe"), (Join-Path $appRoot "KFPS-Updater.exe"))) {
        if (-not (Test-Path -LiteralPath $updaterCopy -PathType Leaf)) {
            throw "Stock package migration did not create $updaterCopy"
        }
    }
    if (-not (Test-Path -LiteralPath $primaryShim -PathType Leaf) -or
        -not ([IO.File]::ReadAllText($primaryShim).Contains("KFPS-Updater.exe"))) {
        throw "Stock package migration did not replace the legacy updater with the bootstrap shim"
    }
    if (Test-Path -LiteralPath $legacyWrapper) {
        throw "Stock package migration did not retire the legacy wrapper"
    }
    $migrationWarmCode = Invoke-Recovery -CheckOnly
    if ($migrationWarmCode -ne 0) {
        throw "Migrated stock package warm check exited $migrationWarmCode"
    }

    Write-Host "Scenario 2: damaged package dry-run and repair"
    $outerLauncher = Join-Path $script:Target "KFPS.exe"
    Write-Utf8NoBom $outerLauncher "corrupt-read-only"
    (Get-Item -LiteralPath $outerLauncher).IsReadOnly = $true
    $missingApplication = Join-Path $appRoot "KFPS.UI\src\kfps_ui\update_service.py"
    $missingCv2 = (Get-ChildItem -LiteralPath (Join-Path $appRoot "python") -Recurse -File -Filter "cv2.pyd" | Select-Object -First 1).FullName
    $missingFfmpeg = (Get-ChildItem -LiteralPath (Join-Path $appRoot "python") -Recurse -File -Filter "opencv_videoio_ffmpeg*_64.dll" | Select-Object -First 1).FullName
    if (-not $missingCv2 -or -not $missingFfmpeg) {
        throw "Could not locate the packaged OpenCV test files"
    }
    Remove-Item -LiteralPath $missingApplication -Force
    Remove-Item -LiteralPath $missingCv2 -Force
    Remove-Item -LiteralPath $missingFfmpeg -Force
    $obsolete = Join-Path $appRoot "python\obsolete-audit-extension.pyd"
    Write-Utf8NoBom $obsolete "obsolete"
    $runtime = Join-Path $appRoot "runtime\audit-preserve.json"
    $key = Join-Path $appRoot "audit-preserve.kfpskey"
    $cache = Join-Path $appRoot "python\Lib\__pycache__\audit-preserve.pyc"
    Write-Utf8NoBom $runtime "runtime-preserve"
    Write-Utf8NoBom $key "key-preserve"
    Write-Utf8NoBom $cache "cache-preserve"

    $damagedCheckCode = Invoke-Recovery -CheckOnly
    if ($damagedCheckCode -ne 3) {
        throw "Damaged recovery check exited $damagedCheckCode instead of 3"
    }
    if ((Get-Content -LiteralPath $outerLauncher -Raw) -ne "corrupt-read-only" -or (Test-Path -LiteralPath $missingApplication)) {
        throw "Dry-run changed the damaged installation"
    }
    $repairCode = Invoke-Recovery
    if ($repairCode -ne 0) {
        throw "Damaged recovery apply exited $repairCode"
    }
    foreach ($path in @($missingApplication, $missingCv2, $missingFfmpeg)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Recovery did not restore $path"
        }
    }
    if (Test-Path -LiteralPath $obsolete) {
        throw "Recovery did not remove the obsolete Python file"
    }
    if ([IO.File]::ReadAllText($runtime) -ne "runtime-preserve" -or
        [IO.File]::ReadAllText($key) -ne "key-preserve" -or
        [IO.File]::ReadAllText($cache) -ne "cache-preserve") {
        throw "Recovery changed protected user data"
    }
    $repairedInventory = Test-ReleaseInventory
    if ($repairedInventory.Failed -ne 0) {
        throw "Repaired package has $($repairedInventory.Failed) manifest mismatch(es)"
    }
    $warmCode = Invoke-Recovery -CheckOnly
    if ($warmCode -ne 0) {
        throw "Warm repaired-package check exited $warmCode"
    }

    Write-Host "Scenario 3: nearly empty legacy package rebuild"
    $resolvedTarget = [IO.Path]::GetFullPath($script:Target)
    if (-not $resolvedTarget.StartsWith($resolvedRun, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to reset unsafe recovery target: $resolvedTarget"
    }
    [IO.Directory]::Delete($resolvedTarget, $true)
    $appRoot = Join-Path $script:Target "KloudysFH6Painter"
    [IO.Directory]::CreateDirectory($appRoot) | Out-Null
    Copy-Item -LiteralPath $Updater -Destination (Join-Path $script:Target "KFPS-Updater.exe")
    $runtime = Join-Path $appRoot "runtime\legacy-preserve.json"
    $key = Join-Path $appRoot "legacy-preserve.kfpskey"
    $cache = Join-Path $appRoot "python\Lib\__pycache__\legacy-preserve.pyc"
    $obsolete = Join-Path $appRoot "python\obsolete-legacy.pyd"
    Write-Utf8NoBom $runtime "legacy-runtime"
    Write-Utf8NoBom $key "legacy-key"
    Write-Utf8NoBom $cache "legacy-cache"
    Write-Utf8NoBom $obsolete "legacy-obsolete"

    $legacyCode = Invoke-Recovery
    if ($legacyCode -ne 0) {
        throw "Legacy recovery rebuild exited $legacyCode"
    }
    if ([IO.File]::ReadAllText($runtime) -ne "legacy-runtime" -or
        [IO.File]::ReadAllText($key) -ne "legacy-key" -or
        [IO.File]::ReadAllText($cache) -ne "legacy-cache") {
        throw "Legacy recovery changed protected user data"
    }
    if (Test-Path -LiteralPath $obsolete) {
        throw "Legacy recovery did not remove the obsolete Python file"
    }
    $legacyInventory = Test-ReleaseInventory
    if ($legacyInventory.Failed -ne 0) {
        throw "Legacy package has $($legacyInventory.Failed) manifest mismatch(es)"
    }
    $legacyWarmCode = Invoke-Recovery -CheckOnly
    if ($legacyWarmCode -ne 0) {
        throw "Legacy warm check exited $legacyWarmCode"
    }

    $reports = @(Get-ChildItem -LiteralPath (Join-Path $StateRoot "reports") -File)
    $result = [ordered]@{
        schema = "kfps.bootstrap-real-recovery.v1"
        success = $true
        started_utc = $Started.ToString("o")
        finished_utc = [DateTime]::UtcNow.ToString("o")
        archive_sha256 = $archiveHash
        migration_check_exit = $migrationCheckCode
        migration_exit = $migrationCode
        migration_warm_exit = $migrationWarmCode
        damaged_check_exit = $damagedCheckCode
        repair_exit = $repairCode
        warm_check_exit = $warmCode
        legacy_rebuild_exit = $legacyCode
        legacy_warm_exit = $legacyWarmCode
        repaired_declared_files = $repairedInventory.Declared
        repaired_managed_files = $repairedInventory.Managed
        repaired_hash_failures = $repairedInventory.Failed
        legacy_declared_files = $legacyInventory.Declared
        legacy_managed_files = $legacyInventory.Managed
        legacy_hash_failures = $legacyInventory.Failed
        reports = $reports.Count
        run_root = $RunRoot
    }
    Write-Utf8NoBom (Join-Path $RunRoot "real-recovery-report.json") (($result | ConvertTo-Json -Depth 10) + "`n")
    $result | Format-List
}
finally {
    $env:KFPS_UPDATER_TEST_MODE = $testModeBefore
    $env:KFPS_UPDATER_NO_PAUSE = $pauseBefore
}
