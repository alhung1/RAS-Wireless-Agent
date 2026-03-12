<#
.SYNOPSIS
    Safe deploy of the Router Control Service to 22.100.

.DESCRIPTION
    Two-phase stop strategy: stops the scheduled task, waits for processes to
    exit gracefully, optionally force-kills if they linger.  Uses safe
    backup/restore of runtime state (.env, .playwright, .venv) instead of
    exclusion-based deletion.

    Steps:
      1. Download RASAgent_deploy.zip
      2. Stop scheduled task (Phase 1: graceful, Phase 2: optional force)
      3. Backup runtime state (.env, .playwright, .venv)
      4. Remove install dir, extract new code
      5. Restore runtime state from backup
      6. Start scheduled task and verify /health

.PARAMETER SourceBase
    Base URL of the file server.  Default: http://192.168.22.8:9999
.PARAMETER InstallDir
    Where to install.  Default: C:\RASAgent
.PARAMETER Port
    Port for the router-control service.  Default: 8081
.PARAMETER GracefulTimeoutSec
    Seconds to wait for processes to exit after stopping the task.  Default: 30
.PARAMETER ForceKillAfterTimeout
    If set, force-kill lingering processes under InstallDir after the graceful
    timeout.  By default this is OFF to avoid leaving the system undeployable.
#>
param(
    [string]$SourceBase = "http://192.168.22.8:9999",
    [string]$InstallDir = "C:\RASAgent",
    [int]$Port = 8081,
    [int]$GracefulTimeoutSec = 30,
    [switch]$ForceKillAfterTimeout
)

$ErrorActionPreference = "Stop"
$taskName = "RASAgent-RouterService"
$backupDir = "$env:TEMP\RASAgent_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RAS Agent - Safe Deploy"                    -ForegroundColor Cyan
Write-Host "  Two-Phase Stop + Backup/Restore"            -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# --- Step 1: Download ---
$zipPath = "$env:TEMP\RASAgent_deploy.zip"
Write-Host "`n[1/6] Downloading project from $SourceBase ..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
    Invoke-WebRequest -Uri "$SourceBase/RASAgent_deploy.zip" -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
    Write-Host "  [OK] Downloaded" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Download failed: $_" -ForegroundColor Red
    exit 1
}

# --- Step 2: Two-phase stop ---
Write-Host "`n[2/6] Stopping service (two-phase) ..."

# Phase 1: Stop scheduled task
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task -and $task.State -eq "Running") {
    Write-Host "  Phase 1: Stopping task '$taskName' ..."
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

    $elapsed = 0
    $interval = 2
    while ($elapsed -lt $GracefulTimeoutSec) {
        $procs = Get-Process -Name python*, uvicorn* -ErrorAction SilentlyContinue |
                 Where-Object { $_.Path -like "$InstallDir\*" }
        if (-not $procs) {
            Write-Host "  [OK] All processes exited gracefully (${elapsed}s)" -ForegroundColor Green
            break
        }
        Write-Host "  Waiting for $($procs.Count) process(es) to exit... (${elapsed}s/$GracefulTimeoutSec)"
        Start-Sleep -Seconds $interval
        $elapsed += $interval
        $interval = [Math]::Min($interval * 2, 8)
    }

    # Phase 2: Check if force-kill needed
    $procs = Get-Process -Name python*, uvicorn* -ErrorAction SilentlyContinue |
             Where-Object { $_.Path -like "$InstallDir\*" }
    if ($procs) {
        if ($ForceKillAfterTimeout) {
            Write-Host "  Phase 2: Force-killing $($procs.Count) lingering process(es) ..." -ForegroundColor Yellow
            $procs | Stop-Process -Force
            Start-Sleep -Seconds 2
            Write-Host "  [OK] Force-killed" -ForegroundColor Yellow
        } else {
            Write-Host "  [FAIL] $($procs.Count) process(es) still running after ${GracefulTimeoutSec}s:" -ForegroundColor Red
            $procs | ForEach-Object { Write-Host "    PID=$($_.Id)  Path=$($_.Path)" -ForegroundColor Red }
            Write-Host "  Re-run with -ForceKillAfterTimeout, or stop them manually." -ForegroundColor Yellow
            Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
            exit 1
        }
    }
} else {
    Write-Host "  [OK] Task not running" -ForegroundColor Green
}

