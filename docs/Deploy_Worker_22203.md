# Deploy Worker Service on 22.203 (Intel BE200)

Shortest path to get the worker service running on 192.168.22.203.

---

## Prerequisites

- Windows 10/11 with Python 3.10+
- Intel BE200 Wi-Fi adapter installed
- 22-domain NIC configured with IP 192.168.22.203/24
- Elevated PowerShell

## Step 1: Copy Project Files

From the **orchestrator**, build the zip and serve it:

```powershell
cd "c:\Projects\RAS Wireless Agent"
.\.venv\Scripts\python.exe scripts/deploy_and_restart.py --zip-only
python -m http.server 9999 --bind 0.0.0.0
```

On **22.203** (elevated PowerShell):

```powershell
$installDir = "C:\RASAgent"
$source = "http://192.168.22.8:9999"

# Download and extract
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri "$source/RASAgent_deploy.zip" -OutFile "$env:TEMP\deploy.zip" -UseBasicParsing
if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force }
New-Item -ItemType Directory $installDir | Out-Null
Expand-Archive "$env:TEMP\deploy.zip" -DestinationPath $installDir -Force
Remove-Item "$env:TEMP\deploy.zip"

# Flatten if nested
$nested = Get-ChildItem $installDir -Directory
if ($nested.Count -eq 1 -and (Test-Path "$installDir\$($nested.Name)\requirements.txt")) {
    Get-ChildItem "$installDir\$($nested.Name)" | Move-Item -Destination $installDir -Force
    Remove-Item "$installDir\$($nested.Name)" -Force -ErrorAction SilentlyContinue
}
```

## Step 2: Python + Dependencies

```powershell
cd $installDir

# Create venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install deps (offline or online)
if (Test-Path offline_packages) {
    pip install --no-index --find-links offline_packages -r requirements.txt -q
} else {
    pip install -r requirements.txt -q
}
```

## Step 3: Firewall Rule

```powershell
New-NetFirewallRule -DisplayName "RASAgent-Worker-8080" `
    -Direction Inbound -Protocol TCP -LocalPort 8080 `
    -RemoteAddress 192.168.22.0/24 -Action Allow
```

## Step 4: Start Worker Service

```powershell
cd C:\RASAgent
.\.venv\Scripts\Activate.ps1
uvicorn worker.app:app --host 192.168.22.203 --port 8080
```

## Step 5: Verify

From orchestrator (or any 22-domain machine):

```powershell
Invoke-RestMethod http://192.168.22.203:8080/health
# Expected: {"status":"ok","service":"worker"}

Invoke-RestMethod http://192.168.22.203:8080/wifi/status
# Should list Intel BE200 interface
```

## Optional: Register as Scheduled Task (Auto-Start)

```powershell
$taskName = "RASAgent-Worker"
$installDir = "C:\RASAgent"
$bindIP = "192.168.22.203"

$action = New-ScheduledTaskAction `
    -Execute "$installDir\.venv\Scripts\python.exe" `
    -Argument "-m uvicorn worker.app:app --host $bindIP --port 8080" `
    -WorkingDirectory $installDir

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
    -Description "RAS Wireless Agent - Worker Service (port 8080)"

Start-ScheduledTask -TaskName $taskName
Start-Sleep 5
Invoke-RestMethod http://${bindIP}:8080/health
```

## Running the E2E Test

From the orchestrator:

```powershell
python scripts/test_e2e_be200_2g.py --router-host 192.168.22.100 --worker-host 192.168.22.203
```
