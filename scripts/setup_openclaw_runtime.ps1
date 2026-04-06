param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OpenClawHome = (Join-Path $env:USERPROFILE ".openclaw"),
    [string]$WorkspaceNamespace = "quant-research",
    [string]$Model,
    [string]$FeishuAccountId,
    [switch]$SkipBackup,
    [switch]$SkipGatewayRestart,
    [switch]$SkipCron
)

$ErrorActionPreference = "Stop"

function Invoke-OpenClaw {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )

    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $script:OpenClawNode
    $processInfo.UseShellExecute = $false
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.CreateNoWindow = $true

    $allArgs = @($script:OpenClawBaseArgs + $Args)
    $processInfo.Arguments = ($allArgs | ForEach-Object { Format-ProcessArgument $_ }) -join " "

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $processInfo
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    $combined = @()
    if ($stdout) {
        $combined += $stdout.Trim()
    }
    if ($stderr) {
        $combined += $stderr.Trim()
    }

    if ($process.ExitCode -ne 0) {
        throw "openclaw $($Args -join ' ') failed.`n$($combined -join [Environment]::NewLine)"
    }

    return ($combined -join [Environment]::NewLine)
}

function Format-ProcessArgument {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Ensure-ObjectProperty {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    if ($Object.PSObject.Properties.Name -contains $Name) {
        $Object.$Name = $Value
    } else {
        Add-Member -InputObject $Object -MemberType NoteProperty -Name $Name -Value $Value
    }
}

function New-WorkspaceBootstrap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkspacePath
    )

    $bootstrap = @"
# Bootstrap

Project code is available under `./project`.
Use `./project` as the working tree for repository tasks.
Keep workspace-local metadata in this directory only when needed.
OpenClaw-native workspace materials are available under `./project/openclaw`.
Reusable skills are documented under `./project/openclaw/skills`.
"@

    Set-Content -LiteralPath (Join-Path $WorkspacePath "BOOTSTRAP.md") -Value $bootstrap -Encoding utf8
}

function Copy-WorkspaceScaffold {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceWorkspacePath,
        [Parameter(Mandatory = $true)]
        [string]$TargetWorkspacePath
    )

    if (-not (Test-Path -LiteralPath $SourceWorkspacePath)) {
        throw "Missing workspace scaffold: $SourceWorkspacePath"
    }

    $sourceItems = Get-ChildItem -LiteralPath $SourceWorkspacePath -Force
    foreach ($item in $sourceItems) {
        if ($item.PSIsContainer) {
            Copy-Item -LiteralPath $item.FullName -Destination $TargetWorkspacePath -Recurse -Force
            continue
        }
        $destination = Join-Path $TargetWorkspacePath $item.Name
        Copy-Item -LiteralPath $item.FullName -Destination $destination -Force
    }
}

function Resolve-FeishuAccountId {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Config,
        [Parameter(Mandatory = $true)]
        [string]$OpenClawHome
    )

    if ($FeishuAccountId) {
        return $FeishuAccountId
    }

    if ($Config.PSObject.Properties.Name -contains "bindings") {
        foreach ($binding in @($Config.bindings)) {
            if ($binding.match.channel -eq "feishu" -and $binding.match.accountId) {
                return [string]$binding.match.accountId
            }
        }
    }

    if (
        $Config.PSObject.Properties.Name -contains "channels" -and
        $Config.channels.PSObject.Properties.Name -contains "feishu" -and
        $Config.channels.feishu.PSObject.Properties.Name -contains "defaultAccount" -and
        $Config.channels.feishu.defaultAccount
    ) {
        return [string]$Config.channels.feishu.defaultAccount
    }

    $credentialsDir = Join-Path $OpenClawHome "credentials"
    if (Test-Path -LiteralPath $credentialsDir) {
        $candidate = Get-ChildItem -LiteralPath $credentialsDir -Filter "feishu-*-allowFrom.json" |
            Select-Object -First 1
        if ($candidate -and $candidate.BaseName -match "^feishu-(.+)-allowFrom$") {
            return $Matches[1]
        }
    }

    return "default"
}

