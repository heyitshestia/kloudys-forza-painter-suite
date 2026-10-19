# Shared by Studio launch/build scripts. Dot-sourcing does not start an application.
function Resolve-StudioBaseline([string]$LabRoot, [string]$ExplicitRoot) {
    $lab = [IO.Path]::GetFullPath($LabRoot)
    if ($ExplicitRoot) { $root = [IO.Path]::GetFullPath($ExplicitRoot) }
    elseif ((Split-Path $lab -Leaf) -eq 'livery-studio' -and (Split-Path (Split-Path $lab -Parent) -Leaf) -eq 'tools') {
        $root = Split-Path (Split-Path $lab -Parent) -Parent
    } elseif ((Split-Path $lab -Leaf) -eq 'livery') {
        $root = Join-Path (Split-Path $lab -Parent) 'repo'
    } else { throw 'Supply an explicit KFPS root for this custom Studio folder layout.' }
    foreach ($start in @($root, $lab)) {
        for ($cursor=$start; $cursor; $cursor=[IO.Path]::GetDirectoryName($cursor)) {
            if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'Studio installation discovery cannot follow redirected paths.'
            }
        }
    }
    foreach ($relative in @('KFPS.Editor/manifest.json','json_preview_renderer.py')) {
        if (!(Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf)) { throw 'The Studio KFPS installation is incomplete.' }
    }
    return (Resolve-Path -LiteralPath $root).Path
}
