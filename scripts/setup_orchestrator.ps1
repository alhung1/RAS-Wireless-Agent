#Requires -RunAsAdministrator
<#
.SYNOPSIS
    One-click setup for the Orchestrator machine (192.168.22.100).
    Run this script as Administrator on the orchestrator PC.
.DESCRIPTION
    1. Checks Python 3.10+
    2. Creates venv and installs dependencies + Playwright Chromium
    3. Configures .env with router credentials
    4. Runs smoke tests (recon_router.py, check_ssid.py)
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Orchestrator Setup                    " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# --- Check Python ---
$py = $null
foreach ($cmd in @("python", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python\s+(\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $py = $cmd
                Write-Host "[OK] $ver ($cmd)" -ForegroundColor Green
                break
            }
        }
    } catch {}
}
if (-not $py) {
    Write-Host "[ERROR] Python 3.10+ not found. Install from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

# --- Create venv ---
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[...] Creating virtual environment..." -ForegroundColor Yellow
    & $py -m venv .venv
}
Write-Host "[OK] Virtual environment ready" -ForegroundColor Green

# --- Activate and install ---
. .\.venv\Scripts\Activate.ps1
Write-Host "[...] Installing dependencies..." -ForegroundColor Yellow
pip install -q -r requirements.txt
Write-Host "[OK] Dependencies installed" -ForegroundColor Green

Write-Host "[...] Installing Playwright Chromium..." -ForegroundColor Yellow
playwright install chromium
Write-Host "[OK] Playwright Chromium installed" -ForegroundColor Green

# --- Verify .env ---
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}
$envContent = Get-Content ".env" -Raw
if ($envContent -match "ROUTER_PASS=\s*$" -or $envContent -notmatch "ROUTER_PASS") {
    Write-Host "[WARN] .env has empty ROUTER_PASS. Updating with default..." -ForegroundColor Yellow
    Set-Content ".env" "ROUTER_USER=admin`nROUTER_PASS=Password@1`n"
}
Write-Host "[OK] .env configured" -ForegroundColor Green

# --- Verify connectivity ---
Write-Host ""
Write-Host "--- Connectivity Checks ---" -ForegroundColor Cyan

Write-Host "[...] Pinging router 192.168.1.1..."
$pingRouter = Test-Connection -ComputerName 192.168.1.1 -Count 2 -Quiet
if ($pingRouter) {
    Write-Host "[OK] Router 192.168.1.1 reachable" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Router 192.168.1.1 NOT reachable. Check Ethernet connection." -ForegroundColor Red
}

Write-Host "[...] Pinging worker 192.168.22.203..."
$pingWorker = Test-Connection -ComputerName 192.168.22.203 -Count 2 -Quiet
if ($pingWorker) {
    Write-Host "[OK] Worker 192.168.22.203 reachable" -ForegroundColor Green
} else {
    Write-Host "[WARN] Worker 192.168.22.203 NOT reachable" -ForegroundColor Yellow
}

Write-Host "[...] Checking worker API http://192.168.22.203:8080/wifi/status..."
try {
    $resp = Invoke-RestMethod -Uri "http://192.168.22.203:8080/wifi/status" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "[OK] Worker API responding" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Worker API not responding. Start worker on 192.168.22.203 first." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup complete!                       " -ForegroundColor Cyan
Write-Host "                                        " -ForegroundColor Cyan
Write-Host "  Next steps:                           " -ForegroundColor Cyan
Write-Host "  1. Ensure worker is running on .203   " -ForegroundColor Cyan
Write-Host "  2. Run smoke test:                    " -ForegroundColor Cyan
Write-Host "     python scripts/check_ssid.py       " -ForegroundColor Cyan
Write-Host "  3. Run E2E test (5G):                 " -ForegroundColor Cyan
Write-Host "     python scripts/run_e2e_lab.py ``    " -ForegroundColor Cyan
Write-Host "       --workflow workflows/test_2pc.yaml ``" -ForegroundColor Cyan
Write-Host "       --connect-band 5G ``              " -ForegroundColor Cyan
Write-Host "       --scan-ssid RFLabTest_5G         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
