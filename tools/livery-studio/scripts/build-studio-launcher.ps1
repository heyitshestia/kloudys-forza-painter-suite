param(
    [switch]$WorkspaceLayout
)

$ErrorActionPreference = 'Stop'
$Lab = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$BuildRoot = Join-Path $Lab 'build/20261019-standalone'
$OutputDirectory = if ($WorkspaceLayout) { Join-Path $BuildRoot 'workspace-test' } else { $BuildRoot }
$Evidence = Join-Path $Lab 'runs/20261019-viewer-project-storage/launcher'
$Flavor = if ($WorkspaceLayout) { 'workspace-test' } else { 'installed' }
$Source = Join-Path $Lab 'src/launcher/KFPSLiverySudio.cs'
$Output = Join-Path $OutputDirectory 'KFPSLiverySudio.exe'
$Manifest = Join-Path $OutputDirectory 'build-manifest.json'
$Compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $Compiler -PathType Leaf)) {
    throw 'The .NET Framework C# compiler was not found. No runtime or dependency will be downloaded.'
}
if (Test-Path -LiteralPath $Output) {
    if (-not (Test-Path -LiteralPath $Manifest)) { throw 'Existing launcher has no build receipt; it was not overwritten.' }
    $Previous = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
    if ($Previous.sha256 -ne (Get-FileHash -LiteralPath $Output -Algorithm SHA256).Hash) {
        throw 'Existing launcher differs from its build receipt; it was not overwritten.'
    }
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
$Staging = Join-Path $OutputDirectory ('.studio-build-' + [Guid]::NewGuid().ToString('N') + '.exe')
$CompilerArguments = @('/nologo', '/target:winexe', '/platform:x86', '/optimize+',
    '/reference:System.dll', '/reference:System.Core.dll', '/reference:System.Windows.Forms.dll',
    '/reference:System.Web.Extensions.dll', "/out:$Staging", $Source)
if ($WorkspaceLayout) { $CompilerArguments += '/define:KFPS_STUDIO_WORKSPACE' }
$Icon = Join-Path $Lab '../repo/assets/kfps-logo.ico'
if (Test-Path -LiteralPath $Icon -PathType Leaf) { $CompilerArguments += "/win32icon:$Icon" }
try {
    & $Compiler @CompilerArguments 2>&1 | Tee-Object -FilePath (Join-Path $Evidence ("build-$Flavor.log"))
    if ($LASTEXITCODE -ne 0) { throw "Launcher compilation failed: $LASTEXITCODE" }
    $Boundary = [System.IO.Path]::GetFullPath($BuildRoot).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    foreach ($Path in @($Staging, $Output)) {
        if (-not [System.IO.Path]::GetFullPath($Path).StartsWith($Boundary, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Launcher output escaped its dedicated build directory.'
        }
    }
    Move-Item -LiteralPath $Staging -Destination $Output -Force
    $Receipt = [ordered]@{
        format = 'kfps-studio-launcher-build-v1'
        file = $Output
        bytes = (Get-Item -LiteralPath $Output).Length
        sha256 = (Get-FileHash -LiteralPath $Output -Algorithm SHA256).Hash
        source_sha256 = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
        entrypoint_sha256 = (Get-FileHash -LiteralPath (Join-Path $Lab 'src/launch_studio.py') -Algorithm SHA256).Hash
        workspace_lookup_enabled = [bool]$WorkspaceLayout
        installed = $false
    }
    $Receipt | ConvertTo-Json | Set-Content -LiteralPath $Manifest -Encoding UTF8
    $Receipt | ConvertTo-Json
} finally {
    if (Test-Path -LiteralPath $Staging -PathType Leaf) { Remove-Item -LiteralPath $Staging }
}
