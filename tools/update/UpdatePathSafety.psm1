Set-StrictMode -Version Latest

function Get-KfpsNormalizedPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return [IO.Path]::GetFullPath($Path).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
}

function Test-KfpsPathInTree {
    param(
        [string]$Path,
        [string]$Base
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or [string]::IsNullOrWhiteSpace($Base)) {
        return $false
    }
    try {
        $full = Get-KfpsNormalizedPath -Path $Path
        $baseFull = Get-KfpsNormalizedPath -Path $Base
        return $full.Equals($baseFull, [StringComparison]::OrdinalIgnoreCase) -or
            $full.StartsWith(
                $baseFull + [IO.Path]::DirectorySeparatorChar,
                [StringComparison]::OrdinalIgnoreCase
            )
    } catch {
        return $false
    }
}

function Test-KfpsPathEqual {
    param(
        [string]$Path,
        [string]$Expected
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or [string]::IsNullOrWhiteSpace($Expected)) {
        return $false
    }
    try {
        return (Get-KfpsNormalizedPath -Path $Path).Equals(
            (Get-KfpsNormalizedPath -Path $Expected),
            [StringComparison]::OrdinalIgnoreCase
        )
    } catch {
        return $false
    }
}

function Test-KfpsCommandReferencesTree {
    param(
        [string]$CommandLine,
        [string]$Base
    )

    if ([string]::IsNullOrWhiteSpace($CommandLine) -or [string]::IsNullOrWhiteSpace($Base)) {
        return $false
    }
    try {
        $baseFull = Get-KfpsNormalizedPath -Path $Base
        $pattern = '(?i)(?:^|[\s"])' + [Regex]::Escape($baseFull) + '(?:[\\/]|["\s]|$)'
        return [Regex]::IsMatch($CommandLine, $pattern)
    } catch {
        return $false
    }
}

function Test-KfpsCommandReferencesPath {
    param(
        [string]$CommandLine,
        [string]$Expected
    )

    if ([string]::IsNullOrWhiteSpace($CommandLine) -or [string]::IsNullOrWhiteSpace($Expected)) {
        return $false
    }
    try {
        $expectedFull = Get-KfpsNormalizedPath -Path $Expected
        $pattern = '(?i)(?:^|[\s"])' + [Regex]::Escape($expectedFull) + '(?:["\s]|$)'
        return [Regex]::IsMatch($CommandLine, $pattern)
    } catch {
        return $false
    }
}

Export-ModuleMember -Function @(
    'Test-KfpsPathInTree',
    'Test-KfpsPathEqual',
    'Test-KfpsCommandReferencesTree',
    'Test-KfpsCommandReferencesPath'
)
