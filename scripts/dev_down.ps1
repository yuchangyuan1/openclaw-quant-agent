param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$pidDir = Join-Path $ProjectRoot "runtime-logs\pids"
if (-not (Test-Path -LiteralPath $pidDir)) {
    Write-Host "[done] No pid directory found."
    return
}

$pidFiles = Get-ChildItem -LiteralPath $pidDir -Filter "*.pid" -File
if (-not $pidFiles) {
    Write-Host "[done] No managed service processes found."
    return
}

foreach ($pidFile in $pidFiles) {
    $serviceName = [IO.Path]::GetFileNameWithoutExtension($pidFile.Name)
    $pidValue = (Get-Content -LiteralPath $pidFile.FullName -Raw).Trim()
    if (-not $pidValue) {
        Remove-Item -LiteralPath $pidFile.FullName -Force -ErrorAction SilentlyContinue
        continue
    }

    $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $process.Id -Force
        Write-Host ("[ok] stopped " + $serviceName + " (pid " + $process.Id + ")")
    } else {
        Write-Host ("[skip] " + $serviceName + " not running")
    }

    Remove-Item -LiteralPath $pidFile.FullName -Force -ErrorAction SilentlyContinue
}

Write-Host "[done] Managed local API services stopped."
