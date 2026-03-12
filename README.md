# RAS Wireless Agent

Automate Wi-Fi SSID, password, channel, and security changes on a **Netgear RS700**
tri-band router (2.4 GHz / 5 GHz / 6 GHz) and verify connectivity from remote
Windows worker PCs.  The orchestrator machine never touches the router subnet
directly -- all router operations are proxied through a FastAPI service running
on a relay PC (22.100) that has wired LAN access to the router.

---

## Architecture

```
Orchestrator PC                    22.100 PC                       Router (192.168.1.1)
  (local machine)                    router_service :8081             Netgear RS700
  NIC-1 (200-domain, internet)       22-domain NIC (mgmt)            LAN: 192.168.1.x
  NIC-2 (22-domain, control) ------> Router NIC (192.168.1.50)       Wi-Fi: 2.4G / 5G / 6G
                                      worker service  :8080
```

**Data flow:**

```
                    HTTP (22-domain)                  Playwright (LAN)
  Orchestrator  ──────────────────>  router_service  ──────────────>  Router GUI
  (scripts/)         POST /router/apply              (Chromium headless)
                     GET  /router/status             WLG_wireless_tri_band.htm
```

### 5-Layer Network Safety

1. **Layer 1:** `wifi_connect_local` is disabled on the orchestrator (CI guard enforced)
2. **Layer 2:** 22.100 router NIC uses static IP with no default gateway
3. **Layer 3:** Interface metrics are pinned (no Windows auto-metric)
4. **Layer 4:** Router control runs as an HTTP service on 22.100
5. **Layer 5:** 3-stage health check before/after every dangerous operation

---

## A. Network Requirements (Strict)

### Orchestrator Machine

- **NIC-1 (Internet / 200-domain):** Default gateway, metric 10
- **NIC-2 (22-domain control):** IP in 192.168.22.0/24, metric 20, **no route to 192.168.1.0/24**

**Critical rule:** The orchestrator must NOT have any route to `192.168.1.0/24`.
All 192.168.1.x traffic must go through the router-control service HTTP API.

### Worker Machine (22.100)

- **22-domain NIC:** IP in 192.168.22.0/24, metric 10 (management traffic)
- **Router NIC:** Static IP `192.168.1.50`, mask `255.255.255.0`, **no default gateway**, metric 100

### Prechecks

```powershell
# Orchestrator: verify no route to router subnet
route print | Select-String "192.168.1"
# Expected: EMPTY (no entries)

# Orchestrator: verify 22-domain metrics
Get-NetIPInterface -AddressFamily IPv4 | Sort InterfaceMetric |
  Format-Table InterfaceAlias, InterfaceMetric, AutomaticMetric

# Orchestrator: verify control path to worker
Test-NetConnection 192.168.22.100 -Port 8081
# Expected: TcpTestSucceeded = True

# Worker (22.100): verify router reachable
Test-NetConnection 192.168.1.1 -Port 80
# Expected: TcpTestSucceeded = True

# Worker (22.100): verify metrics
Get-NetIPInterface -AddressFamily IPv4 | Sort InterfaceMetric |
  Format-Table InterfaceAlias, InterfaceMetric, AutomaticMetric
```

---

## B. System Health Checklist

Quick verification commands and expected outputs:

```powershell
# 1. Service health
Invoke-RestMethod http://192.168.22.100:8081/health
# Expected: {"status":"ok","router_reachable":true}

# 2. TCP connectivity
Test-NetConnection 192.168.22.100 -Port 8081
# Expected: TcpTestSucceeded = True

# 3. Router status (all 3 bands)
Invoke-RestMethod http://192.168.22.100:8081/router/status
# Expected: {"success":true,"bands":{"2.4G":{...},"5G":{...},"6G":{...}}}

# 4. Service version
Invoke-RestMethod http://192.168.22.100:8081/admin/version
# Expected: {"version":"1.1.0","commit":"abc1234","python":"3.14.0","service_mode":"lab","bind_ip":"..."}

# 5. Route sanity (orchestrator)
route print | Select-String "192.168.1"
# Expected: EMPTY

# 6. Metric sanity (worker)
Get-NetIPInterface -AddressFamily IPv4 |
  Where-Object { $_.ConnectionState -eq "Connected" } |
  Sort InterfaceMetric |
  Format-Table InterfaceAlias, InterfaceIndex, InterfaceMetric, AutomaticMetric
# Expected: all AutomaticMetric = Disabled, 22-domain < router NIC
```

---

## C. Security Model

### Credentials

