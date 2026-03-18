# RAS Wireless Automation -- Reference

## Complete Coordinate Map

All coordinates are window-relative (top-left = 0,0) for a 1288x1040 window at screen position (0,0).

### Step 1: Click Throughput

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Throughput Testing icon | (130, 240) | Main screen `480 000.vi` |

### Step 2: Login

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Username field | Triple-click to select | Login popup sized 356x200 |
| Password field | Tab from username | |
| Green OK button | Detected by template or (290, 170) fallback | |

### Step 3: Test Type

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Test type dropdown | (330, 368) | Navigate with Up/Down keys |

### Step 5: Frequency and Channel

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Freq Range dropdown | (511, 344) | Select MLO via Up/Down nav |
| RF Channel 2.4G | (460, 752) | Clear and type "10" |
| RF Channel 5G | (655, 752) | Clear and type "44" |
| RF Channel 6G | (850, 753) | Clear and type "69" |
| User Information | (690, 845) | Type "2G test" |

### Step 6: Select AP

| Element | Coordinates | Notes |
|---------|-------------|-------|
| AP selection icon | (100, 350) | Opens popup list |
| Listbox click area | (120, 300) relative to popup | Before Home+Down nav |
| Done button | (480, 870) fallback | In popup window |

### Step 7: Use Last AP

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Firmware rev field | (610, 335) | Triple-click, type "V1.0.10.8" |
| Use Last toggle (AP) | (700, 229) | Vertical slide boolean, bottom knob |

### Step 8: Select Client

| Element | Coordinates | Notes |
|---------|-------------|-------|
| USB image (primary) | (100, 348) | Opens client popup |
| Text button (fallback) | (225, 350) | If USB click fails |
| Done button | (480, 870) fallback | In popup window |

### Step 10: Use Last DUT

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Use Last toggle (DUT) | (1060, 895) | Different layout from AP screen |

### Step 11: Band Select (IP Dual LAN)

| Element | Coordinates | Notes |
|---------|-------------|-------|
| "1" button | (360, 830) | Near DUT/AP label at bottom-left |
| 2G/MLO dropdown (open) | (600, 552) | Click yellow text area |
| 2G/MLO item "3" | (600, 646) | In opened dropdown popup |
| 5G/6G dropdown (open) | (920, 552) | Click yellow text area |
| 5G/6G item "3" | (920, 646) | In opened dropdown popup |
| Neutral click (close modal) | (400, 300) | After Escape, before arrow |

Dropdown items in the 2G/MLO list (y-coordinates from pixel analysis):

| Item | y-coordinate | Selectable |
|------|-------------|------------|
| Not Valid | ~556 | Yes (default) |
| 1 | ~612 | Yes |
| 2 | ~626 | Yes |
| 3 | ~646 | Yes |
| 4 | ~659 | No (grayed) |
| 5 | ~680 | No (grayed) |
| 4 & 5 | ~740 | No (grayed) |
| 2 & 6 | ~790 | Yes |
| Not in use | ~820 | Yes |

### Step 12: Chariot Pairs

| Element | Coordinates | Notes |
|---------|-------------|-------|
| 2G/MLO pairs field | (580, 406) | Type "8" |
| 5G/6G pairs field | (580, 706) | Type "0" (if applicable) |

### Step 14: Mode

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Mode dropdown | (249, 757) | Navigate using BW_MODE_NAV map |

BW_MODE_NAV key mappings (from current position at top):

| Mode | Up presses | Down presses |
|------|-----------|-------------|
| BW20 | 6 | 0 |
| BW40 | 6 | 1 |
| BW80 | 6 | 2 |
| BW160 | 6 | 3 |
| BW320 | 6 | 4 |

### Step 15: Attenuation

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Start atten | (153, 496) | Type "0" |
| Step size | (566, 496) | Type "3" |
| Steps | (750, 496) | Type "30" |

### Step 16: Design Stage

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Design stage dropdown | (734, 491) | Navigate to "Beta" |

### Step 17: Region

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Region dropdown | (295, 488) | Navigate to "US" |

### Orange Arrow (All Steps)