# --- Step 3: Backup runtime state ---
Write-Host "`n[3/6] Backing up runtime state ..."
Set-Location $env:SystemRoot

if (Test-Path $InstallDir) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    foreach ($item in @(".env", ".playwright", ".venv")) {
        $src = Join-Path $InstallDir $item
        if (Test-Path $src) {
            $dst = Join-Path $backupDir $item
            if ((Get-Item $src).PSIsContainer) {
                Copy-Item $src $dst -Recurse -Force
            } else {
                Copy-Item $src $dst -Force
            }
            Write-Host "  Backed up: $item"
        }
    }
    Write-Host "  [OK] Backup at $backupDir" -ForegroundColor Green

    Write-Host "  Removing $InstallDir ..."
    Remove-Item $InstallDir -Recurse -Force
} else {
    Write-Host "  [OK] Clean install (no existing dir)" -ForegroundColor Green
}

# --- Step 4: Extract new code ---
Write-Host "`n[4/6] Extracting new code ..."
try {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force
    Remove-Item $zipPath -Force

    $nested = Get-ChildItem -Path $InstallDir -Directory
    if ($nested.Count -eq 1 -and (Test-Path "$InstallDir\$($nested.Name)\requirements.txt")) {
        $src = "$InstallDir\$($nested.Name)"
        Get-ChildItem -Path $src | Move-Item -Destination $InstallDir -Force
        Remove-Item $src -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  [OK] Extracted to $InstallDir" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Extract failed: $_" -ForegroundColor Red
    if (Test-Path $backupDir) {
        Write-Host "  Restoring from backup ..." -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        Get-ChildItem -Path $backupDir | ForEach-Object {
            Copy-Item $_.FullName (Join-Path $InstallDir $_.Name) -Recurse -Force
        }
        Write-Host "  [OK] Backup restored" -ForegroundColor Yellow
    }
    exit 1
}

# --- Step 5: Restore runtime state ---
Write-Host "`n[5/6] Restoring runtime state ..."
if (Test-Path $backupDir) {
    foreach ($item in @(".env", ".playwright", ".venv")) {
        $src = Join-Path $backupDir $item
        $dst = Join-Path $InstallDir $item
        if (Test-Path $src) {
            if (-not (Test-Path $dst)) {
                if ((Get-Item $src).PSIsContainer) {
                    Copy-Item $src $dst -Recurse -Force
                } else {
                    Copy-Item $src $dst -Force
                }
                Write-Host "  Restored: $item"
            }
        }
    }
    Remove-Item $backupDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Runtime state restored, backup cleaned" -ForegroundColor Green
} else {
    Write-Host "  [OK] No backup to restore (fresh install)" -ForegroundColor Green
}

# --- Step 6: Start and verify ---
Write-Host "`n[6/6] Starting service and verifying ..."
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Start-ScheduledTask -TaskName $taskName

    $healthy = $false
    for ($i = 1; $i -le 8; $i++) {
        Start-Sleep -Seconds 3
        try {
            $r = Invoke-RestMethod -Uri "http://localhost:$Port/health" -TimeoutSec 5
            if ($r.status -eq "ok") {
                Write-Host "  [OK] Service healthy: $($r | ConvertTo-Json -Compress)" -ForegroundColor Green
                $healthy = $true
                break
            }
        } catch {}
        Write-Host "  Polling health ($i/8) ..."
    }
    if (-not $healthy) {
        Write-Host "  [WARN] Service did not respond. Check logs." -ForegroundColor Yellow
    }
} else {
    Write-Host "  [WARN] Scheduled task '$taskName' not found. Register it first." -ForegroundColor Yellow
    Write-Host "  Run: .\scripts\setup_22100_autostart.ps1" -ForegroundColor Yellow
}

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  Deploy complete!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
