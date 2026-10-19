param(
    [string]$BaselineRoot,
    [string]$Dotnet = 'C:/Program Files/dotnet/dotnet.exe',
    [string]$RunRoot,
    [ValidateSet('auto','development','pinned')][string]$PrerequisiteMode = 'auto',
    [switch]$Tests
)
$ErrorActionPreference = 'Stop'
$lab = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'resolve-baseline.ps1')
$baseline = Resolve-StudioBaseline $lab $BaselineRoot
if ($PrerequisiteMode -eq 'auto') {
    $packaged = Join-Path $baseline 'tools/livery-studio'
    $PrerequisiteMode = if ($lab -eq [IO.Path]::GetFullPath($packaged)) { 'pinned' } else { 'development' }
}
if (-not $RunRoot) { $RunRoot = Join-Path $lab 'runs/component-converter' }
$run = [IO.Path]::GetFullPath($RunRoot)
if (-not $run.StartsWith((Join-Path $lab 'runs') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build output must be inside livery/runs.'
}
$ancestor = $run
while ($ancestor) {
    if (Test-Path -LiteralPath $ancestor) {
        $item = Get-Item -LiteralPath $ancestor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Build path contains a reparse point: $ancestor" }
        if (-not $item.PSIsContainer) { throw "Build path ancestor is not a directory: $ancestor" }
    }
    $parent = Split-Path $ancestor -Parent
    if ($parent -eq $ancestor) { break }
    $ancestor = $parent
}
if (Test-Path -LiteralPath $run) {
    $links = @(Get-ChildItem -LiteralPath $run -Recurse -Force -Attributes ReparsePoint -ErrorAction Stop)
    if ($links.Count) { throw "Build tree contains a reparse point: $($links[0].FullName)" }
}
$python = Join-Path $baseline 'python/python.exe'
$provenance = Join-Path $lab 'src/kfps_livery_lab/converter_provenance.py'
if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'The KFPS bundled Python runtime is required to verify converter inputs.' }
$inputArgs = @('-I','-B',$provenance,'inspect','--lab',$lab,'--baseline',$baseline,'--mode',$PrerequisiteMode)
if ($Tests) { $inputArgs += '--tests' }
$inputJson = & $python @inputArgs
if ($LASTEXITCODE -ne 0) { throw 'Converter prerequisite verification failed. No build was started.' }
$inputs = ($inputJson -join "`n") | ConvertFrom-Json
$names = @('DOTNET_CLI_HOME','DOTNET_SKIP_FIRST_TIME_EXPERIENCE','DOTNET_CLI_TELEMETRY_OPTOUT','DOTNET_NOLOGO','NUGET_PACKAGES','NUGET_HTTP_CACHE_PATH','NUGET_PLUGINS_CACHE_PATH','TEMP','TMP')
$old = @{}
foreach ($name in $names) { $old[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
try {
    foreach ($dir in @($run,"$run/dotnet-home","$run/packages","$run/http-cache","$run/plugins-cache","$run/tmp")) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $env:DOTNET_CLI_HOME="$run/dotnet-home"
    $env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1'
    $env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
    $env:DOTNET_NOLOGO='1'
    $env:NUGET_PACKAGES="$run/packages"
    $env:NUGET_HTTP_CACHE_PATH="$run/http-cache"
    $env:NUGET_PLUGINS_CACHE_PATH="$run/plugins-cache"
    $env:TEMP="$run/tmp"
    $env:TMP="$run/tmp"
    $variant = if ($Tests) { 'tests' } else { 'converter' }
    $build = Join-Path $run $variant
    [void](New-Item -ItemType Directory -Path $build -Force)
    $snapshot = Join-Path $build 'source-inputs.json'
    [IO.File]::WriteAllText($snapshot, ($inputs | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    $source = Join-Path $lab 'src/chassis-converter'
    $args = @('publish',"$source/Kfps.LiveryLab.Converter.csproj",'-c','Release','--configfile',"$source/NuGet.Config",'-o',"$run/$variant/publish",
        '-p:IsolatedBuild=true',"-p:BaselineRoot=$baseline","-p:BaseIntermediateOutputPath=$run/$variant/obj/",
        "-p:MSBuildProjectExtensionsPath=$run/$variant/obj/","-p:BaseOutputPath=$run/$variant/bin/",'-p:UseSharedCompilation=false','-p:NuGetAudit=false',
        '-p:ImportDirectoryBuildProps=false','-p:ImportDirectoryBuildTargets=false','-p:ImportDirectoryPackagesProps=false')
    if ($Tests) { $args += '-p:ConverterTests=true' }
    & $Dotnet @args *> "$run/build-$variant.log"
    if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath "$run/build-$variant.log" -Tail 60; throw "Converter build failed ($LASTEXITCODE)." }
    $manifestJson = & $python -I -B $provenance finish --lab $lab --baseline $baseline --build $build --snapshot $snapshot
    if ($LASTEXITCODE -ne 0) { throw 'Converter inputs changed during build or output verification failed. No ready manifest was written.' }
    $manifest = ($manifestJson -join "`n") | ConvertFrom-Json
    [IO.File]::WriteAllText((Join-Path $build 'build-manifest.json'), ($manifest | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    Write-Output "$run/$variant/publish"
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$old[$name],'Process') }
}
