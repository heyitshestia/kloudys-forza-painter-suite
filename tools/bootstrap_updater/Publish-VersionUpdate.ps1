[CmdletBinding()]
param(
    [string]$Repository = "heyitshestia/kloudys-forza-painter-suite",
    [string]$Commit = "",
    [Parameter(Mandatory = $true)]
    [string]$PrivateKeyPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [switch]$Publish
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)] [scriptblock]$Action,
        [Parameter(Mandatory = $true)] [string]$Failure
    )
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Failure (exit code $LASTEXITCODE)"
    }
}

function Get-JsonFile {
    param([Parameter(Mandatory = $true)] [string]$Path)
    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory = $true)] [string]$Url,
        [Parameter(Mandatory = $true)] [string]$Destination,
        [Parameter(Mandatory = $true)] [long]$Size,
        [Parameter(Mandatory = $true)] [string]$Sha256
    )
    if ($Url -notmatch '^https://') { throw "Refusing non-HTTPS update artifact: $Url" }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    for ($attempt = 1; $attempt -le 4; $attempt++) {
        Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
        & curl.exe --fail --location --silent --show-error --retry 2 --retry-all-errors --connect-timeout 30 --output $Destination $Url
        if ($LASTEXITCODE -eq 0) { break }
        if ($attempt -eq 4) { throw "Download failed after four attempts: $Url" }
        Start-Sleep -Seconds (10 * $attempt)
    }
    $file = Get-Item -LiteralPath $Destination
    if ($file.Length -ne $Size) { throw "Downloaded size mismatch for $Url" }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash.ToLowerInvariant()
    if ($actual -ne $Sha256.ToLowerInvariant()) { throw "Downloaded SHA-256 mismatch for $Url" }
}

function Assert-SameFile {
    param([string]$Expected, [string]$Actual)
    $expectedFile = Get-Item -LiteralPath $Expected
    $actualFile = Get-Item -LiteralPath $Actual
    if ($expectedFile.Length -ne $actualFile.Length) { throw "Uploaded size mismatch for $($expectedFile.Name)" }
    $expectedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Expected).Hash
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Actual).Hash
    if ($expectedHash -ne $actualHash) { throw "Uploaded SHA-256 mismatch for $($expectedFile.Name)" }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$publicKey = Join-Path $repoRoot "tools\bootstrap_updater\trust\production-ed25519.public"
$updater = Join-Path $repoRoot "KFPS-Updater.exe"
$channelPath = Join-Path $repoRoot "updates\stable\channel.json"
$channelSignaturePath = "$channelPath.sig"

