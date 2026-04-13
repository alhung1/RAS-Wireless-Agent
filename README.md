# RAS Wireless Agent

Automate end-to-end Wi-Fi throughput testing on a **Netgear RS700** tri-band router
(2.4 GHz / 5 GHz / 6 GHz) across three coordinated machines:

1. **Router GUI control** (22.100) -- Playwright-based SSID/channel/security configuration
2. **LabVIEW automation** (22.8) -- PyAutoGUI-driven 19-step (0–18) throughput wizard
3. **WiFi client control** (22.203) -- `netsh wlan` based Intel BE200 connection management

---

## Documentation (LabVIEW automation & milestone)

**Start here:** [docs/README.md](docs/README.md)

| Doc | Purpose |
|-----|---------|
| [docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md) | Commands: profiles, matrix, resume, single-step, legacy scripts |
| [docs/LABVIEW_RUNNER.md](docs/LABVIEW_RUNNER.md) | Thin `labview_runner` vs `labview_runner_legacy`, `result.json` / `run.json`, `LV_PRODUCT` |
| [docs/ARCHITECTURE_SUMMARY.md](docs/ARCHITECTURE_SUMMARY.md) | Layers, native vs legacy steps, what is production-ready |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Matrix/finish, dry-run artifacts, `run_single_step` parity |
| [docs/MIGRATION_LEGACY_STEPS.md](docs/MIGRATION_LEGACY_STEPS.md) | Remaining legacy step buckets (bucket 1: `s00` native) |
| [docs/DESIGN_MATRIX_FINISH_ORCHESTRATION.md](docs/DESIGN_MATRIX_FINISH_ORCHESTRATION.md) | Next phase: finish detector + matrix between profiles |
| [docs/RELEASE_NOTES_v1.0.0-labview-refactor.md](docs/RELEASE_NOTES_v1.0.0-labview-refactor.md) | Milestone release notes (v1.0.0-labview-refactor) |
| [docs/RELEASE_PROPOSAL.md](docs/RELEASE_PROPOSAL.md) | Tag rationale + link to release notes |
| [docs/HOW_TO_ADD_PRODUCT.md](docs/HOW_TO_ADD_PRODUCT.md) | New product adapter, YAML, registration |
| [docs/MIGRATION_STATUS.md](docs/MIGRATION_STATUS.md) | Refactor phases, deferred work, CI hooks |
| [docs/Safe_Upgrade_and_Deploy.md](docs/Safe_Upgrade_and_Deploy.md) | Upgrade and deploy procedures |
| [docs/Deploy_Worker_22203.md](docs/Deploy_Worker_22203.md) | Worker (22.203) deployment guide |
| [docs/ACCOMPLISHMENT_ENGINEERING.md](docs/ACCOMPLISHMENT_ENGINEERING.md) | Technical handoff summary |
| [docs/ACCOMPLISHMENT_STAKEHOLDER.md](docs/ACCOMPLISHMENT_STAKEHOLDER.md) | Stakeholder / deck summary |
| [scripts/README_LOCAL.md](scripts/README_LOCAL.md) | Local calibration / diagnostics / `_archive_local` script layout |

---

## Quick Start (2.4G Test)

```powershell
cd "c:\Projects\RAS Wireless Agent"
.\.venv\Scripts\Activate.ps1

# Run the LabVIEW wizard and start a 2.4G throughput test
python scripts/run_24g.py
```

This launches LabVIEW `480.000.v2.03.exe`, walks through the wizard
(login, AP/client selection, band/mode/attenuation config), and starts the test.
The finish detector monitors `D:\480\LOG\RBU\*.pdf` for test completion.

**Profile-driven runs** (YAML + `StepEngine`): see [docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md). From repo root, for example:

```powershell
python scripts/validate_profiles.py --dir profiles/test_matrix/
python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml --dry-run
python scripts/run_matrix.py --dir profiles/test_matrix/ --dry-run
python scripts/smoke_labview_compat.py
```

---

## Architecture

