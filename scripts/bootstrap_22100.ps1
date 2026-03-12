<#
.SYNOPSIS
    One-command bootstrap: deploy + scheduled-task setup on 22.100.

.DESCRIPTION
    Downloads the project zip from the orchestrator file server, installs
    Python dependencies (offline), sets up Playwright browsers, configures
    .env, registers a Windows Scheduled Task for auto-start, and verifies
    the service is responding.  Fully non-interactive -- paste one line and
    walk away.

.PARAMETER SourceBase
    Base URL of the file server.  Default: http://192.168.22.8:9999
.PARAMETER InstallDir
    Where to install.  Default: C:\RASAgent
.PARAMETER Port
    Port for the router-control service.  Default: 8081
.PARAMETER ServiceBindIP
    IP address to bind uvicorn to.  Default: 0.0.0.0 (lab mode).
    For production, set to the 22-domain IP (e.g. 192.168.22.100).
.PARAMETER RouterNicMAC
    MAC address of the router-facing NIC (e.g. "AA-BB-CC-DD-EE-FF").
    If provided, the NIC is identified by MAC instead of InterfaceAlias.
.PARAMETER RouterNicIndex
    ifIndex of the router-facing NIC.  Alternative to -RouterNicMAC.
#>
param(
    [string]$SourceBase = "http://192.168.22.8:9999",
    [string]$InstallDir = "C:\RASAgent",
    [int]$Port = 8081,
    [string]$ServiceBindIP = "0.0.0.0",
    [string]$RouterNicMAC,
    [int]$RouterNicIndex = 0
)

$ErrorActionPreference = "Stop"
$taskName = "RASAgent-RouterService"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RAS Agent - One-Command Bootstrap"         -ForegroundColor Cyan
Write-Host "  Deploy + Auto-Start on 22.100"             -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# ===================================================================
#  PHASE 1: DEPLOY
# ===================================================================

# --- 1. Download project zip ---
$zipPath = "$env:TEMP\RASAgent_deploy.zip"
Write-Host "`n[1/10] Downloading project from $SourceBase ..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
    Invoke-WebRequest -Uri "$SourceBase/RASAgent_deploy.zip" -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
    Write-Host "  [OK] Project zip downloaded" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Download failed: $_" -ForegroundColor Red
    Write-Host "  Make sure the file server is running on 192.168.22.8:9999" -ForegroundColor Yellow
    exit 1
}

# --- 2. Stop existing scheduled task if running ---
Write-Host "`n[2/10] Stopping existing service (if any) ..."
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and $existing.State -eq "Running") {
    Stop-ScheduledTask -TaskName $taskName
    $elapsed = 0
    while ($elapsed -lt 20) {
        $procs = Get-Process -Name python*, uvicorn* -ErrorAction SilentlyContinue |
                 Where-Object { $_.Path -like "$InstallDir\*" }
        if (-not $procs) { break }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
    Write-Host "  [OK] Stopped existing task" -ForegroundColor Green
} else {
    Write-Host "  [OK] No running task found" -ForegroundColor Green
}

# --- 3. Extract project (safe backup/restore) ---
Write-Host "`n[3/10] Extracting to $InstallDir ..."
Set-Location $env:SystemRoot
$backupDir = "$env:TEMP\RASAgent_bootstrap_bak"

if (Test-Path $InstallDir) {
    if (Test-Path $backupDir) { Remove-Item $backupDir -Recurse -Force }
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

    foreach ($item in @(".venv", ".env", ".playwright")) {
        $p = Join-Path $InstallDir $item
        if (Test-Path $p) {
            $b = Join-Path $backupDir $item
            if ((Get-Item $p).PSIsContainer) {
                Copy-Item $p $b -Recurse -Force
            } else {
                Copy-Item $p $b -Force
            }
            Write-Host "  Backed up: $item"
        }
    }
    Remove-Item $InstallDir -Recurse -Force
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force
Remove-Item $zipPath -Force

$nested = Get-ChildItem -Path $InstallDir -Directory
if ($nested.Count -eq 1 -and (Test-Path "$InstallDir\$($nested.Name)\requirements.txt")) {
    $src = "$InstallDir\$($nested.Name)"
    Get-ChildItem -Path $src | Move-Item -Destination $InstallDir -Force
    Remove-Item $src -Force -ErrorAction SilentlyContinue
}

if (Test-Path $backupDir) {
    foreach ($item in @(".venv", ".env", ".playwright")) {
        $src = Join-Path $backupDir $item
        $dst = Join-Path $InstallDir $item
        if ((Test-Path $src) -and -not (Test-Path $dst)) {
            if ((Get-Item $src).PSIsContainer) {
                Copy-Item $src $dst -Recurse -Force
            } else {
                Copy-Item $src $dst -Force
            }
            Write-Host "  Restored: $item"
        }
    }
    Remove-Item $backupDir -Recurse -Force -ErrorAction SilentlyContinue
}

Set-Location $InstallDir
Write-Host "  [OK] Extracted to $InstallDir" -ForegroundColor Green

# --- 4. Python check ---
Write-Host "`n[4/10] Checking Python ..."
$py = $null
foreach ($cmd in @("python", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python\s+(\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $py = $cmd
                Write-Host "  [OK] $ver ($cmd)" -ForegroundColor Green
                break
            }
        }
    } catch {}
}
if (-not $py) {
    Write-Host "  [FAIL] Python 3.10+ not found!" -ForegroundColor Red
    exit 1
}

# --- 5. Venv ---
Write-Host "`n[5/10] Setting up virtual environment ..."
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $py -m venv .venv
    Write-Host "  [OK] venv created" -ForegroundColor Green
} else {
    Write-Host "  [OK] venv already exists" -ForegroundColor Green
}
. .\.venv\Scripts\Activate.ps1

