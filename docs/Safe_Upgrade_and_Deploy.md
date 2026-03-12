# Safe Upgrade and Deploy Runbook

Copy-paste-ready commands for upgrading the Router Control Service on a worker machine (e.g. 22.100).

---

## Pre-Flight

```powershell
# Verify control path from orchestrator
Test-NetConnection 192.168.22.100 -Port 8081

# Check current version
Invoke-RestMethod http://192.168.22.100:8081/admin/version

# Capture current router config as backup reference
Invoke-RestMethod http://192.168.22.100:8081/router/status | ConvertTo-Json -Depth 5 > baseline_backup.json
```

## Option A: Automated Deploy (Recommended)

From the **orchestrator** machine:

```powershell
cd "c:\Projects\RAS Wireless Agent"
python scripts/deploy_and_restart.py --remote-host 192.168.22.100
```

This builds the zip (including `build_info.json`), pushes it to the worker, and verifies `/health`.

## Option B: Manual Deploy on Worker

Run these commands **on the worker machine** (22.100):

### 1. Stop the Service

```powershell
Stop-ScheduledTask -TaskName "RASAgent-RouterService"
```

### 2. Wait for Processes to Exit

```powershell
# Poll until processes are gone (up to 30 seconds)
$timeout = 30; $elapsed = 0
do {
    $procs = Get-Process -Name python* -ErrorAction SilentlyContinue |
             Where-Object { $_.Path -like "C:\RASAgent\*" }
    if (-not $procs) { Write-Host "All processes exited."; break }
    Write-Host "Waiting... ($elapsed/$timeout)"
    Start-Sleep -Seconds 3; $elapsed += 3
} while ($elapsed -lt $timeout)

# If still running after timeout, force-kill (only if safe)
Get-Process -Name python* -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "C:\RASAgent\*" } |
    Stop-Process -Force
```

### 3. Backup Runtime State

```powershell
$bak = "$env:TEMP\RASAgent_bak"
if (Test-Path $bak) { Remove-Item $bak -Recurse -Force }
New-Item -ItemType Directory $bak | Out-Null
Copy-Item C:\RASAgent\.env $bak\.env -Force
Copy-Item C:\RASAgent\.playwright $bak\.playwright -Recurse -Force
Copy-Item C:\RASAgent\.venv $bak\.venv -Recurse -Force
```

### 4. Remove and Deploy

```powershell
Set-Location $env:SystemRoot
Remove-Item C:\RASAgent -Recurse -Force
New-Item -ItemType Directory C:\RASAgent | Out-Null
Expand-Archive -Path "$env:TEMP\RASAgent_deploy.zip" -DestinationPath C:\RASAgent -Force
```

### 5. Restore Runtime State

```powershell
Copy-Item $bak\.env C:\RASAgent\.env -Force
Copy-Item $bak\.playwright C:\RASAgent\.playwright -Recurse -Force
Copy-Item $bak\.venv C:\RASAgent\.venv -Recurse -Force
Remove-Item $bak -Recurse -Force
```

### 6. Start and Verify

```powershell
Start-ScheduledTask -TaskName "RASAgent-RouterService"
Start-Sleep -Seconds 5
Invoke-RestMethod http://localhost:8081/health
Invoke-RestMethod http://localhost:8081/admin/version
```

## Option C: Full Bootstrap (New Worker)

On the **orchestrator**, start the file server and build zip:

```powershell
python scripts/deploy_and_restart.py --zip-only
cd "c:\Projects\RAS Wireless Agent"
python -m http.server 9999
```

On the **new worker**, run:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
iwr http://192.168.22.8:9999/scripts/bootstrap_22100.ps1 -OutFile $env:TEMP\bootstrap.ps1
& $env:TEMP\bootstrap.ps1 -ServiceBindIP 192.168.22.XXX
```

## Rollback

If the upgrade fails, restore from the backup:

```powershell
Stop-ScheduledTask -TaskName "RASAgent-RouterService" -ErrorAction SilentlyContinue
Get-Process python* -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "C:\RASAgent\*" } | Stop-Process -Force

Set-Location $env:SystemRoot
Remove-Item C:\RASAgent -Recurse -Force
# Restore from your pre-upgrade backup
Copy-Item $env:TEMP\RASAgent_bak C:\RASAgent -Recurse -Force
Start-ScheduledTask -TaskName "RASAgent-RouterService"
Invoke-RestMethod http://localhost:8081/health
```

## Post-Upgrade Validation

```powershell
# From orchestrator
python scripts/test_e2e_wireless.py --remote-host 192.168.22.100

# Verify version
Invoke-RestMethod http://192.168.22.100:8081/admin/version
```
