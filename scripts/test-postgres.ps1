[CmdletBinding()]
param(
    [ValidateSet("test", "up", "down", "reset")]
    [string]$Action = "test",
    [switch]$Keep,
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$composeFile = Join-Path $root "docker-compose.test.yml"
$composeArgs = @("compose", "-f", $composeFile)
$testUrl = "postgresql+psycopg://maintenance_test:maintenance_test_password@localhost:15433/maintenance_copilot_test"
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

if ($testUrl -notmatch '^postgresql\+psycopg://[^@]+@localhost:15433/[A-Za-z0-9_-]+_test$') {
    throw "The test Compose target must remain a local postgresql+psycopg database ending in _test."
}

function Invoke-Compose {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE."
    }
}

function Invoke-CheckedProcess {
    param([Parameter(Mandatory)][string]$Executable, [Parameter(Mandatory)][string[]]$Arguments)
    # Start-Process keeps native stdout/stderr visible and gives the caller a
    # scalar exit code without PowerShell's stream-assignment semantics.
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -NoNewWindow -Wait -PassThru
    return $process.ExitCode
}

function Start-TestPostgres {
    Invoke-Compose -Arguments @("up", "-d", "postgres-test")
    $deadline = (Get-Date).AddSeconds(90)
    do {
        & docker @composeArgs exec -T postgres-test pg_isready -U maintenance_test -d maintenance_copilot_test *> $null
        if ($LASTEXITCODE -eq 0) {
            $database = (& docker @composeArgs exec -T postgres-test psql -U maintenance_test -d maintenance_copilot_test -Atqc "SELECT current_database()" 2>$null).Trim()
            if ($database -and $database.EndsWith("_test")) {
                return
            }
        }
        if ((Get-Date) -ge $deadline) {
            throw "Timed out waiting for the isolated PostgreSQL test database."
        }
        Start-Sleep -Seconds 2
    } while ($true)
}

if ($Action -in @("up", "test")) {
    $env:APP_ENVIRONMENT = "test"
    $env:STORAGE_BACKEND = "postgresql"
    $env:TEST_DATABASE_URL = $testUrl
    $env:DATABASE_URL = $testUrl
}

$exitCode = 0
$startedByScript = $false
try {
    if ($Action -eq "reset") {
        # This is the only destructive action and the Compose file is fixed to
        # maintenance_copilot_test on the dedicated test port.
        Invoke-Compose -Arguments @("down", "-v", "--remove-orphans")
    } elseif ($Action -eq "down") {
        Invoke-Compose -Arguments @("stop", "postgres-test")
    } else {
        Start-TestPostgres
        $startedByScript = $true
    }

    if ($Action -eq "test") {
        $exitCode = Invoke-CheckedProcess -Executable $python -Arguments @("-m", "alembic", "upgrade", "head")
        if ($exitCode -eq 0) {
            $pytestArgs = if ($Full) { @("-q") } else { @("-m", "postgres", "-q") }
            $exitCode = Invoke-CheckedProcess -Executable $python -Arguments (@("-m", "pytest") + $pytestArgs)
        }
        if ($exitCode -eq 0) {
            $exitCode = Invoke-CheckedProcess -Executable $python -Arguments @("-m", "alembic", "heads")
        }
        if ($exitCode -eq 0) {
            $exitCode = Invoke-CheckedProcess -Executable $python -Arguments @("-m", "alembic", "current")
        }
        if ($exitCode -eq 0) {
            $exitCode = Invoke-CheckedProcess -Executable $python -Arguments @("-m", "alembic", "check")
        }
    }
} catch {
    Write-Error $_
    if ($exitCode -eq 0) {
        $exitCode = 1
    }
} finally {
    if ($startedByScript -and -not $Keep) {
        try {
            Invoke-Compose -Arguments @("stop", "postgres-test")
        } catch {
            Write-Error $_
            if ($exitCode -eq 0) {
                $exitCode = 1
            }
        }
    }
}

if ($Action -eq "up") {
    Write-Output "Isolated PostgreSQL is running at $testUrl"
}
exit $exitCode
