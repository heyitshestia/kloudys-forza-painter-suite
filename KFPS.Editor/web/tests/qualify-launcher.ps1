param([Parameter(Mandatory=$true)][string]$Launcher, [Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$outputRoot = [IO.Path]::GetFullPath($Output)
$runRoot = [IO.Path]::GetFullPath((Join-Path $root 'runtime\test-runs')) + '\'
if (-not $outputRoot.StartsWith($runRoot, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $outputRoot)) {
    throw 'Launcher qualification needs a new isolated test-run directory'
}
[IO.Directory]::CreateDirectory($outputRoot) | Out-Null
$assembly = [Reflection.Assembly]::LoadFile([IO.Path]::GetFullPath($Launcher))
$type = $assembly.GetType('KfpsLauncher', $true)
$flags = [Reflection.BindingFlags]'Static,NonPublic'
function Invoke-Private([string]$Name, [object[]]$Values) {
    $type.GetMethod($Name, $flags).Invoke($null, [object[]]@([string]$Values[0]))
}
function New-Layout([string]$Name, [string]$Entry) {
    $path = Join-Path $outputRoot $Name
    $target = Join-Path $path $Entry
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
    [IO.File]::WriteAllText($target, '')
    [IO.File]::WriteAllText((Join-Path $path 'VERSION'), 'test')
    return $path
}
$direct = New-Layout 'Direct with spaces' 'KFPS.Editor\editor.py'
$wrapped = New-Layout 'Wrapped\KloudysFH6Painter' 'KFPS.Editor\editor.py'
$legacy = New-Layout 'Legacy' 'KFPS.UI\editor.py'
$partial = New-Layout 'Partial' 'KFPS.UI\editor.py'
[IO.Directory]::CreateDirectory((Join-Path $partial 'KFPS.Editor')) | Out-Null
foreach ($pair in @(@($direct,$direct), @((Split-Path $wrapped),$wrapped))) {
    if ((Invoke-Private 'ResolveAppRoot' @($pair[0])) -ne $pair[1]) { throw 'Root discovery mismatch' }
}
if (Invoke-Private 'LooksLikeAppRoot' @($partial)) { throw 'Partial new package fell back to old entry' }
if (Invoke-Private 'LooksLikeAppRoot' @($legacy)) { throw 'New launcher accepted an unconverted old package' }
if ((Invoke-Private 'ResolveEntryPoint' @($direct)) -ne (Join-Path $direct 'KFPS.Editor\editor.py')) { throw 'Wrong canonical entry' }
if (Invoke-Private 'ResolvePython' @($direct)) { throw 'Installed editor fell back to an external runtime' }
$arguments = Invoke-Private 'BundledArguments' @($direct)
if ($arguments -notmatch '^-I -B -X ' -or $arguments -notmatch 'pycache_prefix=') { throw 'Installed editor isolation is missing' }
$probe = $type.GetField('PythonProbe', $flags).GetRawConstantValue()
if ($probe -match 'cv2' -or $probe -notmatch 'QtWebEngineWidgets' -or $probe -notmatch 'win32file') { throw 'Wrong standalone runtime probe' }
$result = @{direct=$true; wrapped=$true; legacyRejected=$true; partialRejected=$true; editorOnlyProbe=$true; noExternalRuntimeFallback=$true; isolatedArguments=$true}
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputRoot 'result.json') -Encoding UTF8
$result | ConvertTo-Json -Compress
