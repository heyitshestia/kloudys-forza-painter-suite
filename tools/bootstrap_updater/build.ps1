param(
    [string]$Version = "1.0.2",
    [string]$Output = "",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ToolRoot = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $ToolRoot "..\..")).Path
$PublicKeyPath = Join-Path $ToolRoot "trust\production-ed25519.public"
if (-not $Output) {
    $Output = Join-Path $RepoRoot "KFPS-Updater.exe"
}
if (-not (Test-Path -LiteralPath $PublicKeyPath -PathType Leaf)) {
    throw "Production updater public key is missing: $PublicKeyPath"
}
$PublicKey = (Get-Content -LiteralPath $PublicKeyPath -Raw).Trim()
if ($PublicKey -notmatch '^[A-Za-z0-9+/]{43}=$') {
    throw "Production updater public key is malformed."
}

Push-Location $ToolRoot
try {
    if (-not $SkipTests) {
        & go test ./... -count=1
        if ($LASTEXITCODE -ne 0) {
            throw "Bootstrap updater tests failed."
        }
        & go vet ./...
        if ($LASTEXITCODE -ne 0) {
            throw "Bootstrap updater static checks failed."
        }

        $UpdaterIntegrationTest = Join-Path $RepoRoot "KFPS.UI\tests\test_updater_safety.py"
        $ReleaseIntegrationTest = Join-Path $RepoRoot "KFPS.UI\tests\test_release_builder.py"
        $UpdaterIntegrationPresent = Test-Path -LiteralPath $UpdaterIntegrationTest -PathType Leaf
        $ReleaseIntegrationPresent = Test-Path -LiteralPath $ReleaseIntegrationTest -PathType Leaf
        if ($UpdaterIntegrationPresent -and $ReleaseIntegrationPresent) {
            & py -3 $UpdaterIntegrationTest -q
            if ($LASTEXITCODE -ne 0) {
                throw "KFPS updater integration tests failed."
            }
            & py -3 $ReleaseIntegrationTest -q
            if ($LASTEXITCODE -ne 0) {
                throw "KFPS release integration tests failed."
            }
        }
        elseif ($UpdaterIntegrationPresent -or $ReleaseIntegrationPresent) {
            throw "The KFPS repository integration-test set is incomplete."
        }
        else {
            Write-Host "Full KFPS repository integration tests are not included in this standalone source package; skipping them."
        }
    }

    $PreviousCgo = $env:CGO_ENABLED
    $PreviousOs = $env:GOOS
    $PreviousArch = $env:GOARCH
    try {
        $env:CGO_ENABLED = "0"
        $env:GOOS = "windows"
        $env:GOARCH = "amd64"
        $OutputParent = Split-Path -Parent $Output
        New-Item -ItemType Directory -Force -Path $OutputParent | Out-Null
        $TemporaryOutput = "$Output.new"
        Remove-Item -LiteralPath $TemporaryOutput -Force -ErrorAction SilentlyContinue
        $Ldflags = "-s -w -buildid= -X main.version=$Version -X main.trustedPublicKey=$PublicKey"
        & go build -trimpath -buildvcs=false -ldflags $Ldflags -o $TemporaryOutput ./cmd/kfps-updater
        if ($LASTEXITCODE -ne 0) {
            throw "KFPS-Updater.exe build failed."
        }
        Move-Item -LiteralPath $TemporaryOutput -Destination $Output -Force

        $BuildDir = Join-Path $ToolRoot "build"
        New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
        $Publisher = Join-Path $BuildDir "KFPS-Update-Publisher.exe"
        $TemporaryPublisher = "$Publisher.new"
        Remove-Item -LiteralPath $TemporaryPublisher -Force -ErrorAction SilentlyContinue
        & go build -trimpath -buildvcs=false -ldflags "-s -w -buildid=" -o $TemporaryPublisher ./cmd/kfps-update-tool
        if ($LASTEXITCODE -ne 0) {
            throw "KFPS update publisher build failed."
        }
        Move-Item -LiteralPath $TemporaryPublisher -Destination $Publisher -Force
    }
    finally {
        $env:CGO_ENABLED = $PreviousCgo
        $env:GOOS = $PreviousOs
        $env:GOARCH = $PreviousArch
    }

    $VersionOutput = & $Output --version
    if ($LASTEXITCODE -ne 0 -or $VersionOutput -notcontains "KFPS Bootstrap Updater $Version") {
        throw "Built updater did not report the expected version."
    }
    $Updater = Get-Item -LiteralPath $Output
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Output).Hash
    $DistDir = Join-Path $ToolRoot "dist"
    New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
    $PackageStage = Join-Path $BuildDir "standalone-$Version"
    if (Test-Path -LiteralPath $PackageStage) {
        [IO.Directory]::Delete($PackageStage, $true)
    }
    New-Item -ItemType Directory -Path $PackageStage | Out-Null
    Copy-Item -LiteralPath $Output -Destination (Join-Path $PackageStage "KFPS-Updater.exe")
    Copy-Item -LiteralPath (Join-Path $ToolRoot "STANDALONE-README.txt") -Destination (Join-Path $PackageStage "README.txt")
    [IO.File]::WriteAllText(
        (Join-Path $PackageStage "SHA256SUMS.txt"),
        "$($Hash.ToLowerInvariant())  KFPS-Updater.exe`n",
        [Text.UTF8Encoding]::new($false)
    )
    $Package = Join-Path $DistDir "KFPS-Bootstrap-Updater-$Version-Windows-x64.zip"
    Compress-Archive -LiteralPath (Join-Path $PackageStage "KFPS-Updater.exe"), (Join-Path $PackageStage "README.txt"), (Join-Path $PackageStage "SHA256SUMS.txt") -DestinationPath $Package -CompressionLevel Optimal -Force
    [IO.Directory]::Delete($PackageStage, $true)
    $PackageHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Package).Hash
    Write-Host "Built $($Updater.FullName)"
    Write-Host "Size: $($Updater.Length) bytes"
    Write-Host "SHA-256: $Hash"
    Write-Host "Publisher: $Publisher"
    Write-Host "Standalone package: $Package"
    Write-Host "Package SHA-256: $PackageHash"
}
finally {
    Pop-Location
}