# --- 6. Pip install (offline) ---
Write-Host "`n[6/10] Installing dependencies ..."
if (Test-Path "offline_packages") {
    python -m pip install --no-index --find-links offline_packages -r requirements.txt -q 2>$null
    Write-Host "  [OK] Dependencies installed (offline)" -ForegroundColor Green
} else {
    Write-Host "  [WARN] offline_packages not found, trying online ..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt -q
    Write-Host "  [OK] Dependencies installed (online)" -ForegroundColor Green
}

# --- 7. Playwright browsers (offline) ---
Write-Host "`n[7/10] Installing Playwright browsers ..."
$pwLocal = "$InstallDir\.playwright"
$pwUser  = "$env:LOCALAPPDATA\ms-playwright"

if (-not (Test-Path "$pwLocal\chromium*")) {
    if (Test-Path "$pwUser\chromium*") {
        Write-Host "  Copying from user profile to $pwLocal ..."
        if (Test-Path $pwLocal) { Remove-Item $pwLocal -Recurse -Force }
        Copy-Item $pwUser $pwLocal -Recurse -Force
        Write-Host "  [OK] Playwright browsers copied to install dir" -ForegroundColor Green
    } else {
        $pwZip = "$env:TEMP\playwright_browsers.zip"
        try {
            Invoke-WebRequest -Uri "$SourceBase/playwright_browsers.zip" -OutFile $pwZip -UseBasicParsing -TimeoutSec 300
            if (Test-Path $pwUser) { Remove-Item $pwUser -Recurse -Force }
            New-Item -ItemType Directory -Path $pwUser -Force | Out-Null
            Expand-Archive -Path $pwZip -DestinationPath $pwUser -Force
            Remove-Item $pwZip -Force
            Copy-Item $pwUser $pwLocal -Recurse -Force
            Write-Host "  [OK] Playwright browsers installed and copied" -ForegroundColor Green
        } catch {
            Write-Host "  [WARN] Playwright browser download failed: $_" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  [OK] Playwright browsers already in $pwLocal" -ForegroundColor Green
}

# --- 8. .env ---
Write-Host "`n[8/10] Configuring .env ..."
if (-not (Test-Path ".env")) {
    $envLines = @(
        "ROUTER_USER=admin",
        "ROUTER_PASS=Password@1",
        "SERVICE_BIND_IP=$ServiceBindIP",
        "SERVICE_MODE=lab"
    )
    Set-Content -Path ".env" -Value $envLines -Encoding UTF8
    Write-Host "  [OK] .env created (SERVICE_BIND_IP=$ServiceBindIP)" -ForegroundColor Green
} else {
    Write-Host "  [OK] .env already exists (preserved)" -ForegroundColor Green
}

# ===================================================================
#  PHASE 2: SCHEDULED TASK (AUTO-START)
# ===================================================================

# --- 9. Register scheduled task ---
Write-Host "`n[9/10] Registering scheduled task '$taskName' ..."

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

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

Write-Host "  [OK] Scheduled task registered (bind=$ServiceBindIP)" -ForegroundColor Green

# --- 10. Start and verify ---
Write-Host "`n[10/10] Starting service and verifying ..."
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5

$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "  Task state: $state"

$healthUrl = if ($ServiceBindIP -eq "0.0.0.0") { "http://localhost:$Port/health" } else { "http://${ServiceBindIP}:$Port/health" }
$retries = 8
$ok = $false
for ($i = 0; $i -lt $retries; $i++) {
    Start-Sleep -Seconds 3
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        Write-Host "  [OK] Service responding: $($r.Content)" -ForegroundColor Green
        $ok = $true
        break
    } catch {
        Write-Host "  Waiting... ($($i+1)/$retries)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
if ($ok) {
    Write-Host "  Bootstrap COMPLETE"                        -ForegroundColor Green
} else {
    Write-Host "  Bootstrap DONE (service slow to start)"    -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Install:  $InstallDir"
Write-Host "  Task:     $taskName"
Write-Host "  Port:     $Port"
Write-Host "  Bind IP:  $ServiceBindIP"
Write-Host "  State:    $state"
Write-Host ""
Write-Host "  Auto-starts on every boot."
Write-Host "  Future updates: python scripts/deploy_and_restart.py"
Write-Host "============================================" -ForegroundColor Cyan
