# bootstrap_22203_worker.ps1 - Deploy worker service on 192.168.22.203
# Run as elevated PowerShell:
#   Set-ExecutionPolicy Bypass -Scope Process -Force; iwr http://192.168.22.8:9999/scripts/bootstrap_22203_worker.ps1 -OutFile $env:TEMP\boot203.ps1; & $env:TEMP\boot203.ps1

param(
    [string]$SourceBaseUrl = "http://192.168.22.8:9999",
    [string]$InstallDir    = "C:\RASAgent",
    [string]$BindIP        = "192.168.22.203",
    [int]   $Port          = 8080,
    [string]$TaskName      = "RASAgent-Worker"
)

$ErrorActionPreference = "Stop"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  RAS Wireless Agent - Worker Bootstrap (22.203)"
Write-Host "  Source:   $SourceBaseUrl"
Write-Host "  Install:  $InstallDir"
Write-Host "  Bind:     ${BindIP}:${Port}"
Write-Host "============================================================" -ForegroundColor Cyan

# --- Phase 1: Stop existing service ---
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "[1] Stopping existing task: $TaskName"
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep 3
    $procs = Get-Process python* -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "${InstallDir}*" }
    if ($procs) {
        Write-Host "    Waiting for processes to exit..."
        $procs | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
        $still = Get-Process python* -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "${InstallDir}*" }
        if ($still) {
            Write-Host "    Force-killing lingering processes"
            $still | Stop-Process -Force
        }
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} else {
    Write-Host "[1] No existing task found"
}

# --- Phase 2: Backup & Extract ---
Write-Host "[2] Downloading deploy zip..."
$zipPath = "$env:TEMP\RASAgent_deploy.zip"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri "$SourceBaseUrl/RASAgent_deploy.zip" -OutFile $zipPath -UseBasicParsing

# Backup .venv and .env
$backupDir = "$env:TEMP\rasagent_backup"
if (Test-Path $backupDir) { Remove-Item $backupDir -Recurse -Force }
New-Item -ItemType Directory $backupDir -Force | Out-Null
foreach ($item in @(".venv", ".env")) {
    $src = Join-Path $InstallDir $item
    if (Test-Path $src) {
        Write-Host "    Backing up $item"
        Copy-Item $src -Destination (Join-Path $backupDir $item) -Recurse -Force
    }
}

# Remove and extract
if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }
New-Item -ItemType Directory $InstallDir | Out-Null
Expand-Archive $zipPath -DestinationPath $InstallDir -Force
Remove-Item $zipPath -ErrorAction SilentlyContinue

# Flatten if nested
$nested = Get-ChildItem $InstallDir -Directory
if ($nested.Count -eq 1 -and (Test-Path (Join-Path $InstallDir "$($nested.Name)\requirements.txt"))) {
    Write-Host "    Flattening nested directory"
    Get-ChildItem (Join-Path $InstallDir $nested.Name) |
        Move-Item -Destination $InstallDir -Force
    Remove-Item (Join-Path $InstallDir $nested.Name) -Force -ErrorAction SilentlyContinue
}

# Restore backups
foreach ($item in @(".venv", ".env")) {
    $bak = Join-Path $backupDir $item
    if (Test-Path $bak) {
        Write-Host "    Restoring $item from backup"
        Copy-Item $bak -Destination (Join-Path $InstallDir $item) -Recurse -Force
    }
}
Remove-Item $backupDir -Recurse -Force -ErrorAction SilentlyContinue

# --- Phase 3: Python venv & deps ---
Write-Host "[3] Setting up Python environment..."
$venvDir = Join-Path $InstallDir ".venv"
if (-not (Test-Path (Join-Path $venvDir "Scripts\python.exe"))) {
    & python -m venv $venvDir
}
$pip = Join-Path $venvDir "Scripts\pip.exe"
$offlinePkgs = Join-Path $InstallDir "offline_packages"
if (Test-Path $offlinePkgs) {
    & $pip install --no-index --find-links $offlinePkgs -r (Join-Path $InstallDir "requirements.txt") -q 2>$null
} else {
    & $pip install -r (Join-Path $InstallDir "requirements.txt") -q 2>$null
}

# --- Phase 4: Firewall ---
Write-Host "[4] Ensuring firewall rule..."
$fwRule = Get-NetFirewallRule -DisplayName "RASAgent-Worker-${Port}" -ErrorAction SilentlyContinue
if (-not $fwRule) {
    New-NetFirewallRule -DisplayName "RASAgent-Worker-${Port}" `
        -Direction Inbound -Protocol TCP -LocalPort $Port `
        -RemoteAddress 192.168.22.0/24 -Action Allow | Out-Null
    Write-Host "    Created firewall rule for port $Port"
} else {
    Write-Host "    Firewall rule exists"
}

# --- Phase 5: Scheduled Task ---
Write-Host "[5] Registering scheduled task: $TaskName"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "-m uvicorn worker.app:app --host $BindIP --port $Port" `
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
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User "SYSTEM" `
    -RunLevel Highest `
    -Description "RAS Wireless Agent - Worker (port $Port)" `
    -Force | Out-Null

# --- Phase 6: Start & Verify ---
Write-Host "[6] Starting task and verifying..."
Start-ScheduledTask -TaskName $TaskName

$healthUrl = "http://${BindIP}:${Port}/health"
$ok = $false
for ($i = 1; $i -le 12; $i++) {
    Start-Sleep 5
    try {
        $resp = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
        if ($resp.status -eq "ok") {
            Write-Host "    Health OK after $($i * 5)s" -ForegroundColor Green
            $ok = $true
            break
        }
    } catch {
        Write-Host "    Attempt $i - waiting..."
    }
}

if ($ok) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  Worker deployed on ${BindIP}:${Port}" -ForegroundColor Green
    Write-Host "  Health: $healthUrl" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "  WARNING: Health check did not pass in 60s." -ForegroundColor Yellow
    Write-Host "  Check task status: Get-ScheduledTask -TaskName $TaskName"
    Write-Host "  Check logs in: $InstallDir\artifacts"
}
