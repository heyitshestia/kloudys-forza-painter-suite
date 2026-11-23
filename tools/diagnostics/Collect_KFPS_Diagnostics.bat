@echo off
setlocal DisableDelayedExpansion
set "KFPS_DIAG_SELF=%~f0"
echo KFPS startup and update diagnostics
echo Read-only collection. No update, repair, upload, or administrator access.
echo Logs may contain personal paths. Send the resulting ZIP privately.
echo.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { $s=[IO.File]::ReadAllText($env:KFPS_DIAG_SELF); $m='#'+' KFPS_DIAGNOSTICS_POWERSHELL'; & ([scriptblock]::Create($s.Substring($s.IndexOf($m)+$m.Length))) } catch { Write-Host ('FAILED: '+$_.Exception.Message); exit 1 }"
set "KFPS_DIAG_RESULT=%ERRORLEVEL%"
echo.
if /i not "%~1"=="--no-pause" pause
exit /b %KFPS_DIAG_RESULT%
# KFPS_DIAGNOSTICS_POWERSHELL
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion -lt [version]'5.1') { throw 'Windows PowerShell 5.1 or later is required.' }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$base = [IO.Path]::GetDirectoryName($env:KFPS_DIAG_SELF)
if (-not [IO.File]::Exists((Join-Path $base 'KFPS.exe'))) { throw 'Place this BAT beside KFPS.exe, then run it again.' }
$app = $base
$install = $base
if ([IO.Directory]::Exists((Join-Path $base 'KloudysFH6Painter'))) {
    $app = Join-Path $base 'KloudysFH6Painter'
} elseif ([IO.Path]::GetFileName($base) -ieq 'KloudysFH6Painter') {
    $install = [IO.Path]::GetDirectoryName($base)
}
$issues = New-Object 'System.Collections.Generic.List[string]'
$files = New-Object 'System.Collections.Generic.List[object]'
$expected = New-Object 'System.Collections.Generic.List[object]'
$utf8 = New-Object Text.UTF8Encoding($false)
$limits = @{remaining=16MB}

