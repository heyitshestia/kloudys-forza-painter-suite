param(
    [string]$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$Updater = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path "KFPS-Updater.exe"),
    [Parameter(Mandatory = $true)]
    [string]$RecoveryArchive,
    [string]$ContractPath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "legacy_bridge_contract.json"),
    [string]$ReleaseCacheRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "build\historical-release-cache"),
    [string[]]$Versions = @("3.1.28", "3.1.52"),
    [switch]$KeepWork
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RetiredPaths = @(
    "KloudysFH6Painter/03_update_from_github.bat",
    "KloudysFH6Painter/update_from_github.bat"
)

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-NativeCapture {
    param(
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$LogPath,
        [hashtable]$Environment
    )
    $previous = @{}
    foreach ($name in $Environment.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, [string]$Environment[$name], "Process")
    }
    try {
        Push-Location -LiteralPath $WorkingDirectory
        try {
            $output = & $Executable @Arguments 2>&1
            $exitCode = $LASTEXITCODE
        } finally {
            Pop-Location
        }
    } finally {
        foreach ($name in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process")
        }
    }
    @($output | ForEach-Object { $_.ToString() }) | Set-Content -LiteralPath $LogPath -Encoding utf8
    return $exitCode
}

function New-SourceFixture([string]$Repository, [string]$Destination) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $files = @(& git -C $Repository -c core.quotepath=false ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE -ne 0 -or $files.Count -eq 0) {
        throw "Could not inventory the current KFPS source tree."
    }
    foreach ($relative in $files) {
        if ([string]::IsNullOrWhiteSpace($relative)) {
            continue
        }
        $source = Join-Path $Repository $relative
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            continue
        }
        $target = Join-Path $Destination $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
    }
    & git -C $Destination init -b main | Out-Null
    & git -C $Destination config user.name "KFPS Legacy Migration Gate"
    & git -C $Destination config user.email "updater-gate@example.invalid"
    & git -C $Destination config core.autocrlf false
    & git -C $Destination add -A
    & git -C $Destination commit -m "Exact local bridge fixture" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not commit the local bridge fixture."
    }
    return (& git -C $Destination rev-parse HEAD).Trim()
}

function Get-ReleaseManifestFromArchive([string]$Archive) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $entry = $zip.Entries | Where-Object { $_.FullName -match '(^|/)RELEASE-MANIFEST\.json$' } | Select-Object -First 1
        if (-not $entry) {
            throw "Recovery archive has no release manifest."
        }
        $reader = [System.IO.StreamReader]::new($entry.Open())
        try {
            return ($reader.ReadToEnd() | ConvertFrom-Json)
        } finally {
            $reader.Dispose()
        }
    } finally {
        $zip.Dispose()
    }
}

function Test-FinalInventory([string]$InstallRoot, [object]$Manifest) {
    $retired = @{}
    foreach ($relative in $RetiredPaths) {
        $retired[$relative.ToLowerInvariant()] = $true
    }
    $checked = 0
    $failures = @()
    foreach ($record in @($Manifest.files)) {
        $relative = ([string]$record.path).Replace('\', '/')
        $key = $relative.ToLowerInvariant()
        if ($key.EndsWith(".pyc") -or $key.Contains("/__pycache__/")) {
            continue
        }
        if ($retired.ContainsKey($key)) {
            continue
        }
        $path = Join-Path $InstallRoot $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            $failures += "missing:$relative"
            continue
        }
        $item = Get-Item -LiteralPath $path
        if ($item.Length -ne [int64]$record.size) {
            $failures += "size:$relative"
            continue
        }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
        if (-not $hash.Equals([string]$record.sha256, [StringComparison]::OrdinalIgnoreCase)) {
            $failures += "hash:$relative"
            continue
        }
        $checked++
    }
    return [pscustomobject]@{
        Declared = @($Manifest.files).Count
        Checked = $checked
        Failures = $failures
    }
}