- All secrets are stored in `.env` (never committed, listed in `.gitignore`)
- `.env.example` provides placeholder keys
- Required variables: `ROUTER_USER`, `ROUTER_PASS`, `SERVICE_BIND_IP`, `SERVICE_MODE`

### Binding Restrictions

The service bind IP is enforced at two levels:

1. **Primary (uvicorn CLI):** The scheduled task starts uvicorn with `--host %SERVICE_BIND_IP%`.
   Configured in `scripts/bootstrap_22100.ps1` and `scripts/setup_22100_autostart.ps1`.
2. **Secondary (FastAPI startup):** `router_service/app.py` validates `SERVICE_BIND_IP` on startup.
   In `production` mode, `0.0.0.0` is rejected. In `lab` mode (default), a warning is logged.

To change the bind IP: update `SERVICE_BIND_IP` in `C:\RASAgent\.env` and re-register the scheduled task
via `scripts/setup_22100_autostart.ps1`.

### WinRM / TrustedHosts

WinRM is NOT used for day-to-day operations. All communication is HTTP via `/admin/update`.
If WinRM is needed for debugging:

```powershell
# On orchestrator (restrict scope)
Set-Item WSMan:\localhost\Client\TrustedHosts -Value "192.168.22.100"
```

### Recommended Firewall Rules (Lab)

```powershell
# On worker: restrict WinRM to 22-domain only
New-NetFirewallRule -DisplayName "WINRM-HTTP-In-TCP-22" `
    -Direction Inbound -Protocol TCP -LocalPort 5985 `
    -RemoteAddress 192.168.22.0/24 -Action Allow

# On worker: restrict router-service to 22-domain only
New-NetFirewallRule -DisplayName "RASAgent-Router-Service" `
    -Direction Inbound -Protocol TCP -LocalPort 8081 `
    -RemoteAddress 192.168.22.0/24 -Action Allow
```

### Service Account

The scheduled task runs as `SYSTEM`. For production, consider creating a dedicated
low-privilege service account with access only to `C:\RASAgent` and the router NIC.

---

## D. Deploying to Additional Workers

### What Is Per-Worker

- `C:\RASAgent\.env` -- router credentials and `SERVICE_BIND_IP`
- NIC configuration (static IP, gateway, metrics)
- Scheduled task registration

### What Is Shared

- The deploy zip (`RASAgent_deploy.zip`) is identical for all workers
- `offline_packages/` wheels are architecture-specific (all workers must match OS/arch)

### Steps for a New Worker

1. **On the orchestrator**, build the zip and start file server:

```powershell
python scripts/deploy_and_restart.py --zip-only
python -m http.server 9999 --bind 0.0.0.0
```

2. **On the new worker** (elevated PowerShell):

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
iwr http://192.168.22.8:9999/scripts/bootstrap_22100.ps1 -OutFile $env:TEMP\bootstrap.ps1
& $env:TEMP\bootstrap.ps1 -SourceBase http://192.168.22.8:9999 -ServiceBindIP 192.168.22.XXX
```

3. **Configure NIC** (if not already done):

```powershell
# Set static IP on router-facing NIC (identify by MAC or alias)
.\scripts\pin_metrics_22100.ps1 -ControlNicMAC "AA-BB-CC-DD-EE-FF" -RouterNicMAC "11-22-33-44-55-66"
```

4. **In workflows**, set `router_control_url` per worker:

```yaml
router:
  router_control_url: "http://192.168.22.XXX:8081"
```

---

## E. Verification Depth / Validation Test

### E2E Wireless Verification

```powershell
python scripts/test_e2e_wireless.py --remote-host 192.168.22.100
# With Wi-Fi scan verification:
python scripts/test_e2e_wireless.py --remote-host 192.168.22.100 --worker-host 192.168.22.100 --worker-port 8080
```

**Steps performed:**

1. **Health check** -- verify `/health` returns OK
2. **Baseline snapshot** -- `GET /router/status` captures current SSID/password/channel for all bands
3. **Apply test config** -- `POST /router/apply` with distinct SSIDs per band
4. **Verify via /router/status** -- poll until config readback matches (primary verification)
5. **Wi-Fi scan verification** -- `GET /wifi/scan` on worker checks SSID broadcast presence (required)
   and channel match (best-effort, especially for 6 GHz)
6. **Restore baseline** -- `POST /router/apply` with saved baseline values
7. **Verify restoration** -- confirm SSIDs match original

**Pass/fail criteria:**

- Router reported config (`/router/status`) MUST match applied values for all bands
- Wi-Fi scan MUST find all expected SSIDs broadcasting
- Channel match in scan is best-effort (warn only) -- 6 GHz channels may not be visible
- Baseline MUST be fully restored after test

**Output:** `artifacts/e2e_wireless_test_report.json`

### Test Workflow YAML Example

```yaml
name: "validation_test"
router:
  base_url: "http://192.168.1.1"
  router_control_url: "http://192.168.22.100:8081"
  bands:
    2.4G:
      ssid: "RFLab2g_VERIFY"
      password: "TestPass24!"
      channel: "6"
      security: "wpa2"
    5G:
      ssid: "RFLab5g_VERIFY"
      password: "TestPass5g!"
      channel: "36"
      security: "wpa2"
    6G:
      ssid: "RFLab6g_VERIFY"
      password: "TestPass6g!"
      channel: "37"
      security: "wpa3"
