# LabVIEW Template Images

This directory stores reference screenshots (PNG) used for visual
verification during automated LabVIEW wizard steps.

## How to Capture Templates

Run the capture utility with LabVIEW open and idle on the main screen:

```
python scripts/capture_templates.py
```

The script walks through each wizard screen and crops the necessary
reference regions.  You can also capture individual templates manually
by specifying the step:

```
python scripts/capture_templates.py --step 3
```

## Required Templates

| Filename | Purpose | Source Step |
|---|---|---|
| `orange_arrow.png` | Next-page arrow (right) | Any wizard page |
| `orange_arrow_left.png` | Previous-page arrow (left) | Any wizard page |
| `throughput_tab.png` | "Throughput Testing" tab on main screen | Step 01 |
| `green_ok_button.png` | OK/green button on login dialog | Step 02 |
| `done_button.png` | "Done" button in popup lists | Steps 06, 08 |
| `test_type_screen.png` | Test-type selection header area | Step 03 |
| `freq_channel_screen.png` | Frequency/channel VI header | Step 05 |
| `ip_address_screen.png` | IP Address / Dual LAN header | Step 11 |
| `mode_screen.png` | MODE selection header | Step 14 |
| `atten_screen.png` | Attenuation configuration header | Step 15 |
| `design_stage_screen.png` | Design stage / Chariot header | Step 16 |
| `region_screen.png` | Region selection header | Step 17 |
| `test_running.png` | Indicator that test is in progress | Step 18 / Finish |

## Notes

- Templates are captured at **2560x1440 display, 125% DPI** with
  the LabVIEW window pinned to (0, 0) and sized to 1288x1040.
- If display settings change, re-capture all templates.
- Template matching uses OpenCV `TM_CCOEFF_NORMED` with a default
  threshold of 0.75.
