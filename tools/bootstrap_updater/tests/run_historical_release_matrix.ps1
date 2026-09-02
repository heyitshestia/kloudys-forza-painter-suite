param(
    [Parameter(Mandatory = $true)]
    [string]$RecoveryArchive,
    [string]$Updater = "",
    [string]$Repository = "heyitshestia/kloudys-forza-painter-suite",
    [string[]]$Fixture = @(
        "v3.1.52-advanced",
        "v3.1.52-bundled",
        "v3.1.28-advanced",
        "v3.1.28-bundled",
        "v3.1.14-bundled",
        "v3.0.96-bundled",
        "v2.0.59",
        "v1.10.75",
        "v1.6.1"
    ),
    [switch]$KeepRuns
)

$ErrorActionPreference = "Stop"
$ToolRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $ToolRoot "build"
$CacheRoot = Join-Path $BuildRoot "historical-release-cache"
$RunBase = Join-Path $BuildRoot "historical-release-runs"
$ResultRoot = Join-Path $BuildRoot ("historical-release-results-" + [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss"))
$ExpectedRecoveryHash = "551f4052ee8f6707d7c7e24fb7b42ed74be9bfac45e3cfdd7281ca773e1ad0ec"
$Started = [DateTime]::UtcNow

if (-not $Updater) {
    $Updater = Join-Path (Resolve-Path (Join-Path $ToolRoot "..\..")).Path "KFPS-Updater.exe"
}

$Catalog = @{
    "v3.1.52-advanced" = @{ Tag = "v3.1.52"; Asset = "KFPS-3.1.52-ADVANCED-NO-PYTHON-NO-DEPENDENCIES.zip" }
    "v3.1.52-bundled" = @{ Tag = "v3.1.52"; Asset = "KFPS-3.1.52-bundled.zip" }
    "v3.1.28-advanced" = @{ Tag = "v3.1.28"; Asset = "KFPS-3.1.28-ADVANCED-NO-PYTHON-NO-DEPENDENCIES.zip" }
    "v3.1.28-bundled" = @{ Tag = "v3.1.28"; Asset = "KFPS-3.1.28-bundled.zip" }
    "v3.1.14-bundled" = @{ Tag = "v3.1.14"; Asset = "KFPS-3.1.14-bundled.zip" }
    "v3.0.96-bundled" = @{ Tag = "v3.0.96"; Asset = "KFPS-3.0.96-bundled.zip" }
    "v2.0.59" = @{ Tag = "v2.0.59"; Asset = "Kloudys-FH6-Painter-2.0.59.zip" }
    "v1.10.75" = @{ Tag = "v1.10.75"; Asset = "Kloudys-FH6-Painter-1.10.75.zip" }
    "v1.6.1" = @{ Tag = "v1.6.1"; Asset = "Kloudys-FH6-Painter-v1.6.1.zip" }
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Remove-SafeTree {
    param([string]$Path, [string]$AllowedRoot)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $root = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd("\") + "\"
    $target = [IO.Path]::GetFullPath($Path).TrimEnd("\")
    if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the historical-test root: $target"
    }
    Get-ChildItem -LiteralPath $target -File -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object IsReadOnly |
        ForEach-Object { $_.IsReadOnly = $false }
    [IO.Directory]::Delete($target, $true)
}

function Assert-SafeZip {
    param([string]$Path)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName.Replace("\", "/")
            if (-not $name -or $name.StartsWith("/") -or $name -match "^[A-Za-z]:" -or
                $name -match "(^|/)\.\.(/|$)") {
                throw "Unsafe ZIP entry in $Path`: $name"
            }
            if (-not $seen.Add($name)) {
                throw "Duplicate ZIP entry in $Path`: $name"
            }
            $unixMode = ($entry.ExternalAttributes -shr 16) -band 0xF000
            if ($unixMode -eq 0xA000) {
                throw "Symbolic-link ZIP entry in $Path`: $name"
            }
        }
        return $archive.Entries.Count
    }
    finally {
        $archive.Dispose()
    }
}

function Find-InstallRoot {
    param([string]$ExtractRoot)
    $candidates = @($ExtractRoot)
    $candidates += @(Get-ChildItem -LiteralPath $ExtractRoot -Directory -Recurse -Depth 2 |
        Select-Object -ExpandProperty FullName)
    $matches = @($candidates | Where-Object {
        Test-Path -LiteralPath (Join-Path $_ "KloudysFH6Painter") -PathType Container
    } | Sort-Object Length)
    if ($matches.Count -gt 0) {
        return $matches[0]
    }
    $apps = @(Get-ChildItem -LiteralPath $ExtractRoot -Directory -Recurse -Depth 2 | Where-Object {
        $_.Name -eq "KloudysFH6Painter"
    } | Sort-Object { $_.FullName.Length })
    if ($apps.Count -gt 0) {
        return $apps[0].Parent.FullName
    }
    $legacy = @($candidates | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_ "VERSION") -PathType Leaf) -and
        ((Test-Path -LiteralPath (Join-Path $_ "app.py") -PathType Leaf) -or
         (Test-Path -LiteralPath (Join-Path $_ "00_launcher.bat") -PathType Leaf))
    } | Sort-Object Length)
    if ($legacy.Count -gt 0) {
        return $legacy[0]
    }
    throw "The extracted archive does not contain a recognizable KFPS installation root."
}

