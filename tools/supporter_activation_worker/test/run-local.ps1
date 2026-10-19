param(
    [Parameter(Mandatory = $true)][string]$RunDirectory,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9-]+$')][string]$Phase,
    [string[]]$TestFiles = @(),
    [switch]$Typecheck
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$run = [System.IO.Path]::GetFullPath($RunDirectory)
$directories = @($run, "$run/temp", "$run/config", "$run/cache", "$run/wrangler-logs")
foreach ($directory in $directories) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
$settings = @{
    KFPS_WORKER_TEST_RUN = $run
    TEMP = "$run/temp"
    TMP = "$run/temp"
    XDG_CONFIG_HOME = "$run/config"
    XDG_CACHE_HOME = "$run/cache"
    WRANGLER_LOG_PATH = "$run/wrangler-logs"
    WRANGLER_SEND_METRICS = 'false'
    CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV = 'false'
    npm_config_cache = "$run/cache/npm"
    NO_COLOR = '1'
}
$previous = @{}
foreach ($name in $settings.Keys) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
}
Push-Location $root
try {
    if ($Typecheck) {
        & node ./node_modules/typescript/bin/tsc --noEmit 2>&1 | Tee-Object -FilePath "$run/$Phase.log"
    } else {
        $arguments = @('./node_modules/vitest/vitest.mjs', 'run', '--config', 'test/vitest.local.ts', '--configLoader', 'runner', '--reporter=verbose')
        & node @arguments @TestFiles 2>&1 | Tee-Object -FilePath "$run/$Phase.log"
    }
    $result = $LASTEXITCODE
    Write-Output "Exit code: $result" | Tee-Object -FilePath "$run/$Phase.log" -Append
} finally {
    Pop-Location
    foreach ($name in $settings.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
exit $result