function Backup-OpenClawState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OpenClawHome
    )

    $backupRoot = Join-Path $OpenClawHome "backups"
    $backupDir = Join-Path $backupRoot ("before-runtime-sync-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

    foreach ($relativePath in @("openclaw.json", "cron\jobs.json")) {
        $source = Join-Path $OpenClawHome $relativePath
        if (-not (Test-Path -LiteralPath $source)) {
            continue
        }

        $targetDir = Join-Path $backupDir (Split-Path $relativePath -Parent)
        if ($targetDir -and -not (Test-Path -LiteralPath $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $source -Destination (Join-Path $backupDir $relativePath) -Force
    }

    return $backupDir
}

function Ensure-AgentWorkspaces {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$AgentSpecs,
        [Parameter(Mandatory = $true)]
        [string]$WorkspaceRoot,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    foreach ($agent in $AgentSpecs) {
        $workspacePath = Join-Path $WorkspaceRoot $agent.id
        $sourceWorkspace = Join-Path $ProjectRoot ("openclaw\workspaces\" + $agent.id)
        $sourcePrompt = Join-Path $sourceWorkspace "AGENTS.md"
        $projectLink = Join-Path $workspacePath "project"

        if (-not (Test-Path -LiteralPath $sourcePrompt)) {
            throw "Missing agent prompt: $sourcePrompt"
        }

        New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null
        Copy-WorkspaceScaffold -SourceWorkspacePath $sourceWorkspace -TargetWorkspacePath $workspacePath
        New-WorkspaceBootstrap -WorkspacePath $workspacePath

        if (Test-Path -LiteralPath $projectLink) {
            $existing = Get-Item -LiteralPath $projectLink -Force
            if (-not ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Workspace path already exists and is not a junction: $projectLink"
            }
            try {
                Remove-Item -LiteralPath $projectLink -Force -Recurse -ErrorAction Stop
            } catch {
                [System.IO.Directory]::Delete($projectLink)
            }
        }

        New-Item -ItemType Junction -Path $projectLink -Target $ProjectRoot | Out-Null
    }
}

$configPath = Join-Path $OpenClawHome "openclaw.json"
$projectConfigPath = Join-Path $ProjectRoot "openclaw.config.json"

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "OpenClaw config not found: $configPath"
}
if (-not (Test-Path -LiteralPath $projectConfigPath)) {
    throw "Project config not found: $projectConfigPath"
}

$commandInfo = Get-Command openclaw -ErrorAction SilentlyContinue
if (-not $commandInfo) {
    throw "OpenClaw CLI not found in PATH."
}

$nodeInfo = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeInfo) {
    throw "Node.js not found in PATH."
}

$commandSource = $commandInfo.Source
$commandRoot = Split-Path -Parent $commandSource
$mjsCandidate = Join-Path $commandRoot "node_modules\openclaw\openclaw.mjs"

if (-not (Test-Path -LiteralPath $mjsCandidate)) {
    throw "OpenClaw module entry not found: $mjsCandidate"
}

$script:OpenClawNode = $nodeInfo.Source
$script:OpenClawBaseArgs = @($mjsCandidate)

$currentConfig = Get-Content -LiteralPath $configPath -Raw -Encoding utf8 | ConvertFrom-Json
$projectConfig = Get-Content -LiteralPath $projectConfigPath -Raw -Encoding utf8 | ConvertFrom-Json
$agentSpecs = @($projectConfig.agents.list)

if (-not $Model) {
    if (
        $currentConfig.PSObject.Properties.Name -contains "agents" -and
        $currentConfig.agents.PSObject.Properties.Name -contains "defaults" -and
        $currentConfig.agents.defaults.PSObject.Properties.Name -contains "model" -and
        $currentConfig.agents.defaults.model.PSObject.Properties.Name -contains "primary"
    ) {
        $Model = [string]$currentConfig.agents.defaults.model.primary
    } else {
        $Model = "openai-codex/gpt-5.3-codex"
    }
}

$resolvedFeishuAccountId = Resolve-FeishuAccountId -Config $currentConfig -OpenClawHome $OpenClawHome
$workspaceRoot = Join-Path $OpenClawHome ("workspaces\" + $WorkspaceNamespace)

if (-not $SkipBackup) {
    $backupDir = Backup-OpenClawState -OpenClawHome $OpenClawHome
    Write-Host "[backup] $backupDir"
}

Ensure-AgentWorkspaces -AgentSpecs $agentSpecs -WorkspaceRoot $workspaceRoot -ProjectRoot $ProjectRoot

$runtimeDefaults = [pscustomobject]@{
    model = [pscustomobject]@{
        primary = $Model
    }
    workspace = (Join-Path $workspaceRoot "planner")
}

if (
    $currentConfig.PSObject.Properties.Name -contains "agents" -and
    $currentConfig.agents.PSObject.Properties.Name -contains "defaults" -and
    $currentConfig.agents.defaults.PSObject.Properties.Name -contains "models"
) {
    Add-Member -InputObject $runtimeDefaults -MemberType NoteProperty -Name "models" -Value $currentConfig.agents.defaults.models
}

if (
    $currentConfig.PSObject.Properties.Name -contains "agents" -and
    $currentConfig.agents.PSObject.Properties.Name -contains "defaults" -and
    $currentConfig.agents.defaults.PSObject.Properties.Name -contains "compaction"
) {
    Add-Member -InputObject $runtimeDefaults -MemberType NoteProperty -Name "compaction" -Value $currentConfig.agents.defaults.compaction
}

if (
    $currentConfig.PSObject.Properties.Name -contains "agents" -and
    $currentConfig.agents.PSObject.Properties.Name -contains "defaults" -and
    $currentConfig.agents.defaults.PSObject.Properties.Name -contains "maxConcurrent"
) {
    Add-Member -InputObject $runtimeDefaults -MemberType NoteProperty -Name "maxConcurrent" -Value $currentConfig.agents.defaults.maxConcurrent
}

if (-not ($currentConfig.PSObject.Properties.Name -contains "agents")) {
    Add-Member -InputObject $currentConfig -MemberType NoteProperty -Name "agents" -Value ([pscustomobject]@{})
}

if ($currentConfig.agents.PSObject.Properties.Name -contains "list") {
    $currentConfig.agents.PSObject.Properties.Remove("list")
}
if ($currentConfig.PSObject.Properties.Name -contains "cron") {
    $currentConfig.PSObject.Properties.Remove("cron")
}
if ($currentConfig.PSObject.Properties.Name -contains "services") {
    $currentConfig.PSObject.Properties.Remove("services")
}

Ensure-ObjectProperty -Object $currentConfig.agents -Name "defaults" -Value $runtimeDefaults
Ensure-ObjectProperty -Object $currentConfig -Name "bindings" -Value @()

if ($currentConfig.PSObject.Properties.Name -contains "meta") {
    Ensure-ObjectProperty -Object $currentConfig.meta -Name "lastTouchedVersion" -Value "2026.2.26"
    Ensure-ObjectProperty -Object $currentConfig.meta -Name "lastTouchedAt" -Value ((Get-Date).ToUniversalTime().ToString("o"))
}

$currentConfig | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $configPath -Encoding utf8

$registeredAgentsRaw = Invoke-OpenClaw "agents" "list" "--json"
$registeredAgents = $registeredAgentsRaw | ConvertFrom-Json
$registeredIds = @($registeredAgents | ForEach-Object { $_.id })

foreach ($agent in $agentSpecs) {
    if ($registeredIds -contains $agent.id) {
        continue
    }

    $workspacePath = Join-Path $workspaceRoot $agent.id
    Invoke-OpenClaw "agents" "add" $agent.id "--workspace" $workspacePath "--non-interactive" "--model" $Model | Out-Null
}

Invoke-OpenClaw "config" "set" "--strict-json" "bindings" "[]" | Out-Null
Invoke-OpenClaw "agents" "bind" "--agent" "planner" "--bind" ("feishu:" + $resolvedFeishuAccountId) | Out-Null

if (-not $SkipGatewayRestart) {
    try {
        Invoke-OpenClaw "gateway" "restart" | Out-Null
    } catch {
        Invoke-OpenClaw "gateway" "start" | Out-Null
    }
}

if (-not $SkipCron) {
    try {
        $cronSpecs = @(
            [pscustomobject]@{
                id = "daily_report"
                agentId = "planner"
                schedule = "15 8 * * 1-5"
                description = "Weekday 08:15 daily report generation"
                message = "Scheduled task: generate today's quant research daily report for {{date}}. Follow the standard pipeline: ingestion -> Knowledge -> Quant -> Risk -> Report -> Critic -> Feishu delivery."
            },
            [pscustomobject]@{
                id = "weekly_report"
                agentId = "planner"
                schedule = "0 8 * * 1"
                description = "Monday 08:00 weekly report generation"
                message = "Scheduled task: generate this week's quant research weekly report for {{week_start}} to {{week_end}}. Summarize the week's daily reports, quantitative signals, and risk observations, then deliver the final report."
            },
            [pscustomobject]@{
                id = "evening_data_fetch"
                agentId = "planner"
                schedule = "30 16 * * 1-5"
                description = "Weekday 16:30 close data ingestion"
                message = "Scheduled task: run target-pool end-of-day incremental ingestion. Call the ingestion target-pool sync flow to collect close-related announcements, news, and market updates, then refresh the Quant data store."
            },
            [pscustomobject]@{
                id = "morning_target_pool_sync"
                agentId = "planner"
                schedule = "35 8 * * 1-5"
                description = "Weekday 08:35 target-pool morning incremental ingestion"
                message = "Scheduled task: run target-pool morning incremental ingestion. Call the ingestion target-pool sync flow and prioritize all_news plus all_announcements coverage before market open."
            },
            [pscustomobject]@{
                id = "midday_target_pool_sync"
                agentId = "planner"
                schedule = "35 12 * * 1-5"
                description = "Weekday 12:35 target-pool midday incremental ingestion"
                message = "Scheduled task: run target-pool midday incremental ingestion. Call the ingestion target-pool sync flow to backfill newly published announcements and news for the target stock pool."
            }
        )

        $existingJobsRaw = Invoke-OpenClaw "cron" "list" "--all" "--json"
        $existingJobs = @()
        if ($existingJobsRaw) {
            $existingJobsParsed = $existingJobsRaw | ConvertFrom-Json
            if (
                $existingJobsParsed -and
                $existingJobsParsed.PSObject.Properties.Name -contains "jobs"
            ) {
                $existingJobs = @($existingJobsParsed.jobs)
            } else {
                $existingJobs = @($existingJobsParsed)
            }
        }

        foreach ($job in $existingJobs) {
            if (@("daily_report", "weekly_report", "evening_data_fetch", "morning_target_pool_sync", "midday_target_pool_sync") -contains $job.name) {
                Invoke-OpenClaw "cron" "rm" $job.id | Out-Null
            }
        }

        foreach ($job in $cronSpecs) {
            Invoke-OpenClaw `
                "cron" "add" `
                "--name" $job.id `
                "--agent" $job.agentId `
                "--cron" $job.schedule `
                "--message" $job.message `
                "--description" $job.description `
                "--tz" "Asia/Shanghai" `
                "--no-deliver" | Out-Null
        }
    } catch {
        Write-Warning ("Cron sync skipped: " + $_.Exception.Message)
    }
}

$finalAgents = Invoke-OpenClaw "agents" "list" "--json"
$finalBindings = Invoke-OpenClaw "agents" "bindings" "--json"

Write-Host "[model] $Model"
Write-Host "[feishu] $resolvedFeishuAccountId"
Write-Host "[workspace] $workspaceRoot"
Write-Host "[agents] $finalAgents"
Write-Host "[bindings] $finalBindings"