| Element | Coordinates | Notes |
|---------|-------------|-------|
| Right orange arrow | Detected via HSV | Dynamic position per screen |
| Fallback position | (1183, 976) | `ORANGE_ARROW_PX` constant |
| Alternative fallback | (window_w - 85, window_h - 85) | Relative to window size |

---

## RunConfig Field Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `rf_channel_2g` | str | `"10"` | 2.4 GHz RF channel |
| `rf_channel_5g` | str | `"44"` | 5 GHz RF channel |
| `rf_channel_6g` | str | `"69"` | 6 GHz RF channel |
| `user_information` | str | `"2G test"` | Test label in wizard |
| `band` | str | `"2.4G"` | Active band: 2.4G, 5G, 6G |
| `username` | str | `"Alex"` | LabVIEW login username |
| `password` | str | `"123"` | LabVIEW login password |
| `test_type` | str | `"1 rpm (fast)"` | Test type selection |
| `freq_range` | str | `"MLO"` | Frequency range mode |
| `ap_name` | str | `"RS700"` | AP folder name in `E:\AP` |
| `client_name` | str | `"INTEL_BE200"` | Client folder name in `E:\Client` |
| `mode` | str | `"BW20"` | Bandwidth mode |
| `graph_range` | str | `"100"` | Graph display range |
| `start_atten` | str | `"0"` | Starting attenuation (dB) |
| `step_size` | str | `"3"` | Attenuation step (dB) |
| `steps` | str | `"30"` | Number of attenuation steps |
| `number_of_pairs` | str | `"8"` | Chariot pairs for 2G/MLO |
| `number_of_pairs_5g6g` | str | `"0"` | Chariot pairs for 5G/6G |
| `design_stage` | str | `"Beta"` | Design cycle stage |
| `region` | str | `"US"` | Test region |
| `exe_path` | str | `C:\480.builds\v2.03\480.000.v2.03.exe` | LabVIEW executable |
| `timeout_seconds` | int | `14400` | Max wait for test completion (4hr) |
| `ip_dropdown_2g` | str | `"3"` | 2G/MLO laptop selector (1-5) |
| `ip_dropdown_5g6g` | str | `"3"` | 5G/6G laptop selector (1-5) |
| `ap_ip` | str | `"192.168.1.1"` | AP IP address |

---

## Helper Function Catalog

### Click and Input

| Function | Purpose |
|----------|---------|
| `_safe_click(hwnd, px, py)` | Click at window-relative coords with bounds check |
| `_click_at(hwnd, px, py)` | Alias for `_safe_click` |
| `_safe_type(text)` | Type text with English IME enforcement |
| `_safe_press(key)` | Press single key |
| `_type_in_field(hwnd, px, py, text)` | Triple-click field, then type |
| `_clear_and_type(hwnd, px, py, text)` | End + Backspace to clear, then type |
| `_force_english_ime()` | `ActivateKeyboardLayout(0x04090409, 0)` |

### Navigation and Detection

| Function | Purpose |
|----------|---------|
| `_click_orange_arrow_smart(hwnd)` | HSV detect arrow position, dismiss popups, click |
| `_detect_orange_arrow_right(hwnd)` | HSV color scan for orange arrow |
| `_select_dropdown_by_nav(hwnd, pos, up, down)` | Open dropdown, navigate with arrow keys |
| `_select_list_item_by_folder_index(popup, folder, name, ...)` | Home+Down(N) listbox selection |
| `_click_done_button_smart(popup)` | Click Done in popup with fallback |
| `_click_green_ok_smart(login)` | Click green OK on login |
| `_fill_firmware_rev(hwnd, ad)` | Triple-click firmware field, type value |

### Window Management

| Function | Purpose |
|----------|---------|
| `_dismiss_lv_popups()` | Minimize `480_214.vi` and other blockers |
| `_ensure_foreground(hwnd)` | Bring window to foreground (3 retries) |
| `_setup_vi(hwnd)` | Resize/position to STEP_WINDOW_SIZE |
| `_poll_for_window_appear(hint, timeout)` | Poll for window by title substring |
| `_verify_transition(old_hwnd, timeout)` | Wait for screen to change |
| `_screenshot(hwnd, ad, step, name)` | Capture and save window screenshot |

### Orchestration