```

---

## F. Safe Upgrade Procedure

See [docs/Safe_Upgrade_and_Deploy.md](docs/Safe_Upgrade_and_Deploy.md) for full copy-paste runbook.

**Summary:**

```powershell
# 1. Stop service
Stop-ScheduledTask -TaskName "RASAgent-RouterService"

# 2. Wait for processes to exit
$timeout = 30; $elapsed = 0
do {
    $procs = Get-Process python* -ErrorAction SilentlyContinue |
             Where-Object { $_.Path -like "C:\RASAgent\*" }
    if (-not $procs) { break }
    Start-Sleep 3; $elapsed += 3
} while ($elapsed -lt $timeout)

# 3. Force-kill only if needed (only C:\RASAgent processes)
Get-Process python* -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "C:\RASAgent\*" } | Stop-Process -Force

# 4. Backup -> Remove -> Deploy -> Restore
# (see deploy_22100_routerservice.ps1 for automated version)

# 5. Start and verify
Start-ScheduledTask -TaskName "RASAgent-RouterService"
Invoke-RestMethod http://localhost:8081/health
```

Or use the automated deploy script:

```powershell
# From orchestrator (handles everything):
python scripts/deploy_and_restart.py
```

---

## G. Binding and UID

### Where Bind IP Is Configured

- **`.env` on worker:** `SERVICE_BIND_IP=192.168.22.100` (or `0.0.0.0` for lab)
- **Scheduled task command:** `--host %SERVICE_BIND_IP%` passed to uvicorn
- **FastAPI startup validation:** `router_service/app.py` checks bind IP on boot

### Changing Bind IP

```powershell
# 1. Update .env
Set-Content C:\RASAgent\.env -Value @(
    "ROUTER_USER=admin",
    "ROUTER_PASS=Password@1",
    "SERVICE_BIND_IP=192.168.22.100",
    "SERVICE_MODE=lab"
)

