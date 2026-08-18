param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Target,
    [Parameter(Mandatory = $true)][string]$AppRoot,
    [Parameter(Mandatory = $true)][string]$ParentRoot,
    [string]$LogFile = ""
)

$ErrorActionPreference = "Stop"
$modulePath = Join-Path $PSScriptRoot "UpdatePathSafety.psm1"
Import-Module -Name $modulePath -Force

function Write-UpdateLog([string]$Message) {
    if ($LogFile) {
        Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format 'dd.MM.yyyy HH:mm:ss,ff')] $Message" -Encoding ASCII
    }
}

$names = @("KFPS.exe", "Kloudys Painter Launcher.exe", "Kloudys Painter.exe")
$locks = @(Get-CimInstance Win32_Process | Where-Object {
    ($names -contains $_.Name) -and (
        (Test-KfpsPathInTree -Path $_.ExecutablePath -Base $AppRoot) -or
        (Test-KfpsPathEqual -Path $_.ExecutablePath -Expected $Target)
    )
})
if ($locks.Count -gt 0) {
    Write-UpdateLog "Stopped native launcher process(es) before replacing KFPS.exe."
    $locks | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 1200
}

$lastError = ""
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        Copy-Item -LiteralPath $Source -Destination $Target -Force
        exit 0
    } catch {
        $lastError = $_.Exception.Message
        Start-Sleep -Milliseconds 500
    }
}

Write-UpdateLog "Native launcher replacement failed after retries: $lastError"
exit 2
