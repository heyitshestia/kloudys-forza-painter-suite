param(
    [string]$Launcher = "",
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $Launcher) {
    $Launcher = Join-Path $Root "KFPS.exe"
}
$Launcher = (Resolve-Path -LiteralPath $Launcher).Path
$Python312 = (& py -3.12 -c "import sys; print(sys.executable)").Trim()
if (-not (Test-Path -LiteralPath $Python312 -PathType Leaf)) {
    throw "Python 3.12 could not be resolved through the Windows Python Launcher."
}

$Stage = Join-Path ([System.IO.Path]::GetTempPath()) ("KFPS Launcher Tests " + [Guid]::NewGuid().ToString("N"))
$Junctions = [System.Collections.Generic.List[string]]::new()

function New-ProbeLayout {
    param([string]$Name)

    $Outer = Join-Path $Stage $Name
    $AppRoot = Join-Path $Outer "KloudysFH6Painter"
    $UiRoot = Join-Path $AppRoot "KFPS.UI"
    New-Item -ItemType Directory -Path $UiRoot -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $Outer "Images") -Force | Out-Null
    Copy-Item -LiteralPath $Launcher -Destination (Join-Path $Outer "KFPS.exe")
    Set-Content -LiteralPath (Join-Path $AppRoot "VERSION") -Value "test" -Encoding Ascii
    @'
from __future__ import annotations
import json
import os
import struct
import sys
from pathlib import Path

target = Path(sys.argv[1])
target.write_text(json.dumps({
    "version": f"{sys.version_info.major}.{sys.version_info.minor}",
    "bits": struct.calcsize("P") * 8,
    "executable": sys.executable,
    "app_root": os.environ.get("KFPS_APP_ROOT", ""),
    "source": os.environ.get("KFPS_PYTHON_SOURCE", ""),
    "forwarded": sys.argv[2:],
}, indent=2), encoding="utf-8")
'@ | Set-Content -LiteralPath (Join-Path $UiRoot "app.py") -Encoding Utf8
    return [pscustomobject]@{
        Outer = $Outer
        AppRoot = $AppRoot
        Launcher = Join-Path $Outer "KFPS.exe"
    }
}

function Invoke-Probe {
    param(
        [object]$Layout,
        [string]$Name,
        [string[]]$Forwarded = @()
    )

    $Marker = Join-Path $Layout.Outer ($Name + " result.json")
    $ProcessArguments = @('"' + $Marker + '"')
    foreach ($Value in $Forwarded) {
        if ($Value -match '\s') {
            $ProcessArguments += ('"' + $Value + '"')
        } else {
            $ProcessArguments += $Value
        }
    }
    $Process = Start-Process -FilePath $Layout.Launcher -ArgumentList $ProcessArguments -PassThru -Wait -WindowStyle Hidden
    if ($Process.ExitCode -ne 0) {
        throw "$Name launcher exit code was $($Process.ExitCode)."
    }
    if (-not (Test-Path -LiteralPath $Marker -PathType Leaf)) {
        throw "$Name did not create its probe result."
    }
    return Get-Content -Raw -LiteralPath $Marker | ConvertFrom-Json
}