function Test-ReleaseInventory {
    param([string]$InstallRoot)
    $manifestPath = Join-Path $InstallRoot "RELEASE-MANIFEST.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Recovered installation has no RELEASE-MANIFEST.json."
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $failed = 0
    $managed = 0
    foreach ($record in $manifest.files) {
        $key = $record.path.ToLowerInvariant()
        if ($key.EndsWith(".pyc") -or $key.Contains("/__pycache__/")) {
            continue
        }
        $managed++
        $path = Join-Path $InstallRoot ($record.path -replace "/", "\")
        $info = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        if ($null -eq $info -or $info.PSIsContainer) {
            $failed++
            continue
        }
        $hash = Get-Sha256 $path
        if ($info.Length -ne [int64]$record.size -or $hash -ne $record.sha256.ToLowerInvariant()) {
            $failed++
        }
    }
    return [pscustomobject]@{
        Version = $manifest.version
        Declared = @($manifest.files).Count
        Managed = $managed
        Failed = $failed
    }
}

function Invoke-Recovery {
    param([string]$Executable, [string]$InstallRoot, [switch]$CheckOnly)
    $arguments = @(
        "--root", $InstallRoot,
        "--recover",
        "--recovery-archive", $RecoveryArchive,
        "--no-pause"
    )
    if ($CheckOnly) {
        $arguments += "--check"
    }
    & $Executable @arguments | Out-Host
    return $LASTEXITCODE
}

function Copy-Diagnostics {
    param([string]$StateRoot, [string]$Destination)
    [IO.Directory]::CreateDirectory($Destination) | Out-Null
    if (Test-Path -LiteralPath $StateRoot -PathType Container) {
        Copy-Item -LiteralPath $StateRoot -Destination (Join-Path $Destination "localappdata") -Recurse -Force
    }
}

foreach ($name in $Fixture) {
    if (-not $Catalog.ContainsKey($name)) {
        throw "Unknown historical fixture '$name'."
    }
}
if (-not (Test-Path -LiteralPath $RecoveryArchive -PathType Leaf)) {
    throw "Recovery archive is missing: $RecoveryArchive"
}
if ((Get-Sha256 $RecoveryArchive) -ne $ExpectedRecoveryHash) {
    throw "Recovery archive does not match the pinned KFPS 3.1.54 fixture."
}
if (-not (Test-Path -LiteralPath $Updater -PathType Leaf)) {
    throw "Bootstrap updater is missing: $Updater"
}
$UpdaterHash = Get-Sha256 $Updater
$VersionOutput = & $Updater --version
if ($LASTEXITCODE -ne 0 -or $VersionOutput -notcontains "KFPS Bootstrap Updater 1.0.1") {
    throw "Historical matrix requires bootstrap updater 1.0.1."
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI is required to retrieve authenticated draft release assets."
}
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated."
}

