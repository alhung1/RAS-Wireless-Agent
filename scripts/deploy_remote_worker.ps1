<#
.SYNOPSIS
    Paste this ENTIRE script into an ADMIN PowerShell on worker 192.168.22.203.
    It downloads the project, installs deps, opens firewall, and starts the worker.
#>
$ErrorActionPreference = "Stop"
$installDir = "C:\RASAgent"
$sourceUrl = "http://192.168.22.8:9999/RASAgent_deploy.zip"
$zipPath = "$env:TEMP\RASAgent_deploy.zip"

Write-Host "=== Worker Deploy (192.168.22.203) ===" -ForegroundColor Cyan

# Download
Write-Host "[1/6] Downloading project..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $sourceUrl -OutFile $zipPath -UseBasicParsing

# Extract
Write-Host "[2/6] Extracting to $installDir..."
if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force }
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
Expand-Archive -Path $zipPath -DestinationPath $installDir -Force
Remove-Item $zipPath -Force

# Python check
Write-Host "[3/6] Checking Python..."
$py = $null
foreach ($cmd in @("python", "py")) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match "(\d+)\.(\d+)" -and [int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 10) {
            $py = $cmd; Write-Host "  Found: $v"; break
        }
    } catch {}
}
if (-not $py) { Write-Host "[ERROR] Python 3.10+ required!" -ForegroundColor Red; exit 1 }

# Venv + deps
Write-Host "[4/6] Creating venv and installing dependencies..."
Set-Location $installDir
if (-not (Test-Path ".venv")) { & $py -m venv .venv }
. .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt

# Firewall
Write-Host "[5/6] Configuring firewall..."
$rule = Get-NetFirewallRule -DisplayName "RASAgent-Worker-8080" -ErrorAction SilentlyContinue
if (-not $rule) {
    New-NetFirewallRule -DisplayName "RASAgent-Worker-8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow | Out-Null
    Write-Host "  Firewall rule added for port 8080"
}

# Start
Write-Host "[6/6] Starting worker..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Worker running on 0.0.0.0:8080       " -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop                  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
uvicorn worker.app:app --host 0.0.0.0 --port 8080
