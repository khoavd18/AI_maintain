param(
    [ValidateSet("baseline", "incremental")]
    [string]$Phase = "baseline",
    [string]$RunId = "stage10-domain-seed-20260824",
    [ValidateRange(1000, 200000)]
    [int]$BatchSize = 50000,
    [string]$DatabaseName = "maintenance_copilot_benchmark_scale"
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Repository virtual environment is missing: $Python"
}
if (-not $DatabaseName.EndsWith("_scale")) {
    throw "Stage 10 refuses a database name that does not end with _scale."
}

if (-not $env:DATA_PLATFORM_DB_HOST) {
    $env:DATA_PLATFORM_DB_HOST = "127.0.0.1"
}
if (-not $env:DATA_PLATFORM_DB_PORT) {
    $env:DATA_PLATFORM_DB_PORT = "25432"
}
$env:DATA_PLATFORM_DB_NAME = $DatabaseName
if (-not $env:DATA_PLATFORM_DB_USER) {
    $env:DATA_PLATFORM_DB_USER = "maintenance_scale"
}
if (-not $env:DATA_PLATFORM_DB_PASSWORD) {
    $env:DATA_PLATFORM_DB_PASSWORD = "maintenance_scale_local_only"
}

Push-Location -LiteralPath $RepositoryRoot
try {
    & $Python -m data_platform.domain_loader migrate
    & $Python -m data_platform.domain_generator `
        --phase $Phase `
        --run-id $RunId `
        --output-root data/scale `
        --batch-size $BatchSize
    $Manifest = Join-Path $RepositoryRoot "data\scale\$RunId\$Phase\manifest.json"
    & $Python -m data_platform.domain_loader load --manifest $Manifest
}
finally {
    Pop-Location
}
