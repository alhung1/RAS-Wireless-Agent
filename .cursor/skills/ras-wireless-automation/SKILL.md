---
name: ras-wireless-automation
description: Automate Netgear RS700 Wi-Fi throughput testing across 3 machines -- router GUI config via Playwright (22.100), LabVIEW 480 wizard via PyAutoGUI (22.8), and Intel BE200 WiFi connect via netsh (22.203). Use when setting up, running, debugging, or calibrating RAS wireless test automation, or deploying to a new test environment.
---

# RAS Wireless Automation

## Quick Start

```powershell
cd "c:\Projects\RAS Wireless Agent"
.\.venv\Scripts\Activate.ps1
python scripts/run_24g.py
```

This runs all 18 LabVIEW wizard steps for a 2.4G throughput test (~4.5 min wizard, then test runs).

## 3-Part Architecture

| Part | Machine | Role | Technology |
|------|---------|------|------------|
| 1 | 22.100 | Router GUI config (Netgear RS700) | FastAPI + Playwright |
| 2 | 22.8 | LabVIEW 480 wizard automation | PyAutoGUI + Win32 API + OpenCV |
| 3 | 22.203 | Intel BE200 WiFi band connection | FastAPI + `netsh wlan` |

Communication: Orchestrator (22.8) calls 22.100 and 22.203 via HTTP. LabVIEW runs locally on 22.8.

### Execution Order

1. **Phase 1** -- Router config: `POST http://22.100:8081/router/apply`
2. **Phase 2** -- LabVIEW steps 0-16 on 22.8
3. **Phase 3** -- WiFi connect after step 16: `POST http://22.203:8080/wifi/connect`
4. **Phase 2 cont.** -- LabVIEW steps 17-18, test starts
5. **Phase 4** -- Monitor `D:\480\LOG\RBU\*.pdf` for completion

## LabVIEW 18-Step Flow

| Step | Action | Key Coordinates |
|------|--------|----------------|
| 0 | Attach to `480 000.vi` | -- |
| 1 | Click Throughput Testing | (130, 240) |
| 2 | Login (Alex / 123) | Green OK button |
| 3 | Test type: 1 rpm (fast) | Dropdown at (330, 368) |
| 4 | Table position (pass-through) | Orange arrow |
| 5 | Freq MLO, channels 10/44/69, user info | (511,344), (460,752), (655,752), (850,753) |
| 6 | Select AP: RS700 | Home+Down(155) in popup |
| 7 | Fill firmware + Use Last AP | (610,335) firmware, (700,229) toggle |
| 8 | Select Client: INTEL_BE200 | (100,348) USB image, Home+Down(30) |
| 9 | DUT IP (pass-through) | Orange arrow |
| 10 | Use Last DUT | (1060, 895) toggle |
| 11 | Band select: "1" + dropdowns "3" | (360,830), (600,552)/(600,646), (920,552)/(920,646) |
| 12 | Chariot pairs: 8 | (580, 406) |
| 13 | Pass-through | Orange arrow |
| 14 | Mode: BW20 | Dropdown at (249, 757) |
| 15 | Attenuation: 0/3/30 | (153,496), (566,496), (750,496) |
| 16 | Design stage: Beta | Dropdown at (734, 491) |
| 17 | Region: US | Dropdown at (295, 488) |
| 18 | Final start | Orange arrow |

Window is fixed at **1288x1040** (positioned at 0,0). All coordinates are relative to window top-left.

## Coordinate Calibration

When deploying to a new machine with different DPI or resolution:

1. Run LabVIEW and position window at (0,0) sized to 1288x1040
2. Take a screenshot: `capture_window(hwnd)` from `screen_utils.py`
3. Use pixel scanning to find UI elements:

```python
from PIL import Image
import numpy as np
img = Image.open("screenshot.png")
arr = np.array(img)
# Scan for yellow regions (dropdowns), gray buttons, etc.
for y in range(0, arr.shape[0], 5):
    for x in range(0, arr.shape[1]):
        r, g, b = arr[y, x, :3]
        if r > 200 and g > 200 and b < 50:  # Yellow
            print(f"Yellow at ({x}, {y})")
```

4. Update coordinates in the step functions in `labview_runner.py`

## Known Issues and Solutions

| Issue | Solution |
|-------|----------|
| AP/Client listbox selection unreliable | `Home+Down(N)` via folder-index from `E:\AP` or `E:\Client` |
| Chinese IME garbles typed input | `_force_english_ime()` using `ActivateKeyboardLayout(0x04090409, 0)` |
| `480_214.vi` blocks wizard steps | Auto-minimize in `_dismiss_lv_popups()` before every action |
| Firmware rev field empty/garbled | Direct typing `V1.0.10.8` instead of copy/paste |
| Dropdown modal blocks orange arrow | Press Escape + click neutral area (400,300) before arrow |
| OCR unavailable (no pytesseract) | All verification uses `strict=False` |
| PyAutoGUI failsafe trigger | Bounds check in `_safe_click`, window at (0,0) |

