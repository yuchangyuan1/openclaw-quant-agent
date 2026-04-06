param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$SkipSampleData,
    [switch]$SkipSmoke,
    [switch]$SyncOpenClaw,
    [switch]$StartServices
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action,
        [Parameter(Mandatory = $true)]
        [string]$StepName
    )

    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw ($StepName + " failed with exit code " + $LASTEXITCODE)
    }
}

$envPath = Join-Path $ProjectRoot ".env"
$envTemplatePath = Join-Path $ProjectRoot ".env.example"
if (-not (Test-Path -LiteralPath $envPath)) {
    if (-not (Test-Path -LiteralPath $envTemplatePath)) {
        throw "Missing .env.example"
    }
    Copy-Item -LiteralPath $envTemplatePath -Destination $envPath
    Write-Host "[setup] Created .env from .env.example"
}

Write-Host "[step] Starting Docker services"
Invoke-Checked -StepName "docker compose up" -Action {
    docker compose -f (Join-Path $ProjectRoot "docker-compose.yml") up -d postgres chroma adminer
}

Write-Host "[step] Initializing database"
Invoke-Checked -StepName "init_db" -Action {
    python (Join-Path $ProjectRoot "scripts\init_db.py")
}

if (-not $SkipSampleData) {
    Write-Host "[step] Fetching sample market data"
    Invoke-Checked -StepName "fetch_sample_data" -Action {
        python (Join-Path $ProjectRoot "scripts\fetch_sample_data.py")
    }
}

Write-Host "[step] Verifying infrastructure"
Invoke-Checked -StepName "verify_stack" -Action {
    python (Join-Path $ProjectRoot "scripts\verify_stack.py")
}

if (-not $SkipSmoke) {
    Write-Host "[step] Running smoke tests"
    Invoke-Checked -StepName "run_phase0_smoke" -Action {
        python (Join-Path $ProjectRoot "scripts\run_phase0_smoke.py")
    }
}

if ($SyncOpenClaw) {
    Write-Host "[step] Syncing OpenClaw runtime"
    Invoke-Checked -StepName "openclaw runtime bootstrap" -Action {
        powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "openclaw\runtime\bootstrap.ps1") -SkipGatewayRestart
    }
}

if ($StartServices) {
    Write-Host "[step] Starting local API services"
    Invoke-Checked -StepName "dev_up" -Action {
        powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\dev_up.ps1")
    }
}

Write-Host "[done] Bootstrap completed."
