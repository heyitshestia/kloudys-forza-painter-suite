param(
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Launcher = Join-Path $Root "KFPS.exe"
$Python312 = (& py -3.12 -c "import sys; print(sys.executable)").Trim()
$PythonDir = Split-Path -Parent $Python312
$Stage = Join-Path ([System.IO.Path]::GetTempPath()) ("KFPS Release Layout Tests " + [Guid]::NewGuid().ToString("N"))
$Results = Join-Path $Stage "Results"
$Junctions = [System.Collections.Generic.List[string]]::new()

function Copy-TrackedTree {
    param([string]$Destination)

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $Tracked = & git -C $Root ls-files
    if ($LASTEXITCODE -ne 0) {
        throw "git ls-files failed while preparing the release-layout test."
    }
    foreach ($Relative in $Tracked) {
        if ($Relative -eq "KFPS.exe") {
            continue
        }
        $Source = Join-Path $Root $Relative
        if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
            continue
        }
        $Target = Join-Path $Destination $Relative
        $TargetParent = Split-Path -Parent $Target
        New-Item -ItemType Directory -Path $TargetParent -Force | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Target
    }
}

function Invoke-KfpsScreenshot {
    param(
        [string]$Executable,
        [string]$Target,
        [switch]$AllowSource
    )

    $Arguments = @(
        "--demo",
        "--skip-startup-index",
        "--skip-startup-thumbnails",
        "--width", "1360",
        "--height", "820",
        "--screenshot", ('"' + $Target + '"')
    )
    if ($AllowSource) {
        $Arguments = @("--allow-source-download") + $Arguments
    }
    $Info = [System.Diagnostics.ProcessStartInfo]::new()
    $Info.FileName = $Executable
    $Info.Arguments = $Arguments -join " "
    $Info.WorkingDirectory = Split-Path -Parent $Executable
    $Info.UseShellExecute = $false
    $Info.CreateNoWindow = $true
    $Process = [System.Diagnostics.Process]::Start($Info)
    if (-not $Process.WaitForExit(90000)) {
        $Process.Kill()
        throw "KFPS did not finish the screenshot test within 90 seconds."
    }
    if ($Process.ExitCode -ne 0) {
        throw "KFPS screenshot test exited with code $($Process.ExitCode): $Target"
    }
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
        throw "KFPS did not create the expected screenshot: $Target"
    }
    if ((Get-Item -LiteralPath $Target).Length -lt 10000) {
        throw "KFPS created an unexpectedly small screenshot: $Target"
    }
}

$PreviousEnvironment = @{
    KFPS_PYTHON = $env:KFPS_PYTHON
    QT_QPA_PLATFORM = $env:QT_QPA_PLATFORM
    QT_QUICK_BACKEND = $env:QT_QUICK_BACKEND
    QSG_RHI_BACKEND = $env:QSG_RHI_BACKEND
    KFPS_QML_GRAPHICS = $env:KFPS_QML_GRAPHICS
}

try {
    New-Item -ItemType Directory -Path $Results -Force | Out-Null
    Remove-Item Env:KFPS_PYTHON -ErrorAction SilentlyContinue
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:QT_QUICK_BACKEND = "software"
    $env:QSG_RHI_BACKEND = "software"
    $env:KFPS_QML_GRAPHICS = "software"

    $Release = Join-Path $Stage "KFPS-TEST-binary"
    $ReleaseApp = Join-Path $Release "KloudysFH6Painter"
    Copy-TrackedTree $ReleaseApp
    New-Item -ItemType Directory -Path (Join-Path $Release "Images") -Force | Out-Null
    Copy-Item -LiteralPath $Launcher -Destination (Join-Path $Release "KFPS.exe")
    if (Test-Path -LiteralPath (Join-Path $ReleaseApp "python")) {
        throw "The no-runtime release fixture unexpectedly contains a python directory."
    }
    Invoke-KfpsScreenshot (Join-Path $Release "KFPS.exe") (Join-Path $Results "release-no-runtime.png")

    $Source = Join-Path $Stage "kloudys-forza-painter-suite-main"
    Copy-TrackedTree $Source
    Copy-Item -LiteralPath $Launcher -Destination (Join-Path $Source "KFPS.exe")
    Invoke-KfpsScreenshot (Join-Path $Source "KFPS.exe") (Join-Path $Results "source-blocked-no-runtime.png")
    if (Test-Path -LiteralPath (Join-Path $Source "runtime")) {
        throw "Blocked source startup initialized runtime state before showing the blocker."
    }

    $PythonJunction = Join-Path $Source "python"
    New-Item -ItemType Junction -Path $PythonJunction -Target $PythonDir | Out-Null
    $Junctions.Add($PythonJunction)
    Invoke-KfpsScreenshot (Join-Path $Source "KFPS.exe") (Join-Path $Results "source-blocked-with-python.png")
    if (Test-Path -LiteralPath (Join-Path $Source "runtime")) {
        throw "A source folder with a manually added runtime bypassed the startup guard."
    }

    Invoke-KfpsScreenshot (Join-Path $Source "KFPS.exe") (Join-Path $Results "source-explicit-bypass.png") -AllowSource

    Write-Host "PASS: no-runtime nested release launched the normal QML application"
    Write-Host "PASS: flat source download was blocked before runtime initialization"
    Write-Host "PASS: adding a Python directory did not bypass the source guard"
    Write-Host "PASS: explicit emergency bypass still launched the normal application"
    Write-Host "RESULTS: $Results"
}
finally {
    foreach ($Name in $PreviousEnvironment.Keys) {
        $Value = $PreviousEnvironment[$Name]
        if ($null -eq $Value) {
            Remove-Item ("Env:" + $Name) -ErrorAction SilentlyContinue
        } else {
            Set-Item ("Env:" + $Name) $Value
        }
    }
    foreach ($Junction in $Junctions) {
        if (Test-Path -LiteralPath $Junction) {
            [System.IO.Directory]::Delete($Junction)
        }
    }
    if (-not $KeepTemp -and (Test-Path -LiteralPath $Stage)) {
        $ResolvedStage = [System.IO.Path]::GetFullPath($Stage)
        $ResolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        if (-not $ResolvedStage.StartsWith($ResolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove a test folder outside the system temp directory: $ResolvedStage"
        }
        Remove-Item -LiteralPath $ResolvedStage -Recurse -Force
    }
}