foreach ($required in @($PrivateKeyPath, $publicKey, $updater, $channelPath, $channelSignaturePath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required publication input is missing: $required" }
}

Push-Location $repoRoot
try {
    $head = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not resolve repository HEAD." }
    if ([string]::IsNullOrWhiteSpace($Commit)) { $Commit = $head }
    if ($Commit -notmatch '^[0-9a-fA-F]{40}$' -or $Commit -ne $head) {
        throw "Publication commit must be the exact current HEAD."
    }
    & git diff --quiet
    if ($LASTEXITCODE -ne 0) { throw "Tracked working-tree changes are not allowed during publication." }
    & git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) { throw "Staged working-tree changes are not allowed during publication." }

    $version = (Get-Content -LiteralPath (Join-Path $repoRoot "VERSION") -Raw).Trim()
    if ($version -notmatch '^\d+\.\d+(?:\.\d+){0,2}$') { throw "VERSION is invalid: $version" }

    $buildRoot = Join-Path $OutputRoot "build"
    $payloadRoot = Join-Path $OutputRoot "payload"
    $downloadRoot = Join-Path $OutputRoot "downloads"
    $verifyRoot = Join-Path $OutputRoot "uploaded"
    if (Test-Path -LiteralPath $OutputRoot) { throw "Publication output must not already exist: $OutputRoot" }
    New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null

    $publisher = Join-Path $buildRoot "KFPS-Update-Publisher.exe"
    Push-Location (Join-Path $repoRoot "tools\bootstrap_updater")
    try {
        Invoke-Checked { go test ./... } "Updater publisher tests failed"
        Invoke-Checked { go vet ./... } "Updater publisher static checks failed"
        Invoke-Checked { go build -trimpath -buildvcs=false -o $publisher ./cmd/kfps-update-tool } "Updater publisher build failed"
    } finally {
        Pop-Location
    }

    Invoke-Checked { & $publisher verify --public $publicKey --input $channelPath --signature $channelSignaturePath } "Committed channel signature is invalid"
    $channel = Get-JsonFile $channelPath
    if ($channel.schema -ne 'kfps.update-channel.v1' -or $channel.channel -ne 'stable' -or [uint64]$channel.sequence -lt 1) {
        throw "Committed stable channel contract is invalid."
    }

    $previousManifestPath = Join-Path $downloadRoot "previous-manifest.json"
    $previousSignaturePath = "$previousManifestPath.sig"
    Get-VerifiedDownload -Url ([string]$channel.manifest.url) -Destination $previousManifestPath -Size ([long]$channel.manifest.size) -Sha256 ([string]$channel.manifest.sha256)
    New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
    & curl.exe --fail --location --silent --show-error --retry 3 --retry-all-errors --connect-timeout 30 --output $previousSignaturePath ([string]$channel.manifest.signature_url)
    if ($LASTEXITCODE -ne 0) { throw "Previous manifest signature download failed." }
    Invoke-Checked { & $publisher verify --public $publicKey --input $previousManifestPath --signature $previousSignaturePath } "Previous manifest signature is invalid"

    $previous = Get-JsonFile $previousManifestPath
    if ($previous.schema -ne 'kfps.update-manifest.v1' -or $previous.channel -ne 'stable' -or [uint64]$previous.sequence -ne [uint64]$channel.sequence) {
        throw "Previous manifest does not match the committed channel."
    }
    if ([string]$previous.version -eq $version) {
        Write-Host "KFPS $version is already the signed stable update. Nothing to publish."
        exit 0
    }
    if ([version]$version -le [version]([string]$previous.version)) {
        throw "VERSION $version does not advance published version $($previous.version)."
    }
    if ([string]$previous.commit -notmatch '^[0-9a-fA-F]{40}$') { throw "Previous manifest commit is invalid." }
    Invoke-Checked { git cat-file -e "$($previous.commit)^{commit}" } "Previous manifest commit is unavailable"
    & git diff --quiet $previous.commit $Commit -- requirements.lock.txt
    if ($LASTEXITCODE -ne 0) {
        throw "requirements.lock.txt changed; publish a freshly built Python runtime instead of reusing the stable runtime."
    }

    $pythonComponents = @($previous.components | Where-Object { $_.name -eq 'python-runtime' -and $_.target -eq 'app-root' })
    if ($pythonComponents.Count -ne 1) { throw "Previous manifest does not contain one reusable Python runtime." }
    $pythonArchive = Join-Path $downloadRoot "python-runtime.zip"
    Get-VerifiedDownload -Url ([string]$pythonComponents[0].archive.url) -Destination $pythonArchive -Size ([long]$pythonComponents[0].archive.size) -Sha256 ([string]$pythonComponents[0].archive.sha256)
    $runtimeExtract = Join-Path $downloadRoot "python-runtime"
    Expand-Archive -LiteralPath $pythonArchive -DestinationPath $runtimeExtract -Force
    $pythonRoot = Join-Path $runtimeExtract "python"
    if (-not (Test-Path -LiteralPath (Join-Path $pythonRoot "python.exe") -PathType Leaf)) {
        throw "The verified stable Python archive did not contain python/python.exe."
    }

    $sequence = [uint64]$channel.sequence + 1
    $tag = "kfps-update-data-v$version-s$sequence"
    $baseUrl = "https://github.com/$Repository/releases/download/$tag"
    Invoke-Checked {
        & $publisher build --app-root $repoRoot --python-root $pythonRoot --updater $updater --private $PrivateKeyPath --public $publicKey --output $payloadRoot --base-url $baseUrl --version $version --commit $Commit --bootstrap-version ([string]$channel.updater.version) --sequence $sequence
    } "Signed update payload build failed"

    $manifestPath = Join-Path $payloadRoot "kfps-update-$version.json"
    Invoke-Checked { & $publisher verify --public $publicKey --input $manifestPath --signature "$manifestPath.sig" } "Generated manifest signature is invalid"
    Invoke-Checked { & $publisher verify --public $publicKey --input (Join-Path $payloadRoot "channel.json") --signature (Join-Path $payloadRoot "channel.json.sig") } "Generated channel signature is invalid"
    if (-not $Publish) {
        Write-Host "Built and verified KFPS $version sequence $sequence at $payloadRoot"
        exit 0
    }

    Invoke-Checked { gh auth status } "GitHub authentication is unavailable"
    & gh release view $tag --repo $Repository *> $null
    if ($LASTEXITCODE -eq 0) { throw "Immutable publication tag already exists: $tag" }

    $releaseCreated = $false
    $channelPushed = $false
    try {
        Invoke-Checked {
            gh release create $tag --repo $Repository --target $Commit --title "KFPS $version Update Data" --notes "Internal signed updater payload for KFPS $version. Use the public KFPS release for manual downloads." --draft --prerelease
        } "Draft update-data release creation failed"
        $releaseCreated = $true

        $assetNames = @(
            "kfps-$version-application.zip",
            "kfps-$version-python-runtime.zip",
            "kfps-$version-native-launchers.zip",
            "KFPS-Updater-$($channel.updater.version).exe",
            "kfps-update-$version.json",
            "kfps-update-$version.json.sig",
            "SHA256SUMS.txt"
        )
        $assetPaths = @($assetNames | ForEach-Object { Join-Path $payloadRoot $_ })
        foreach ($asset in $assetPaths) {
            if (-not (Test-Path -LiteralPath $asset -PathType Leaf)) { throw "Publisher omitted required asset: $asset" }
        }
        Invoke-Checked { gh release upload $tag @assetPaths --repo $Repository } "Update-data asset upload failed"

        New-Item -ItemType Directory -Path $verifyRoot -Force | Out-Null
        Invoke-Checked { gh release download $tag --repo $Repository --dir $verifyRoot } "Uploaded asset verification download failed"
        foreach ($name in $assetNames) {
            Assert-SameFile -Expected (Join-Path $payloadRoot $name) -Actual (Join-Path $verifyRoot $name)
        }

        Invoke-Checked { git fetch origin main } "Could not refresh origin/main before publication"
        $remoteHead = (& git rev-parse origin/main).Trim()
        if ($remoteHead -ne $Commit) { throw "main advanced during publication; refusing to publish a stale channel." }

        Invoke-Checked { gh release edit $tag --repo $Repository --draft=false --prerelease } "Update-data prerelease publication failed"
        Copy-Item -LiteralPath (Join-Path $payloadRoot "channel.json") -Destination $channelPath -Force
        Copy-Item -LiteralPath (Join-Path $payloadRoot "channel.json.sig") -Destination $channelSignaturePath -Force
        Invoke-Checked { & $publisher verify --public $publicKey --input $channelPath --signature $channelSignaturePath } "Promoted channel signature is invalid"
        Invoke-Checked { git add -- updates/stable/channel.json updates/stable/channel.json.sig } "Could not stage the stable channel"
        $staged = @(git diff --cached --name-only)
        if ($staged.Count -ne 2 -or $staged -notcontains 'updates/stable/channel.json' -or $staged -notcontains 'updates/stable/channel.json.sig') {
            throw "Channel publication staged an unexpected file set: $($staged -join ', ')"
        }
        Invoke-Checked { git commit -m "Publish KFPS $version updater channel" } "Channel commit failed"
        Invoke-Checked { git push origin HEAD:main } "Channel push failed"
        $channelPushed = $true
        Write-Host "Published KFPS $version as signed stable sequence $sequence."
    } finally {
        if ($releaseCreated -and -not $channelPushed) {
            gh release delete $tag --repo $Repository --yes --cleanup-tag 2>$null
        }
    }
} finally {
    Pop-Location
}