# 2. Re-register scheduled task (reads SERVICE_BIND_IP from .env)
.\scripts\setup_22100_autostart.ps1
```

---

## H. Versioning and Admin Endpoint

### VERSION File

The repo root contains a `VERSION` file (e.g., `1.1.0`).

### Build Info

`scripts/deploy_and_restart.py` generates `build_info.json` during zip build:

```json
{
  "version": "1.1.0",
  "commit": "abc1234",
  "tag": "v1.1.0",
  "build_time": "2026-03-11T12:00:00+00:00"
}
```

### GET /admin/version

```powershell
Invoke-RestMethod http://192.168.22.100:8081/admin/version
```

Returns:

```json
{
  "version": "1.1.0",
  "commit": "abc1234",
  "build_time": "2026-03-11T12:00:00+00:00",
  "python": "3.14.0",
  "service_mode": "lab",
  "bind_ip": "0.0.0.0"
}
```

---

## I. File Locations

### Core Service Files

- `router_service/app.py` -- FastAPI service (runs on worker)
- `router/netgear_rs700/driver.py` -- Playwright automation for RS700
- `router/netgear_rs700/selectors.py` -- HTML form field mappings per band
- `orchestrator/utils/health.py` -- 3-stage health check (control path, router, WAN)
- `orchestrator/actions/e2e_steps.py` -- E2E workflow steps with baseline + rollback
- `orchestrator/actions/router_netgear.py` -- Orchestrator-side router API client
- `worker/app.py` -- Worker FastAPI service (Wi-Fi scan, connect, ping)

### Scripts

- `scripts/bootstrap_22100.ps1` -- One-command bootstrap for new workers
- `scripts/deploy_22100_routerservice.ps1` -- Safe deploy with two-phase stop + backup/restore
- `scripts/deploy_and_restart.py` -- Orchestrator-side zero-touch deploy
- `scripts/setup_22100_autostart.ps1` -- Register/update scheduled task
- `scripts/setup_22100_network.ps1` -- Configure static IP on router NIC
- `scripts/pin_metrics_22100.ps1` -- Pin interface metrics on worker (supports MAC/ifIndex)
- `scripts/pin_metrics_orchestrator.ps1` -- Pin interface metrics on orchestrator
- `scripts/test_e2e_wireless.py` -- E2E wireless verification test
- `scripts/ci_guard_no_local_wifi.py` -- CI guard against local Wi-Fi commands

### Configuration

- `.env.example` -- Template for environment variables
- `VERSION` -- Repo version string
- `build_info.json` -- Generated during deploy (version, commit, timestamp)
- `workflows/*.yaml` -- Workflow definitions

### Tests

- `tests/test_ci_guard.py` -- CI guard unit tests
- `tests/test_health_gate.py` -- Health gating and rollback unit tests

### Documentation

- `docs/Safe_Upgrade_and_Deploy.md` -- Safe upgrade runbook

### Artifacts (Runtime, Never Committed)

- `artifacts/e2e_wireless_test_report.json` -- Wireless E2E results
- `artifacts/final_report.json` -- E2E workflow summary
- `artifacts/sweep_summary.json` -- Channel sweep results
- `artifacts/screenshot_*.png` -- Browser screenshots on failure
- `artifacts/page_*.html` -- HTML dump on failure
- `artifacts/trace*.zip` -- Playwright trace
- `artifacts/network.har` -- Network traffic log

---

## Directory Structure

```
orchestrator/           Workflow engine, actions, coordination
router/                 Playwright-based router UI automation
  netgear_rs700/        RS700-specific driver, selectors, evidence
  netgear_nighthawk/    Legacy Nighthawk driver (reference)
router_service/         FastAPI service deployed on 22.100
worker/                 FastAPI service on each remote Windows PC
scripts/                Entry-point scripts, deploy tools, tests
workflows/              YAML workflow definitions
tests/                  Unit tests
docs/                   Runbooks and documentation
artifacts/              Runtime output -- never committed
```

---

## Prerequisites

- **Orchestrator PC:** Python 3.10+, pip, wired connection to 22-domain network
- **22.100 PC:** Python 3.10+ (tested with 3.13/3.14), wired Ethernet to both 22-domain and router LAN
- **Router:** Netgear RS700, accessible at `192.168.1.1`, HTTP Basic Auth

> The 22.100 machine does **not** need internet access.  All dependencies are
> deployed offline from the orchestrator.

---

## Configuration

```powershell
Copy-Item .env.example .env
# Edit .env:
#   ROUTER_USER=admin
#   ROUTER_PASS=<your router password>
#   SERVICE_BIND_IP=192.168.22.100   # or 0.0.0.0 for lab
#   SERVICE_MODE=lab                  # or production
```

> **Never commit `.env`.** It is listed in `.gitignore`.

---

## Deployment

### First-Time Setup (New Machine)

#### Step 1 -- Orchestrator: Build and Serve

```powershell
cd "c:\Projects\RAS Wireless Agent"
.\.venv\Scripts\Activate.ps1
python scripts/deploy_and_restart.py --zip-only
python -m http.server 9999 --bind 0.0.0.0
```

#### Step 2 -- Target Machine: One-Line Bootstrap

Open an **elevated PowerShell** on the target machine:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
iwr http://192.168.22.8:9999/scripts/bootstrap_22100.ps1 -OutFile $env:TEMP\bootstrap.ps1
& $env:TEMP\bootstrap.ps1 -SourceBase http://192.168.22.8:9999 -ServiceBindIP 192.168.22.100
```

The bootstrap handles: download, extract, venv, offline pip, Playwright browsers,
.env creation, scheduled task registration, health verification.

#### Step 3 -- Verify

```powershell
Invoke-RestMethod http://192.168.22.100:8081/health
Invoke-RestMethod http://192.168.22.100:8081/admin/version
```

### Subsequent Deploys (Zero-Touch)

```powershell
python scripts/deploy_and_restart.py
```

Options: `--no-restart`, `--zip-only`, `--remote-host IP`, `--remote-port N`, `--serve-port N`

---

## Router Service API

The router service runs on 22.100 at port 8081.

### Core Endpoints

- **GET `/health`** -- Liveness check + router reachability
- **GET `/router/status`** -- Read SSID, channel, passphrase, security for all bands
- **POST `/router/apply`** -- Configure SSID/channel/password/security for any combination of bands
- **POST `/router/detect-bands`** -- Detect available bands

### Admin Endpoints

- **POST `/admin/update`** -- Download new code zip, swap files, restart service
- **POST `/admin/restart`** -- Restart the service via scheduled task
- **POST `/admin/fix-playwright`** -- Copy Playwright browsers to SYSTEM-accessible path
- **GET `/admin/version`** -- Build version, commit, runtime info

### POST /router/apply

```json
{
  "bands": {
    "2.4G": {"ssid": "MyNet_2G", "password": "secret123", "channel": "6", "security": "wpa2"},
    "5G":   {"ssid": "MyNet_5G", "password": "secret456", "channel": "36", "security": "wpa2"},
    "6G":   {"ssid": "MyNet_6G", "password": "secret789", "security": "wpa3"}
  }
}
```

**Supported `security` values:**

- 2.4G/5G: `disable`, `wpa2`, `auto`, `wpa3`, `wpa3-mixed`, `owe`
- 6G: `wpa3`, `owe`

---

## Router Field Mappings (Netgear RS700)

The RS700 uses a single tri-band page at `/WLG_wireless_tri_band.htm`:

- 2.4G: `ssid`, `passphrase`, `w_channel`, `security_type`, `opmode`
- 5G: `ssid_an`, `passphrase_an`, `w_channel_an`, `security_type_an`, `opmode_an`
- 6G: `ssid_an_2`, `passphrase_an_2`, `w_channel_an_2`, `security_type_an_2`, `opmode_an_2`

> The per-band ADVANCED pages show unified "Smart Connect" settings.
> The 6G page (`WLG_wireless4.htm`) returns 404.  Always use the tri-band BASIC page.

---

## Known Issues and Solutions

### 1. Netgear SSO Modal Blocks Playwright Clicks

**Cause:** RS700 firmware displays "Install Nighthawk App" modal overlay.
**Solution:** Driver dismisses it via JavaScript injection after every navigation + `force=True` on Apply.

### 2. Playwright Browsers Not Found Under SYSTEM Account

**Cause:** SYSTEM cannot access user-profile `ms-playwright`.
**Solution:** `PLAYWRIGHT_BROWSERS_PATH` set to `C:\RASAgent\.playwright`.

### 3. Scheduled Task Kills Child Processes (Job Object)

**Cause:** Windows Job Objects terminate all children on task end.
**Solution:** `CREATE_BREAKAWAY_FROM_JOB` flag + `os._exit(1)` fallback.

### 4. Blank-Password Admin Blocks WinRM

**Cause:** Local admin has no password.
**Solution:** Bootstrap runs locally (one-time); subsequent deploys use HTTP `/admin/update`.

### 5. Directory Lock During Redeploy

**Cause:** Python process holds file lock.
**Solution:** `deploy_22100_routerservice.ps1` uses two-phase stop (graceful + optional force-kill)
and backup/restore of `.env`, `.playwright`, `.venv`.

### 6. 6 GHz Channel Not Visible in Wi-Fi Scan

**Cause:** 6 GHz requires Wi-Fi 6E hardware; scan results may not show 6 GHz networks.
**Solution:** Channel matching is best-effort (warn only).  SSID presence is the primary check.
Regional regulatory constraints may further limit 6 GHz channel availability.

---

## Install (Development)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Playwright is NOT needed on the orchestrator -- it runs on 22.100.

### Network Setup (Run Once, As Admin)

```powershell
# On 22.100
.\scripts\setup_22100_network.ps1
.\scripts\pin_metrics_22100.ps1

# On Orchestrator
.\scripts\pin_metrics_orchestrator.ps1
```

---

## Running Tests

```powershell
# Unit tests
python -m pytest tests/ -v

# CI guard (no local Wi-Fi in orchestrator code)
python scripts/ci_guard_no_local_wifi.py

# E2E wireless test
python scripts/test_e2e_wireless.py --remote-host 192.168.22.100
```

---

## Limitations

- **Wired LAN required:** 22.100 must have wired Ethernet to the router.
- **Admin privileges:** `netsh wlan` commands require elevated access.
- **Router firmware:** Selectors target Netgear RS700 firmware. Other models need new selectors.
- **Single router:** Targets one Netgear RS700 at a fixed IP.
- **First bootstrap is manual:** Must be run locally on the target machine (blank-password WinRM restriction).
- **6 GHz scan limitations:** Wi-Fi 6E hardware required; channel visibility varies by region and adapter.
