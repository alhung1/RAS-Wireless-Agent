#Requires -RunAsAdministrator
<#
.SYNOPSIS
    One-click setup for the Worker machine (192.168.22.203).
    Run this script as Administrator on the worker PC.
.DESCRIPTION
    1. Checks Python 3.10+
    2. Creates venv and installs dependencies
    3. Opens firewall for port 8080
    4. Starts the FastAPI worker service
#>
param(
    [int]$Port = 8080,
    [string]$Host_ = "0.0.0.0"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Worker Setup (Wi-Fi Worker Agent)     " -ForegroundColor Cyan
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

# --- Firewall rule ---
$ruleName = "WiFi-Worker-Agent-$Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "[...] Adding firewall rule for port $Port..." -ForegroundColor Yellow
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow | Out-Null
    Write-Host "[OK] Firewall rule added" -ForegroundColor Green
} else {
    Write-Host "[OK] Firewall rule already exists" -ForegroundColor Green
}

# --- Start worker ---
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting Worker on ${Host_}:${Port}   " -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop                  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
uvicorn worker.app:app --host $Host_ --port $Port