function Safe-Path([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    $cursor = $item
    while ($null -ne $cursor) {
        if ($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked path skipped.' }
        if ($cursor -is [IO.FileInfo]) { $cursor = $cursor.Directory } else { $cursor = $cursor.Parent }
    }
    return $item
}
function Hash-Bytes([byte[]]$Bytes) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hash.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose() }
}
function Redact([string]$Text) {
    $Text = [regex]::Replace($Text, '(?i)(authorization\s*[:=]\s*(?:Bearer|Basic)\s+)[^\s"'']+', '$1[REDACTED]')
    $Text = [regex]::Replace($Text, '(?i)([?&](?:access_token|refresh_token|token|key)=)[^&\s"'']+', '$1[REDACTED]')
    $Text = [regex]::Replace($Text, '(?i)("(?:access_token|refresh_token|password|secret|api_key)"\s*:\s*")[^"]*(")', '$1[REDACTED]$2')
    return [regex]::Replace($Text, '\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b', '[REDACTED]')
}
function Zip-Text([string]$Name, [string]$Text) {
    $bytes = $utf8.GetBytes($Text)
    $entry = $zip.CreateEntry($Name, [IO.Compression.CompressionLevel]::Optimal)
    $stream = $entry.Open()
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
    $expected.Add([pscustomobject]@{name=$Name; bytes=$bytes.Length; sha256=(Hash-Bytes $bytes)})
}
function Collect-File([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    if ($limits.remaining -le 0 -or $files.Count -ge 48) { $issues.Add('Collection size limit reached.'); return }
    try {
        $item = Safe-Path $Path
        if ($item -isnot [IO.FileInfo]) { throw 'Not a regular file.' }
        $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
        try {
            $length = $stream.Length
            $head = New-Object byte[] 4
            $headCount = $stream.Read($head, 0, 4)
            $encoding = $utf8
            $alignment = 1
            if ($headCount -ge 4 -and $head[0] -eq 255 -and $head[1] -eq 254 -and $head[2] -eq 0 -and $head[3] -eq 0) { $encoding = [Text.Encoding]::UTF32; $alignment = 4 }
            elseif ($headCount -ge 2 -and $head[0] -eq 255 -and $head[1] -eq 254) { $encoding = [Text.Encoding]::Unicode; $alignment = 2 }
            elseif ($headCount -ge 2 -and $head[0] -eq 254 -and $head[1] -eq 255) { $encoding = [Text.Encoding]::BigEndianUnicode; $alignment = 2 }
            $count = [int][Math]::Min([Math]::Min($length, 2MB), $limits.remaining)
            $offset = $length - $count
            $offset = [long]([Math]::Ceiling($offset / [double]$alignment) * $alignment)
            $count = [int]($length - $offset)
            [void]$stream.Seek($offset, [IO.SeekOrigin]::Begin)
            $buffer = New-Object byte[] $count
            $read = 0
            while ($read -lt $count) {
                $n = $stream.Read($buffer, $read, $count - $read)
                if ($n -eq 0) { break }
                $read += $n
            }
        } finally { $stream.Dispose() }
        $limits.remaining -= $read
        $text = $encoding.GetString($buffer, 0, $read).TrimStart([char]0xfeff)
        if ($offset -gt 0) {
            $Name += '.tail.txt'
            $text = "[Only the last $read bytes of $length bytes were collected.]`r`n" + $text
        }
        Zip-Text $Name (Redact $text)
        $files.Add([pscustomobject]@{source=$Path; entry=$Name; source_bytes=$length; collected_bytes=$read; truncated=($offset -gt 0)})
    } catch { $issues.Add($Path + ': ' + $_.Exception.Message) }
}
function Collect-Recent([string]$Folder, [string]$Pattern, [int]$Count, [string]$Prefix) {
    if (-not (Test-Path -LiteralPath $Folder)) { return }
    try {
        [void](Safe-Path $Folder)
        $items = @(Get-ChildItem -LiteralPath $Folder -File -Force | Where-Object { $_.Name -match $Pattern } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First $Count)
        foreach ($item in $items) { Collect-File $item.FullName ($Prefix + '/' + $item.Name) }
    } catch { $issues.Add($Folder + ': ' + $_.Exception.Message) }
}
function Collect-Updater($State) {
    Collect-Recent (Join-Path $State.path 'logs') '^update-[\w-]+\.log$' 2 ('updater/' + $State.id + '/logs')
    Collect-Recent (Join-Path $State.path 'reports') '^update-[\w-]+\.json$' 2 ('updater/' + $State.id + '/reports')
}

$name = 'KFPS-Diagnostics-' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.zip'
$output = Join-Path $base $name
try { $destination = [IO.File]::Open($output, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
catch {
    $fallback = Join-Path ([IO.Path]::GetTempPath()) 'KFPS-Diagnostics'
    [void][IO.Directory]::CreateDirectory($fallback)
    [void](Safe-Path $fallback)
    $output = Join-Path $fallback $name
    $destination = [IO.File]::Open($output, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $issues.Add('Installation folder was not writable; ZIP placed in the temporary diagnostics folder.')
}
$zip = New-Object IO.Compression.ZipArchive($destination, [IO.Compression.ZipArchiveMode]::Create, $true)
try {
    Write-Host 'Collecting recent updater and startup logs...'
    Collect-File (Join-Path $app 'VERSION') 'application/VERSION.txt'
    $states = $null
    if ($env:LOCALAPPDATA) { $states = Join-Path $env:LOCALAPPDATA 'KloudysFH6Painter\updater\installations' }
    else { $issues.Add('LOCALAPPDATA is unavailable; updater logs could not be located.') }
    $identities = @($install, $app | Select-Object -Unique | ForEach-Object { Hash-Bytes ($utf8.GetBytes(([IO.Path]::GetFullPath($_).Replace('\','/').TrimEnd('/')).ToLowerInvariant())) })
    $stateDirs = @()
    if ($states -and (Test-Path -LiteralPath $states)) {
        try {
            [void](Safe-Path $states)
            $stateDirs = @(Get-ChildItem -LiteralPath $states -Directory | Where-Object { $_.Name -match '^[0-9a-f]{64}$' -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } | ForEach-Object {
                $latest = $null
                $logs = Join-Path $_.FullName 'logs'
                if (Test-Path -LiteralPath $logs) {
                    try {
                        [void](Safe-Path $logs)
                        $latest = Get-ChildItem -LiteralPath $logs -File | Where-Object Name -Match '^update-[\w-]+\.log$' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
                    } catch { $issues.Add($logs + ': ' + $_.Exception.Message) }
                }
                [pscustomobject]@{path=$_.FullName; id=$_.Name; match=($identities -contains $_.Name); time=$(if ($latest) { $latest.LastWriteTimeUtc } else { $_.LastWriteTimeUtc })}
            } | Sort-Object @{Expression='match';Descending=$true}, @{Expression='time';Descending=$true} | Select-Object -First 3)
        } catch { $issues.Add('Updater discovery: ' + $_.Exception.Message) }
    }
    foreach ($state in $stateDirs | Where-Object match) { Collect-Updater $state }
    Collect-Recent (Join-Path $app 'runtime\update-reports') '^update-[\w-]+\.json$' 2 'application/update-reports'
    Collect-Recent (Join-Path $app 'runtime\update-logs') '^update-[\w-]+\.log$' 2 'application/update-logs'
    Collect-Recent (Join-Path $app 'runtime\app-logs') '^app-\d+\.log(?:\.[12])?$' 4 'application/app-logs'
    Collect-Recent (Join-Path $app 'runtime\fabric-editor') '^(?:desktop|server)\.log(?:\.[12])?$|^desktop-startup-error\.json$' 5 'application/editor'
    Collect-Recent (Join-Path $app 'tools\livery-studio\runs\studio-launch') '^backend\.(?:stdout|stderr)\.log$' 2 'application/studio'
    foreach ($state in $stateDirs | Where-Object { -not $_.match }) { Collect-Updater $state }

    $inventory = @()
    foreach ($root in @($install, $app | Select-Object -Unique)) {
        foreach ($relative in @('KFPS.exe','KFPS-Updater.exe','KFPS Editor.exe','KFPSLiverySudio.exe','python\python.exe','python\pythonw.exe','KFPS.UI\app.py','KFPS.Editor\editor.py')) {
            $path = Join-Path $root $relative
            $row = [ordered]@{path=$path; present=(Test-Path -LiteralPath $path -PathType Leaf)}
            if ($row.present) {
                try {
                    $item = Safe-Path $path
                    $row.bytes = $item.Length
                    $row.modified_utc = $item.LastWriteTimeUtc.ToString('o')
                    if ($item.Extension -ieq '.exe' -and $item.Length -le 32MB) {
                        $row.sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
                        $row.file_version = $item.VersionInfo.FileVersion
                    }
                } catch { $row.error = $_.Exception.Message }
            }
            $inventory += [pscustomobject]$row
        }
    }
    $system = [ordered]@{os_version=[Environment]::OSVersion.VersionString; is_64bit_os=[Environment]::Is64BitOperatingSystem; powershell=$PSVersionTable.PSVersion.ToString()}
    try {
        $windows = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
        $system.windows_build = $windows.CurrentBuildNumber
        $system.windows_revision = $windows.UBR
        $system.windows_display_version = $windows.DisplayVersion
    } catch { $issues.Add('Windows build details unavailable: ' + $_.Exception.Message) }
    Zip-Text 'diagnostics.json' (([ordered]@{format='kfps-startup-collector-v1'; created_utc=[DateTime]::UtcNow.ToString('o'); launched_from=$base; install_root=$install; application_root=$app; expected_updater_identities=$identities; updater_locations=$stateDirs; system=$system; inventory=$inventory; collected=$files.ToArray(); issues=$issues.ToArray()}) | ConvertTo-Json -Depth 8)
    Zip-Text 'READ-ME.txt' @"
KFPS startup/update diagnostics. Send this ZIP privately to KFPS support.
No update, repair, application launch, internet request or upload was performed.
Only allowlisted diagnostic files were read; artwork, game saves, settings,
credentials, updater caches and rollback backups were not collected.
Common token/password patterns were redacted, but logs can still contain
personal paths and filenames. This ZIP is not an anonymous public report.

Also attach a FULL screenshot of the repair error, including its filename/path.
If using a shortcut, send its Properties -> Target. The collector cannot infer
which shortcut you used. If antivirus reported a KFPS detection, attach that
specific detection screenshot; do not disable protection.

diagnostics.json lists paths, versions, collected files and any missing access.
Recent updater logs from up to three KFPS installation identities are included
to identify repairs applied to a different copy. Matching identities come first.
Logs are capped at 2 MiB each / 16 MiB total; truncated files end in .tail.txt.
Missing logs are normal if startup failed before logging began.
"@
} finally { $zip.Dispose(); $destination.Dispose() }

$check = [IO.Compression.ZipFile]::OpenRead($output)
try {
    if ($check.Entries.Count -ne $expected.Count) { throw 'ZIP verification: entry count differs.' }
    foreach ($record in $expected) {
        $entry = $check.GetEntry($record.name)
        if ($null -eq $entry -or $entry.Length -ne $record.bytes) { throw 'ZIP verification: entry missing or incomplete.' }
        $stream = $entry.Open()
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $actual = ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
        finally { $stream.Dispose(); $sha.Dispose() }
        if ($actual -ne $record.sha256) { throw 'ZIP verification: content differs.' }
    }
} finally { $check.Dispose() }
Write-Host ''
Write-Host ('SUCCESS: ' + $files.Count + ' diagnostic files collected; ZIP reopened and verified.')
Write-Host ('ZIP: ' + $output)
Write-Host 'Send this ZIP privately, plus a screenshot of the full error.'
if ($issues.Count) { Write-Host 'Some files were unavailable or limited; details are inside diagnostics.json.' }
