param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$syncScript = Join-Path $projectRoot "scripts\setup_openclaw_runtime.ps1"

if (-not (Test-Path -LiteralPath $syncScript)) {
    throw "Runtime sync script not found: $syncScript"
}

& powershell -ExecutionPolicy Bypass -File $syncScript @Args