```
 22.8 (Orchestrator)          22.100 (Router Relay)         22.203 (WiFi Worker)
 ┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
 │  Orchestrator     │  HTTP   │  Router Service   │  PW    │  Worker Service   │
 │  LabVIEW Runner   │───────>│  :8081             │──────>│  :8080             │
 │  Finish Detector  │         │  Playwright driver │        │  netsh wlan       │
 └────────┬─────────┘         └────────┬─────────┘         └────────┬─────────┘
          │ PyAutoGUI                  │ Web UI                     │ WiFi
          v                            v                            v
   LabVIEW 480.exe              Netgear RS700              Intel BE200 adapter
                               (192.168.1.1)
```

### Data Flow

```
                    HTTP (22-domain)                  Playwright (LAN)
  Orchestrator  ──────────────────>  router_service  ──────────────>  Router GUI
  (22.8)             POST /router/apply              (22.100)

  Orchestrator  ──────────────────>  worker          ──────────────>  Intel BE200
  (22.8)             POST /wifi/connect              (22.203)        netsh wlan

  Orchestrator  ──── PyAutoGUI ────>  LabVIEW 480.000.v2.03.exe     (local on 22.8)
```

### End-to-End Test Sequence

| Phase | Machine | Action |
|-------|---------|--------|
| 1 | 22.100 | Configure router (SSID, channel, security) via Playwright |
| 2 | 22.8 | Run LabVIEW wizard steps 0-16 |
| 3 | 22.203 | Connect Intel BE200 to test frequency band via `netsh wlan` |
| 4 | 22.8 | Complete LabVIEW wizard steps 17-18, test begins |
| 5 | 22.8 | Monitor for test completion (PDF in `D:\480\LOG\RBU`) |
| 6 | -- | Repeat for next band/channel |

### 5-Layer Network Safety

1. **Layer 1:** `wifi_connect_local` is disabled on the orchestrator (CI guard enforced)
2. **Layer 2:** 22.100 router NIC uses static IP with no default gateway
3. **Layer 3:** Interface metrics are pinned (no Windows auto-metric)
4. **Layer 4:** Router control runs as an HTTP service on 22.100
5. **Layer 5:** 3-stage health check before/after every dangerous operation

---

## LabVIEW Automation (Part 2 -- 22.8)

The LabVIEW stack is **config-driven** (`profiles/*.yaml`) with a **`StepEngine`** (preflight, verification, recovery). **`labview_runner.py`** is a thin facade over the engine; implementations and legacy `step_*` helpers live in **`labview_runner_legacy.py`**. See [docs/README.md](docs/README.md).

The runner drives `480.000.v2.03.exe` through a 19-step (0–18) throughput testing
wizard using PyAutoGUI, Win32 API, and OpenCV HSV color detection.

### 19-Step Wizard Flow (indices 0–18)

| Step | Function | Screen | Action | ~Time |
|------|----------|--------|--------|-------|
| 0 | `step_00_attach` | `480 000.vi` | Find and attach to LabVIEW window | 1s |
| 1 | `step_01_click_throughput` | `480 000.vi` | Click Throughput Testing icon | 10s |
| 2 | `step_02_login` | login popup | Type username/password, click green OK | 10s |
| 3 | `step_03_test_type` | test type screen | Select "1 rpm (fast)", click arrow | 10s |
| 4 | `step_04_table_position` | table screen | Click orange arrow | 12s |
| 5 | `step_05_freq_channel` | freq/channel screen | Set MLO, RF channels, user info | 32s |
| 6 | `step_06_select_ap` | AP screen | Select RS700 from listbox via Home+Down(N) | 30s |
| 7 | `step_07_use_last_ap` | AP screen | Fill firmware, click Use Last toggle, arrow | 22s |
| 8 | `step_08_select_client` | STN screen | Select INTEL_BE200 from listbox | 12s |
| 9 | `step_09_dut_ip` | DUT screen | Click orange arrow (pass-through) | 12s |
| 10 | `step_10_use_last_dut` | DUT screen | Click Use Last toggle, arrow | 19s |
| 11 | `step_11_band_select` | IP Dual LAN screen | Click "1", set 2G/5G dropdowns to "3" | 26s |
| 12 | `step_12_chariot_pairs` | Chariot pairs screen | Type number of pairs | 13s |
| 13 | `step_13_pass_through` | angle screen | Click orange arrow | 12s |
| 14 | `step_14_mode` | MODE screen | Select BW20 | 17s |
| 15 | `step_15_attenuation` | atten screen | Set start/step/steps | 16s |
| 16 | `step_16_design_stage` | Chariot screen | Select "Beta" | 22s |
| 17 | `step_17_region` | REGION screen | Select "US" | 19s |
| 18 | `step_18_final_start` | review screen | Click arrow to start test | 13s |