[IO.Directory]::CreateDirectory($CacheRoot) | Out-Null
[IO.Directory]::CreateDirectory($RunBase) | Out-Null
[IO.Directory]::CreateDirectory($ResultRoot) | Out-Null
Write-Host "HISTORICAL_RESULT_ROOT=$ResultRoot"

$releaseJson = & gh api "repos/$Repository/releases?per_page=100"
if ($LASTEXITCODE -ne 0) {
    throw "Could not enumerate draft releases from $Repository."
}
$releases = $releaseJson | ConvertFrom-Json
$results = [Collections.Generic.List[object]]::new()
$pauseBefore = $env:KFPS_UPDATER_NO_PAUSE
$localAppDataBefore = $env:LOCALAPPDATA
$env:KFPS_UPDATER_NO_PAUSE = "1"

try {
    foreach ($name in $Fixture) {
        $fixtureStarted = [DateTime]::UtcNow
        $definition = $Catalog[$name]
        $release = @($releases | Where-Object tag_name -eq $definition.Tag)
        if ($release.Count -ne 1 -or -not $release[0].draft) {
            throw "Expected exactly one draft release for $($definition.Tag)."
        }
        $asset = @($release[0].assets | Where-Object name -eq $definition.Asset)
        if ($asset.Count -ne 1) {
            throw "Draft $($definition.Tag) does not contain $($definition.Asset)."
        }
        $asset = $asset[0]
        $expectedAssetHash = ([string]$asset.digest -replace "^sha256:", "").ToLowerInvariant()
        if ($expectedAssetHash -notmatch "^[0-9a-f]{64}$") {
            throw "GitHub did not provide a valid SHA-256 for $($definition.Asset)."
        }

        $tagCache = Join-Path $CacheRoot $definition.Tag
        [IO.Directory]::CreateDirectory($tagCache) | Out-Null
        $archive = Join-Path $tagCache $definition.Asset
        if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
            $downloadRoot = Join-Path $tagCache ("download-" + [guid]::NewGuid().ToString("N"))
            [IO.Directory]::CreateDirectory($downloadRoot) | Out-Null
            try {
                Write-Host "Downloading authenticated draft fixture $name..."
                & gh release download $definition.Tag --repo $Repository --pattern $definition.Asset --dir $downloadRoot
                if ($LASTEXITCODE -ne 0) {
                    throw "Draft fixture download failed for $name."
                }
                $downloaded = Join-Path $downloadRoot $definition.Asset
                if (-not (Test-Path -LiteralPath $downloaded -PathType Leaf)) {
                    throw "GitHub CLI did not produce the requested asset for $name."
                }
                Move-Item -LiteralPath $downloaded -Destination $archive
            }
            finally {
                Remove-SafeTree $downloadRoot $tagCache
            }
        }
        $archiveInfo = Get-Item -LiteralPath $archive
        $archiveHash = Get-Sha256 $archive
        if ($archiveInfo.Length -ne [int64]$asset.size -or $archiveHash -ne $expectedAssetHash) {
            throw "Cached fixture does not match GitHub metadata for $name."
        }
        $entryCount = Assert-SafeZip $archive
        $fixtureMetadata = [ordered]@{
            schema = "kfps.bootstrap-historical-fixture.v1"
            fixture = $name
            repository = $Repository
            release_id = $release[0].id
            tag = $definition.Tag
            draft = $release[0].draft
            asset_id = $asset.id
            asset_name = $asset.name
            asset_bytes = $archiveInfo.Length
            asset_sha256 = $archiveHash
            asset_created_utc = ([DateTime]$asset.created_at).ToUniversalTime().ToString("o")
            zip_entries = $entryCount
        }
        Write-Utf8NoBom ($archive + ".fixture.json") (($fixtureMetadata | ConvertTo-Json -Depth 8) + "`n")

        $runRoot = Join-Path $RunBase (([DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")) + "-" + $name)
        $extractRoot = Join-Path $runRoot "extract"
        $stateRoot = Join-Path $runRoot "state"
        $fixtureResultRoot = Join-Path $ResultRoot $name
        [IO.Directory]::CreateDirectory($extractRoot) | Out-Null
        [IO.Directory]::CreateDirectory($fixtureResultRoot) | Out-Null
        $result = [ordered]@{
            schema = "kfps.bootstrap-historical-result.v1"
            fixture = $name
            tag = $definition.Tag
            asset_id = $asset.id
            asset_name = $asset.name
            asset_bytes = $archiveInfo.Length
            asset_sha256 = $archiveHash
            updater_sha256 = $UpdaterHash
            success = $false
            started_utc = $fixtureStarted.ToString("o")
            run_root = $runRoot
        }
        try {
            Write-Host "[$name] Extracting $($definition.Asset)..."
            Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot
            $installRoot = Find-InstallRoot $extractRoot
            $resolvedRun = [IO.Path]::GetFullPath($runRoot).TrimEnd("\") + "\"
            $resolvedInstall = [IO.Path]::GetFullPath($installRoot)
            if (-not $resolvedInstall.StartsWith($resolvedRun, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Extracted installation escaped its disposable run root."
            }
            $modernAppRoot = Join-Path $installRoot "KloudysFH6Painter"
            $legacyFlat = -not (Test-Path -LiteralPath $modernAppRoot -PathType Container)
            $appRoot = if ($legacyFlat) { $installRoot } else { $modernAppRoot }
            $versionPath = Join-Path $appRoot "VERSION"
            $originalVersion = if (Test-Path -LiteralPath $versionPath -PathType Leaf) {
                (Get-Content -LiteralPath $versionPath -Raw).Trim()
            }
            else {
                "unknown"
            }
            $result.original_version = $originalVersion
            $result.legacy_flat_layout = $legacyFlat
            $fixtureUpdater = Join-Path $installRoot "KFPS-Updater.exe"
            Copy-Item -LiteralPath $Updater -Destination $fixtureUpdater -Force
            if ((Get-Sha256 $fixtureUpdater) -ne $UpdaterHash) {
                throw "Copied updater hash changed inside fixture $name."
            }

            $runtimeMarker = Join-Path $appRoot "runtime\historical-updater-validation\$name.json"
            $keyMarker = Join-Path $appRoot "historical-updater-validation-$name.kfpskey"
            $imageMarker = Join-Path $appRoot "imgs\historical-updater-validation\$name.txt"
            $cacheMarker = Join-Path $appRoot "python\Lib\__pycache__\historical-updater-validation-$name.pyc"
            $obsolete = if ($legacyFlat) { "" } else { Join-Path $appRoot "python\historical-obsolete-$name.pyd" }
            $markers = [ordered]@{
                $runtimeMarker = "runtime-$name"
                $keyMarker = "key-$name"
                $imageMarker = "image-$name"
                $cacheMarker = "cache-$name"
            }
            foreach ($marker in $markers.GetEnumerator()) {
                Write-Utf8NoBom $marker.Key $marker.Value
            }
            if ($obsolete) {
                Write-Utf8NoBom $obsolete "obsolete-$name"
            }
            $versionHashBefore = if (Test-Path -LiteralPath $versionPath -PathType Leaf) {
                Get-Sha256 $versionPath
            }
            else {
                ""
            }

            Write-Host "[$name] Checking historical installation..."
            $env:LOCALAPPDATA = $stateRoot
            $checkExit = Invoke-Recovery $fixtureUpdater $installRoot -CheckOnly
            $result.check_exit = $checkExit
            if ($checkExit -ne 3) {
                throw "Historical dry-run exited $checkExit instead of 3."
            }
            if ($versionHashBefore -and (Get-Sha256 $versionPath) -ne $versionHashBefore) {
                throw "Historical dry-run changed VERSION."
            }
            foreach ($marker in $markers.GetEnumerator()) {
                if ([IO.File]::ReadAllText($marker.Key) -ne $marker.Value) {
                    throw "Historical dry-run changed protected marker $($marker.Key)."
                }
            }

            Write-Host "[$name] Applying pinned 3.1.54 recovery..."
            $applyExit = Invoke-Recovery $fixtureUpdater $installRoot
            $result.apply_exit = $applyExit
            if ($applyExit -ne 0) {
                throw "Historical recovery exited $applyExit."
            }
            foreach ($marker in $markers.GetEnumerator()) {
                if ([IO.File]::ReadAllText($marker.Key) -ne $marker.Value) {
                    throw "Historical recovery changed protected marker $($marker.Key)."
                }
            }
            if ($legacyFlat -and $versionHashBefore -and (Get-Sha256 $versionPath) -ne $versionHashBefore) {
                throw "Historical recovery changed the legacy root VERSION marker."
            }
            if ($obsolete -and (Test-Path -LiteralPath $obsolete)) {
                throw "Historical recovery did not remove the obsolete Python file."
            }
            if ((Get-Sha256 $fixtureUpdater) -ne $UpdaterHash) {
                throw "Historical recovery changed the bootstrap updater."
            }
            $inventory = Test-ReleaseInventory $installRoot
            if ($inventory.Version -ne "3.1.54" -or $inventory.Failed -ne 0) {
                throw "Recovered inventory is invalid: version=$($inventory.Version), failures=$($inventory.Failed)."
            }
            Write-Host "[$name] Verifying warm no-op..."
            $warmExit = Invoke-Recovery $fixtureUpdater $installRoot -CheckOnly
            $result.warm_check_exit = $warmExit
            if ($warmExit -ne 0) {
                throw "Historical warm check exited $warmExit."
            }
            $activeJournals = @(Get-ChildItem -LiteralPath $stateRoot -File -Recurse -Filter "journal.json" -ErrorAction SilentlyContinue)
            if ($activeJournals.Count -gt 0) {
                throw "Historical recovery left an active transaction journal."
            }

            $result.final_version = $inventory.Version
            $result.final_declared_files = $inventory.Declared
            $result.final_managed_files = $inventory.Managed
            $result.final_hash_failures = $inventory.Failed
            $result.protected_markers = $markers.Count
            $result.obsolete_python_removed = -not $legacyFlat
            $result.legacy_root_preserved = if ($legacyFlat) { $true } else { $null }
            $result.success = $true
        }
        catch {
            $result.error = $_.Exception.Message
            Write-Warning "[$name] $($result.error)"
        }
        finally {
            $result.finished_utc = [DateTime]::UtcNow.ToString("o")
            $result.duration_seconds = [math]::Round(([DateTime]::UtcNow - $fixtureStarted).TotalSeconds, 3)
            $removeRun = $result.success -and -not $KeepRuns
            $result.run_retained = -not $removeRun
            if ($removeRun) {
                $result.run_root = $null
            }
            Copy-Diagnostics $stateRoot (Join-Path $fixtureResultRoot "updater-state")
            Write-Utf8NoBom (Join-Path $fixtureResultRoot "result.json") (($result | ConvertTo-Json -Depth 10) + "`n")
            $results.Add([pscustomobject]$result)
            if ($removeRun) {
                Remove-SafeTree $runRoot $RunBase
            }
        }
    }
}
finally {
    $env:KFPS_UPDATER_NO_PAUSE = $pauseBefore
    $env:LOCALAPPDATA = $localAppDataBefore
}

$failed = @($results | Where-Object { -not $_.success })
$matrix = [ordered]@{
    schema = "kfps.bootstrap-historical-matrix.v1"
    success = $failed.Count -eq 0
    started_utc = $Started.ToString("o")
    finished_utc = [DateTime]::UtcNow.ToString("o")
    repository = $Repository
    recovery_archive = (Resolve-Path -LiteralPath $RecoveryArchive).Path
    recovery_sha256 = Get-Sha256 $RecoveryArchive
    updater = (Resolve-Path -LiteralPath $Updater).Path
    updater_sha256 = $UpdaterHash
    fixture_count = $results.Count
    passed = $results.Count - $failed.Count
    failed = $failed.Count
    results = @($results)
}
Write-Utf8NoBom (Join-Path $ResultRoot "historical-release-matrix.json") (($matrix | ConvertTo-Json -Depth 12) + "`n")
$results | Select-Object fixture, original_version, final_version, check_exit, apply_exit, warm_check_exit, success, error |
    Format-Table -AutoSize
if ($failed.Count -gt 0) {
    throw "$($failed.Count) historical fixture(s) failed. Results: $ResultRoot"
}
Write-Host "Historical release matrix passed. Results: $ResultRoot"
