param(
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$ToolRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $ToolRoot "..\..")).Path
$BuildRoot = Join-Path $ToolRoot "build"
$RunRoot = Join-Path $BuildRoot ("signed-cli-" + [guid]::NewGuid().ToString("N"))
$Publisher = Join-Path $BuildRoot "KFPS-Update-Publisher.exe"
$TestUpdater = Join-Path $RunRoot "KFPS-Updater-1.0.1.exe"
$OldUpdater = Join-Path $RunRoot "KFPS-Updater-1.0.0.exe"
$PrivateKey = Join-Path $RunRoot "test.private"
$PublicKey = Join-Path $RunRoot "test.public"
$Payload = Join-Path $RunRoot "payload"
$Source = Join-Path $RunRoot "source"
$Python = Join-Path $RunRoot "python"
$Target = Join-Path $RunRoot "target"
$State = Join-Path $RunRoot "state"
$ReportPath = Join-Path $RunRoot "release-gate-report.json"

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Message)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Message (exit $LASTEXITCODE)"
    }
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    $parent = Split-Path -Parent $Path
    if ($parent) {
        [IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

function Get-FileUri {
    param([string]$Path)
    return [Uri]::new([IO.Path]::GetFullPath($Path)).AbsoluteUri
}

function Invoke-TestUpdater {
    param([string]$Executable, [switch]$CheckOnly)
    $arguments = @(
        "--root", $Target,
        "--state-dir", $State,
        "--channel-url", (Get-FileUri (Join-Path $Payload "channel.json")),
        "--channel-signature-url", (Get-FileUri (Join-Path $Payload "channel.json.sig")),
        "--no-recovery-fallback",
        "--no-pause"
    )
    if ($CheckOnly) {
        $arguments += "--check"
    }
    & $Executable @arguments | Out-Host
    $exitCode = $LASTEXITCODE
    return $exitCode
}

function Assert-Text {
    param([string]$Path, [string]$Expected)
    $actual = [IO.File]::ReadAllText($Path)
    if ($actual -ne $Expected) {
        throw "$Path contains '$actual'; expected '$Expected'"
    }
}

[IO.Directory]::CreateDirectory($RunRoot) | Out-Null
$environmentBefore = $env:KFPS_UPDATER_TEST_MODE
$pauseBefore = $env:KFPS_UPDATER_NO_PAUSE
try {
    if (-not (Test-Path -LiteralPath $Publisher -PathType Leaf)) {
        throw "Build the updater first; publisher is missing: $Publisher"
    }
    Push-Location $ToolRoot
    try {
        Invoke-Checked { & $Publisher keygen --private $PrivateKey --public $PublicKey } "Ephemeral key generation failed"
        $public = [IO.File]::ReadAllText($PublicKey).Trim()
        $baseFlags = "-s -w -buildid="
        Invoke-Checked {
            & go build -trimpath -buildvcs=false -ldflags "$baseFlags -X main.version=1.0.1 -X main.trustedPublicKey=$public -X main.testFeatures=enabled" -o $TestUpdater ./cmd/kfps-updater
        } "Current test updater build failed"
        Invoke-Checked {
            & go build -trimpath -buildvcs=false -ldflags "$baseFlags -X main.version=1.0.0 -X main.trustedPublicKey=$public -X main.testFeatures=enabled" -o $OldUpdater ./cmd/kfps-updater
        } "Old test updater build failed"
    }
    finally {
        Pop-Location
    }

    Write-Utf8NoBom (Join-Path $Source "VERSION") "2.0.0`n"
    Write-Utf8NoBom (Join-Path $Source "KFPS.exe") "new-launcher"
    Copy-Item -LiteralPath $TestUpdater -Destination (Join-Path $Source "KFPS-Updater.exe")
    Write-Utf8NoBom (Join-Path $Source "KFPS.UI\program.txt") "new-program"
    Push-Location $Source
    try {
        Invoke-Checked { & git init -b main } "Fixture Git initialization failed"
        Invoke-Checked { & git config user.name "KFPS Updater Release Gate" } "Fixture Git user setup failed"
        Invoke-Checked { & git config user.email "updater-release-gate@example.invalid" } "Fixture Git email setup failed"
        Invoke-Checked { & git config core.autocrlf false } "Fixture Git line-ending setup failed"
        Invoke-Checked { & git add . } "Fixture Git add failed"
        Invoke-Checked { & git commit -m "signed updater fixture" } "Fixture Git commit failed"
        $commit = (& git rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "Fixture Git commit resolution failed"
        }
    }
    finally {
        Pop-Location
    }

    Write-Utf8NoBom (Join-Path $Python "python.exe") "new-python"
    Write-Utf8NoBom (Join-Path $Python "Lib\site.py") "new-site"
    Invoke-Checked {
        & $Publisher build --app-root $Source --python-root $Python --updater $TestUpdater --private $PrivateKey --public $PublicKey --output $Payload --base-url "https://updates.example.invalid/stable" --version 2.0.0 --commit $commit --bootstrap-version 1.0.1 --sequence 1 --published-utc "2026-09-01T12:00:00Z" --retired-file "retired.txt"
    } "Signed payload publication failed"

    $manifestPath = Join-Path $Payload "kfps-update-2.0.0.json"
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    foreach ($component in $manifest.components) {
        $name = Split-Path -Leaf $component.archive.url
        $component.archive.url = Get-FileUri (Join-Path $Payload $name)
    }
    Write-Utf8NoBom $manifestPath (($manifest | ConvertTo-Json -Depth 20) + "`n")
    Invoke-Checked { & $Publisher sign --private $PrivateKey --input $manifestPath --output ($manifestPath + ".sig") --overwrite } "Manifest re-signing failed"

    $channelPath = Join-Path $Payload "channel.json"
    $channel = Get-Content -LiteralPath $channelPath -Raw | ConvertFrom-Json
    $channel.updater.url = Get-FileUri (Join-Path $Payload (Split-Path -Leaf $channel.updater.url))
    $channel.manifest.url = Get-FileUri $manifestPath
    $channel.manifest.signature_url = Get-FileUri ($manifestPath + ".sig")
    $channel.manifest.size = (Get-Item -LiteralPath $manifestPath).Length
    $channel.manifest.sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
    Write-Utf8NoBom $channelPath (($channel | ConvertTo-Json -Depth 20) + "`n")
    Invoke-Checked { & $Publisher sign --private $PrivateKey --input $channelPath --output ($channelPath + ".sig") --overwrite } "Channel re-signing failed"

    Write-Utf8NoBom (Join-Path $Target "KFPS.exe") "old-launcher"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\VERSION") "1.0.0`n"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\KFPS.UI\program.txt") "old-program"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\03_update_from_github.bat") "bootstrap compatibility shim"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\update_from_github.bat") "legacy wrapper"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\retired.txt") "retire-me"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\python\obsolete.pyd") "obsolete"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\runtime\user.json") "preserve-runtime"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\user.kfpskey") "preserve-key"
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\python\Lib\__pycache__\generated.pyc") "preserve-cache"

    $env:KFPS_UPDATER_TEST_MODE = "1"
    $env:KFPS_UPDATER_NO_PAUSE = "1"
    $dryCode = Invoke-TestUpdater -Executable $TestUpdater -CheckOnly
	if ($dryCode -ne 3) {
		throw "Signed dry run did not report required repairs with exit 3; got $dryCode"
    }
    Assert-Text (Join-Path $Target "KloudysFH6Painter\VERSION") "1.0.0`n"
    if (Test-Path -LiteralPath (Join-Path $State "state.json")) {
        throw "Dry run advanced signed sequence state"
    }

    $handoffCheckCode = Invoke-TestUpdater -Executable $OldUpdater -CheckOnly
    if ($handoffCheckCode -ne 3) {
        throw "Verified check handoff did not propagate child repair-required exit 3; got $handoffCheckCode"
    }
    Assert-Text (Join-Path $Target "KloudysFH6Painter\VERSION") "1.0.0`n"
    if (Test-Path -LiteralPath (Join-Path $State "state.json")) {
        throw "Verified check handoff advanced signed sequence state"
    }

    $handoffCode = Invoke-TestUpdater -Executable $OldUpdater
    if ($handoffCode -ne 4) {
        throw "Self-update handoff did not report verified child pending with exit 4; got $handoffCode"
    }
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $versionPath = Join-Path $Target "KloudysFH6Painter\VERSION"
        $lockPath = Join-Path $State "updater.lock"
        if ((Test-Path -LiteralPath $versionPath) -and ([IO.File]::ReadAllText($versionPath).Trim() -eq "2.0.0") -and -not (Test-Path -LiteralPath $lockPath)) {
            break
        }
        Start-Sleep -Milliseconds 200
    }
    Assert-Text (Join-Path $Target "KloudysFH6Painter\VERSION") "2.0.0`n"
    Assert-Text (Join-Path $Target "KloudysFH6Painter\KFPS.UI\program.txt") "new-program"
    Assert-Text (Join-Path $Target "KloudysFH6Painter\runtime\user.json") "preserve-runtime"
    Assert-Text (Join-Path $Target "KloudysFH6Painter\user.kfpskey") "preserve-key"
    Assert-Text (Join-Path $Target "KloudysFH6Painter\python\Lib\__pycache__\generated.pyc") "preserve-cache"
    foreach ($removed in @(
        "KloudysFH6Painter\03_update_from_github.bat",
        "KloudysFH6Painter\update_from_github.bat",
        "KloudysFH6Painter\retired.txt",
        "KloudysFH6Painter\python\obsolete.pyd"
    )) {
        if (Test-Path -LiteralPath (Join-Path $Target $removed)) {
            throw "Signed update did not remove $removed"
        }
    }

    $noOpCode = Invoke-TestUpdater -Executable $TestUpdater
    if ($noOpCode -ne 0) {
        throw "Healthy signed no-op failed with exit $noOpCode"
    }
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\KFPS.UI\program.txt") "corrupt-program"
    $repairCode = Invoke-TestUpdater -Executable $TestUpdater
    if ($repairCode -ne 0) {
        throw "Same-version signed repair failed with exit $repairCode"
    }
    Assert-Text (Join-Path $Target "KloudysFH6Painter\KFPS.UI\program.txt") "new-program"

    $statePath = Join-Path $State "state.json"
    $persistent = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $persistent.highest_sequence = 2
    Write-Utf8NoBom $statePath (($persistent | ConvertTo-Json -Depth 10) + "`n")
    Write-Utf8NoBom (Join-Path $Target "KloudysFH6Painter\KFPS.UI\program.txt") "must-remain-corrupt"
    $rollbackCode = Invoke-TestUpdater -Executable $TestUpdater
    if ($rollbackCode -eq 0) {
        throw "Signed sequence rollback was accepted"
    }
    Assert-Text (Join-Path $Target "KloudysFH6Painter\KFPS.UI\program.txt") "must-remain-corrupt"

    $reports = Get-ChildItem -LiteralPath (Join-Path $State "reports") -File | ForEach-Object {
        Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
    }
    $result = [ordered]@{
        schema = "kfps.bootstrap-release-gate.v1"
        success = $true
        dry_run_exit = $dryCode
        handoff_check_exit = $handoffCheckCode
        handoff_pending_exit = $handoffCode
        no_op_exit = $noOpCode
        repair_exit = $repairCode
        rollback_rejection_exit = $rollbackCode
        reports = $reports.Count
        completed = @($reports | Where-Object status -eq "completed").Count
        handoffs = @($reports | Where-Object status -eq "handoff-pending").Count
        failures = @($reports | Where-Object status -eq "failed").Count
        run_root = $RunRoot
    }
    Write-Utf8NoBom $ReportPath (($result | ConvertTo-Json -Depth 10) + "`n")
    $result | Format-List
}
finally {
    $env:KFPS_UPDATER_TEST_MODE = $environmentBefore
    $env:KFPS_UPDATER_NO_PAUSE = $pauseBefore
    if (-not $KeepArtifacts -and (Test-Path -LiteralPath $RunRoot)) {
        $resolvedRun = [IO.Path]::GetFullPath($RunRoot)
        $resolvedBuild = [IO.Path]::GetFullPath($BuildRoot) + [IO.Path]::DirectorySeparatorChar
        if (-not $resolvedRun.StartsWith($resolvedBuild, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean an unsafe release-gate path: $resolvedRun"
        }
        Get-ChildItem -LiteralPath $resolvedRun -Recurse -Force -File -ErrorAction SilentlyContinue | ForEach-Object {
            $_.Attributes = [IO.FileAttributes]::Normal
        }
        [IO.Directory]::Delete($resolvedRun, $true)
    }
}