Total wizard time: ~4.5 minutes.

### Default Configuration (2.4G Test)

| Parameter | Value |
|-----------|-------|
| exe_path | `C:\480.builds\v2.03\480.000.v2.03.exe` |
| ap_name | RS700 |
| client_name | INTEL_BE200 |
| freq_range | MLO |
| band | 2.4G |
| RF channels | 2G=10, 5G=44, 6G=69 |
| mode | BW20 |
| number_of_pairs | 8 |
| start_atten / step_size / steps | 0 / 3 / 30 |
| design_stage | Beta |
| region | US |

### Key Techniques

- **Listbox selection:** `Home + Down(N)` via folder-index lookup (`E:\AP`, `E:\Client`)
- **Orange arrow detection:** HSV color matching with fallback to fixed coordinates
- **Popup management:** Auto-minimize `480_214.vi`, `500 Information window`, `2512 display status`
- **IME handling:** Force English input via `ActivateKeyboardLayout(0x04090409, 0)`
- **Dropdown modal fix:** Escape + neutral click before orange arrow to close lingering dropdowns

### Resolved Issues (v1)

| # | Issue | Solution |
|---|-------|----------|
| 1 | AP/Client listbox unreliable | Home+Down(N) with folder-index matching |
| 2 | Chinese IME garbled text | `_force_english_ime()` before every type |
| 3 | `480_214.vi` popup blocker | Auto-minimize in `_dismiss_lv_popups()` |
| 4 | Firmware rev field garbled | Direct typing instead of copy/paste |
| 5 | Use Last AP toggle wrong coords | Pixel analysis: (700, 229) |
| 6 | Client popup not opening | Pixel analysis: USB image at (100, 348) |
| 7 | Use Last DUT toggle wrong coords | Pixel analysis: (1060, 895) |
| 8 | Step 11 band select failures | Full pixel scan, Escape+neutral before arrow |
| 9 | OCR strict verification fail | Set `strict=False` (pytesseract unavailable) |
| 10 | PyAutoGUI failsafe trigger | Bounds checking in `_safe_click` |

---

## Router Service (Part 1 -- 22.100)

FastAPI service on the relay PC with wired access to the router. Runs Playwright
locally; the orchestrator only talks HTTP.

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness + router reachability |
| `/router/apply` | POST | Apply SSID/password/channel per band |
| `/router/status` | GET | Read current band config |
| `/router/detect-bands` | POST | Detect available bands |
| `/admin/update` | POST | Download zip, swap code, restart |
| `/admin/version` | GET | Build version info |

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

---

## WiFi Worker Service (Part 3 -- 22.203)

FastAPI service on the worker PC with an Intel BE200 WiFi adapter. Uses `netsh wlan`
exclusively (no coordinate-based automation).

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness check |
| `/wifi/connect` | POST | Connect to SSID (profile + connect + optional static IP) |
| `/wifi/status` | GET | Current SSID, IP, gateway |
| `/wifi/scan` | GET | Scan visible networks |
| `/net/ping` | POST | Ping a host |

### Timing

The worker connects to the test frequency band **after LabVIEW step 16** (design stage)
and before step 18 (final start). This ensures the WiFi card is associated to the
correct band when the throughput test begins.

---

