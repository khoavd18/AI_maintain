[CmdletBinding()]
param(
    [ValidateRange(0, 20000000)]
    [int]$WorkOrderCount = 1000000,
    [int]$Seed = 20260823,
    [ValidateSet("baseline", "incremental")]
    [string]$Phase = "baseline",
    [ValidateRange(1000, 200000)]
    [int]$BatchSize = 50000,
    [ValidateRange(0, 20000000)]
    [int]$BaselineCount = 1000000,
    [ValidateRange(0, 20000000)]
    [int]$UpdateCount = 0,
    [string]$RunId = "stage9-1m-seed-20260823",
    [string]$OutputRoot = "data/scale"
)

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "../.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Target virtual environment was not found at $python"
}

$arguments = @(
    "-m", "data_platform.generator",
    "--work-order-count", $WorkOrderCount,
    "--seed", $Seed,
    "--phase", $Phase,
    "--batch-size", $BatchSize,
    "--baseline-count", $BaselineCount,
    "--update-count", $UpdateCount,
    "--run-id", $RunId,
    "--output-root", $OutputRoot
)

$projectedFinalCount = if ($Phase -eq "baseline") {
    $WorkOrderCount + [math]::Max(100000, [math]::Ceiling($WorkOrderCount * 0.1))
} else {
    $BaselineCount + $WorkOrderCount
}
& $python -m data_platform.preflight --work-order-count $projectedFinalCount
if ($LASTEXITCODE -ne 0) {
    throw "Scale preflight failed; no data was generated."
}

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Scale data generation failed with exit code $LASTEXITCODE"
}
