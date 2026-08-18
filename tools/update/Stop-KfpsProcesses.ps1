param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Parent,
    [Parameter(Mandatory = $true)][string]$ReportPath
)

$ErrorActionPreference = "Stop"
$modulePath = Join-Path $PSScriptRoot "UpdatePathSafety.psm1"
Import-Module -Name $modulePath -Force

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$parentPath = (Resolve-Path -LiteralPath $Parent).Path
$parentLaunchers = @(
    (Join-Path $parentPath "KFPS.exe"),
    (Join-Path $parentPath "Kloudys Painter Launcher.exe"),
    (Join-Path $parentPath "Kloudys Painter.exe")
)
$names = @(
    "KFPS.exe", "Kloudys Painter Launcher.exe", "Kloudys Painter.exe",
    "KloudysGalateaGenesis.exe", "KloudysGeneratorV7.exe", "KloudysGeneratorV6.exe",
    "KloudysGeneratorV6-Go.exe", "KloudysGeneratorV5.exe",
    "KloudysGeneratorV5DetailLock.exe", "KloudysGeneratorV4.exe",
    "KloudysGeneratorV2.exe", "KloudysGeneratorV2Fast.exe",
    "KloudysGeneratorV2Speed.exe", "ForzaVinylStudio.exe"
)

function Get-KfpsProcesses {
    Get-CimInstance Win32_Process | Where-Object {
        $command = [string]$_.CommandLine
        $path = [string]$_.ExecutablePath
        $isParentLauncher = $parentLaunchers | Where-Object {
            (Test-KfpsPathEqual -Path $path -Expected $_) -or
            (Test-KfpsCommandReferencesPath -CommandLine $command -Expected $_)
        }
        $knownExecutable = ($names -contains $_.Name) -and (
            (Test-KfpsPathInTree -Path $path -Base $rootPath) -or
            (Test-KfpsCommandReferencesTree -CommandLine $command -Base $rootPath) -or
            $isParentLauncher
        )
        $kfpsPython = ($_.Name -match '^pythonw?\.exe$') -and
            (Test-KfpsCommandReferencesTree -CommandLine $command -Base $rootPath) -and
            ($command -match 'app_qt\.py|start_fabric_editor\.py|forza_generator_v2\.py|benchmark_generator_settings\.py|KFPS\.UI')
        $knownExecutable -or $kfpsPython
    }
}

$locks = @(Get-KfpsProcesses)
if ($locks.Count -eq 0) {
    exit 0
}

$locks | ForEach-Object { "PID $($_.ProcessId) - $($_.Name)" } |
    Set-Content -LiteralPath $ReportPath -Encoding ASCII
$locks | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 1500

$remaining = @(Get-KfpsProcesses)
if ($remaining.Count -gt 0) {
    "Still running after termination attempt:" |
        Add-Content -LiteralPath $ReportPath -Encoding ASCII
    $remaining | ForEach-Object { "PID $($_.ProcessId) - $($_.Name)" } |
        Add-Content -LiteralPath $ReportPath -Encoding ASCII
    exit 2
}

exit 0