## Directory Structure

```
orchestrator/               Workflow engine, actions, coordination
  local_automation/         LabVIEW GUI automation (PyAutoGUI)
    labview_runner.py       Thin facade → StepEngine + dual run.json / result.json
    labview_runner_legacy.py Legacy step_* implementations
    labview_legacy_report_mapping.py Engine → legacy report mapping
    engine/                   StepEngine, preflight, matrix_runner, context, report
    steps/                    Native BaseStep modules + registry (mixed legacy wrappers)
    products/                 Product adapters (e.g. BE200)
    profiles/                 YAML loader, schema, validator (in-package)
    ui/                       Reusable UI primitives, verification, OCR helpers
    recovery/                 Diagnosis / recovery helpers
    finish_detector.py      Test completion detection (PDF/UI/log)
    screen_utils.py         Window capture, template matching
    ui_flow.yaml            Flow config, coordinates, band overrides
    templates/              Reference screenshots for verification
  actions/                  E2E step implementations
  utils/                    Health checks, retry, timeouts
profiles/                   Repo-root test matrix + product YAML (see docs/HOW_TO_RUN.md)
router/                     Playwright-based router UI automation
  netgear_rs700/            RS700 driver, selectors, evidence
  netgear_nighthawk/        Legacy Nighthawk driver (reference)
router_service/             FastAPI service deployed on 22.100
worker/                     FastAPI worker service (WiFi, ping)
scripts/                    Entry points, deploy, E2E, LabVIEW helpers
  run_profile.py            Single profile through StepEngine
  run_matrix.py             Multiple profiles (matrix)
  validate_profiles.py      YAML schema + capability checks
  smoke_labview_compat.py   Imports, --help, fast dry-run smoke
  run_24g.py                Run 2.4G LabVIEW automation (legacy path)
  run_labview_all_bands.py  All bands sequentially
  calibrate_labview.py      Coordinate calibration (tracked)
  calibration/              Optional UI / step calibration scripts
  diagnostics/              Click, template, dropdown diagnostics
  dev/                      Live validation harness, small utilities
  _archive_local/           Archived one-off debug iterations (see README_LOCAL.md)
  run_e2e_lab.py            Full E2E workflow
  deploy_and_restart.py     Zero-touch deploy to 22.100
  bootstrap_22100.ps1       One-command bootstrap for 22.100
  bootstrap_22203_worker.ps1  Worker bootstrap for 22.203
workflows/                  YAML workflow definitions
  e2e_lab.yaml              Full E2E: router + workers + automation
  e2e_be200_2g.yaml         RS700 2.4G -> Intel BE200 -> ping
tests/                      Unit tests
docs/                       Runbooks and documentation
artifacts/                  Runtime output -- never committed
```

---

## Network Requirements

### Machine Roles

| Machine | IP (22-domain) | Role | Services |
|---------|-----------------|------|----------|
| Orchestrator | 192.168.22.8 | Workflow engine, LabVIEW host | Orchestrator, LabVIEW runner |
| Router Relay | 192.168.22.100 | Router GUI proxy | Router service :8081 |
| WiFi Worker | 192.168.22.203 | Intel BE200 WiFi control | Worker service :8080 |
| Router | 192.168.1.1 | Device under test | Netgear RS700 |

### Orchestrator (22.8)

- **NIC-1 (Internet / 200-domain):** Default gateway, metric 10
- **NIC-2 (22-domain control):** IP in 192.168.22.0/24, metric 20, **no route to 192.168.1.0/24**

### Router Relay (22.100)

- **22-domain NIC:** IP `192.168.22.100`, metric 10 (management)
- **Router NIC:** Static IP `192.168.1.50`, **no default gateway**, metric 100

### WiFi Worker (22.203)

- **22-domain NIC:** IP `192.168.22.203`, metric 10 (management)
- **WiFi adapter:** Intel BE200, connects to router SSID on test band

### Prechecks