if ($env:OS -ne "Windows_NT") {
    throw "This gate requires Windows."
}
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$Updater = (Resolve-Path -LiteralPath $Updater).Path
$RecoveryArchive = (Resolve-Path -LiteralPath $RecoveryArchive).Path
$ReleaseCacheRoot = (Resolve-Path -LiteralPath $ReleaseCacheRoot).Path
$ContractPath = (Resolve-Path -LiteralPath $ContractPath).Path
$Contract = Get-Content -LiteralPath $ContractPath -Raw | ConvertFrom-Json
Assert-True ([string]$Contract.schema -eq "kfps.legacy-bootstrap-bridge.v1") "Legacy bridge contract schema is invalid."
$ExpectedBatchHashes = @{}
foreach ($release in @($Contract.legacy_releases)) {
    $ExpectedBatchHashes[[string]$release.version] = ([string]$release.batch_sha256).ToLowerInvariant()
}
$LauncherHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $SourceRoot "KFPS.exe")).Hash.ToLowerInvariant()
Assert-True ($LauncherHash -eq ([string]$Contract.launcher_sha256).ToLowerInvariant()) "Current KFPS.exe no longer matches the legacy BAT launcher contract."
$UpdaterHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Updater).Hash.ToLowerInvariant()
$RecoveryManifest = Get-ReleaseManifestFromArchive $RecoveryArchive
$Cv2Record = @($RecoveryManifest.files) | Where-Object { $_.path -match '(?i)^KloudysFH6Painter/python/Lib/site-packages/cv2/.*\.pyd$' } | Select-Object -First 1
if (-not $Cv2Record) {
    throw "The pinned recovery inventory has no cv2 binary to damage and repair."
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ResultRoot = Join-Path (Split-Path -Parent $PSScriptRoot) "build\legacy-bat-bridge-results\$Stamp"
$WorkRoot = Join-Path ([IO.Path]::GetTempPath()) "KFPS-Legacy-BAT-Bridge-$Stamp-$PID"
New-Item -ItemType Directory -Path $ResultRoot -Force | Out-Null
New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null
$SourceFixture = Join-Path $WorkRoot "source repository with spaces"
$Commit = New-SourceFixture $SourceRoot $SourceFixture
$SourceFixtureUpdater = Join-Path $SourceFixture "KFPS-Updater.exe"
$SourceUpdateService = Join-Path $SourceFixture "KFPS.UI\src\kfps_ui\update_service.py"
$SourceUpdateServiceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $SourceUpdateService).Hash.ToLowerInvariant()
Assert-True (Test-Path -LiteralPath $SourceFixtureUpdater -PathType Leaf) "Current source fixture did not include KFPS-Updater.exe."
Assert-True (((Get-FileHash -Algorithm SHA256 -LiteralPath $SourceFixtureUpdater).Hash.ToLowerInvariant()) -eq $UpdaterHash) "Source fixture updater differs from the tested updater."