function Assert-ProbeBase {
    param([object]$Result, [object]$Layout, [string]$Name)

    if ($Result.version -ne "3.12") { throw "$Name used Python $($Result.version), expected 3.12." }
    if ([int]$Result.bits -ne 64) { throw "$Name used $($Result.bits)-bit Python, expected 64-bit." }
    if (-not [string]::Equals(
        [System.IO.Path]::GetFullPath($Result.app_root).TrimEnd('\'),
        [System.IO.Path]::GetFullPath($Layout.AppRoot).TrimEnd('\'),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "$Name received the wrong KFPS_APP_ROOT: $($Result.app_root)"
    }
}

$PreviousPython = $env:KFPS_PYTHON
try {
    New-Item -ItemType Directory -Path $Stage -Force | Out-Null

    Remove-Item Env:KFPS_PYTHON -ErrorAction SilentlyContinue
    $External = New-ProbeLayout "External Python"
    $ExternalResult = Invoke-Probe $External "external" @("value with spaces", "trailing\")
    Assert-ProbeBase $ExternalResult $External "External discovery"
    if ($ExternalResult.source -notin @("py -3.12", "system Python 3.12")) {
        throw "External discovery reported an unexpected source: $($ExternalResult.source)"
    }
    if (($ExternalResult.forwarded | ConvertTo-Json -Compress) -ne '["value with spaces","trailing\\"]') {
        throw "Launcher argument forwarding changed: $($ExternalResult.forwarded | ConvertTo-Json -Compress)"
    }

    $env:KFPS_PYTHON = Split-Path -Parent $Python312
    $Configured = New-ProbeLayout "Configured Python"
    $ConfiguredResult = Invoke-Probe $Configured "configured"
    Assert-ProbeBase $ConfiguredResult $Configured "KFPS_PYTHON"
    if ($ConfiguredResult.source -ne "KFPS_PYTHON") {
        throw "KFPS_PYTHON was not preferred: $($ConfiguredResult.source)"
    }

    $Python311 = (& py -3.11 -c "import sys; print(sys.executable)" 2>$null).Trim()
    if ($Python311) {
        $env:KFPS_PYTHON = $Python311
        $WrongVersion = New-ProbeLayout "Wrong Override"
        $WrongVersionResult = Invoke-Probe $WrongVersion "wrong override"
        Assert-ProbeBase $WrongVersionResult $WrongVersion "Wrong-version fallback"
        if ($WrongVersionResult.source -eq "KFPS_PYTHON") {
            throw "The launcher accepted an incompatible Python 3.11 override."
        }
    }

    $EmptyVenv = Join-Path $Stage "Python 3.12 without KFPS dependencies"
    & $Python312 -m venv $EmptyVenv
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the isolated Python 3.12 dependency test environment."
    }
    $env:KFPS_PYTHON = Join-Path $EmptyVenv "Scripts\python.exe"
    $MissingDependencies = New-ProbeLayout "Missing Dependencies"
    $MissingDependenciesResult = Invoke-Probe $MissingDependencies "missing dependencies"
    Assert-ProbeBase $MissingDependenciesResult $MissingDependencies "Missing-dependency fallback"
    if ($MissingDependenciesResult.source -eq "KFPS_PYTHON") {
        throw "The launcher accepted Python 3.12 without the required KFPS packages."
    }

    $env:KFPS_PYTHON = if ($Python311) { $Python311 } else { Join-Path $Stage "not-python.exe" }
    $Bundled = New-ProbeLayout "Bundled Python"
    $PythonDir = Split-Path -Parent $Python312
    $PythonJunction = Join-Path $Bundled.AppRoot "python"
    New-Item -ItemType Junction -Path $PythonJunction -Target $PythonDir | Out-Null
    $Junctions.Add($PythonJunction)
    $BundledResult = Invoke-Probe $Bundled "bundled"
    Assert-ProbeBase $BundledResult $Bundled "Bundled precedence"
    if ($BundledResult.source -ne "bundled") {
        throw "The packaged runtime was not preferred: $($BundledResult.source)"
    }

    Write-Host "PASS: packaged runtime precedence"
    Write-Host "PASS: KFPS_PYTHON directory override"
    Write-Host "PASS: Python 3.11 override rejection and Python 3.12 fallback"
    Write-Host "PASS: Python 3.12 without KFPS dependencies was rejected"
    Write-Host "PASS: 64-bit validation, app-root propagation, and argument quoting"
}
finally {
    if ($null -eq $PreviousPython) {
        Remove-Item Env:KFPS_PYTHON -ErrorAction SilentlyContinue
    } else {
        $env:KFPS_PYTHON = $PreviousPython
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
