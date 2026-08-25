[CmdletBinding()]
param(
    [ValidateSet("Offline", "LocalReadOnly", "ScaleReadOnly")]
    [string]$Mode = "Offline",
    [switch]$RequireCleanCommit
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:Passed = 0
$script:Failed = 0
$script:Skipped = 0
$script:ReleaseManifest = $null

function Write-CheckResult {
    param(
        [Parameter(Mandatory)][ValidateSet("PASS", "FAIL", "SKIP")]
        [string]$Status,
        [Parameter(Mandatory)][string]$Name,
        [string]$Detail = ""
    )

    if ($Status -eq "PASS") {
        $script:Passed += 1
    } elseif ($Status -eq "FAIL") {
        $script:Failed += 1
    } else {
        $script:Skipped += 1
    }
    $suffix = if ($Detail) { " - $Detail" } else { "" }
    Write-Output ("[{0}] {1}{2}" -f $Status, $Name, $suffix)
}

function Invoke-RequiredCheck {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Check
    )

    try {
        & $Check
        Write-CheckResult -Status PASS -Name $Name
    } catch {
        Write-CheckResult -Status FAIL -Name $Name -Detail $_.Exception.Message
    }
}

function Assert-ReleaseCondition {
    param(
        [Parameter(Mandatory)][bool]$Condition,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Get-PythonCommand {
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    return $null
}

function Invoke-SilentNativeCommand {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Executable @Arguments *> $null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Test-PublicIpv4 {
    param([Parameter(Mandatory)][string]$Value)

    $parts = $Value.Split(".")
    if ($parts.Count -ne 4) {
        return $false
    }
    $octets = @()
    foreach ($part in $parts) {
        $number = 0
        if (-not [int]::TryParse($part, [ref]$number) -or $number -lt 0 -or $number -gt 255) {
            return $false
        }
        $octets += $number
    }
    if ($octets[0] -eq 0 -or $octets[0] -eq 10 -or $octets[0] -eq 127) {
        return $false
    }
    if ($octets[0] -eq 169 -and $octets[1] -eq 254) {
        return $false
    }
    if ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) {
        return $false
    }
    if ($octets[0] -eq 192 -and $octets[1] -eq 168) {
        return $false
    }
    if ($octets[0] -ge 224) {
        return $false
    }
    return $true
}

Push-Location $root
try {
    Write-Output "AI Maintenance Copilot final release verification"
    Write-Output ("Mode={0} RequireCleanCommit={1}" -f $Mode, $RequireCleanCommit.IsPresent)

    $requiredDocs = @(
        "README.md",
        "docs/architecture.md",
        "docs/demo-runbook.md",
        "docs/operations-runbook.md",
        "docs/portfolio/project-summary.md",
        "docs/portfolio/cv-bullets.md",
        "docs/portfolio/interview-guide.md",
        "docs/project-handover.md",
        "docs/final-release-checklist.md",
        "docs/release-manifest.json",
        "scripts/verify_final_release.ps1"
    )
    $releaseMarkdown = @($requiredDocs | Where-Object { $_ -like "*.md" })

    Invoke-RequiredCheck "required release files" {
        $missing = @($requiredDocs | Where-Object { -not (Test-Path -LiteralPath $_) })
        Assert-ReleaseCondition ($missing.Count -eq 0) ("Missing: " + ($missing -join ", "))
    }

    Invoke-RequiredCheck "release manifest JSON and required fields" {
        $script:ReleaseManifest = Get-Content -Raw "docs/release-manifest.json" | ConvertFrom-Json
        Assert-ReleaseCondition ($script:ReleaseManifest.schema_version -eq "stage12-release-manifest-v1") "Unexpected schema_version."
        Assert-ReleaseCondition ($script:ReleaseManifest.stage -eq 12) "Stage must be numeric 12."
        Assert-ReleaseCondition ($script:ReleaseManifest.base_commit -eq "33ac82efbe5f37ed07d412ba2554fd94bde0b6f3") "Base commit mismatch."
        Assert-ReleaseCondition ($script:ReleaseManifest.migration_heads.application -eq "20260726_0008") "Application head mismatch."
        Assert-ReleaseCondition ($script:ReleaseManifest.migration_heads.data_platform -eq "20260824_dp0003") "Data Platform head mismatch."
        Assert-ReleaseCondition ($script:ReleaseManifest.migration_heads.data_platform_version_table -eq "data_platform_alembic_version") "Data Platform version table mismatch."
    }
    $manifest = $script:ReleaseManifest

    Invoke-RequiredCheck "manifest evidence paths" {
        Assert-ReleaseCondition ($null -ne $manifest) "Manifest was not loaded."
        $missing = @()
        foreach ($property in $manifest.evidence_documents.PSObject.Properties) {
            if (-not (Test-Path -LiteralPath $property.Value)) {
                $missing += $property.Value
            }
        }
        Assert-ReleaseCondition ($missing.Count -eq 0) ("Missing evidence: " + ($missing -join ", "))
    }

    Invoke-RequiredCheck "source evidence and manifest metric consistency" {
        Assert-ReleaseCondition ($null -ne $manifest) "Manifest was not loaded."
        $stage9 = Get-Content -Raw "docs/benchmark-results-1m.json" | ConvertFrom-Json
        $stage10 = Get-Content -Raw "docs/benchmark-results-domain-scale.json" | ConvertFrom-Json
        $stage10Manifest = Get-Content -Raw "docs/benchmark-manifest-domain-scale.json" | ConvertFrom-Json
        $stage11 = Get-Content -Raw "docs/benchmark-results-api-stage11.json" | ConvertFrom-Json

        Assert-ReleaseCondition ($manifest.dataset.stage9.unique_work_orders -eq $stage9.counts.source_work_orders) "Stage 9 work-order mismatch."
        Assert-ReleaseCondition ($manifest.dataset.stage9.raw_work_order_versions -eq $stage9.counts.raw_work_order_versions) "Stage 9 raw-version mismatch."
        Assert-ReleaseCondition ($manifest.dataset.stage9.maintenance_logs -eq $stage9.counts.maintenance_logs) "Stage 9 log mismatch."
        Assert-ReleaseCondition ($manifest.performance.stage9_watermark_index.p50_speedup -eq $stage9.optimization.p50_speedup) "Stage 9 p50 speedup mismatch."
        Assert-ReleaseCondition ($manifest.performance.stage9_watermark_index.p95_speedup -eq $stage9.optimization.p95_speedup) "Stage 9 p95 speedup mismatch."

        foreach ($property in $stage10.counts.PSObject.Properties) {
            Assert-ReleaseCondition ($manifest.dataset.stage10.domains.($property.Name) -eq $property.Value) ("Stage 10 domain mismatch: " + $property.Name)
        }
        $generatedRows = $stage10Manifest.baseline.copy_result.rows + $stage10Manifest.incremental.copy_result.rows
        $generatedBytes = $stage10Manifest.baseline.bytes_excluding_manifest + $stage10Manifest.incremental.bytes_excluding_manifest
        $generatedChunks = $stage10Manifest.baseline.file_count + $stage10Manifest.incremental.file_count
        Assert-ReleaseCondition ($manifest.dataset.stage10.generated_and_copied_rows -eq $generatedRows) "Stage 10 generated-row mismatch."
        Assert-ReleaseCondition ($manifest.dataset.stage10.generated_bytes -eq $generatedBytes) "Stage 10 generated-byte mismatch."
        Assert-ReleaseCondition ($manifest.dataset.stage10.generated_chunks -eq $generatedChunks) "Stage 10 chunk mismatch."
        Assert-ReleaseCondition ($manifest.dbt.stage10.models -eq 26) "Stage 10 model count mismatch."
        Assert-ReleaseCondition ($manifest.dbt.stage10.data_tests -eq $stage10.dbt.data_tests) "Stage 10 dbt-test mismatch."
        Assert-ReleaseCondition ($manifest.dbt.stage10.build_nodes_passed -eq $stage10.dbt.passed) "Stage 10 dbt-node mismatch."
        $stage10Total = $stage10.verification.backend_passed + $stage10.verification.postgres_integration_passed + $stage10.verification.frontend_passed + $stage10.verification.dbt_passed
        Assert-ReleaseCondition ($manifest.testing.stage10_historical.total -eq $stage10Total) "Stage 10 validation-total mismatch."

        $final50 = @($stage11.median_comparison | Where-Object { $_.clients -eq 50 })[0]
        Assert-ReleaseCondition ($manifest.performance.stage11_api.clients_50.final_rps -eq $final50.final.requests_per_second) "Stage 11 RPS mismatch."
        Assert-ReleaseCondition ($manifest.performance.stage11_api.clients_50.final_p95_ms -eq $final50.final.p95_ms) "Stage 11 p95 mismatch."
        Assert-ReleaseCondition ($manifest.performance.stage11_api.requests -eq 900) "Stage 11 request count mismatch."
        Assert-ReleaseCondition ($manifest.performance.stage11_api.valid_nonempty_analytics_payloads -eq $stage11.acceptance.final_nonempty_analytics_payloads) "Stage 11 payload mismatch."
        Assert-ReleaseCondition ($manifest.performance.stage11_api.postgres_connections_final_max -eq $stage11.connections.final.clients_50_overall_maximum) "Stage 11 connection mismatch."
    }

    Invoke-RequiredCheck "public metric tokens across canonical documents" {
        $readme = Get-Content -Raw "README.md"
        $portfolio = Get-Content -Raw "docs/portfolio/project-summary.md"
        $handover = Get-Content -Raw "docs/project-handover.md"
        foreach ($token in @("7,728,467", "1,100,000", "459/459", "2,052", "774/774", "33 to 23")) {
            Assert-ReleaseCondition ($readme.Contains($token)) ("README missing metric: " + $token)
            Assert-ReleaseCondition ($portfolio.Contains($token)) ("Portfolio missing metric: " + $token)
            Assert-ReleaseCondition ($handover.Contains($token)) ("Handover missing metric: " + $token)
        }
    }

    Invoke-RequiredCheck "release Markdown internal links" {
        $broken = @()
        foreach ($path in $releaseMarkdown) {
            $file = Get-Item -LiteralPath $path
            $text = Get-Content -Raw $file.FullName
            $matches = [regex]::Matches($text, '(?<!!)\[[^\]]+\]\(([^)]+)\)')
            foreach ($match in $matches) {
                $target = $match.Groups[1].Value.Trim('<', '>')
                if ($target -match '^(https?://|mailto:|#)') {
                    continue
                }
                $target = ($target -split '#')[0]
                if (-not $target) {
                    continue
                }
                $resolved = Join-Path $file.DirectoryName $target
                if (-not (Test-Path -LiteralPath $resolved)) {
                    $broken += ("{0} -> {1}" -f $path, $target)
                }
            }
        }
        Assert-ReleaseCondition ($broken.Count -eq 0) ("Broken links: " + ($broken -join "; "))
    }

    Invoke-RequiredCheck "Markdown and Mermaid fence balance" {
        $unbalanced = @()
        foreach ($path in $releaseMarkdown) {
            $inside = $false
            $mermaidOpen = 0
            $mermaidClose = 0
            foreach ($line in Get-Content -LiteralPath $path) {
                if ($line -match '^```(?<language>[A-Za-z0-9_-]*)\s*$') {
                    if (-not $inside) {
                        $inside = $true
                        if ($Matches.language -eq "mermaid") {
                            $mermaidOpen += 1
                        }
                    } else {
                        $inside = $false
                        $mermaidClose += 1
                    }
                }
            }
            if ($inside -or $mermaidOpen -gt $mermaidClose) {
                $unbalanced += $path
            }
        }
        Assert-ReleaseCondition ($unbalanced.Count -eq 0) ("Unbalanced fences: " + ($unbalanced -join ", "))
    }

    Invoke-RequiredCheck "PowerShell parser validation" {
        $tokens = $null
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $root "scripts\verify_final_release.ps1"),
            [ref]$tokens,
            [ref]$errors
        )
        Assert-ReleaseCondition ($errors.Count -eq 0) (($errors | ForEach-Object Message) -join "; ")
    }

    Invoke-RequiredCheck "tracked generated and runtime artifact exclusions" {
        $tracked = @(git ls-files)
        Assert-ReleaseCondition ($LASTEXITCODE -eq 0) "git ls-files failed."
        $bad = @()
        foreach ($path in $tracked) {
            $normalized = $path.Replace("\", "/")
            if (
                $normalized -match '(^|/)(data/scale|data/analytics_input|data/attachments|\.venv|venv|\.pytest_cache|\.ruff_cache|\.mypy_cache|__pycache__|node_modules|\.next)(/|$)' -or
                $normalized -match '^data_platform/dbt/.*/(target|logs|dbt_packages)/' -or
                $normalized -match '\.(dump|backup|bak|partial|restore\.sql|rehearsal\.log|sqlite|db)$'
            ) {
                $bad += $path
            }
            if ($normalized -match '(^|/)\.env(\.|$)' -and $normalized -notmatch '\.env\.(example|pilot\.example|test\.example)$') {
                $bad += $path
            }
        }
        Assert-ReleaseCondition ($bad.Count -eq 0) ("Tracked generated/runtime paths: " + (($bad | Sort-Object -Unique) -join ", "))
        foreach ($pattern in @("data/scale/", "data_platform/dbt/**/target/", "*.dump", "pilot-evidence/")) {
            Assert-ReleaseCondition ((Get-Content -Raw ".gitignore").Contains($pattern)) (".gitignore missing: " + $pattern)
        }
    }

    Invoke-RequiredCheck "high-confidence secret scan" {
        $extensions = @(
            ".md", ".json", ".py", ".ps1", ".yml", ".yaml", ".toml", ".ini",
            ".txt", ".example", ".tsx", ".ts", ".js", ".mjs", ".sql", ".html", ".css"
        )
        $patterns = @(
            'AKIA[0-9A-Z]{16}',
            'ASIA[0-9A-Z]{16}',
            'sk-[A-Za-z0-9_-]{20,}',
            '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',
            'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}',
            'Authorization:\s*Bearer\s+[A-Za-z0-9._-]{20,}'
        )
        $findings = @()
        $scanFiles = @(@(git ls-files) + $requiredDocs | Sort-Object -Unique)
        foreach ($path in $scanFiles) {
            if ($extensions -notcontains [IO.Path]::GetExtension($path).ToLowerInvariant()) {
                continue
            }
            $text = Get-Content -Raw -LiteralPath $path -ErrorAction SilentlyContinue
            if ($null -eq $text) {
                continue
            }
            foreach ($pattern in $patterns) {
                if ($text -match $pattern) {
                    $findings += $path
                    break
                }
            }
        }
        Assert-ReleaseCondition ($findings.Count -eq 0) ("Potential secrets: " + (($findings | Sort-Object -Unique) -join ", "))
    }

    Invoke-RequiredCheck "release public-IP and credential-URI scan" {
        $textExtensions = @(
            ".md", ".json", ".py", ".ps1", ".yml", ".yaml", ".toml", ".ini",
            ".txt", ".example", ".tsx", ".ts", ".js", ".mjs", ".sql", ".html", ".css"
        )
        $scanPaths = @(@(git ls-files) + $requiredDocs | Sort-Object -Unique)
        $findings = @()
        foreach ($path in $scanPaths) {
            if ($textExtensions -notcontains [IO.Path]::GetExtension($path).ToLowerInvariant()) {
                continue
            }
            $text = Get-Content -Raw -LiteralPath $path
            foreach ($match in [regex]::Matches($text, '(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])')) {
                if (Test-PublicIpv4 -Value $match.Value) {
                    $findings += ("{0}: public IP {1}" -f $path, $match.Value)
                }
            }
            if ($requiredDocs -contains $path -and $text -match '(?i)(postgres(?:ql)?(?:\+[A-Za-z0-9_]+)?://)[^\s/@:]+:[^\s/@]+@') {
                $findings += ("{0}: credential-bearing connection URI" -f $path)
            }
        }
        Assert-ReleaseCondition ($findings.Count -eq 0) ($findings -join "; ")
    }

    Invoke-RequiredCheck "Git checkpoint lineage" {
        $branch = git branch --show-current
        Assert-ReleaseCondition ($LASTEXITCODE -eq 0) "Unable to read branch."
        Assert-ReleaseCondition ($branch -eq "release/stage12-final-portfolio") ("Unexpected branch: " + $branch)
        git merge-base --is-ancestor 33ac82efbe5f37ed07d412ba2554fd94bde0b6f3 HEAD
        Assert-ReleaseCondition ($LASTEXITCODE -eq 0) "Stage 11 base is not an ancestor of HEAD."
        Assert-ReleaseCondition ($manifest.checkpoint_lineage.stage9 -eq "9d556946d33bb7340dc28feee33b2fb5cebc5c02") "Stage 9 lineage mismatch."
        Assert-ReleaseCondition ($manifest.checkpoint_lineage.stage10 -eq "3de9e53d072097665c9ecf718ddd4c22d418b4e6") "Stage 10 lineage mismatch."
        Assert-ReleaseCondition ($manifest.checkpoint_lineage.stage11 -eq "33ac82efbe5f37ed07d412ba2554fd94bde0b6f3") "Stage 11 lineage mismatch."
    }

    Invoke-RequiredCheck "protected-file exclusions and hashes" {
        foreach ($entry in $manifest.protected_file_exclusions) {
            Assert-ReleaseCondition (-not $entry.included_in_stage9_to_stage12_lineage) ("Protected file marked included: " + $entry.path)
            Assert-ReleaseCondition (Test-Path -LiteralPath $entry.path) ("Missing protected file: " + $entry.path)
            $hash = (Get-FileHash -LiteralPath $entry.path -Algorithm SHA256).Hash.ToLowerInvariant()
            Assert-ReleaseCondition ($hash -eq $entry.sha256) ("Protected hash mismatch: " + $entry.path)
        }
    }

    if ($RequireCleanCommit.IsPresent) {
        Invoke-RequiredCheck "clean committed release tree" {
            $status = @(git status --porcelain=v1)
            Assert-ReleaseCondition ($LASTEXITCODE -eq 0) "Unable to inspect Git status."
            Assert-ReleaseCondition ($status.Count -eq 0) "Working tree or index is not clean."
            $head = git rev-parse HEAD
            Assert-ReleaseCondition ($head -ne $manifest.base_commit) "No committed Stage 12 checkpoint exists above the base."
        }
    } else {
        Write-CheckResult -Status SKIP -Name "clean committed release tree" -Detail "Use -RequireCleanCommit after an approved Stage 12 commit."
    }

    $python = Get-PythonCommand
    if ($null -eq $python) {
        Write-CheckResult -Status SKIP -Name "Python compileall" -Detail "Python is not installed."
        Write-CheckResult -Status SKIP -Name "Airflow DagBag import" -Detail "Python/Airflow is not installed."
    } else {
        Invoke-RequiredCheck "Python compileall" {
            & $python -m compileall -q src data_platform tests *> $null
            Assert-ReleaseCondition ($LASTEXITCODE -eq 0) "compileall failed."
        }

        & $python -c "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('airflow') else 3)" *> $null
        if ($LASTEXITCODE -eq 3) {
            Write-CheckResult -Status SKIP -Name "Airflow DagBag import" -Detail "Airflow is not installed in the selected Python environment."
        } elseif ($LASTEXITCODE -ne 0) {
            Write-CheckResult -Status FAIL -Name "Airflow DagBag import" -Detail "Unable to detect Airflow."
        } else {
            Invoke-RequiredCheck "Airflow DagBag import" {
                & $python -c "from airflow.models import DagBag;b=DagBag(dag_folder='data_platform/airflow/dags',include_examples=False);assert not b.import_errors,b.import_errors" *> $null
                Assert-ReleaseCondition ($LASTEXITCODE -eq 0) "DagBag import failed."
            }
        }
    }

    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($null -eq $docker) {
        Write-CheckResult -Status SKIP -Name "Docker Compose config" -Detail "Docker CLI is not installed."
    } else {
        Invoke-RequiredCheck "Docker Compose config" {
            foreach ($compose in @("docker-compose.yml", "docker-compose.test.yml", "docker-compose.scale.yml")) {
                & $docker.Source compose -f $compose config --quiet *> $null
                Assert-ReleaseCondition ($LASTEXITCODE -eq 0) ("Compose validation failed: " + $compose)
            }
        }
    }

    $dbt = Get-Command dbt -ErrorAction SilentlyContinue
    if ($null -eq $dbt) {
        Write-CheckResult -Status SKIP -Name "dbt parse" -Detail "dbt is not installed."
    } else {
        Invoke-RequiredCheck "dbt parse" {
            & $dbt.Source parse `
                --project-dir data_platform/dbt/maintenance_analytics `
                --profiles-dir data_platform/dbt/profiles `
                --target scale --no-partial-parse *> $null
            Assert-ReleaseCondition ($LASTEXITCODE -eq 0) "dbt parse failed."
        }
    }

    if ($Mode -eq "LocalReadOnly") {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/live" -TimeoutSec 5
            Assert-ReleaseCondition ($health.status -eq "alive") "Local API liveness was not alive."
            Write-CheckResult -Status PASS -Name "local API read-only liveness"
        } catch {
            Write-CheckResult -Status SKIP -Name "local API read-only liveness" -Detail "Local API is not reachable; no service was started."
        }
    } elseif ($Mode -eq "ScaleReadOnly") {
        if ($null -eq $docker) {
            Write-CheckResult -Status SKIP -Name "scale Docker state" -Detail "Docker CLI is not installed."
        } else {
            $dockerInfoExit = Invoke-SilentNativeCommand `
                -Executable $docker.Source -Arguments @("info")
            if ($dockerInfoExit -ne 0) {
                Write-CheckResult -Status SKIP -Name "scale Docker state" -Detail "Docker daemon is unavailable; no service was started."
            } else {
                Invoke-RequiredCheck "scale Docker state" {
                    & $docker.Source compose -f docker-compose.scale.yml ps --all *> $null
                    Assert-ReleaseCondition ($LASTEXITCODE -eq 0) "Unable to inspect scale services."
                }
            }
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:18082/health/live" -TimeoutSec 5
            Assert-ReleaseCondition ($health.status -eq "alive") "Scale API liveness was not alive."
            Write-CheckResult -Status PASS -Name "scale API read-only liveness"
        } catch {
            Write-CheckResult -Status SKIP -Name "scale API read-only liveness" -Detail "Scale API is not reachable; no service was started."
        }
    } else {
        Write-CheckResult -Status SKIP -Name "live read-only probes" -Detail "Offline mode does not require running services."
    }
} finally {
    Pop-Location
}

Write-Output ("SUMMARY PASS={0} FAIL={1} SKIP={2}" -f $script:Passed, $script:Failed, $script:Skipped)
if ($script:Failed -gt 0) {
    exit 1
}
exit 0
