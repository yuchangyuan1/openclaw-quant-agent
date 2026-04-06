param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

function Get-PortValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EnvPath,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [int]$Default
    )

    if (-not (Test-Path -LiteralPath $EnvPath)) {
        return $Default
    }

    $match = Select-String -Path $EnvPath -Pattern ("^" + [regex]::Escape($Name) + "=(.+)$") | Select-Object -First 1
    if (-not $match) {
        return $Default
    }

    $value = $match.Matches[0].Groups[1].Value.Trim()
    $parsed = 0
    if ([int]::TryParse($value, [ref]$parsed)) {
        return $parsed
    }
    return $Default
}

function Test-PortListening {
    param([int]$Port)
    try {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1
        return $null -ne $listener
    } catch {
        return $false
    }
}

function Start-ServiceProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Module,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$HostAddress,
        [Parameter(Mandatory = $true)]
        [string]$LogsDir,
        [Parameter(Mandatory = $true)]
        [string]$PidDir
    )

    $pidPath = Join-Path $PidDir ($Name + ".pid")
    if (Test-Path -LiteralPath $pidPath) {
        $pidValue = (Get-Content -LiteralPath $pidPath -Raw).Trim()
        if ($pidValue) {
            $existing = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
            if ($existing -and -not $existing.HasExited) {
                Write-Host ("[skip] " + $Name + " already running (pid " + $pidValue + ")")
                return
            }
        }
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    }

    if (Test-PortListening -Port $Port) {
        Write-Host ("[skip] " + $Name + " port " + $Port + " already in use")
        return
    }

    $outLog = Join-Path $LogsDir ($Name + ".out.log")
    $errLog = Join-Path $LogsDir ($Name + ".err.log")

    $process = Start-Process `
        -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", $Module, "--host", $HostAddress, "--port", $Port) `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru

    Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding utf8
    Start-Sleep -Seconds 2

    if (Test-PortListening -Port $Port) {
        Write-Host ("[ok] " + $Name + " listening on " + $HostAddress + ":" + $Port)
        return
    }

    Write-Warning ("[warn] " + $Name + " did not bind to port " + $Port + ". Check " + $errLog)
}

$envPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing .env file. Copy .env.example to .env first."
}

$logsDir = Join-Path $ProjectRoot "runtime-logs"
$pidDir = Join-Path $logsDir "pids"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
New-Item -ItemType Directory -Path $pidDir -Force | Out-Null

$services = @(
    @{ Name = "ingestion"; Module = "services.ingestion.main:app"; Port = (Get-PortValue -EnvPath $envPath -Name "INGESTION_PORT" -Default 8001) },
    @{ Name = "rag"; Module = "services.rag.main:app"; Port = (Get-PortValue -EnvPath $envPath -Name "RAG_PORT" -Default 8002) },
    @{ Name = "quant"; Module = "services.quant.main:app"; Port = (Get-PortValue -EnvPath $envPath -Name "QUANT_PORT" -Default 8003) },
    @{ Name = "risk"; Module = "services.risk.main:app"; Port = (Get-PortValue -EnvPath $envPath -Name "RISK_PORT" -Default 8004) },
    @{ Name = "planner"; Module = "services.planner.main:app"; Port = (Get-PortValue -EnvPath $envPath -Name "PLANNER_PORT" -Default 8005) },
    @{ Name = "report"; Module = "services.report.main:app"; Port = (Get-PortValue -EnvPath $envPath -Name "REPORT_PORT" -Default 8006) },
    @{ Name = "critic"; Module = "services.critic.main:app"; Port = (Get-PortValue -EnvPath $envPath -Name "CRITIC_PORT" -Default 8007) }
)

foreach ($service in $services) {
    Start-ServiceProcess `
        -Name $service.Name `
        -Module $service.Module `
        -Port $service.Port `
        -ProjectRoot $ProjectRoot `
        -HostAddress $HostAddress `
        -LogsDir $logsDir `
        -PidDir $pidDir
}

Write-Host "[done] Local API services started."
