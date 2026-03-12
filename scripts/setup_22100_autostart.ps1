<#
.SYNOPSIS
    Register router_service as a Scheduled Task on 22.100 for auto-start at boot.

.DESCRIPTION
    One-time setup. After running this, the router-control service will
    automatically start when the machine boots. No new accounts, no registry
    changes, no impact on RDP.

    The scheduled task runs as SYSTEM with WorkingDirectory set to InstallDir.
    Uses CREATE_BREAKAWAY_FROM_JOB in the restart mechanism (handled by
    router_service/app.py _schedule_restart()).

.PARAMETER InstallDir
    Where the project is installed.  Default: C:\RASAgent
.PARAMETER Port
    Port for the router-control service.  Default: 8081
.PARAMETER ServiceBindIP
    IP to bind uvicorn to.  Default reads from .env SERVICE_BIND_IP,
    falls back to 0.0.0.0.
#>
param(
    [string]$InstallDir = "C:\RASAgent",
    [int]$Port = 8081,
    [string]$ServiceBindIP
)

$ErrorActionPreference = "Stop"
$taskName = "RASAgent-RouterService"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Router Service Auto-Start Setup"           -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# --- Validate install dir ---
if (-not (Test-Path "$InstallDir\.venv\Scripts\python.exe")) {
    Write-Host "[FAIL] $InstallDir\.venv\Scripts\python.exe not found." -ForegroundColor Red
    Write-Host "  Run deploy_22100_routerservice.ps1 first." -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] Install dir: $InstallDir" -ForegroundColor Green

# --- Resolve bind IP from .env if not provided ---
if (-not $ServiceBindIP) {
    $envFile = Join-Path $InstallDir ".env"
    if (Test-Path $envFile) {
        $match = Select-String -Path $envFile -Pattern "^SERVICE_BIND_IP=(.+)" -ErrorAction SilentlyContinue
        if ($match) {
            $ServiceBindIP = $match.Matches[0].Groups[1].Value.Trim()
        }
    }
    if (-not $ServiceBindIP) { $ServiceBindIP = "0.0.0.0" }
}
Write-Host "[OK] Bind IP: $ServiceBindIP" -ForegroundColor Green

# --- Remove existing task if present ---
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.State -eq "Running") {
        Stop-ScheduledTask -TaskName $taskName
        Start-Sleep -Seconds 3
    }
    Write-Host "[...] Removing existing task '$taskName' ..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# --- Create the service task ---
Write-Host "[...] Creating scheduled task '$taskName' ..."

$uvicornArgs = "-m uvicorn router_service.app:app --host $ServiceBindIP --port $Port"

$action = New-ScheduledTaskAction `
    -Execute "$InstallDir\.venv\Scripts\python.exe" `
    -Argument $uvicornArgs `
    -WorkingDirectory $InstallDir

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 9999)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User "SYSTEM" `
    -RunLevel Highest `
    -Description "RAS Wireless Agent - Router Control Service (port $Port, bind $ServiceBindIP)" | Out-Null

Write-Host "[OK] Scheduled task '$taskName' registered" -ForegroundColor Green

# --- Start the task now ---
Write-Host "[...] Starting task now ..."
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5

$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "[OK] Task state: $state" -ForegroundColor Green

# --- Verify service is responding (polling with backoff) ---
Write-Host "[...] Verifying service on port $Port ..."
$healthUrl = if ($ServiceBindIP -eq "0.0.0.0") { "http://localhost:$Port/health" } else { "http://${ServiceBindIP}:$Port/health" }
$retries = 10
$ok = $false
$interval = 2
for ($i = 0; $i -lt $retries; $i++) {
    Start-Sleep -Seconds $interval
    try {
        $r = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
        if ($r.status -eq "ok") {
            Write-Host "[OK] Service healthy: $($r | ConvertTo-Json -Compress)" -ForegroundColor Green
            $ok = $true
            break
        }
    } catch {
        Write-Host "  Waiting... ($($i+1)/$retries)" -ForegroundColor Yellow
    }
    $interval = [Math]::Min($interval * 2, 10)
}
if (-not $ok) {
    Write-Host "[WARN] Service not responding yet. Check logs at:" -ForegroundColor Yellow
    Write-Host "  $InstallDir\artifacts\router_service\" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Setup Complete"                             -ForegroundColor Cyan
Write-Host ""
Write-Host "  Task:     $taskName"
Write-Host "  State:    $state"
Write-Host "  Port:     $Port"
Write-Host "  Bind IP:  $ServiceBindIP"
Write-Host "  WorkDir:  $InstallDir"
Write-Host ""
Write-Host "  The service will auto-start on every boot."
Write-Host "  Manual control:"
Write-Host "    Start-ScheduledTask -TaskName '$taskName'"
Write-Host "    Stop-ScheduledTask  -TaskName '$taskName'"
Write-Host "============================================" -ForegroundColor Cyan
