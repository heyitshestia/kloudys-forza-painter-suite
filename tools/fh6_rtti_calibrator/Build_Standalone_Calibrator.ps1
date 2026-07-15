$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root "build"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    python -m venv $Venv
}

& $Python -m pip install --disable-pip-version-check --upgrade pip
& $Python -m pip install --disable-pip-version-check -r (Join-Path $Root "requirements-build.txt")
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name "KFPS_FH6_Locator_Calibrator" `
    --distpath $Dist `
    --workpath $Build `
    (Join-Path $Root "kfps_fh6_six_step_locator_calibrator.py")

$Exe = Join-Path $Dist "KFPS_FH6_Locator_Calibrator.exe"
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    throw "PyInstaller did not produce the expected executable."
}

Get-FileHash -LiteralPath $Exe -Algorithm SHA256