## Integrating Part 3 (WiFi Connect After Step 16)

After step 16 (design_stage), the WiFi worker on 22.203 must connect to the test band.
Use the `post_step_hooks` mechanism:

```powershell
# CLI: pass --wifi-worker to run_24g.py
python scripts/run_24g.py --wifi-worker http://192.168.22.203:8080 RS700_2G TestPass

# Or in code:
from orchestrator.local_automation.labview_runner import (
    make_wifi_connect_hook, STEP_IDX_DESIGN_STAGE, run_labview_flow,
)
hook = make_wifi_connect_hook("http://192.168.22.203:8080", "RS700_2G", "TestPass")
run_labview_flow(cfg, post_step_hooks={STEP_IDX_DESIGN_STAGE: hook})
```

The hook calls `POST /wifi/connect` on the worker, which runs `netsh wlan connect`.
If the hook fails, it logs an error but does NOT abort the wizard.

## Adding a New Test Case

Modify `RunConfig` fields in `scripts/run_24g.py` or `ui_flow.yaml`:

```python
cfg = RunConfig(
    ap_name="RS700",           # Must match folder name in E:\AP
    client_name="INTEL_BE200", # Must match folder name in E:\Client
    band="2.4G",               # 2.4G, 5G, or 6G
    freq_range="MLO",
    rf_channel_2g="10",
    rf_channel_5g="44",
    rf_channel_6g="69",
    mode="BW20",               # BW20, BW40, BW80, BW160
    number_of_pairs="8",
    start_atten="0",
    step_size="3",
    steps="30",
    design_stage="Beta",
    region="US",
    ip_dropdown_2g="3",        # 2G/MLO laptop selector (1-5)
    ip_dropdown_5g6g="3",      # 5G/6G laptop selector (1-5)
)
```

For a different AP, update `ap_name` and verify the listbox index matches `E:\AP` folder contents.

## Deploying to a New Environment

### Checklist

- [ ] Python 3.10+ installed on all 3 machines
- [ ] LabVIEW `480.000.v2.03.exe` installed on 22.8 at `C:\480.builds\v2.03\`
- [ ] AP config files in `E:\AP\`, client configs in `E:\Client\` on 22.8
- [ ] `.env` configured with router credentials on 22.100
- [ ] Network: 22.8 can reach 22.100:8081 and 22.203:8080
- [ ] Network: 22.100 can reach router at 192.168.1.1
- [ ] Router service bootstrapped on 22.100 (`scripts/bootstrap_22100.ps1`)
- [ ] Worker service bootstrapped on 22.203 (`scripts/bootstrap_22203_worker.ps1`)
- [ ] DPI is 100% (96 DPI) on 22.8, or recalibrate coordinates
- [ ] Window size 1288x1040 confirmed for LabVIEW

### Install on Orchestrator (22.8)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Key Dependencies

- `pyautogui` -- mouse/keyboard control
- `opencv-python` -- HSV arrow detection, template matching
- `Pillow`, `numpy` -- screenshot analysis
- `pywin32` -- Win32 window management
- `pyyaml` -- config loading
- `python-dotenv` -- secret management

## Critical Engineering Rules

1. Every network call and Playwright action MUST have retry + timeout
2. Every state change MUST be verified (SSID matches, screen transitioned)
3. All actions produce structured JSON-line logs
4. On Playwright failure: collect screenshot, HTML, trace.zip, HAR
5. WiFi operations use `netsh wlan` only (no coordinate clicking)
6. Router UI uses Playwright label/text selectors (no pixel coordinates)
7. Credentials from `.env` only (never hardcoded)

## Key Files

| File | Purpose |
|------|---------|
| `orchestrator/local_automation/labview_runner.py` | 18-step wizard driver |
| `orchestrator/local_automation/finish_detector.py` | Test completion detection |
| `orchestrator/local_automation/ui_flow.yaml` | Coordinates and config |
| `orchestrator/local_automation/screen_utils.py` | Window capture, template matching |
| `router/netgear_rs700/driver.py` | Playwright router automation |
| `router_service/app.py` | Router control FastAPI service |
| `worker/app.py` | WiFi worker FastAPI service |
| `scripts/run_24g.py` | 2.4G test entry point |

For detailed coordinate maps and full config reference, see [reference.md](reference.md).