| Function | Purpose |
|----------|---------|
| `run_labview_flow(cfg, ..., post_step_hooks)` | Run all 18 steps with retry/recovery and optional hooks |
| `run_all_bands(bands, ..., post_step_hooks)` | Run flow once per band, forwarding hooks |
| `make_wifi_connect_hook(url, ssid, pw)` | Create a post-step hook for WiFi worker connect |
| `STEP_IDX_DESIGN_STAGE` | Constant = 16, the step index for WiFi hook injection |
| `_diagnose_failure(hwnd, step, ad)` | Capture diagnosis artifacts |
| `_recover_from_failure(hwnd, diag)` | Close popups, restore state |

### Post-Step Hooks

`post_step_hooks` is a `dict[int, Callable]` passed to `run_labview_flow`. After each
successful step, if the step index is in the dict, the hook is called with `(cfg, artifacts_dir)`.

Primary use case: connect WiFi worker after step 16 (design_stage) so the Intel BE200
is associated to the test band before step 18 starts the throughput test.

```python
hook = make_wifi_connect_hook("http://192.168.22.203:8080", "RS700_2G", "pass")
run_labview_flow(cfg, post_step_hooks={STEP_IDX_DESIGN_STAGE: hook})
```

---

## Finish Detector Configuration

The finish detector (`finish_detector.py`) monitors for test completion after
all wizard steps succeed.

### Detection Methods (in priority order)

1. **Result file**: New PDF/CSV in `result_file_dir`
2. **Log keyword**: Scan log file for completion keyword
3. **UI text**: Screenshot + OCR/template for keywords

### FinishConfig Fields

| Field | Default | Description |
|-------|---------|-------------|
| `result_file_dir` | `D:\480\LOG\RBU` | Directory to watch for new files |
| `result_file_glob` | `*.pdf` | File pattern to match |
| `result_file_min_size` | 1024 | Minimum file size (bytes) |
| `timeout_sec` | 14400 | Max wait (4 hours) |
| `poll_interval_sec` | 30 | Check interval |
| `log_file_path` | None | Optional log file to monitor |
| `log_keyword` | None | Completion keyword in log |
| `ui_keywords` | `["Completed", "Finished", "PASS", "FAIL", "Done"]` | UI text indicators |

---

## API Endpoint Reference

### Router Service (22.100:8081)

| Endpoint | Method | Body | Response |
|----------|--------|------|----------|
| `/health` | GET | -- | `{"status":"ok","router_reachable":true}` |
| `/router/status` | GET | -- | `{"success":true,"bands":{...}}` |
| `/router/apply` | POST | `{"bands":{"2.4G":{...}}}` | `{"success":true}` |
| `/router/detect-bands` | POST | -- | `{"bands":["2.4G","5G","6G"]}` |
| `/admin/version` | GET | -- | `{"version":"1.1.0",...}` |
| `/admin/update` | POST | `{"zip_url":"..."}` | `{"success":true}` |

### Worker Service (22.203:8080)

| Endpoint | Method | Body | Response |
|----------|--------|------|----------|
| `/health` | GET | -- | `{"status":"ok"}` |
| `/wifi/connect` | POST | `{"ssid":"...","password":"..."}` | `{"connected":true,"ssid":"..."}` |
| `/wifi/status` | GET | -- | `{"ssid":"...","ip":"..."}` |
| `/wifi/scan` | GET | -- | `{"networks":[...]}` |
| `/net/ping` | POST | `{"host":"192.168.1.1"}` | `{"reachable":true,"rtt_ms":5}` |

---

## Folder-Index Listbox Navigation

The `_select_list_item_by_folder_index` function determines the correct listbox
index by reading the filesystem:

1. List all `.txt` files in the target folder (`E:\AP` or `E:\Client`)
2. Extract file stems (filenames without `.txt`)
3. Filter out items in `_LISTBOX_EXCLUDE` (currently empty set)
4. Sort alphabetically (matches LabVIEW listbox order)
5. Find the index of the target name
6. Click the listbox, press Home, then Down N times

If the folder contents change (new AP/client added), the index recalculates automatically.

### Current Known Indices

| Target | Folder | Item Count | Index |
|--------|--------|------------|-------|
| RS700 | `E:\AP` | 196 | 155 |
| INTEL_BE200 | `E:\Client` | 94 | 30 |
