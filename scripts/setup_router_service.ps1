#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Setup and start the router-control service on 22.100.

.DESCRIPTION
    Layer 4: Installs dependencies, Playwright Chromium, opens firewall
    for port 8081, and starts the FastAPI router-control service.

    This service runs Playwright locally to control the router at
    192.168.1.1 and exposes an HTTP API on the 22.x management network.
    The orchestrator calls this service instead of running Playwright itself.

.PARAMETER Port
    Port to listen on.  Default: 8081.
#>
param(
    [int]$Port = 8081,
    [string]$Host_ = "0.0.0.0"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Router Control Service Setup (Layer 4)" -ForegroundColor Cyan
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
    Write-Host "[ERROR] Python 3.10+ not found." -ForegroundColor Red
    exit 1
}

# --- Venv ---
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[...] Creating virtual environment..." -ForegroundColor Yellow
    & $py -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
Write-Host "[OK] Virtual environment ready" -ForegroundColor Green

# --- Dependencies ---
Write-Host "[...] Installing dependencies..." -ForegroundColor Yellow
pip install -q -r requirements.txt
Write-Host "[OK] Dependencies installed" -ForegroundColor Green

Write-Host "[...] Installing Playwright Chromium..." -ForegroundColor Yellow
playwright install chromium
Write-Host "[OK] Playwright Chromium installed" -ForegroundColor Green

# --- .env ---
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}
$envContent = Get-Content ".env" -Raw
if ($envContent -match "ROUTER_PASS=\s*$" -or $envContent -notmatch "ROUTER_PASS") {
    Write-Host "[WARN] .env has empty ROUTER_PASS. Please configure it." -ForegroundColor Yellow
}
Write-Host "[OK] .env present" -ForegroundColor Green

# --- Firewall ---
$ruleName = "RASAgent-RouterService-$Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "[...] Adding firewall rule for port $Port..." -ForegroundColor Yellow
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP `
        -LocalPort $Port -Action Allow | Out-Null
    Write-Host "[OK] Firewall rule added" -ForegroundColor Green
} else {
    Write-Host "[OK] Firewall rule already exists" -ForegroundColor Green
}

# --- Connectivity check ---
Write-Host ""
Write-Host "--- Pre-flight checks ---" -ForegroundColor Cyan
$routerPing = Test-Connection -ComputerName 192.168.1.1 -Count 1 -Quiet -ErrorAction SilentlyContinue
if ($routerPing) {
    Write-Host "[OK] Router 192.168.1.1 reachable" -ForegroundColor Green
} else {
    Write-Host "[WARN] Router 192.168.1.1 NOT reachable" -ForegroundColor Yellow
}

# --- Start service ---
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting Router Control Service       " -ForegroundColor Cyan
Write-Host "  http://${Host_}:${Port}               " -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop                  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
uvicorn router_service.app:app --host $Host_ --port $Port