```powershell
# Orchestrator: verify no route to router subnet
route print | Select-String "192.168.1"
# Expected: EMPTY

# Orchestrator: verify control path
Test-NetConnection 192.168.22.100 -Port 8081   # Router service
Test-NetConnection 192.168.22.203 -Port 8080   # Worker service

# Router Relay: verify router reachable
Test-NetConnection 192.168.1.1 -Port 80
```

---

## Configuration

```powershell
Copy-Item .env.example .env
# Edit .env:
#   ROUTER_USER=admin
#   ROUTER_PASS=<your router password>
#   SERVICE_BIND_IP=192.168.22.100
#   SERVICE_MODE=lab
```

LabVIEW automation parameters are configured in `orchestrator/local_automation/ui_flow.yaml`
and can be overridden via `RunConfig` in code.

---

## Deployment

### Router Service (22.100)

```powershell
# From orchestrator -- one-time bootstrap
python scripts/deploy_and_restart.py --zip-only
python -m http.server 9999 --bind 0.0.0.0

# On 22.100 (elevated PowerShell)
Set-ExecutionPolicy Bypass -Scope Process -Force
iwr http://192.168.22.8:9999/scripts/bootstrap_22100.ps1 -OutFile $env:TEMP\bootstrap.ps1
& $env:TEMP\bootstrap.ps1 -SourceBase http://192.168.22.8:9999 -ServiceBindIP 192.168.22.100

# Subsequent deploys (zero-touch)
python scripts/deploy_and_restart.py
```

### WiFi Worker (22.203)

```powershell
# On 22.203 (elevated PowerShell)
iwr http://192.168.22.8:9999/scripts/bootstrap_22203_worker.ps1 -OutFile $env:TEMP\bootstrap.ps1
& $env:TEMP\bootstrap.ps1 -SourceBase http://192.168.22.8:9999
```

### Orchestrator (22.8)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Security Model

- All secrets in `.env` (never committed, listed in `.gitignore`)
- `.env.example` provides placeholder keys
- Required: `ROUTER_USER`, `ROUTER_PASS`, `SERVICE_BIND_IP`, `SERVICE_MODE`
- Service bind IP enforced by uvicorn CLI and FastAPI startup validation
- Router credentials loaded via `python-dotenv`

---

## Prerequisites

| Machine | Requirements |
|---------|-------------|
| Orchestrator (22.8) | Python 3.10+, PyAutoGUI, OpenCV, pywin32, LabVIEW 480.000.v2.03.exe |
| Router Relay (22.100) | Python 3.10+, Playwright, Chromium, wired Ethernet to router |
| WiFi Worker (22.203) | Python 3.10+, Intel BE200 adapter, admin privileges for netsh |

---

## Known Issues

| # | Issue | Mitigation |
|---|-------|------------|
| 1 | Netgear SSO modal blocks Playwright | JS injection dismissal + `force=True` |
| 2 | Playwright browsers not found under SYSTEM | `PLAYWRIGHT_BROWSERS_PATH=C:\RASAgent\.playwright` |
| 3 | Scheduled task kills child processes | `CREATE_BREAKAWAY_FROM_JOB` flag |
| 4 | 6 GHz channel not visible in scan | SSID presence check only (warn on channel) |
| 5 | LabVIEW `480_214.vi` blocks wizard | Auto-minimize before every major action |
| 6 | Chinese IME garbles typed input | Force English layout before every keystroke |
| 7 | pytesseract not installed | OCR verification runs in `strict=False` mode |

---

## Running Tests

```powershell
# Unit tests
python -m pytest tests/ -v

# CI guard (no local Wi-Fi in orchestrator code)
python scripts/ci_guard_no_local_wifi.py

# E2E wireless test
python scripts/test_e2e_wireless.py --remote-host 192.168.22.100

# 2.4G LabVIEW automation
python scripts/run_24g.py

# All bands
python scripts/run_labview_all_bands.py

# LabVIEW refactor smoke (imports + dry-run module path)
python scripts/smoke_labview_compat.py

# Profile YAML validation
python scripts/validate_profiles.py --dir profiles/test_matrix/
```