$results = @()
$auxiliaryTempRoots = @()
try {
    foreach ($version in $Versions) {
        if (-not $ExpectedBatchHashes.ContainsKey($version)) {
            throw "No immutable BAT hash is recorded for historical version $version."
        }
        $archive = Join-Path $ReleaseCacheRoot "v$version\KFPS-$version-bundled.zip"
        Assert-True (Test-Path -LiteralPath $archive -PathType Leaf) "Historical bundle is missing: $archive"
        $fixture = Join-Path $WorkRoot "KFPS $version user install"
        Expand-Archive -LiteralPath $archive -DestinationPath $fixture -Force
        $batch = @(Get-ChildItem -LiteralPath $fixture -Recurse -File -Filter "03_update_from_github.bat")
        Assert-True ($batch.Count -eq 1) "Historical $version bundle has $($batch.Count) primary BAT updaters."
        $batch = $batch[0]
        $appRoot = $batch.Directory.FullName
        $installRoot = Split-Path -Parent $appRoot
        $batchHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $batch.FullName).Hash.ToLowerInvariant()
        Assert-True ($batchHash -eq $ExpectedBatchHashes[$version]) "Historical $version BAT bytes changed."

        $temp = Join-Path ([IO.Path]::GetTempPath()) "kg-$PID-$($version.Replace('.', ''))-$Stamp"
        $auxiliaryTempRoots += $temp
        $localAppData = Join-Path $fixture "isolated local app data"
        New-Item -ItemType Directory -Path $temp, $localAppData -Force | Out-Null
        $markers = @(
            (Join-Path $appRoot "runtime\legacy-runtime.txt"),
            (Join-Path $appRoot "imgs\legacy-image.txt"),
            (Join-Path $appRoot "webui-data\legacy-web-state.txt"),
            (Join-Path $appRoot "legacy-user.kfpskey")
        )
        foreach ($marker in $markers) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $marker) -Force | Out-Null
            Set-Content -LiteralPath $marker -Value "preserve-$version" -Encoding ascii
        }
        $cv2Path = Join-Path $installRoot ([string]$Cv2Record.path)
        Remove-Item -LiteralPath $cv2Path -Force -ErrorAction SilentlyContinue
        $obsoletePython = Join-Path $appRoot "python\obsolete-from-legacy.bin"
        New-Item -ItemType Directory -Path (Split-Path -Parent $obsoletePython) -Force | Out-Null
        Set-Content -LiteralPath $obsoletePython -Value "obsolete" -Encoding ascii

        $environment = @{
            KFPS_ALLOW_CUSTOM_UPDATE_SOURCE = "1"
            REPO_URL = $SourceFixture
            BRANCH = "main"
            KFPS_UPDATER_ROOT = $appRoot
            FORZA_PAINTER_NO_PAUSE = "1"
            KFPS_RELAUNCH_AFTER_UPDATE = ""
            KFPS_RELAUNCH_TARGET = ""
            KFPS_UPDATER_HANDOFF = ""
            LOCALAPPDATA = $localAppData
            TEMP = $temp
            TMP = $temp
        }
        $firstLog = Join-Path $ResultRoot "v$version-stage1-original-bat.log"
        $firstExit = Invoke-NativeCapture "cmd.exe" @("/d", "/c", ('"' + $batch.FullName + '"')) $appRoot $firstLog $environment
        Assert-True ($firstExit -eq 0) "Historical $version BAT failed; see $firstLog"
        $innerUpdater = Join-Path $appRoot "KFPS-Updater.exe"
        $outerUpdater = Join-Path $installRoot "KFPS-Updater.exe"
        Assert-True (Test-Path -LiteralPath $innerUpdater -PathType Leaf) "Historical $version BAT did not acquire the inner bootstrap."
        Assert-True (((Get-FileHash -Algorithm SHA256 -LiteralPath $innerUpdater).Hash.ToLowerInvariant()) -eq $UpdaterHash) "Historical $version BAT acquired the wrong bootstrap bytes."
        $installedUpdateService = Join-Path $appRoot "KFPS.UI\src\kfps_ui\update_service.py"
        Assert-True (((Get-FileHash -Algorithm SHA256 -LiteralPath $installedUpdateService).Hash.ToLowerInvariant()) -eq $SourceUpdateServiceHash) "Historical $version BAT did not install the bootstrap-aware UI update service."
        Assert-True (-not (Test-Path -LiteralPath $outerUpdater)) "Historical $version BAT unexpectedly created the second-stage outer bootstrap."
        Assert-True (-not (Test-Path -LiteralPath $cv2Path)) "Historical $version BAT unexpectedly modified preserved Python."
        foreach ($marker in $markers) {
            Assert-True (Test-Path -LiteralPath $marker -PathType Leaf) "Historical $version BAT removed protected user data: $marker"
        }

        $secondLog = Join-Path $ResultRoot "v$version-stage2-bootstrap.log"
        $secondExit = Invoke-NativeCapture $innerUpdater @("--root", $installRoot, "--recover", "--recovery-archive", $RecoveryArchive, "--no-pause") $installRoot $secondLog $environment
        Assert-True ($secondExit -eq 0) "Historical $version bootstrap stage failed; see $secondLog"
        foreach ($candidate in @($innerUpdater, $outerUpdater)) {
            Assert-True (Test-Path -LiteralPath $candidate -PathType Leaf) "Bootstrap migration did not create $candidate"
            Assert-True (((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()) -eq $UpdaterHash) "Bootstrap migration copy is invalid: $candidate"
        }
        $primaryShim = Join-Path $installRoot $RetiredPaths[0]
        $retiredWrapper = Join-Path $installRoot $RetiredPaths[1]
        Assert-True (Test-Path -LiteralPath $primaryShim -PathType Leaf) "Bootstrap did not install the recovery compatibility shim."
        Assert-True ((Get-Content -LiteralPath $primaryShim -Raw).Contains("KFPS-Updater.exe")) "Recovery compatibility shim does not invoke the bootstrap."
        Assert-True (-not (Test-Path -LiteralPath $retiredWrapper)) "Bootstrap did not retire the legacy wrapper."
        Assert-True (Test-Path -LiteralPath $cv2Path -PathType Leaf) "Bootstrap did not repair the missing cv2 binary."
        Assert-True (-not (Test-Path -LiteralPath $obsoletePython)) "Bootstrap did not remove obsolete Python content."

        Remove-Item -LiteralPath $innerUpdater -Force
        $copyRepairLog = Join-Path $ResultRoot "v$version-stage3-repair-inner-copy.log"
        $copyRepairExit = Invoke-NativeCapture $outerUpdater @("--root", $installRoot, "--recover", "--recovery-archive", $RecoveryArchive, "--no-pause") $installRoot $copyRepairLog $environment
        Assert-True ($copyRepairExit -eq 0) "Outer bootstrap could not repair the inner copy for $version."
        Assert-True (((Get-FileHash -Algorithm SHA256 -LiteralPath $innerUpdater).Hash.ToLowerInvariant()) -eq $UpdaterHash) "Inner bootstrap repair is invalid for $version."

        Remove-Item -LiteralPath $cv2Path -Force
        foreach ($retired in $RetiredPaths) {
            $path = Join-Path $installRoot $retired
            Set-Content -LiteralPath $path -Value "stale legacy updater" -Encoding ascii
        }
        $repairLog = Join-Path $ResultRoot "v$version-stage4-repeat-repair.log"
        $repairExit = Invoke-NativeCapture $innerUpdater @("--root", $installRoot, "--recover", "--recovery-archive", $RecoveryArchive, "--no-pause") $installRoot $repairLog $environment
        Assert-True ($repairExit -eq 0) "Repeated repair failed for $version; see $repairLog"
        Assert-True (Test-Path -LiteralPath $cv2Path -PathType Leaf) "Repeated repair did not restore cv2 for $version."
        Assert-True ((Get-Content -LiteralPath $primaryShim -Raw).Contains("KFPS-Updater.exe")) "Repeated repair did not restore the bootstrap shim for $version."
        Assert-True (-not (Test-Path -LiteralPath $retiredWrapper)) "Repeated repair left the legacy wrapper for $version."

        $uiShimLog = Join-Path $ResultRoot "v$version-stage5-recovered-ui-shim.log"
        $uiShimExit = Invoke-NativeCapture "cmd.exe" @("/d", "/c", ('"' + $primaryShim + '"'), "--version") $appRoot $uiShimLog $environment
        Assert-True ($uiShimExit -eq 0) "Recovered UI compatibility shim could not start the bootstrap for $version."
        Assert-True ((Get-Content -LiteralPath $uiShimLog -Raw).Contains("KFPS Bootstrap Updater")) "Recovered UI shim did not execute the bootstrap for $version."

        Set-Content -LiteralPath $outerUpdater -Value "not a Windows executable" -Encoding ascii
        $uiShimCopyFallbackLog = Join-Path $ResultRoot "v$version-stage5-recovered-ui-copy-fallback.log"
        $uiShimCopyFallbackExit = Invoke-NativeCapture "cmd.exe" @("/d", "/c", ('"' + $primaryShim + '"'), "--version") $appRoot $uiShimCopyFallbackLog $environment
        Assert-True ($uiShimCopyFallbackExit -eq 0) "Recovered UI compatibility shim could not bypass a broken outer updater for $version."
        Assert-True ((Get-Content -LiteralPath $uiShimCopyFallbackLog -Raw).Contains("independently repairable inner copy")) "Recovered UI shim did not use the inner updater fallback for $version."

        $postFallbackRepairLog = Join-Path $ResultRoot "v$version-stage5-repair-outer-copy.log"
        $postFallbackRepairExit = Invoke-NativeCapture $innerUpdater @("--root", $installRoot, "--recover", "--recovery-archive", $RecoveryArchive, "--no-pause") $installRoot $postFallbackRepairLog $environment
        Assert-True ($postFallbackRepairExit -eq 0) "Inner bootstrap could not repair the outer copy after UI fallback for $version."
        Assert-True (((Get-FileHash -Algorithm SHA256 -LiteralPath $outerUpdater).Hash.ToLowerInvariant()) -eq $UpdaterHash) "Outer bootstrap copy remained invalid after UI fallback repair for $version."

        $uiShimFailureLog = Join-Path $ResultRoot "v$version-stage5-recovered-ui-shim-failure.log"
        $uiShimFailureExit = Invoke-NativeCapture "cmd.exe" @("/d", "/c", ('"' + $primaryShim + '"'), "--not-a-real-updater-option") $appRoot $uiShimFailureLog $environment
        Assert-True ($uiShimFailureExit -eq 2) "Recovered UI compatibility shim masked an updater failure for $version."

        $warmLog = Join-Path $ResultRoot "v$version-stage6-warm-check.log"
        $warmExit = Invoke-NativeCapture $outerUpdater @("--root", $installRoot, "--recover", "--recovery-archive", $RecoveryArchive, "--check", "--no-pause") $installRoot $warmLog $environment
        Assert-True ($warmExit -eq 0) "Warm no-op check failed for $version; see $warmLog"
        $inventory = Test-FinalInventory $installRoot $RecoveryManifest
        Assert-True ($inventory.Failures.Count -eq 0) "Final inventory failed for ${version}: $($inventory.Failures -join ', ')"
        foreach ($marker in $markers) {
            Assert-True (Test-Path -LiteralPath $marker -PathType Leaf) "Bootstrap removed protected user data: $marker"
        }
        $appReports = @(Get-ChildItem -LiteralPath (Join-Path $appRoot "runtime\update-reports") -File -Filter "update-*.json" -ErrorAction SilentlyContinue)
        Assert-True ($appReports.Count -ge 1) "No accessible application update report was produced for $version."

        $results += [pscustomobject]@{
            version = $version
            original_batch_sha256 = $batchHash
            source_commit = $Commit
            updater_sha256 = $UpdaterHash
            bootstrap_aware_update_service_sha256 = $SourceUpdateServiceHash
            first_stage_exit = $firstExit
            bootstrap_stage_exit = $secondExit
            copy_repair_exit = $copyRepairExit
            repeat_repair_exit = $repairExit
            recovered_ui_shim_exit = $uiShimExit
            recovered_ui_copy_fallback_exit = $uiShimCopyFallbackExit
            post_fallback_copy_repair_exit = $postFallbackRepairExit
            recovered_ui_failure_exit = $uiShimFailureExit
            warm_check_exit = $warmExit
            manifest_declared_files = $inventory.Declared
            manifest_verified_files = $inventory.Checked
            manifest_failures = $inventory.Failures.Count
            protected_markers = $markers.Count
            accessible_reports = $appReports.Count
            cv2_repaired_path = ([string]$Cv2Record.path)
        }
    }
    $summary = [ordered]@{
        schema = "kfps.legacy-bat-bootstrap-gate.v1"
        created_utc = [DateTime]::UtcNow.ToString("o")
        source_root = $SourceRoot
        source_fixture_commit = $Commit
        updater_sha256 = $UpdaterHash
        recovery_archive = $RecoveryArchive
        recovery_version = [string]$RecoveryManifest.version
        results = $results
        success = $true
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ResultRoot "summary.json") -Encoding utf8
    Write-Host "Legacy BAT to bootstrap migration gate passed for: $($Versions -join ', ')"
    Write-Host "Evidence: $ResultRoot"
} catch {
    $failure = [ordered]@{
        schema = "kfps.legacy-bat-bootstrap-gate.v1"
        created_utc = [DateTime]::UtcNow.ToString("o")
        source_root = $SourceRoot
        source_fixture_commit = $Commit
        updater_sha256 = $UpdaterHash
        results = $results
        success = $false
        error = $_.Exception.Message
    }
    $failure | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ResultRoot "summary.json") -Encoding utf8
    throw
} finally {
    foreach ($auxiliaryTempRoot in $auxiliaryTempRoots) {
        Remove-Item -LiteralPath $auxiliaryTempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not $KeepWork) {
        Remove-Item -LiteralPath $WorkRoot -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "Retained disposable work root: $WorkRoot"
    }
}
