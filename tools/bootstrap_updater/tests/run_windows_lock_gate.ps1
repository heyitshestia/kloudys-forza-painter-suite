param(
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$ToolRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $ToolRoot "build"
$RunRoot = Join-Path $BuildRoot ("windows-lock-" + [guid]::NewGuid().ToString("N"))
$Updater = Join-Path $RunRoot "KFPS-Updater-test.exe"
$Target = Join-Path $RunRoot "target"
$State = Join-Path $RunRoot "state"
$Outside = Join-Path $RunRoot "outside"
$Marker = Join-Path $Outside "preserve.txt"
$Report = Join-Path $RunRoot "windows-lock-gate.json"

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    $parent = Split-Path -Parent $Path
    if ($parent) {
        [IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

[IO.Directory]::CreateDirectory($RunRoot) | Out-Null
$testModeBefore = $env:KFPS_UPDATER_TEST_MODE
$pauseBefore = $env:KFPS_UPDATER_NO_PAUSE
try {
    $public = [IO.File]::ReadAllText((Join-Path $ToolRoot "trust\production-ed25519.public")).Trim()
    Push-Location $ToolRoot
    try {
        & go build -trimpath -buildvcs=false -ldflags "-s -w -buildid= -X main.version=1.0.1 -X main.trustedPublicKey=$public -X main.testFeatures=enabled" -o $Updater ./cmd/kfps-updater
        if ($LASTEXITCODE -ne 0) {
            throw "Test-enabled updater build failed with exit $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    Write-Utf8NoBom (Join-Path $Target "KFPS.exe") "launcher"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\VERSION") "1.0.0`n"
    [IO.Directory]::CreateDirectory((Join-Path $Target "KloudysFH6Painter\KFPS.UI")) | Out-Null
    [IO.Directory]::CreateDirectory($State) | Out-Null
    [IO.Directory]::CreateDirectory($Outside) | Out-Null
    Write-Utf8NoBom $Marker "preserve-me"
    New-Item -ItemType Junction -Path (Join-Path $State "updater.lock") -Target $Outside | Out-Null

    $env:KFPS_UPDATER_TEST_MODE = "1"
    $env:KFPS_UPDATER_NO_PAUSE = "1"
    & $Updater --root $Target --state-dir $State --no-recovery-fallback --no-pause --check | Out-Host
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 1) {
        throw "Lock-junction check exited $exitCode instead of 1"
    }
    if ([IO.File]::ReadAllText($Marker) -ne "preserve-me") {
        throw "The outside junction target was modified"
    }

    $result = [ordered]@{
        schema = "kfps.bootstrap-windows-lock-gate.v1"
        success = $true
        exit_code = $exitCode
        outside_marker_preserved = $true
        run_root = $RunRoot
    }
    Write-Utf8NoBom $Report (($result | ConvertTo-Json -Depth 5) + "`n")
    $result | Format-List
}
finally {
    $env:KFPS_UPDATER_TEST_MODE = $testModeBefore
    $env:KFPS_UPDATER_NO_PAUSE = $pauseBefore
    if (-not $KeepArtifacts -and (Test-Path -LiteralPath $RunRoot)) {
        $resolvedRun = [IO.Path]::GetFullPath($RunRoot)
        $resolvedBuild = [IO.Path]::GetFullPath($BuildRoot) + [IO.Path]::DirectorySeparatorChar
        if (-not $resolvedRun.StartsWith($resolvedBuild, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean an unsafe lock-gate path: $resolvedRun"
        }
        $lockPath = Join-Path $State "updater.lock"
        if (Test-Path -LiteralPath $lockPath) {
            [IO.Directory]::Delete($lockPath, $false)
        }
        Get-ChildItem -LiteralPath $resolvedRun -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object {
            $_.Attributes = [IO.FileAttributes]::Normal
        }
        [IO.Directory]::Delete($resolvedRun, $true)
    }
}
